"""Tests for the Tailscale-only server environment template (.env.server.example).

These guard the security-relevant defaults of the server profile: loopback-only
bindings, heavy-asset opt-out, and schedule gating.
"""

import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.server.example"
SERVER_COMPOSE = REPO_ROOT / "docker-compose.server.yml"
WAIT_FOR_SERVICE = REPO_ROOT / "scripts" / "docker" / "wait-for-service.sh"
CI_COMPOSE = REPO_ROOT / "docker-compose.yml"

pytestmark = [pytest.mark.fast, pytest.mark.unit]


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


def test_heavy_assets_loaded_but_not_scheduled():
    # Heavy jobs must be runnable by hand now that AWS Batch is gone, but the
    # always-on host must never launch one on its own.
    env = _parse_env(ENV_EXAMPLE)
    assert env["DAGSTER_LOAD_HEAVY_ASSETS"] == "true"
    assert env["SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED"] == "false"


def test_schedules_gated_off_by_default():
    env = _parse_env(ENV_EXAMPLE)
    assert env["SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED"] == "false"
    assert env["SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED"] == "false"


def test_pipeline_chaining_sensors_gated_off_by_default():
    env = _parse_env(ENV_EXAMPLE)
    for name in (
        "SBIR_PIPELINE_AFTER_DOWNLOAD",
        "USPTO_PIPELINE_AFTER_DOWNLOAD",
        "USASPENDING_PIPELINE_AFTER_DOWNLOAD",
    ):
        assert env[f"SBIR_ETL__DAGSTER__SENSORS__{name}_ENABLED"] == "false"


def test_storage_defaults_are_repo_local():
    env = _parse_env(ENV_EXAMPLE)
    for key in (
        "SERVER_DATA_DIR",
        "SERVER_REPORTS_DIR",
        "SERVER_LOGS_DIR",
        "SERVER_ARTIFACTS_DIR",
        "SERVER_NEO4J_DIR",
        "SERVER_BACKUP_DIR",
    ):
        assert env[key].startswith("./"), f"{key} default should be repository-local"


def test_secret_placeholders_are_not_real_values():
    env = _parse_env(ENV_EXAMPLE)
    # The template must ship placeholders, never real credentials.
    assert env["NEO4J_PASSWORD"] == "change_me"


def test_neo4j_healthcheck_receives_credentials_and_valid_plugin_json():
    compose = SERVER_COMPOSE.read_text()

    assert "SBIR_SERVER_NEO4J_USER=${NEO4J_USER:-neo4j}" in compose
    assert "SBIR_SERVER_NEO4J_PASSWORD=${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}" in compose
    assert "$${SBIR_SERVER_NEO4J_PASSWORD}" in compose
    assert "'NEO4J_PLUGINS=${NEO4J_PLUGINS:-[\"apoc\"]}'" in compose


def test_dependency_wait_contract_matches_slim_server_image():
    compose = SERVER_COMPOSE.read_text()
    wait_script = WAIT_FOR_SERVICE.read_text()
    dagster_healthcheck = (
        REPO_ROOT / "scripts" / "docker" / "healthcheck" / "dagster.sh"
    ).read_text()
    daemon_healthcheck = (
        REPO_ROOT / "scripts" / "docker" / "healthcheck" / "daemon.sh"
    ).read_text()

    assert os.access(WAIT_FOR_SERVICE, os.X_OK)
    assert "DAGSTER_HOST: dagster-webserver" in compose
    assert 'HEALTHCHECK_PORT: "3000"' in compose
    assert "command -v python" in wait_script
    assert 'HEALTH_PATH="${HEALTHCHECK_PATH:-/server_info}"' in dagster_healthcheck
    assert "dagster-daemon liveness-check" in daemon_healthcheck


def test_ci_container_mounts_server_env_contract():
    compose = CI_COMPOSE.read_text()
    assert "./.env.server.example:/app/.env.server.example:ro" in compose


def test_dev_runner_live_mounts_do_not_shadow_locked_environment():
    compose = CI_COMPOSE.read_text()
    runner = compose.split("  etl-runner:", 1)[1].split("\n  app:", 1)[0]

    assert "./:/app:ro" not in runner
    assert "./sbir_etl:/app/sbir_etl:ro" in runner
    assert "./packages/sbir-ml/sbir_ml:/app/packages/sbir-ml/sbir_ml:ro" in runner
    assert "PYTHONPATH: /app:/app/packages/sbir-analytics" in runner


def test_ci_profile_uses_locked_test_image_without_startup_installs():
    compose = CI_COMPOSE.read_text()
    app = compose.split("  app:", 1)[1].split("\n  tools:", 1)[0]

    assert "target: test" in app
    assert "pytest -m fast -q" in app
    assert "uv pip install" not in app
    assert "pip install" not in app
