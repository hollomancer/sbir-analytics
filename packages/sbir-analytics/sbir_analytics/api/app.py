"""FastAPI transport for the private analytics service."""

import hmac
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath, Query, Request, status
from neo4j import GraphDatabase

from .models import AnalyticsResponse, HealthResponse
from .repository import AnalyticsRepository
from .service import AnalyticsService
from .snapshots import (
    AnalysisKind,
    FileSnapshotRepository,
    IncompatibleSnapshotsError,
    SnapshotNotFoundError,
    SnapshotStoreError,
    compare_snapshots,
)


SnapshotPeriod = Annotated[str, ApiPath(pattern=r"^\d{4}(-Q[1-4])?$")]


def _service_from_environment() -> AnalyticsService:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_READ_USER", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("NEO4J_READ_PASSWORD", os.getenv("NEO4J_PASSWORD", ""))
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    timeout = float(os.getenv("SBIR_ANALYTICS_QUERY_TIMEOUT_SECONDS", "10"))
    driver = GraphDatabase.driver(uri, auth=(username, password))
    return AnalyticsService(AnalyticsRepository(driver, database=database, timeout=timeout))


def create_app(
    service_factory: Callable[[], AnalyticsService] = _service_from_environment,
    api_token: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="SBIR Analytics API",
        version="1.0.0",
        description="Private, read-only access to curated SBIR/STTR analytical evidence.",
    )

    snapshot_repository = FileSnapshotRepository(
        root=Path(os.getenv("SBIR_ANALYTICS_SNAPSHOT_DIR", "reports/analytics_snapshots"))
    )

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        expected = api_token if api_token is not None else os.getenv("SBIR_ANALYTICS_API_TOKEN")
        if not expected:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "API authentication is not configured"
            )
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")

    def service(request: Request) -> AnalyticsService:
        if not hasattr(request.app.state, "analytics_service"):
            request.app.state.analytics_service = service_factory()
        return request.app.state.analytics_service

    bounded_limit = Query(default=100, ge=1, le=500)
    bounded_offset = Query(default=0, ge=0, le=100_000)

    @app.get("/health/live", response_model=HealthResponse, include_in_schema=False)
    def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/v1/organizations/{identifier}", response_model=AnalyticsResponse)
    def organization(
        identifier: str,
        analytics: AnalyticsService = Depends(service),
        _: None = Depends(authenticate),
    ) -> AnalyticsResponse:
        return analytics.organization(identifier)

    @app.get("/v1/organizations/{identifier}/awards", response_model=AnalyticsResponse)
    def awards(
        identifier: str,
        limit: int = bounded_limit,
        offset: int = bounded_offset,
        analytics: AnalyticsService = Depends(service),
        _: None = Depends(authenticate),
    ) -> AnalyticsResponse:
        return analytics.award_history(identifier, limit, offset)

    @app.get("/v1/analytics/transitions", response_model=AnalyticsResponse)
    def transitions(
        agency: str | None = None,
        fiscal_year: int | None = Query(default=None, ge=1982, le=2100),
        limit: int = bounded_limit,
        offset: int = bounded_offset,
        analytics: AnalyticsService = Depends(service),
        _: None = Depends(authenticate),
    ) -> AnalyticsResponse:
        return analytics.transition_metrics(agency, fiscal_year, limit, offset)

    @app.get("/v1/analytics/cet-concentration", response_model=AnalyticsResponse)
    def cet_concentration(
        agency: str | None = None,
        fiscal_year: int | None = Query(default=None, ge=1982, le=2100),
        limit: int = bounded_limit,
        offset: int = bounded_offset,
        analytics: AnalyticsService = Depends(service),
        _: None = Depends(authenticate),
    ) -> AnalyticsResponse:
        return analytics.cet_concentration(agency, fiscal_year, limit, offset)

    @app.get("/v1/data/freshness", response_model=AnalyticsResponse)
    def freshness(
        analytics: AnalyticsService = Depends(service),
        _: None = Depends(authenticate),
    ) -> AnalyticsResponse:
        return analytics.freshness()

    @app.get("/v1/snapshots")
    def list_snapshots(
        analysis_kind: AnalysisKind | None = None,
        _: None = Depends(authenticate),
    ) -> dict[str, Any]:
        try:
            return {"data": snapshot_repository.list(analysis_kind)}
        except SnapshotStoreError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    @app.get("/v1/snapshots/{analysis_kind}/{period}")
    def get_snapshot(
        analysis_kind: AnalysisKind,
        period: SnapshotPeriod,
        _: None = Depends(authenticate),
    ) -> Any:
        try:
            return snapshot_repository.get(analysis_kind, period)
        except SnapshotNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except SnapshotStoreError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    @app.get("/v1/snapshots/{analysis_kind}/{period}/compare/{comparison_period}")
    def compare_snapshot_periods(
        analysis_kind: AnalysisKind,
        period: SnapshotPeriod,
        comparison_period: SnapshotPeriod,
        _: None = Depends(authenticate),
    ) -> dict[str, Any]:
        try:
            baseline = snapshot_repository.get(analysis_kind, period)
            comparison = snapshot_repository.get(analysis_kind, comparison_period)
            return compare_snapshots(baseline, comparison)
        except SnapshotNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except IncompatibleSnapshotsError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except SnapshotStoreError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return app


app = create_app()
