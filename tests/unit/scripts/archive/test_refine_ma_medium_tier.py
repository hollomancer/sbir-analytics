import json

import pytest

from scripts.archive.data.refine_ma_medium_tier import refine_events


class _IncompleteReferenceClient:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.incomplete_calls = 0
        self.fetch_calls = 0
        self._context_incomplete_callback = self._mark_incomplete

    def _mark_incomplete(self) -> None:
        self.incomplete_calls += 1

    async def search_filing_mentions(self, company_name: str, **kwargs):
        if self.mode == "search_error":
            raise RuntimeError("search failed")
        if self.mode == "malformed":
            return [{"doc_id": "malformed", "filer_cik": "12345"}]
        return [{"doc_id": "0000012345-20-000001:doc.htm", "filer_cik": "12345"}]

    async def fetch_filing_document(self, cik: str, accession: str, filename: str):
        self.fetch_calls += 1
        if self.mode == "fetch_error":
            raise RuntimeError("fetch failed")
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_direction", "expected_fetches"),
    [
        ("malformed", "ambiguous", 0),
        ("search_error", "no_filing", 0),
        ("fetch_error", "ambiguous", 1),
    ],
)
async def test_directional_refinement_marks_incomplete_context(
    tmp_path, mode: str, expected_direction: str, expected_fetches: int
) -> None:
    client = _IncompleteReferenceClient(mode)
    output = tmp_path / "refined.jsonl"

    await refine_events(
        [{"company_name": "Alpha", "confidence": "medium"}],
        client,
        output,
        set(),
        concurrency=1,
    )

    row = json.loads(output.read_text())
    assert row["direction"] == expected_direction
    assert client.incomplete_calls == 1
    assert client.fetch_calls == expected_fetches
