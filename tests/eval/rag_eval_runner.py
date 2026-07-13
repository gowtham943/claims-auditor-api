from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config.config_setting import settings
from models.rag_schema import ChatQueryResponse
from services.rag_chat_service import build_chat_response, build_rag_prompt

EVAL_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = EVAL_DIR.parent / "resources"
DATASET_PATH = EVAL_DIR / "rag_eval_dataset.json"
MARKDOWN_FIXTURE = RESOURCES_DIR / "package_rate_ledger_report.md"
DEFAULT_RETRIEVAL_LIMIT = 4

logger = logging.getLogger(__name__)


def _rag_engine():
    from rag_engine.policy_rag_engine import PolicyRAGEngine

    return PolicyRAGEngine()


class MetricVerdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0, description="Score between 0 and 1.")
    reasoning: str = Field(description="Short explanation for the score.")


class RagEvalMetrics(BaseModel):
    context_relevance: MetricVerdict
    faithfulness: MetricVerdict
    answer_relevance: MetricVerdict


async def _call_with_retry(label: str, call_fn: Callable[[], Any]) -> Any:
    """Mirror policy_rag_engine retry/backoff for generate_content calls."""
    retries = 5
    delay = 60.0

    while retries > 0:
        try:
            result = await asyncio.to_thread(call_fn)
            # Proactive throttle — same idea as policy_rag_engine chunk pacing.
            await asyncio.sleep(4.5)
            return result
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                retries -= 1
                logger.warning(
                    "%s rate limited. Retries left: %s. Backing off %.1fs...",
                    label,
                    retries,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 1.5
                continue
            raise exc

    raise RuntimeError(f"{label} failed after maximum retry attempts.")


async def generate_grounded_answer_rate_limited(prompt: str, citations: list[str]) -> str:
    if not citations:
        raise ValueError("At least one citation chunk is required for grounded generation.")

    system_instruction, prompt_payload = build_rag_prompt(prompt, citations)
    client = genai.Client()

    def _generate() -> str:
        response = client.models.generate_content(
            model=settings.GEMINI_RAG_MODEL,
            contents=prompt_payload,
            config={"system_instruction": system_instruction, "temperature": 0.0},
        )
        return response.text

    return await _call_with_retry("RAG answer generation", _generate)


@dataclass
class RagEvalCase:
    id: str
    question: str
    ground_truth: str
    expected_answer_contains: list[str]
    expected_context_keywords: list[str]
    expects_refusal: bool
    min_scores: dict[str, float]


@dataclass
class RagEvalCaseResult:
    case_id: str
    question: str
    answer: str
    citations: list[str]
    ground_truth: str
    context_relevance: MetricVerdict
    faithfulness: MetricVerdict
    answer_relevance: MetricVerdict
    keyword_checks_passed: bool
    passed: bool
    failure_reasons: list[str]


def load_eval_dataset(path: Path = DATASET_PATH) -> list[RagEvalCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases: list[RagEvalCase] = []

    for item in raw_cases:
        cases.append(
            RagEvalCase(
                id=item["id"],
                question=item["question"],
                ground_truth=item["ground_truth"],
                expected_answer_contains=item.get("expected_answer_contains", []),
                expected_context_keywords=item.get("expected_context_keywords", []),
                expects_refusal=bool(item.get("expects_refusal", False)),
                min_scores=item.get(
                    "min_scores",
                    {
                        "context_relevance": 0.6,
                        "faithfulness": 0.7,
                        "answer_relevance": 0.7,
                    },
                ),
            )
        )

    return cases


def l2_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


class InMemoryRagIndex:
    """Indexes fixture markdown for eval without PostgreSQL."""

    def __init__(self, markdown_text: str):
        self.markdown_text = markdown_text
        self.chunk_records: list[tuple[str, list[float]]] = []
        self._query_embedding_cache: dict[str, list[float]] = {}

    async def build(self) -> None:
        engine = _rag_engine()
        segments = engine.segment_markdown_by_headers(self.markdown_text)
        if not segments:
            raise ValueError("Fixture markdown produced no RAG segments.")

        self.chunk_records = []
        for segment in segments:
            text = segment["text"]
            embedding = await engine.generate_text_embedding(text)
            
            self.chunk_records.append((text, embedding))

    async def prefetch_query_embeddings(self, questions: list[str]) -> None:
        engine = _rag_engine()
        for question in questions:
            if question in self._query_embedding_cache:
                continue
            self._query_embedding_cache[question] = await engine.generate_text_embedding(question)

    async def retrieve(self, question: str, limit: int = DEFAULT_RETRIEVAL_LIMIT) -> list[str]:
        if not self.chunk_records:
            raise RuntimeError("Call build() before retrieve().")

        if question not in self._query_embedding_cache:
            engine = _rag_engine()
            self._query_embedding_cache[question] = await engine.generate_text_embedding(question)

        query_embedding = self._query_embedding_cache[question]
        ranked = sorted(
            self.chunk_records,
            key=lambda record: l2_distance(record[1], query_embedding),
        )
        return [chunk for chunk, _ in ranked[:limit]]

    async def answer(self, question: str, limit: int = DEFAULT_RETRIEVAL_LIMIT) -> ChatQueryResponse:
        citations = await self.retrieve(question, limit=limit)
        answer = await generate_grounded_answer_rate_limited(question, citations)
        return build_chat_response(question, citations, answer)


class RagEvalJudge:
    """LLM-as-judge for RAG quality metrics."""

    def __init__(self, model_name: str | None = None):
        self._client = None
        self.model_name = model_name or settings.GEMINI_RAG_MODEL

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client()
        return self._client

    async def _score(self, rubric: str, payload: str) -> MetricVerdict:
        def _generate() -> MetricVerdict:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=payload,
                config=types.GenerateContentConfig(
                    system_instruction=rubric,
                    response_mime_type="application/json",
                    response_schema=MetricVerdict,
                    temperature=0.0,
                ),
            )
            return MetricVerdict.model_validate_json(response.text)

        return await _call_with_retry("RAG eval judge", _generate)

    async def score_all_metrics(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> RagEvalMetrics:
        context_block = "\n\n---\n\n".join(contexts) if contexts else "(no context retrieved)"
        rubric = (
            "You are evaluating RAG answer quality. Return JSON with three objects: "
            "context_relevance, faithfulness, and answer_relevance. Each object must have "
            "score (0 to 1) and reasoning. "
            "context_relevance: how relevant retrieved context is to the question. "
            "faithfulness: whether the answer is fully supported by the context. "
            "answer_relevance: how directly the answer addresses the question."
        )
        payload = (
            f"QUESTION:\n{question}\n\n"
            f"RETRIEVED CONTEXT:\n{context_block}\n\n"
            f"ANSWER:\n{answer}\n\n"
            "Score all three metrics."
        )

        def _generate() -> RagEvalMetrics:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=payload,
                config=types.GenerateContentConfig(
                    system_instruction=rubric,
                    response_mime_type="application/json",
                    response_schema=RagEvalMetrics,
                    temperature=0.0,
                ),
            )
            return RagEvalMetrics.model_validate_json(response.text)

        return await _call_with_retry("RAG eval judge batch", _generate)

    async def score_context_relevance(self, question: str, contexts: list[str]) -> MetricVerdict:
        context_block = "\n\n---\n\n".join(contexts) if contexts else "(no context retrieved)"
        rubric = (
            "You are evaluating RAG retrieval quality. Score how relevant the retrieved context is "
            "to answering the user question. Return JSON with fields: score (0 to 1) and reasoning. "
            "1.0 means the context clearly contains what is needed. 0.0 means completely irrelevant."
        )
        payload = (
            f"QUESTION:\n{question}\n\n"
            f"RETRIEVED CONTEXT:\n{context_block}\n\n"
            "Score context relevance."
        )
        return await self._score(rubric, payload)

    async def score_faithfulness(self, question: str, answer: str, contexts: list[str]) -> MetricVerdict:
        context_block = "\n\n---\n\n".join(contexts) if contexts else "(no context retrieved)"
        rubric = (
            "You are evaluating RAG answer faithfulness. Score whether every factual claim in the answer "
            "is supported by the retrieved context. Return JSON with fields: score (0 to 1) and reasoning. "
            "1.0 means fully grounded. 0.0 means hallucinated or unsupported claims."
        )
        payload = (
            f"QUESTION:\n{question}\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            f"ANSWER:\n{answer}\n\n"
            "Score faithfulness."
        )
        return await self._score(rubric, payload)

    async def score_answer_relevance(self, question: str, answer: str) -> MetricVerdict:
        rubric = (
            "You are evaluating answer relevance. Score how directly the answer addresses the question. "
            "Return JSON with fields: score (0 to 1) and reasoning. "
            "1.0 means fully on-topic and useful. 0.0 means off-topic."
        )
        payload = f"QUESTION:\n{question}\n\nANSWER:\n{answer}\n\nScore answer relevance."
        return await self._score(rubric, payload)


def keyword_checks_passed(case: RagEvalCase, answer: str, citations: list[str]) -> bool:
    answer_lower = answer.lower()
    context_blob = "\n".join(citations).lower()

    if case.expected_answer_contains:
        if not any(token.lower() in answer_lower for token in case.expected_answer_contains):
            return False

    if case.expected_context_keywords:
        if not any(token.lower() in context_blob for token in case.expected_context_keywords):
            return False

    if case.expects_refusal:
        refusal_markers = ["cannot verify", "not contain", "not present", "not available", "not in"]
        if not any(marker in answer_lower for marker in refusal_markers):
            return False

    return True


class RagEvalRunner:
    def __init__(
        self,
        index: InMemoryRagIndex,
        judge: RagEvalJudge | None = None,
        retrieval_limit: int = DEFAULT_RETRIEVAL_LIMIT,
    ):
        self.index = index
        self.judge = judge or RagEvalJudge()
        self.retrieval_limit = retrieval_limit

    async def evaluate_case(self, case: RagEvalCase) -> RagEvalCaseResult:
        response = await self.index.answer(case.question, limit=self.retrieval_limit)

        metrics = await self.judge.score_all_metrics(
            case.question,
            response.answer,
            response.retrieved_citations,
        )
        context_relevance = metrics.context_relevance
        faithfulness = metrics.faithfulness
        answer_relevance = metrics.answer_relevance

        keyword_ok = keyword_checks_passed(case, response.answer, response.retrieved_citations)
        failure_reasons: list[str] = []

        if context_relevance.score < case.min_scores.get("context_relevance", 0.6):
            failure_reasons.append(
                f"context_relevance {context_relevance.score:.2f} below "
                f"{case.min_scores.get('context_relevance', 0.6):.2f}"
            )
        if faithfulness.score < case.min_scores.get("faithfulness", 0.7):
            failure_reasons.append(
                f"faithfulness {faithfulness.score:.2f} below "
                f"{case.min_scores.get('faithfulness', 0.7):.2f}"
            )
        if answer_relevance.score < case.min_scores.get("answer_relevance", 0.7):
            failure_reasons.append(
                f"answer_relevance {answer_relevance.score:.2f} below "
                f"{case.min_scores.get('answer_relevance', 0.7):.2f}"
            )
        if not keyword_ok:
            failure_reasons.append("keyword/refusal checks failed")

        passed = not failure_reasons

        return RagEvalCaseResult(
            case_id=case.id,
            question=case.question,
            answer=response.answer,
            citations=response.retrieved_citations,
            ground_truth=case.ground_truth,
            context_relevance=context_relevance,
            faithfulness=faithfulness,
            answer_relevance=answer_relevance,
            keyword_checks_passed=keyword_ok,
            passed=passed,
            failure_reasons=failure_reasons,
        )

    async def evaluate_all(self, cases: list[RagEvalCase]) -> list[RagEvalCaseResult]:
        await self.index.prefetch_query_embeddings([case.question for case in cases])

        results: list[RagEvalCaseResult] = []
        total = len(cases)
        for index, case in enumerate(cases, start=1):
            logger.info("Evaluating case %s/%s: %s", index, total, case.id)
            results.append(await self.evaluate_case(case))
            if index < total:
                await asyncio.sleep(1.0)
        return results


def summarize_results(results: list[RagEvalCaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)

    def avg(metric: str) -> float:
        values = [getattr(result, metric).score for result in results]
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "avg_context_relevance": avg("context_relevance"),
        "avg_faithfulness": avg("faithfulness"),
        "avg_answer_relevance": avg("answer_relevance"),
    }
