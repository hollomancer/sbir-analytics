import json

import pytest

from scripts.archive.data.refine_ma_medium_tier import refine_events


class _IncompleteReferenceClient:
    def __init__(self) -> None:
        self.incomplete_calls = 0
        self.fetch_calls = 0
        self._context_incomplete_callback = self._mark_incomplete

    def _mark_incomplete(self) -> None:
        self.incomplete_calls += 1

    async def search_filing_mentions(self, company_name: str, **kwargs):
        return [{"doc_id": "malformed", "filer_cik": "12345"}]

    async def fetch_filing_document(self, cik: str, accession: str, filename: str):
        self.fetch_calls += 1
        return None


@pytest.mark.asyncio
async def test_directional_refinement_marks_malformed_document_reference(tmp_path) -> None:
    client = _IncompleteReferenceClient()
    output = tmp_path / "refined.jsonl"

    await refine_events(
        [{"company_name": "Alpha", "confidence": "medium"}],
        client,
        output,
        set(),
        concurrency=1,
    )

    row = json.loads(output.read_text())
    assert row["direction"] == "ambiguous"
    assert client.incomplete_calls == 1
    assert client.fetch_calls == 0
