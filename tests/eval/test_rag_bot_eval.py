from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio

from tests.eval.rag_eval_runner import (
    MARKDOWN_FIXTURE,
    RagEvalJudge,
    RagEvalRunner,
    InMemoryRagIndex,
    load_eval_dataset,
    summarize_results,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.rag_eval,
]

RUN_RAG_EVAL = os.environ.get("RUN_RAG_EVAL", "").lower() in {"1", "true", "yes"}
HAS_GEMINI_KEY = bool(os.environ.get("GEMINI_API_KEY"))


@pytest.fixture(scope="session")
def ledger_markdown() -> str:
    if not MARKDOWN_FIXTURE.exists():
        pytest.fail(
            f"Missing fixture markdown at {MARKDOWN_FIXTURE}. "
            "Generate it from tests/resources/package_rate_ledger_report.pdf."
        )
    return MARKDOWN_FIXTURE.read_text(encoding="utf-8")


@pytest_asyncio.fixture(scope="session")
async def rag_eval_index(ledger_markdown: str) -> InMemoryRagIndex:
    index = InMemoryRagIndex(ledger_markdown)
    await index.build()
    return index


@pytest.fixture
def eval_runner(rag_eval_index: InMemoryRagIndex) -> RagEvalRunner:
    return RagEvalRunner(index=rag_eval_index, judge=RagEvalJudge())


@pytest.fixture
def eval_cases():
    return load_eval_dataset()


@pytest.mark.skipif(
    not RUN_RAG_EVAL or not HAS_GEMINI_KEY,
    reason="Set RUN_RAG_EVAL=1 and GEMINI_API_KEY to run live RAG eval tests.",
)
async def test_rag_bot_eval_suite(eval_runner: RagEvalRunner, eval_cases):
    results = await eval_runner.evaluate_all(eval_cases)
    summary = summarize_results(results)

    report_path = Path(__file__).resolve().parent / "rag_eval_report.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "cases": [
                    {
                        "case_id": result.case_id,
                        "question": result.question,
                        "passed": result.passed,
                        "failure_reasons": result.failure_reasons,
                        "scores": {
                            "context_relevance": result.context_relevance.score,
                            "faithfulness": result.faithfulness.score,
                            "answer_relevance": result.answer_relevance.score,
                        },
                        "answer_preview": result.answer[:300],
                    }
                    for result in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    failures = [result for result in results if not result.passed]
    assert not failures, (
        f"RAG eval failed for {len(failures)} case(s). "
        f"Summary={summary}. Report={report_path}"
    )


@pytest.mark.skipif(
    not RUN_RAG_EVAL or not HAS_GEMINI_KEY,
    reason="Set RUN_RAG_EVAL=1 and GEMINI_API_KEY to run live RAG eval tests.",
)
@pytest.mark.parametrize(
    "case_id",
    [
        "total_procedures",
        "max_reference_rate",
        "cmu0001_rate",
        "out_of_scope_copay",
    ],
)
async def test_rag_bot_eval_smoke_cases(eval_runner: RagEvalRunner, eval_cases, case_id: str):
    case = next(item for item in eval_cases if item.id == case_id)
    result = await eval_runner.evaluate_case(case)
    assert result.passed, (
        f"Smoke case '{case_id}' failed: {result.failure_reasons}. "
        f"scores={{context: {result.context_relevance.score}, "
        f"faithfulness: {result.faithfulness.score}, "
        f"answer: {result.answer_relevance.score}}}"
    )
