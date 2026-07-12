"""Safety tests for curated Neo4j query execution."""

from typing import Any

from neo4j import Query

from sbir_analytics.api.repository import AnalyticsRepository


class FakeResult:
    def __iter__(self):
        return iter([{"item": {"organization_id": "org-1"}}])


class FakeSession:
    def __init__(self):
        self.query: Query | None = None
        self.parameters: dict[str, Any] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def run(self, query: Query, parameters: dict[str, Any]):
        self.query = query
        self.parameters = parameters
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.session_instance = FakeSession()
        self.options: dict[str, Any] = {}

    def session(self, **kwargs: Any) -> FakeSession:
        self.options = kwargs
        return self.session_instance


def test_repository_uses_read_session_and_parameters() -> None:
    driver = FakeDriver()
    repository = AnalyticsRepository(driver, timeout=3.0)

    result = repository.organization("' MATCH (n) DELETE n //")

    assert result == [{"organization_id": "org-1"}]
    assert driver.options["default_access_mode"] == "READ"
    assert driver.session_instance.parameters == {"identifier": "' MATCH (n) DELETE n //"}
    assert "$identifier" in str(driver.session_instance.query)
