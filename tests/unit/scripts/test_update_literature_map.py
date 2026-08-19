"""Unit tests for the exploratory literature-map refresh."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sbir_etl.enrichers.openalex_client import OpenAlexClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))

from update_literature_map import (  # noqa: E402
    classify_new_work,
    load_map,
    merge_rows,
    parse_work,
    write_map,
)


SAMPLE_WORK = {
    "id": "https://openalex.org/W123",
    "display_name": "An SBIR commercialization study",
    "publication_year": 2024,
    "type": "article",
    "cited_by_count": 4,
    "fwci": 1.2,
    "doi": "https://doi.org/10.1/example",
    "open_access": {"is_oa": True},
    "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
    "primary_location": {"source": {"display_name": "Research Policy"}},
}


def test_parse_work_flattens_openalex_fields() -> None:
    row = parse_work(SAMPLE_WORK)
    assert row["openalex_id"] == "W123"
    assert row["first_author"] == "Ada Lovelace"
    assert row["n_authors"] == "1"
    assert row["doi"] == "10.1/example"
    assert row["open_access"] == "True"
    assert row["citations"] == "4"
    assert row["year"] == "2024"


def test_classify_core_sbir_title() -> None:
    assert classify_new_work("Evaluating the SBIR program") == ("core", "E")


def test_classify_adjacent_defense_without_sbir() -> None:
    assert classify_new_work("Defense industrial base procurement reform") == ("adjacent", "A")


def test_classify_drops_off_topic() -> None:
    assert classify_new_work("A cookbook of pasta sauces") is None


def test_merge_preserves_existing_labels_and_adds_new() -> None:
    existing = [
        {
            "relevance": "core",
            "area": "B",
            "year": "2020",
            "first_author": "Old",
            "n_authors": "1",
            "title": "Old title",
            "venue": "X",
            "type": "article",
            "citations": "1",
            "fwci": "0.1",
            "open_access": "False",
            "doi": "10.old",
            "openalex_id": "W123",
        }
    ]
    incoming = [
        parse_work(SAMPLE_WORK),
        parse_work(
            {
                **SAMPLE_WORK,
                "id": "https://openalex.org/W999",
                "display_name": "Venture capital after Form D offerings",
            }
        ),
    ]
    merged, added = merge_rows(existing, incoming)
    by_id = {row["openalex_id"]: row for row in merged}
    assert added == 1
    assert by_id["W123"]["relevance"] == "core"
    assert by_id["W123"]["area"] == "B"
    assert by_id["W123"]["citations"] == "4"
    assert by_id["W123"]["title"] == "An SBIR commercialization study"
    assert by_id["W999"]["relevance"] == "adjacent"
    assert by_id["W999"]["area"] == "F"


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    write_map(path, [parse_work(SAMPLE_WORK) | {"relevance": "core", "area": "B"}])
    rows = load_map(path)
    assert len(rows) == 1
    assert rows[0]["openalex_id"] == "W123"


def test_search_works_passes_mailto(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_request(self, method, endpoint, params=None):  # noqa: ANN001
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["params"] = params
        return {"results": [], "meta": {}}

    monkeypatch.setattr(OpenAlexClient, "_make_request", fake_request)
    client = OpenAlexClient(mailto="map@example.com")
    data = asyncio.run(client.search_works({"search": "SBIR", "per_page": 2}))
    assert data["results"] == []
    assert captured["endpoint"] == "works"
    assert captured["params"]["mailto"] == "map@example.com"
    assert captured["params"]["search"] == "SBIR"
