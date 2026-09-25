"""Hermetic tests for NIHReporterSourceAdapter. No live network."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from sbir_etl.enrichers.nih_reporter.adapter import NIHReporterSourceAdapter
from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord
from sbir_etl.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from sbir_etl.utils.enrichment.freshness import FreshnessStore


pytestmark = pytest.mark.fast


class _FakeClient:
    def __init__(self, records: list[NIHReporterRecord] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.records = (
            list(records)
            if records is not None
            else [
                NIHReporterRecord(
                    appl_id="10824314",
                    fy=2024,
                    project_num="1R43AI123456-01",
                    payload_hash="pagehash",
                )
            ]
        )

    async def lookup_projects(self, project_nums, fiscal_year, *, window=None, **kwargs):
        del kwargs
        self.calls.append(
            {
                "project_nums": list(project_nums),
                "fiscal_year": fiscal_year,
                "window": window,
            }
        )
        return list(self.records)

    def compute_payload_hash(self, payload: Any) -> str:
        return "computed-hash"


def test_adapter_lookup_and_persist(tmp_path: Path) -> None:
    client = _FakeClient()
    dest = tmp_path / "nih_reporter_awards.parquet"
    adapter = NIHReporterSourceAdapter(client=client, persist_path=dest)

    raw = adapter.fetch_page(
        {
            "award_id": "AW-1",
            "project_num": "1R43AI123456-01",
            "project_nums": ["1R43AI123456-01"],
            "award_year": 2024,
        },
        None,
    )
    records = adapter.normalize(raw)
    quality = adapter.validate(records)
    proven = adapter.provenance(raw)

    assert quality.ok
    assert records[0]["success"] is True
    assert records[0]["payload_hash"] == "pagehash"
    assert proven.citation_url == "https://api.reporter.nih.gov/"
    assert client.calls == [
        {"project_nums": ["1R43AI123456-01"], "fiscal_year": 2024, "window": None}
    ]
    stored = pd.read_parquet(dest)
    assert list(stored["appl_id"]) == ["10824314"]
    assert list(stored["award_id"]) == ["AW-1"]
    assert list(stored["upsert_key"]) == ["1R43AI123456-01|2024"]


def test_date_window_is_passed_to_client(tmp_path: Path) -> None:
    client = _FakeClient()
    adapter = NIHReporterSourceAdapter(client=client, persist_path=tmp_path / "out.parquet")
    adapter.fetch_page(
        {
            "award_id": "AW-1",
            "project_num": "1R43AI123456-01",
            "award_year": 2024,
            "window": "2024-01-01:2024-12-31",
        },
        None,
    )
    assert client.calls[0]["window"] == "2024-01-01:2024-12-31"


def test_missing_request_fields_fail_without_client_call(tmp_path: Path) -> None:
    client = _FakeClient()
    adapter = NIHReporterSourceAdapter(client=client, persist_path=tmp_path / "out.parquet")
    raw = adapter.fetch_page({"award_id": "AW-1"}, None)
    records = adapter.normalize(raw)
    assert adapter.validate(records).ok is False
    assert client.calls == []
    assert records[0]["error"]


def test_empty_lookup_is_success_and_does_not_wipe_table(tmp_path: Path) -> None:
    dest = tmp_path / "nih_reporter_awards.parquet"
    first = NIHReporterSourceAdapter(
        client=_FakeClient(),
        persist_path=dest,
    )
    first.fetch_page(
        {"award_id": "AW-1", "project_num": "1R43AI123456-01", "award_year": 2024},
        None,
    )
    empty = NIHReporterSourceAdapter(
        client=_FakeClient(records=[]),
        persist_path=dest,
    )
    raw = empty.fetch_page(
        {"award_id": "AW-1", "project_num": "1R43AI123456-01", "award_year": 2024},
        None,
    )
    records = empty.normalize(raw)
    assert records[0]["success"] is True
    assert records[0]["metadata"]["match_count"] == 0
    assert list(pd.read_parquet(dest)["appl_id"]) == ["10824314"]


def test_delta_compares_freshness_hash(tmp_path: Path) -> None:
    store = FreshnessStore(tmp_path / "freshness.parquet")
    store.save_record(
        EnrichmentFreshnessRecord(
            award_id="AW-1",
            source="nih_reporter",
            last_attempt_at=datetime(2020, 1, 1),
            last_success_at=datetime(2020, 1, 1),
            status=EnrichmentStatus.SUCCESS,
            payload_hash="pagehash",
        )
    )
    adapter = NIHReporterSourceAdapter(
        _FakeClient(),
        freshness=store,
        persist_path=tmp_path / "out.parquet",
    )
    raw = adapter.fetch_page(
        {"award_id": "AW-1", "project_num": "1R43AI123456-01", "award_year": 2024},
        None,
    )
    assert adapter.normalize(raw)[0]["delta_detected"] is False
