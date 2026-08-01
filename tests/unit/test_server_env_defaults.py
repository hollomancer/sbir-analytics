"""Tests for the Tailscale-only server environment template (.env.server.example).

These guard the security-relevant defaults of the server profile: loopback-only
bindings, the analytics API port, heavy-asset opt-out, and schedule gating.
"""

import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.server.example"
SERVER_COMPOSE = REPO_ROOT / "docker-compose.server.yml"
WAIT_FOR_SERVICE = REPO_ROOT / "scripts" / "docker" / "wait-for-service.sh"
CI_COMPOSE = REPO_ROOT / "docker-compose.yml"
BUILD_IMAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-images.yml"

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
        "SERVER_BACKUP_DIR",
    ):
        assert env[key].startswith("./"), f"{key} default should be repository-local"


def test_secret_placeholders_are_not_real_values():
    env = _parse_env(ENV_EXAMPLE)
    # The template must ship placeholders, never real credentials.
    assert env["NEO4J_PASSWORD"] == "change_me"
    assert "change_me" in env["SBIR_ANALYTICS_API_TOKEN"]


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


def test_image_workflow_rebuilds_arm64_images_when_workflow_changes():
    workflow = BUILD_IMAGES_WORKFLOW.read_text()
    assert workflow.count("platforms: linux/amd64,linux/arm64") == 2
    # One paths entry triggers the workflow and two filter entries ensure the
    # base and ETL jobs actually run on the merge commit.
    assert workflow.count("'.github/workflows/build-images.yml'") == 3
