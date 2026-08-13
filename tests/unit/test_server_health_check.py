"""Regression tests for the live-server health-check profile."""

import builtins
import sys
from types import SimpleNamespace

import pytest

from scripts import e2e_health_check as health


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_server_environment_uses_compose_variable_contract(monkeypatch):
    for name in (
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_URI",
        "ENVIRONMENT",
        "NEO4J_USERNAME",
        "SBIR_ETL__NEO4J__BOLT_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    success, message = health.check_environment_variables("server")

    assert success, message


def test_server_dependencies_do_not_require_pytest(monkeypatch):
    real_import = builtins.__import__

    def import_without_pytest(name, *args, **kwargs):
        if name == "pytest":
            raise ImportError
        if name in {"dagster", "pandas", "neo4j", "pydantic"}:
            return object()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_pytest)

    server_success, server_message = health.check_python_dependencies("server")
    e2e_success, _ = health.check_python_dependencies("e2e")

    assert server_success, server_message
    assert not e2e_success


def test_server_neo4j_connection_uses_production_uri_and_user(monkeypatch):
    captured = {}

    class FakeResult:
        @staticmethod
        def single():
            return {"test": 1}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def run(_query):
            return FakeResult()

    class FakeDriver:
        @staticmethod
        def session():
            return FakeSession()

        @staticmethod
        def close():
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            captured.update(uri=uri, auth=auth)
            return FakeDriver()

    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(GraphDatabase=FakeGraphDatabase))
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "server-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "server-password")

    success, message = health.check_neo4j_connection("server")

    assert success, message
    assert captured == {
        "uri": "bolt://neo4j:7687",
        "auth": ("server-user", "server-password"),
    }
