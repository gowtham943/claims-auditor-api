from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

with patch("google.genai.Client", return_value=MagicMock()):
    from rag_engine.policy_rag_engine import PolicyRAGEngine

FIXTURE_PATH = Path(__file__).parent / "resources" / "package_rate_ledger_report.md"


@pytest.fixture
def chunker():
    with patch("rag_engine.policy_rag_engine.genai.Client", return_value=MagicMock()):
        yield PolicyRAGEngine()


def test_ledger_produces_chunks_by_markdown_headings(chunker):
    markdown_text = FIXTURE_PATH.read_text(encoding="utf-8")
    chunks = chunker.segment_markdown_by_headers(markdown_text)

    assert len(chunks) >= 4
    combined = "\n".join(chunk["text"] for chunk in chunks)

    assert "3,403" in combined
    assert "CMU0001" in combined
    assert "MEDICAL ONCOLOGY" in combined


def test_executive_summary_and_procedure_rows_are_separated(chunker):
    markdown_text = FIXTURE_PATH.read_text(encoding="utf-8")
    chunks = chunker.segment_markdown_by_headers(markdown_text)

    executive_chunks = [c for c in chunks if "TOTAL PROCEDURES" in c["text"]]
    procedure_chunks = [c for c in chunks if "CMU0001" in c["text"]]

    assert executive_chunks
    assert procedure_chunks
    assert executive_chunks[0] is not procedure_chunks[0]


def test_markdown_headers_split_into_sections(chunker):
    markdown_text = """# Coverage Rules

General eligibility applies.

## Co-pays

Outpatient co-pay is 20%.
"""
    chunks = chunker.segment_markdown_by_headers(markdown_text)

    assert len(chunks) == 2
    assert chunks[0]["heading"] == "# Coverage Rules"
    assert chunks[1]["heading"] == "## Co-pays"
    assert "General eligibility applies." in chunks[0]["text"]
    assert "Outpatient co-pay is 20%." in chunks[1]["text"]
