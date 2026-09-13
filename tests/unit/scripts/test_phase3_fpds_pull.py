"""Tests for the research-only FPDS Element 10Q puller."""

import json
import urllib.parse
from pathlib import Path

from scripts.phase3_benchmark.pull_fpds_10q import (
    build_parser,
    build_query_url,
    parse_feed,
    pull_research_code,
    write_outputs,
)


FIXTURE = Path("tests/fixtures/phase3_benchmark/fpds_atom_page.xml")


def _live_shaped_page(
    piid: str, *, next_url: str | None = None, last_url: str | None = None
) -> bytes:
    links = []
    if last_url:
        links.append(f'<link rel="last" href="{last_url.replace("&", "&amp;")}" />')
    if next_url:
        links.append(f'<link rel="next" href="{next_url.replace("&", "&amp;")}" />')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:fpds="https://www.fpds.gov/FPDS">'
        + "".join(links)
        + "<entry><modified>2024-04-16T12:00:00Z</modified><content><fpds:award>"
        f"<fpds:PIID>{piid}</fpds:PIID>"
        "<fpds:modNumber>A00001</fpds:modNumber>"
        "<fpds:transactionNumber>1</fpds:transactionNumber>"
        "<fpds:UEI>UEI000000001</fpds:UEI>"
        "<fpds:descriptionOfContractRequirement>Phase III production</fpds:descriptionOfContractRequirement>"
        "<fpds:signedDate>2024-04-15</fpds:signedDate>"
        "<fpds:agencyID>2100</fpds:agencyID>"
        '<fpds:fundingRequestingAgencyID name="DEPT OF THE NAVY">1700'
        "</fpds:fundingRequestingAgencyID>"
        "<fpds:referencedIDVID><fpds:agencyID>1700</fpds:agencyID>"
        "<fpds:PIID>PARENT-1</fpds:PIID></fpds:referencedIDVID>"
        "</fpds:award></content></entry></feed>"
    ).encode()


def test_parse_feed_extracts_nested_parent_idv_without_replacing_order_piid():
    frame, total = parse_feed(FIXTURE.read_bytes(), "sr3")

    assert total == 1
    assert frame.iloc[0]["modified"] == "2024-04-16T12:00:00Z"
    assert frame.iloc[0]["PIID"] == "0001"
    assert frame.iloc[0]["modNumber"] == "A00001"
    assert frame.iloc[0]["transactionNumber"] == "1"
    assert frame.iloc[0]["referenced_idv_piid"] == "N00019-20-D-0001"
    assert frame.iloc[0]["referenced_idv_agency_id"] == "1700"
    assert frame.iloc[0]["agencyID"] == "2100"
    assert frame.iloc[0]["agencyID_name"] == "Department of Defense"
    assert frame.iloc[0]["fundingRequestingAgencyID"] == "1700"


def test_parse_feed_extracts_transaction_revision_and_funding_agency_fields():
    frame, _total = parse_feed(_live_shaped_page("0001"), "sr3")

    row = frame.iloc[0]
    assert row["modified"] == "2024-04-16T12:00:00Z"
    assert row["modNumber"] == "A00001"
    assert row["transactionNumber"] == "1"
    assert row["fundingRequestingAgencyID"] == "1700"
    assert row["fundingRequestingAgencyID_name"] == "DEPT OF THE NAVY"


def test_build_query_url_encodes_additional_exact_terms():
    terms = (
        "SIGNED_DATE:[2020/01/01,2024/12/31]",
        'CONTRACT_TYPE:"AWARD"',
        'CONTRACTING_AGENCY_ID:"1700"',
        'FUNDING_AGENCY_ID:"1700"',
    )

    url = build_query_url("sr3", 20, terms)
    parameters = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)

    assert parameters["q"] == ["RESEARCH:SR3 " + " ".join(terms)]
    assert parameters["start"] == ["20"]
    assert "CONTRACT_TYPE%3A%22AWARD%22" in url
    assert "SIGNED_DATE%3A%5B2020%2F01%2F01%2C2024%2F12%2F31%5D" in url


def test_parser_accepts_repeated_query_terms(tmp_path):
    args = build_parser().parse_args(
        [
            "sr3",
            "--pages",
            "1",
            "--output",
            str(tmp_path / "records.parquet"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--query-term",
            "SIGNED_DATE:[2020/01/01,2024/12/31]",
            "--query-term",
            'CONTRACT_TYPE:"AWARD"',
        ]
    )

    assert args.query_term == [
        "SIGNED_DATE:[2020/01/01,2024/12/31]",
        'CONTRACT_TYPE:"AWARD"',
    ]


def test_pull_records_manifest_and_writes_outputs(tmp_path):
    payload = FIXTURE.read_bytes()
    requested: list[str] = []

    def fetcher(url: str) -> bytes:
        requested.append(url)
        return payload

    frame, manifest = pull_research_code(
        "sr3",
        pages=3,
        fetcher=fetcher,
        source_vintage="fixture-2024",
        retrieved_at="2026-07-16T00:00:00+00:00",
    )
    output = tmp_path / "records.parquet"
    manifest_path = tmp_path / "manifest.json"
    write_outputs(frame, manifest, output_path=output, manifest_path=manifest_path)

    saved = json.loads(manifest_path.read_text())
    assert requested == [build_query_url("SR3", 0)]
    assert output.exists()
    assert saved["query"] == "RESEARCH:SR3"
    assert saved["parameters"] == {"pages_requested": 3, "research_code": "SR3"}
    assert saved["row_count"] == 1
    assert saved["retrieval_complete"] is True
    assert saved["field_completeness"]["referenced_idv_piid"] == 1.0
    assert saved["field_completeness"]["modified"] == 1.0
    assert saved["field_completeness"]["modNumber"] == 1.0
    assert saved["field_completeness"]["transactionNumber"] == 1.0
    assert saved["field_completeness"]["fundingRequestingAgencyID"] == 1.0
    assert len(saved["raw_pages_sha256"]) == 64


def test_pull_follows_live_atom_links_and_records_feed_exhaustion():
    first_url = build_query_url("SR3", 0)
    next_url = build_query_url("SR3", 10)
    last_url = build_query_url("SR3", 10)
    payloads = {
        first_url: _live_shaped_page("0001", next_url=next_url, last_url=last_url),
        next_url: _live_shaped_page("0002", last_url=last_url),
    }
    requested: list[str] = []

    def fetcher(url: str) -> bytes:
        requested.append(url)
        return payloads[url]

    frame, manifest = pull_research_code(
        "sr3",
        pages=3,
        fetcher=fetcher,
        retrieved_at="2026-07-16T00:00:00+00:00",
    )

    assert requested == [first_url, next_url]
    assert frame["PIID"].tolist() == ["0001", "0002"]
    assert manifest["reported_total_results"] is None
    assert manifest["retrieval_complete"] is True
    assert manifest["termination_reason"] == "feed_exhausted"


def test_pull_marks_page_limit_as_incomplete_without_total_results():
    next_url = build_query_url("SR3", 10)

    frame, manifest = pull_research_code(
        "sr3",
        pages=1,
        fetcher=lambda _url: _live_shaped_page("0001", next_url=next_url),
        retrieved_at="2026-07-16T00:00:00+00:00",
    )

    assert len(frame) == 1
    assert manifest["retrieval_complete"] is False
    assert manifest["termination_reason"] == "page_limit_reached"


def test_cache_is_query_safe_and_retains_original_capture_time(tmp_path):
    cache_dir = tmp_path / "cache"
    calls: list[str] = []

    def fetcher(url: str) -> bytes:
        calls.append(url)
        return _live_shaped_page("0001")

    _, first = pull_research_code(
        "sr3",
        pages=1,
        fetcher=fetcher,
        cache_dir=cache_dir,
        retrieved_at="2026-07-16T00:00:00+00:00",
    )
    pull_research_code(
        "st3",
        pages=1,
        fetcher=fetcher,
        cache_dir=cache_dir,
        retrieved_at="2026-07-17T00:00:00+00:00",
    )

    def unexpected_fetch(_url: str) -> bytes:
        raise AssertionError("SR3 rerun should use its validated cache entry")

    _, cached = pull_research_code(
        "sr3",
        pages=1,
        fetcher=unexpected_fetch,
        cache_dir=cache_dir,
        retrieved_at="2026-07-18T00:00:00+00:00",
    )

    assert calls == [build_query_url("SR3", 0), build_query_url("ST3", 0)]
    assert first["cache_hits"] == 0
    assert cached["cache_hits"] == 1
    assert cached["retrieved_at"] == "2026-07-16T00:00:00+00:00"
    assert cached["run_at"] == "2026-07-18T00:00:00+00:00"
    assert cached["page_provenance"][0]["cache_hit"] is True


def test_pull_with_query_terms_follows_next_links_and_records_manifest():
    terms = (
        "SIGNED_DATE:[2020/01/01,2024/12/31]",
        'CONTRACT_TYPE:"AWARD"',
        'FUNDING_AGENCY_ID:"1700"',
    )
    first_url = build_query_url("SR3", 0, terms)
    second_url = build_query_url("SR3", 10, terms)
    payloads = {
        first_url: _live_shaped_page("0001", next_url=second_url, last_url=second_url),
        second_url: _live_shaped_page("0002", last_url=second_url),
    }
    requested: list[str] = []

    def fetcher(url: str) -> bytes:
        requested.append(url)
        return payloads[url]

    frame, manifest = pull_research_code(
        "sr3",
        pages=3,
        query_terms=terms,
        fetcher=fetcher,
        retrieved_at="2026-07-16T00:00:00+00:00",
    )

    ordered_urls = [first_url, second_url]
    assert requested == ordered_urls
    assert frame["PIID"].tolist() == ["0001", "0002"]
    assert [page["url"] for page in manifest["page_provenance"]] == ordered_urls
    assert manifest["retrieval_complete"] is True
    assert manifest["termination_reason"] == "feed_exhausted"
    assert manifest["query"] == "RESEARCH:SR3 " + " ".join(terms)
    assert manifest["parameters"] == {
        "research_code": "SR3",
        "pages_requested": 3,
        "query_terms": list(terms),
    }
