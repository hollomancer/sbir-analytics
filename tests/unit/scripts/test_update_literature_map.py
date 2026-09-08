"""Unit tests for the exploratory literature-map refresh."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sbir_etl.enrichers.openalex_client import OpenAlexClient
from sbir_etl.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))

from update_literature_map import (  # noqa: E402
    RssSource,
    classify_new_work,
    feed_entry_to_row,
    is_openalex_work_id,
    load_map,
    merge_rows,
    openalex_ids_for_refresh,
    parse_feed,
    parse_work,
    resolve_doi_work_id,
    synthetic_id,
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


GAO_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="/scripts/rss.xsl" ?>
<rss version="2.0">
  <channel>
    <title>Reports News from the GAO</title>
    <item>
      <title>Small Business Research Programs: Increased Performance Standards</title>
      <link>https://www.gao.gov/products/gao-24-106398</link>
      <description>GAO reviewed SBIR/STTR multiple-award performance standards.</description>
      <pubDate>Wed, 15 May 2024 08:00:00 -0400</pubDate>
    </item>
    <item>
      <title>Defense Industrial Base: Dependence on Foreign Suppliers</title>
      <link>https://www.gao.gov/products/gao-25-107283</link>
      <description>DoD supplier visibility past the prime-contractor tier.</description>
      <pubDate>Tue, 11 Mar 2025 08:00:00 -0400</pubDate>
    </item>
    <item>
      <title>Defense Health Care: Blast Exposures</title>
      <link>https://www.gao.gov/products/gao-26-107829</link>
      <description>Cognitive assessments for service members.</description>
      <pubDate>Tue, 18 Aug 2026 06:59:03 -0400</pubDate>
    </item>
    <item>
      <title>International Agreements: DOD Oversight</title>
      <link>https://www.gao.gov/products/gao-26-108249</link>
      <description>Goals for cost-sharing and defense industrial base improvements.</description>
      <pubDate>Mon, 17 Aug 2026 08:00:00 -0400</pubDate>
    </item>
  </channel>
</rss>
"""

NAP_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="https://www.w3.org/2005/Atom">
  <title>New Titles from the National Academies Press</title>
  <entry>
    <title>Review of the SBIR and STTR Programs at the Department of Defense</title>
    <link rel="alternate" href="https://www.nap.edu/catalog/29329"/>
    <id>tag:nap.edu,2026:https://www.nap.edu/catalog/29329#final</id>
    <published>2026-01-15T00:00:00-05:00</published>
    <content type="html">Final Book Now Available</content>
  </entry>
  <entry>
    <title>Report of the Treasurer For the Year Ended December 31, 2025</title>
    <link rel="alternate" href="https://www.nap.edu/catalog/29521"/>
    <published>2026-07-31T10:45:12-04:00</published>
  </entry>
</feed>
"""

GAO_SOURCE = RssSource(
    prefix="gao",
    venue="U.S. Government Accountability Office",
    hint_area="E",
    url="https://www.gao.gov/rss/reports.xml",
    first_author="GAO",
    work_type="report",
)
NAP_SOURCE = RssSource(
    prefix="nap",
    venue="National Academies Press",
    hint_area="E",
    url="https://nap.nationalacademies.org/rss/",
    first_author="NASEM",
    work_type="book",
)


def test_synthetic_ids_from_canonical_urls() -> None:
    assert (
        synthetic_id("gao", "https://www.gao.gov/products/gao-25-107283", "x")
        == "gao:GAO-25-107283"
    )
    assert (
        synthetic_id("crs", "https://www.EveryCRSReport.com/reports/R43695.html", "x")
        == "crs:R43695"
    )
    assert synthetic_id("nap", "https://www.nap.edu/catalog/29329", "x") == "nap:29329"


def test_parse_gao_rss_keeps_sbir_and_dib_drops_unrelated() -> None:
    entries = parse_feed(GAO_RSS)
    rows = [feed_entry_to_row(entry, GAO_SOURCE) for entry in entries]
    kept = {row["openalex_id"]: row for row in rows if row is not None}
    assert set(kept) == {"gao:GAO-24-106398", "gao:GAO-25-107283"}
    assert kept["gao:GAO-24-106398"]["relevance"] == "core"
    assert kept["gao:GAO-24-106398"]["year"] == "2024"
    assert kept["gao:GAO-25-107283"]["relevance"] == "adjacent"
    assert kept["gao:GAO-25-107283"]["area"] == "A"


def test_parse_nap_atom_keeps_sbir_book() -> None:
    entries = parse_feed(NAP_ATOM)
    rows = [feed_entry_to_row(entry, NAP_SOURCE) for entry in entries]
    kept = [row for row in rows if row is not None]
    assert len(kept) == 1
    assert kept[0]["openalex_id"] == "nap:29329"
    assert kept[0]["relevance"] == "core"
    assert kept[0]["year"] == "2026"


def test_merge_dedupes_grey_stub_onto_openalex_id() -> None:
    existing = [
        {
            "relevance": "core",
            "area": "E",
            "year": "2026",
            "first_author": "NASEM",
            "n_authors": "1",
            "title": "Review of the SBIR and STTR Programs at the Department of Defense",
            "venue": "National Academies Press",
            "type": "book",
            "citations": "",
            "fwci": "",
            "open_access": "True",
            "doi": "",
            "openalex_id": "nap:29329",
        }
    ]
    incoming = [
        parse_work(
            {
                **SAMPLE_WORK,
                "id": "https://openalex.org/W555",
                "display_name": "Review of the SBIR and STTR Programs at the Department of Defense",
                "cited_by_count": 12,
                "doi": "https://doi.org/10.17226/29329",
            }
        )
    ]
    merged, added = merge_rows(existing, incoming)
    assert added == 0
    assert len(merged) == 1
    assert merged[0]["openalex_id"] == "W555"
    assert merged[0]["relevance"] == "core"
    assert merged[0]["citations"] == "12"
    assert merged[0]["doi"] == "10.17226/29329"


def test_grey_rss_does_not_clobber_openalex_citations() -> None:
    existing = [
        parse_work(SAMPLE_WORK)
        | {
            "relevance": "core",
            "area": "B",
            "title": "An SBIR commercialization study",
        }
    ]
    incoming = [
        {
            "relevance": "core",
            "area": "B",
            "year": "2024",
            "first_author": "GAO",
            "n_authors": "1",
            "title": "An SBIR commercialization study",
            "venue": "U.S. Government Accountability Office",
            "type": "report",
            "citations": "0",
            "fwci": "",
            "open_access": "True",
            "doi": "",
            "openalex_id": "gao:GAO-24-1",
        }
    ]
    merged, added = merge_rows(existing, incoming)
    assert added == 0
    assert merged[0]["openalex_id"] == "W123"
    assert merged[0]["citations"] == "4"


def test_openalex_refresh_skips_synthetic_ids() -> None:
    rows = [
        {"openalex_id": "W123"},
        {"openalex_id": "gao:GAO-24-106398"},
        {"openalex_id": "nap:29329"},
        {"openalex_id": ""},
    ]
    assert openalex_ids_for_refresh(rows) == ["W123"]
    assert is_openalex_work_id("W123")
    assert not is_openalex_work_id("gao:GAO-24-106398")


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


def test_resolve_doi_work_id_uses_doi_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_search(self, params):  # noqa: ANN001
        captured["params"] = params
        return {"results": [{"id": "https://openalex.org/W2741809807"}], "meta": {}}

    monkeypatch.setattr(OpenAlexClient, "search_works", fake_search)
    oid = asyncio.run(resolve_doi_work_id(OpenAlexClient(), "10.1257/aer.20150491"))
    assert oid == "W2741809807"
    assert captured["params"] == {"filter": "doi:10.1257/aer.20150491", "per_page": 1}


def test_resolve_doi_work_id_raises_when_missing(monkeypatch) -> None:
    async def fake_search(self, params):  # noqa: ANN001
        return {"results": [], "meta": {}}

    monkeypatch.setattr(OpenAlexClient, "search_works", fake_search)
    with pytest.raises(RuntimeError, match="no work id"):
        asyncio.run(resolve_doi_work_id(OpenAlexClient(), "10.0/missing"))


def test_search_works_propagates_malformed_filter(monkeypatch) -> None:
    async def fake_request(self, method, endpoint, params=None):  # noqa: ANN001
        raise APIError("bad filter", api_name="openalex", http_status=400)

    monkeypatch.setattr(OpenAlexClient, "_make_request", fake_request)
    with pytest.raises(APIError):
        asyncio.run(OpenAlexClient().search_works({"filter": "cites:doi:10.1257/aer.20150491"}))


def test_search_works_404_is_empty(monkeypatch) -> None:
    async def fake_request(self, method, endpoint, params=None):  # noqa: ANN001
        raise APIError("gone", api_name="openalex", http_status=404)

    monkeypatch.setattr(OpenAlexClient, "_make_request", fake_request)
    data = asyncio.run(OpenAlexClient().search_works({"filter": "openalex_id:W0"}))
    assert data["results"] == []
