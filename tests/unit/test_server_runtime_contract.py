"""Regression tests for the server container runtime contract."""

import re
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast, pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_COMPOSE = REPO_ROOT / "docker-compose.server.yml"
SERVER_ENV_EXAMPLE = REPO_ROOT / ".env.server.example"
DOCKERFILE = REPO_ROOT / "Dockerfile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SERVER_WORKSPACE = REPO_ROOT / "workspace.server.yaml"
ROOT_PROJECT = REPO_ROOT / "pyproject.toml"
DAGSTER_HEALTHCHECK = REPO_ROOT / "scripts" / "docker" / "healthcheck" / "dagster.sh"
DAEMON_HEALTHCHECK = REPO_ROOT / "scripts" / "docker" / "healthcheck" / "daemon.sh"
ENTRYPOINT = REPO_ROOT / "scripts" / "docker" / "entrypoint.sh"
NSF_DEFENSE_LINEAGE_ASSET = (
    REPO_ROOT
    / "packages"
    / "sbir-analytics"
    / "sbir_analytics"
    / "assets"
    / "nsf_defense_lineage.py"
)


def test_server_ports_are_unconditionally_loopback_only():
    compose = SERVER_COMPOSE.read_text()
    assert "${SERVER_LOOPBACK" not in compose
    assert '"127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474"' in compose
    assert '"127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687"' in compose
    assert '"127.0.0.1:${DAGSTER_PORT:-3000}:3000"' in compose


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
    code_server = compose.split("  dagster-code-server:", 1)[1].split("\n  dagster-webserver:", 1)[
        0
    ]

    assert "host: dagster-code-server" in workspace
    assert "port: 4000" in workspace
    assert re.search(
        r"^COPY --chown=sbir:sbir workspace\.server\.yaml ./workspace\.server\.yaml$",
        DOCKERFILE.read_text(),
        re.MULTILINE,
    )
    assert "\n    ports:" not in code_server
    assert 'expose:\n      - "4000"' in code_server
    assert "grpc-health-check" in code_server


def test_server_code_server_uses_privilege_dropping_entrypoint():
    compose = SERVER_COMPOSE.read_text()
    code_server = compose.split("  dagster-code-server:", 1)[1].split("\n  dagster-webserver:", 1)[
        0
    ]

    assert 'command: ["sh", "/app/scripts/docker/entrypoint.sh", "dagster-code-server"]' in (
        code_server
    )
    assert "ENV_DAGSTER_CMD: dagster api grpc" in code_server


def test_docker_build_rejects_lock_drift_and_caches_dependency_layers():
    dockerfile = DOCKERFILE.read_text()

    assert "uv sync --locked" in dockerfile
    assert "uv sync --frozen" not in dockerfile
    assert "--no-install-project --no-install-workspace" in dockerfile
    assert dockerfile.count("--mount=type=cache,target=/root/.cache/uv") >= 2
    source_copy = "COPY --chown=sbir:sbir sbir_etl/"
    assert dockerfile.index("--no-install-workspace") < dockerfile.index(source_copy)
    assert dockerfile.index("playwright install --with-deps chromium") < dockerfile.index(
        source_copy
    )


def test_runtime_image_provides_non_root_account_and_privilege_drop_tool():
    dockerfile = DOCKERFILE.read_text()

    assert "gosu" in dockerfile
    assert re.search(r"groupadd --system --gid 1001 sbir", dockerfile)
    assert re.search(r"useradd --system --uid 1001 --gid sbir\b", dockerfile)
    assert "COPY --chown=sbir:sbir sbir_etl/" in dockerfile
    assert "chown -R sbir:sbir /app" not in dockerfile


def test_ci_smoke_tests_identity_aware_runtime_ownership_migration():
    workflow = CI_WORKFLOW.read_text()

    assert 'printf "999:999\\n" > /app/reports/.sbir-runtime-owner-v1' in workflow
    assert "sh /app/scripts/docker/entrypoint.sh -- true" in workflow
    assert "cat /app/reports/.sbir-runtime-owner-v1" in workflow
    assert "stat -c %u:%g /app/reports/legacy" in workflow


def test_server_extra_locks_default_spacy_pipeline():
    project = ROOT_PROJECT.read_text()

    assert "en_core_web_sm-3.8.0-py3-none-any.whl" in project


def test_dagster_execution_memory_belongs_to_code_server():
    compose = SERVER_COMPOSE.read_text()
    code_server = compose.split("  dagster-code-server:", 1)[1].split("\n  dagster-webserver:", 1)[
        0
    ]
    daemon = compose.split("  dagster-daemon:", 1)[1].split("\nvolumes:", 1)[0]

    assert "memory: 3G" in code_server
    assert "memory: 768M" in daemon


def test_weekly_awards_report_schedule_gate_reaches_container():
    compose = SERVER_COMPOSE.read_text()
    variable = "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_AWARDS_REPORT_ENABLED"

    assert f"{variable}: ${{{variable}:-false}}" in compose


def test_nsf_defense_lineage_environment_reaches_container():
    compose = SERVER_COMPOSE.read_text()
    env_example = SERVER_ENV_EXAMPLE.read_text()
    asset = NSF_DEFENSE_LINEAGE_ASSET.read_text()
    expected_lineage_defaults = {
        "ANALYSIS_DATE": "",
        "OUTPUT_DIR": "/app/data/processed/nsf_sbir_defense_lineage",
        "SBIR_AWARDS_PATH": "/app/data/raw/sbir/award_data.csv",
        "DIRECT_NSF_SOURCES": "",
        "NSF_MAX_WORKERS": "8",
        "PRIME_API_SNAPSHOTS": "",
        "PRIME_API_PARQUETS": "",
        "FETCH_PRIME_API": "false",
        "PRIME_CONTRACT_ARCHIVES": "",
        "PRIME_ARCHIVE_PARQUETS": "",
        "SUBAWARD_SOURCES": "",
        "MAX_RELEASE_AGE_DAYS": "45",
        "GRAPH_OUTPUT": "/app/artifacts/sbir-dib-network-explorer/data/network.json",
    }
    direct_reads = set(re.findall(r"\{_ENV_PREFIX\}([A-Z][A-Z0-9_]*)", asset))
    helper_reads = set(
        re.findall(r"""_(?:paths|bool)_env\(\s*["']([A-Z][A-Z0-9_]*)["']\s*\)""", asset)
    )

    assert direct_reads | helper_reads == set(expected_lineage_defaults)
    for suffix, default in expected_lineage_defaults.items():
        variable = f"SBIR_ETL__NSF_DEFENSE_LINEAGE__{suffix}"
        assert f"{variable}: ${{{variable}:-{default}}}" in compose
        assert f"\n{variable}={default}\n" in env_example

    schedule_defaults = {
        "SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_NSF_DEFENSE_LINEAGE_REFRESH_ENABLED": "false",
        "SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_NSF_DEFENSE_LINEAGE_REFRESH_CRON": "0 5 8 * *",
    }
    for variable, default in schedule_defaults.items():
        assert f"{variable}: ${{{variable}:-{default}}}" in compose
        assert f"\n{variable}={default}\n" in env_example


def test_server_validate_config_does_not_expand_failure_path(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text("# validation fixture\n")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "server-validate-config",
            f"SERVER_ENV_FILE={env_file}",
            f"SERVER_COMPOSE_FILE={SERVER_COMPOSE}",
            "DOCKER_COMPOSE=true",
            "QUIET=1",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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


def test_entrypoint_prepares_persistent_directories_before_privilege_drop():
    entrypoint = ENTRYPOINT.read_text()
    main = entrypoint.split("main() {", 1)[1]

    assert main.index("prepare_runtime_directories") < main.index(
        'EXEC_PREFIX="$(_make_exec_prefix)"'
    )
    assert "/app/dagster_home" in entrypoint
    assert "chown -R sbir:sbir" in entrypoint
    assert 'owner_identity="$(id -u sbir):$(id -g sbir)"' in entrypoint
    assert 'recorded_identity" != "$owner_identity' in entrypoint
    assert 'printf \'%s\\n\' "$owner_identity" > "$marker"' in entrypoint


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
