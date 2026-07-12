"""Contract tests for the private analytics API."""

import json
import logging
from pathlib import Path
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sbir_analytics.api.app import create_app
from sbir_analytics.api.models import AnalyticsResponse, Provenance
from sbir_analytics.api.repository import AnalyticsBackendUnavailable
from sbir_analytics.api.snapshots import FileSnapshotRepository


class StubService:
    def __init__(self, *, available: bool = True):
        self.available = available
        self.close_calls = 0

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

    def verify_connectivity(self) -> None:
        if not self.available:
            raise AnalyticsBackendUnavailable("secret backend URI")

    def close(self) -> None:
        self.close_calls += 1


@pytest.fixture
def service() -> StubService:
    return StubService()


@pytest.fixture
def client(service: StubService, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        service_factory=lambda: service,
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(app) as test_client:
        yield test_client


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
    assert client.get("/v1/analytics/transitions?limit=501", headers=_headers()).status_code == 422
    response = client.get("/v1/analytics/transitions", headers=_headers())
    assert response.status_code == 200
    assert response.json()["data"][0]["transition_rate"] == 0.5


def test_unauthenticated_request_does_not_construct_service(tmp_path: Path) -> None:
    factory_calls = 0

    def factory() -> StubService:
        nonlocal factory_calls
        factory_calls += 1
        return StubService()

    app = create_app(
        service_factory=factory,
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(app) as test_client:
        response = test_client.get("/v1/data/freshness")
    assert response.status_code == 401
    assert factory_calls == 0


def test_service_is_closed_once_on_shutdown(service: StubService, tmp_path: Path) -> None:
    app = create_app(
        service_factory=lambda: service,
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(app) as test_client:
        assert test_client.get("/v1/data/freshness", headers=_headers()).status_code == 200
        assert test_client.get("/v1/data/freshness", headers=_headers()).status_code == 200
    assert service.close_calls == 1


def test_readiness_reports_backend_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    healthy_app = create_app(
        service_factory=StubService,
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(healthy_app) as healthy_client:
        response = healthy_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["components"] == {
            "authentication": "ready",
            "neo4j": "ready",
            "snapshots": "ready",
        }

    unavailable_app = create_app(
        service_factory=lambda: StubService(available=False),
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(unavailable_app) as unavailable_client:
        assert unavailable_client.get("/health/live").status_code == 200
        response = unavailable_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["components"]["neo4j"] == "unavailable"

    monkeypatch.delenv("SBIR_ANALYTICS_API_TOKEN", raising=False)
    missing_auth_app = create_app(
        service_factory=StubService,
        api_token=None,
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(missing_auth_app) as missing_auth_client:
        response = missing_auth_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["components"]["authentication"] == "unavailable"


def test_backend_error_is_sanitized_to_503(tmp_path: Path) -> None:
    class FailingService(StubService):
        def freshness(self) -> AnalyticsResponse:
            raise AnalyticsBackendUnavailable("bolt://user:password@private-host")

    app = create_app(
        service_factory=FailingService,
        api_token="secret",
        snapshot_repository=FileSnapshotRepository(tmp_path),
    )
    with TestClient(app) as test_client:
        response = test_client.get("/v1/data/freshness", headers=_headers())
    assert response.status_code == 503
    assert response.json() == {"detail": "Analytics backend is unavailable"}
    assert "password" not in response.text


def test_audit_log_uses_route_template_and_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="sbir_analytics.api.audit")
    response = client.get(
        "/v1/organizations/sensitive-identifier?unused=secret", headers=_headers()
    )
    records = [record for record in caplog.records if record.name == "sbir_analytics.api.audit"]
    payload = json.loads(records[-1].message)
    assert payload["route"] == "/v1/organizations/{identifier}"
    assert payload["status"] == 200
    assert response.headers["X-Request-ID"] == payload["request_id"]
    assert "sensitive-identifier" not in records[-1].message
    assert "secret" not in records[-1].message


def test_openapi_exposes_curated_routes_only(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/analytics/cet-concentration" in paths
    assert "/v1/snapshots/{analysis_kind}/{period}" in paths
    assert all("cypher" not in path and "materialize" not in path for path in paths)


def test_snapshot_get_and_compare(client: TestClient, tmp_path: Path) -> None:
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
