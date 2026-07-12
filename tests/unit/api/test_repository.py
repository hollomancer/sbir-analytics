"""Safety tests for curated Neo4j query execution."""

from typing import Any

import pytest
from neo4j import Query
from neo4j.exceptions import ServiceUnavailable

from sbir_analytics.api.repository import AnalyticsBackendUnavailable, AnalyticsRepository


class FakeResult:
    def __iter__(self):
        return iter([{"item": {"organization_id": "org-1"}}])


class FakeSession:
    def __init__(self, error: Exception | None = None):
        self.query: Query | None = None
        self.parameters: dict[str, Any] = {}
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def run(self, query: Query, parameters: dict[str, Any]):
        if self.error:
            raise self.error
        self.query = query
        self.parameters = parameters
        return FakeResult()


class FakeDriver:
    def __init__(self, error: Exception | None = None):
        self.session_instance = FakeSession(error)
        self.options: dict[str, Any] = {}
        self.closed = False

    def session(self, **kwargs: Any) -> FakeSession:
        self.options = kwargs
        return self.session_instance

    def verify_connectivity(self) -> None:
        if self.session_instance.error:
            raise self.session_instance.error

    def close(self) -> None:
        self.closed = True


def test_repository_uses_read_session_and_parameters() -> None:
    driver = FakeDriver()
    repository = AnalyticsRepository(driver, timeout=3.0)

    result = repository.organization("' MATCH (n) DELETE n //")

    assert result == [{"organization_id": "org-1"}]
    assert driver.options["default_access_mode"] == "READ"
    assert driver.session_instance.parameters == {"identifier": "' MATCH (n) DELETE n //"}
    assert "$identifier" in str(driver.session_instance.query)


def test_repository_translates_availability_errors_only() -> None:
    unavailable = AnalyticsRepository(FakeDriver(ServiceUnavailable("private-host")))
    with pytest.raises(AnalyticsBackendUnavailable, match="Analytics backend is unavailable"):
        unavailable.freshness()
    with pytest.raises(AnalyticsBackendUnavailable, match="Analytics backend is unavailable"):
        unavailable.verify_connectivity()

    programming_error = AnalyticsRepository(FakeDriver(RuntimeError("bug")))
    with pytest.raises(RuntimeError, match="bug"):
        programming_error.freshness()
