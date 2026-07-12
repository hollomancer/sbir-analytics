"""Contract tests for the private analytics API."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sbir_analytics.api.app import create_app
from sbir_analytics.api.models import AnalyticsResponse, Provenance


class StubService:
    def organization(self, identifier: str) -> AnalyticsResponse:
        return AnalyticsResponse(data=[{"organization_id": identifier}], provenance=Provenance())

    def award_history(self, identifier: str, limit: int, offset: int) -> AnalyticsResponse:
        return AnalyticsResponse(data=[], provenance=Provenance())

    def transition_metrics(self, *args) -> AnalyticsResponse:
        return AnalyticsResponse(data=[{"transition_rate": 0.5}], provenance=Provenance())

    def cet_concentration(self, *args) -> AnalyticsResponse:
        return AnalyticsResponse(data=[{"award_count_hhi": 0.25}], provenance=Provenance())

    def freshness(self) -> AnalyticsResponse:
        return AnalyticsResponse(data=[{"entity": "Organization"}], provenance=Provenance())


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SBIR_ANALYTICS_SNAPSHOT_DIR", str(tmp_path))
    return TestClient(create_app(service_factory=StubService, api_token="secret"))


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def _write_snapshot(root: Path, period: str, value: int, version: str = "1.0.0") -> None:
    directory = root / "transition_rate"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "analysis_kind": "transition_rate",
        "period": period,
        "as_of": f"{period[:4]}-12-31T00:00:00Z",
        "metadata": {
            "tool_name": "compute_transition_rate",
            "tool_version": version,
            "schema_version": "1",
            "data_sources": [],
            "warnings": [],
        },
        "result": {"awards": value, "transition_rate": value / 100},
    }
    (directory / f"{period}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_authentication_and_bounded_pagination(client: TestClient) -> None:
    assert client.get("/v1/analytics/transitions").status_code == 401
    assert client.get(
        "/v1/analytics/transitions?limit=501", headers=_headers()
    ).status_code == 422
    response = client.get("/v1/analytics/transitions", headers=_headers())
    assert response.status_code == 200
    assert response.json()["data"][0]["transition_rate"] == 0.5


def test_openapi_exposes_curated_routes_only(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/analytics/cet-concentration" in paths
    assert "/v1/snapshots/{analysis_kind}/{period}" in paths
    assert all("cypher" not in path and "materialize" not in path for path in paths)


def test_snapshot_get_and_compare(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_snapshot(tmp_path, "2025-Q4", 100)
    _write_snapshot(tmp_path, "2026-Q1", 125)

    response = client.get(
        "/v1/snapshots/transition_rate/2025-Q4/compare/2026-Q1", headers=_headers()
    )
    assert response.status_code == 200
    assert response.json()["numeric_deltas"] == {"awards": 25.0, "transition_rate": 0.25}


def test_missing_and_incompatible_snapshots(client: TestClient, tmp_path: Path) -> None:
    malformed = client.get("/v1/snapshots/transition_rate/not-a-period", headers=_headers())
    assert malformed.status_code == 422

    missing = client.get("/v1/snapshots/transition_rate/2024-Q1", headers=_headers())
    assert missing.status_code == 404

    _write_snapshot(tmp_path, "2025-Q4", 100)
    _write_snapshot(tmp_path, "2026-Q1", 125, version="2.0.0")
    incompatible = client.get(
        "/v1/snapshots/transition_rate/2025-Q4/compare/2026-Q1", headers=_headers()
    )
    assert incompatible.status_code == 409
