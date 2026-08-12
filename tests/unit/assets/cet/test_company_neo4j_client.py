"""Contract test for the CET Neo4j connection factory.

Every other test of the CET load assets patches ``_get_neo4j_client`` away, so
nothing exercised the real factory and a keyword mismatch against
``Neo4jConfig`` stayed green in CI while making all five CET load assets
unrunnable. This test calls the real factory.
"""

from unittest.mock import patch

import pytest

from sbir_analytics.assets.cet.company import _get_neo4j_client


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_neo4j_client_factory_builds_a_valid_config():
    """The factory must construct a ``Neo4jConfig`` that validates.

    ``Neo4jConfig`` requires ``username``; passing ``user`` raised a pydantic
    ``ValidationError`` before any network call, so the factory failed 100% of
    the time regardless of whether Neo4j was reachable.
    """

    captured = {}

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def run(self, *args, **kwargs):
            return None

    class _FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def session(self):
            return _FakeSession()

    with patch("sbir_analytics.assets.cet.company.Neo4jClient", _FakeClient):
        client = _get_neo4j_client()

    assert client is not None
    config = captured["config"]
    assert config.username, "Neo4jConfig.username must be populated by the factory"
    assert config.uri
    assert config.database


def test_neo4j_client_factory_failure_is_a_connection_error_not_a_config_error():
    """A failure here must come from connecting, never from building the config.

    Pins the distinction the original bug erased: with the config malformed,
    the factory raised before attempting any connection, so an operator saw a
    validation error where they expected a connectivity one.
    """

    class _ExplodingClient:
        def __init__(self, config):
            raise ConnectionError("simulated connection refused")

    with patch("sbir_analytics.assets.cet.company.Neo4jClient", _ExplodingClient):
        with pytest.raises(RuntimeError, match="Neo4j connection failed") as excinfo:
            _get_neo4j_client()

    assert "simulated connection refused" in str(excinfo.value)
    assert "validation error" not in str(excinfo.value).lower()
