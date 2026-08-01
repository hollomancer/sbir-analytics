"""Regression tests for the server container runtime contract."""

import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast, pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_COMPOSE = REPO_ROOT / "docker-compose.server.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
SERVER_WORKSPACE = REPO_ROOT / "workspace.server.yaml"
DAGSTER_HEALTHCHECK = REPO_ROOT / "scripts" / "docker" / "healthcheck" / "dagster.sh"
DAEMON_HEALTHCHECK = REPO_ROOT / "scripts" / "docker" / "healthcheck" / "daemon.sh"
ENTRYPOINT = REPO_ROOT / "scripts" / "docker" / "entrypoint.sh"


def test_server_ports_are_unconditionally_loopback_only():
    compose = SERVER_COMPOSE.read_text()
    assert "${SERVER_LOOPBACK" not in compose
    assert '"127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474"' in compose
    assert '"127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687"' in compose
    assert '"127.0.0.1:${DAGSTER_PORT:-3000}:3000"' in compose
    assert '"127.0.0.1:${SBIR_ANALYTICS_API_PORT:-8010}' in compose


def test_neo4j_runtime_uses_valid_plugin_and_neutral_health_variables():
    compose = SERVER_COMPOSE.read_text()
    assert "'NEO4J_PLUGINS=${NEO4J_PLUGINS:-[\"apoc\"]}'" in compose
    assert "SBIR_SERVER_NEO4J_USER=${NEO4J_USER:-neo4j}" in compose
    assert "SBIR_SERVER_NEO4J_PASSWORD=${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}" in compose
    assert "$${NEO4J_PASSWORD}" not in compose


def test_dagster_daemon_waits_on_webserver_container():
    compose = SERVER_COMPOSE.read_text()
    daemon = compose.split("  dagster-daemon:", 1)[1].split("\nvolumes:", 1)[0]
    assert "DAGSTER_HOST: dagster-webserver" in daemon
    assert "HEALTHCHECK_PORT: 3000" in daemon
    assert "dagster-daemon run -w /app/workspace.server.yaml" in daemon


def test_dagster_uses_shared_internal_code_server():
    compose = SERVER_COMPOSE.read_text()
    workspace = SERVER_WORKSPACE.read_text()
    code_server = compose.split("  dagster-code-server:", 1)[1].split("\n  analytics-api:", 1)[0]

    assert "host: dagster-code-server" in workspace
    assert "port: 4000" in workspace
    assert "COPY workspace.server.yaml /app/workspace.server.yaml" in DOCKERFILE.read_text()
    assert "\n    ports:" not in code_server
    assert 'expose:\n      - "4000"' in code_server
    assert "grpc-health-check" in code_server


def test_dagster_execution_memory_belongs_to_code_server():
    compose = SERVER_COMPOSE.read_text()
    code_server = compose.split("  dagster-code-server:", 1)[1].split("\n  analytics-api:", 1)[0]
    daemon = compose.split("  dagster-daemon:", 1)[1].split("\nvolumes:", 1)[0]

    assert "memory: 3G" in code_server
    assert "memory: 768M" in daemon


def test_dagster_healthcheck_preserves_path_and_calls_configured_url(tmp_path):
    calls = tmp_path / "curl-calls"
    fake_curl = tmp_path / "curl"
    fake_curl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$CURL_CALLS"\n')
    fake_curl.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", str(DAGSTER_HEALTHCHECK)],
        env={
            "PATH": str(tmp_path),
            "CURL_CALLS": str(calls),
            "HEALTHCHECK_HOST": "dagster.test",
            "HEALTHCHECK_PORT": "4321",
            "HEALTHCHECK_PATH": "/ready",
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "http://dagster.test:4321/ready" in calls.read_text()


def test_entrypoint_has_python_tcp_probe_fallback():
    entrypoint = ENTRYPOINT.read_text()
    neo4j_wait = entrypoint.split("wait_for_neo4j()", 1)[1].split("wait_for_dagster_web()", 1)[0]
    assert "socket.create_connection" in entrypoint
    assert 'probe_tcp "$HOST" "$PORT"' in neo4j_wait
    assert "WAIT_SCRIPT=" not in neo4j_wait


def test_entrypoint_only_drops_privileges_when_sbir_user_exists():
    entrypoint = ENTRYPOINT.read_text()
    prefix_function = entrypoint.split("_make_exec_prefix()", 1)[1].split("probe_tcp()", 1)[0]
    assert "id sbir" in prefix_function
    assert "continuing as root" in prefix_function


def test_daemon_healthcheck_uses_heartbeat_liveness_without_procps(tmp_path):
    calls = tmp_path / "daemon-calls"
    fake_daemon = tmp_path / "dagster-daemon"
    fake_daemon.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > "{calls}"\n')
    fake_daemon.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", str(DAEMON_HEALTHCHECK)],
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text().strip() == "liveness-check"
