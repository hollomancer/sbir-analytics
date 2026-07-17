"""Tests for scripts/server/check-prerequisites.sh (--bindings-only mode).

The --bindings-only mode validates loopback bindings and required secrets
without needing Docker or Tailscale, so it can be exercised in CI.
"""

import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "server" / "check-prerequisites.sh"

pytestmark = [pytest.mark.fast, pytest.mark.unit]

GOOD_ENV = """
SERVER_LOOPBACK=127.0.0.1
NEO4J_PASSWORD=a-real-password
SBIR_ANALYTICS_API_TOKEN=deadbeefcafe1234
""".lstrip()


def _run(env_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(SCRIPT), "--bindings-only"],
        env={"SERVER_ENV_FILE": str(env_file), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


def test_script_exists_and_executable():
    assert SCRIPT.is_file()


def test_passes_with_good_env(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text(GOOD_ENV)
    result = _run(env_file)
    assert result.returncode == 0, result.stdout + result.stderr


def test_rejects_non_loopback_binding(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text(GOOD_ENV.replace("127.0.0.1", "0.0.0.0"))
    result = _run(env_file)
    assert result.returncode == 1
    assert "loopback" in (result.stdout + result.stderr).lower()


def test_rejects_placeholder_neo4j_password(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text(
        GOOD_ENV.replace("NEO4J_PASSWORD=a-real-password", "NEO4J_PASSWORD=change_me")
    )
    result = _run(env_file)
    assert result.returncode == 1


def test_rejects_missing_api_token(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text("SERVER_LOOPBACK=127.0.0.1\nNEO4J_PASSWORD=a-real-password\n")
    result = _run(env_file)
    assert result.returncode == 1


def test_env_file_is_parsed_as_data_not_executed(tmp_path):
    marker = tmp_path / "executed"
    env_file = tmp_path / ".env.server"
    env_file.write_text(
        GOOD_ENV
        + f"DAGSTER_PORT=$(touch {marker})\n"
        + "SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_JOB=15 3 * * *\n"
    )

    result = _run(env_file)

    assert result.returncode != 0
    assert not marker.exists()


def test_rejects_duplicate_allowlisted_key(tmp_path):
    env_file = tmp_path / ".env.server"
    env_file.write_text(GOOD_ENV + "NEO4J_PASSWORD=change_me\n")

    result = _run(env_file)

    assert result.returncode != 0
    assert "defined more than once" in (result.stdout + result.stderr)
