#!/usr/bin/env python3
"""
Run RAG bot evaluation and print a summary report.

Example:
  RUN_RAG_EVAL=1 GEMINI_API_KEY=your-key python -m tests.eval.run_rag_eval
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from tests.eval.rag_eval_runner import (
    MARKDOWN_FIXTURE,
    InMemoryRagIndex,
    RagEvalJudge,
    RagEvalRunner,
    load_eval_dataset,
    summarize_results,
)


async def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is required.", file=sys.stderr)
        return 1

    if not MARKDOWN_FIXTURE.exists():
        print(f"Missing fixture: {MARKDOWN_FIXTURE}", file=sys.stderr)
        return 1

    markdown = MARKDOWN_FIXTURE.read_text(encoding="utf-8")
    cases = load_eval_dataset()

    print(f"Indexing fixture ({len(markdown)} chars)...")
    index = InMemoryRagIndex(markdown)
    await index.build()
    print(f"Indexed {len(index.chunk_records)} chunks.")

    runner = RagEvalRunner(index=index, judge=RagEvalJudge())
    print(f"Running {len(cases)} eval cases with rate-limited Gemini calls...")
    results = await runner.evaluate_all(cases)
    summary = summarize_results(results)

    print("\n=== RAG Eval Summary ===")
    print(json.dumps(summary, indent=2))

    print("\n=== Case Results ===")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"[{status}] {result.case_id} | "
            f"context={result.context_relevance.score:.2f} "
            f"faithfulness={result.faithfulness.score:.2f} "
            f"answer={result.answer_relevance.score:.2f}"
        )
        if result.failure_reasons:
            for reason in result.failure_reasons:
                print(f"  - {reason}")

    report_path = Path(__file__).resolve().parent / "rag_eval_report.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "cases": [
                    {
                        "case_id": result.case_id,
                        "question": result.question,
                        "ground_truth": result.ground_truth,
                        "passed": result.passed,
                        "failure_reasons": result.failure_reasons,
                        "scores": {
                            "context_relevance": result.context_relevance.score,
                            "faithfulness": result.faithfulness.score,
                            "answer_relevance": result.answer_relevance.score,
                        },
                        "reasoning": {
                            "context_relevance": result.context_relevance.reasoning,
                            "faithfulness": result.faithfulness.reasoning,
                            "answer_relevance": result.answer_relevance.reasoning,
                        },
                        "answer": result.answer,
                        "citations": result.citations,
                    }
                    for result in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetailed report written to {report_path}")

    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
