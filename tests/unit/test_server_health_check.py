"""Regression tests for the live-server health-check profile."""

import builtins

import pytest

from scripts import e2e_health_check as health


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_server_environment_uses_compose_variable_contract(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "prod")

    success, message = health.check_environment_variables("server")

    assert success, message


def test_server_dependencies_do_not_require_pytest(monkeypatch):
    real_import = builtins.__import__

    def import_without_pytest(name, *args, **kwargs):
        if name == "pytest":
            raise ImportError
        if name in {"dagster", "pandas", "pydantic"}:
            return object()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_pytest)

    server_success, server_message = health.check_python_dependencies("server")
    e2e_success, _ = health.check_python_dependencies("e2e")

    assert server_success, server_message
    assert not e2e_success
