"""Tests for the Tailscale-only server environment template (.env.server.example).

These guard the security-relevant defaults of the server profile: loopback-only
bindings, the analytics API port, heavy-asset opt-out, and schedule gating.
"""

from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast, pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.server.example"


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def test_env_example_exists():
    assert ENV_EXAMPLE.is_file(), ".env.server.example must be committed"


def test_bindings_are_loopback():
    env = _parse_env(ENV_EXAMPLE)
    assert env["SERVER_LOOPBACK"] == "127.0.0.1"


def test_api_port_is_8010():
    env = _parse_env(ENV_EXAMPLE)
    assert env["SBIR_ANALYTICS_API_PORT"] == "8010"


def test_heavy_assets_disabled_by_default():
    env = _parse_env(ENV_EXAMPLE)
    assert env["DAGSTER_LOAD_HEAVY_ASSETS"] == "false"


def test_schedules_gated_off_by_default():
    env = _parse_env(ENV_EXAMPLE)
    assert env["SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED"] == "false"
    assert env["SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED"] == "false"


def test_storage_defaults_are_repo_local():
    env = _parse_env(ENV_EXAMPLE)
    for key in (
        "SERVER_DATA_DIR",
        "SERVER_REPORTS_DIR",
        "SERVER_LOGS_DIR",
        "SERVER_ARTIFACTS_DIR",
        "SERVER_NEO4J_DIR",
    ):
        assert env[key].startswith("./"), f"{key} default should be repository-local"


def test_secret_placeholders_are_not_real_values():
    env = _parse_env(ENV_EXAMPLE)
    # The template must ship placeholders, never real credentials.
    assert env["NEO4J_PASSWORD"] == "change_me"
    assert "change_me" in env["SBIR_ANALYTICS_API_TOKEN"]
