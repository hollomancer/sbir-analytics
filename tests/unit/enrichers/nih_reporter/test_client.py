"""Hermetic tests for NIHReporterAPIClient. No live network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from sbir_etl.enrichers.nih_reporter.client import (
    NIH_ACTIVITY_CODES,
    NIH_INCLUDE_FIELDS,
    NIH_PAGE_SIZE,
    NIHReporterAPIClient,
)
from sbir_etl.exceptions import APIError


pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).parent / "fixtures" / "search_page.json"


def _client(
    handler: httpx.MockTransport | Any,
    tmp_path: Path,
) -> NIHReporterAPIClient:
    transport = (
        handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(handler)
    )
    return NIHReporterAPIClient(
        config={
            "timeout_seconds": 5,
            "rate_limit_per_minute": 120,
            "cache": {"cache_dir": str(tmp_path / "cache")},
        },
        http_client=httpx.AsyncClient(transport=transport),
        cache_dir=tmp_path / "cache",
    )


def test_build_payload_omitted_window_is_activity_code_snapshot() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    payload = client.build_search_payload(offset=0)
    assert payload["criteria"] == {"activity_codes": list(NIH_ACTIVITY_CODES)}
    assert "project_start_date" not in payload["criteria"]
    assert "fiscal_years" not in payload["criteria"]
    assert payload["limit"] == NIH_PAGE_SIZE
    assert payload["include_fields"] == list(NIH_INCLUDE_FIELDS)


def test_build_payload_date_window_is_api_criteria() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    payload = client.build_search_payload(offset=0, window="2020-01-01:2021-12-31")
    assert payload["criteria"]["project_start_date"] == {
        "from_date": "2020-01-01",
        "to_date": "2021-12-31",
    }
    assert payload["criteria"]["activity_codes"] == list(NIH_ACTIVITY_CODES)


def test_build_payload_fy_window_is_api_criteria() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    payload = client.build_search_payload(offset=0, window="fy:2023-2024")
    assert payload["criteria"]["fiscal_years"] == [2023, 2024]


def test_build_payload_exact_lookup_canonicalizes_keys() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    payload = client.build_search_payload(
        offset=0,
        project_nums=[" 1 R43 AI123456-01, "],
        fiscal_years=[2024],
    )
    assert payload["criteria"]["project_nums"] == ["1R43AI123456-01"]
    assert payload["criteria"]["fiscal_years"] == [2024]


def test_build_payload_rejects_fy_window_and_explicit_years() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    with pytest.raises(ValueError, match="fy: window"):
        client.build_search_payload(offset=0, fiscal_years=[2024], window="fy:2023-2024")


def test_payload_hash_is_deterministic() -> None:
    client = NIHReporterAPIClient(config={"rate_limit_per_minute": 30}, cache_dir=".")
    first = client.compute_payload_hash({"b": 1, "a": 2})
    second = client.compute_payload_hash({"a": 2, "b": 1})
    assert first == second
    assert len(first) == 64


@pytest.mark.asyncio
async def test_search_uses_recorded_fixture(tmp_path: Path) -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=FIXTURE.read_bytes())

    client = _client(handler, tmp_path)
    records = await client.search_projects(window="fy:2024-2024", limit=500)
    assert len(records) == 1
    assert records[0].project_num == "1R43AI123456-01"
    assert captured[0]["criteria"]["fiscal_years"] == [2024]
    assert captured[0]["criteria"]["activity_codes"] == list(NIH_ACTIVITY_CODES)
    cached = list((tmp_path / "cache").glob("*.json"))
    assert len(cached) == 1


@pytest.mark.asyncio
async def test_search_paginates_to_declared_total(tmp_path: Path) -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset = int(body["offset"])
        offsets.append(offset)
        result = {
            "appl_id": 100 + offset,
            "fiscal_year": 2024,
            "project_num": "1R43AI123456-01",
            "activity_code": "R43",
        }
        return httpx.Response(
            200,
            json={"meta": {"total": 2, "offset": offset, "limit": 1}, "results": [result]},
        )

    client = _client(handler, tmp_path)
    records = await client.search_projects(limit=1)
    assert offsets == [0, 1]
    assert [record.appl_id for record in records] == ["100", "101"]
    assert {record.upsert_key() for record in records} == {("1R43AI123456-01", 2024)}


@pytest.mark.asyncio
async def test_partial_last_page_when_next_offset_equals_total(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset = int(body["offset"])
        if offset == 0:
            results = [
                {"appl_id": 1, "fiscal_year": 2024, "project_num": "1R43AA000001-01"},
                {"appl_id": 2, "fiscal_year": 2024, "project_num": "1R44AA000002-01"},
            ]
        else:
            results = [{"appl_id": 3, "fiscal_year": 2024, "project_num": "1R41AA000003-01"}]
        return httpx.Response(
            200,
            json={"meta": {"total": 3, "offset": offset, "limit": 2}, "results": results},
        )

    records = await _client(handler, tmp_path).search_projects(limit=2)
    assert [record.appl_id for record in records] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_duplicate_project_num_keeps_both_appl_ids(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "meta": {"total": 2, "offset": 0, "limit": 500},
                "results": [
                    {"appl_id": 10, "fiscal_year": 2024, "project_num": "1R43AI123456-01"},
                    {"appl_id": 11, "fiscal_year": 2024, "project_num": "1R43AI123456-01"},
                ],
            },
        )

    records = await _client(handler, tmp_path).search_projects()
    assert [record.appl_id for record in records] == ["10", "11"]
    assert records[0].upsert_key() == records[1].upsert_key()


@pytest.mark.asyncio
async def test_offset_mismatch_fails_closed(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"total": 1, "offset": 99, "limit": 500}, "results": []},
        )

    with pytest.raises(APIError, match="pagination metadata"):
        await _client(handler, tmp_path).fetch_page(offset=0)


@pytest.mark.asyncio
async def test_empty_page_before_total_fails_closed(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"total": 4, "offset": 0, "limit": 500}, "results": []},
        )

    with pytest.raises(APIError, match="stopped before the declared total"):
        await _client(handler, tmp_path).fetch_page(offset=0)


@pytest.mark.asyncio
async def test_oversized_page_fails_closed(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "meta": {"total": 2, "offset": 0, "limit": 1},
                "results": [
                    {"appl_id": 1, "fiscal_year": 2024},
                    {"appl_id": 2, "fiscal_year": 2024},
                ],
            },
        )

    with pytest.raises(APIError, match="inconsistent result counts"):
        await _client(handler, tmp_path).fetch_page(offset=0, limit=1)


@pytest.mark.asyncio
async def test_server_error_then_success_is_retried(tmp_path: Path) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, content=FIXTURE.read_bytes())

    records = await _client(handler, tmp_path).lookup_projects(["1R43AI123456-01"], 2024)
    assert attempts["count"] == 2
    assert records[0].appl_id == "10824314"


@pytest.mark.asyncio
async def test_lookup_date_window_is_api_criteria(tmp_path: Path) -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=FIXTURE.read_bytes())

    await _client(handler, tmp_path).lookup_projects(
        ["1R43AI123456-01"],
        2024,
        window="2024-01-01:2024-12-31",
    )
    criteria = captured[0]["criteria"]
    assert criteria["project_nums"] == ["1R43AI123456-01"]
    assert criteria["fiscal_years"] == [2024]
    assert criteria["project_start_date"] == {"from_date": "2024-01-01", "to_date": "2024-12-31"}


@pytest.mark.asyncio
async def test_lookup_rejects_fy_window(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FIXTURE.read_bytes())

    with pytest.raises(ValueError, match="fy: window"):
        await _client(handler, tmp_path).lookup_projects(
            ["1R43AI123456-01"],
            2024,
            window="fy:2024-2024",
        )


@pytest.mark.asyncio
async def test_client_error_is_not_retried(tmp_path: Path) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, text="bad request")

    with pytest.raises(APIError, match="HTTP 400"):
        await _client(handler, tmp_path).fetch_page(offset=0)
    assert attempts["count"] == 1
