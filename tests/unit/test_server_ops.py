"""Behavioral tests for server backup, Tailscale, and startup helpers."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast, pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "server" / "backup.sh"
TAILSCALE = REPO_ROOT / "scripts" / "server" / "tailscale-serve.sh"


def _executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
    path.chmod(0o755)


def _run_script(
    script: Path,
    *args: str,
    env_file: Path,
    bin_dir: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in (
        "SERVER_BACKUP_DIR",
        "DAGSTER_PORT",
        "SBIR_ANALYTICS_API_PORT",
        "NEO4J_DATABASE",
    ):
        env.pop(key, None)
    env.update(
        {
            "PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin",
            "SERVER_ENV_FILE": str(env_file),
        }
    )
    env.update(extra_env or {})
    return subprocess.run(
        ["/bin/sh", str(script), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _calls(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _install_fake_docker(bin_dir: Path) -> None:
    _executable(
        bin_dir / "docker",
        r"""
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        with Path(os.environ["CALL_LOG"]).open("a") as stream:
            stream.write(json.dumps(args) + "\n")

        if "ps" in args:
            print("fake-neo4j-id")
        if "stop" in args and os.environ.get("FAIL_STOP") == "1":
            raise SystemExit(7)
        if "run" in args and "database" in args and "dump" in args:
            if os.environ.get("FAIL_DUMP") == "1":
                raise SystemExit(9)
            mount = args[args.index("-v") + 1]
            host_dir = Path(mount.rsplit(":/backup", 1)[0])
            database = args[args.index("dump") + 1]
            (host_dir / f"{database}.dump").write_bytes(b"valid dump")
        """,
    )


def _call_index(calls: list[list[str]], *tokens: str) -> int:
    return next(index for index, call in enumerate(calls) if all(token in call for token in tokens))


def test_backup_honors_env_directory_and_runs_offline(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_docker(bin_dir)
    call_log = tmp_path / "docker-calls"
    backup_dir = tmp_path / "backup folder"
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"SERVER_BACKUP_DIR={backup_dir}\n")

    result = _run_script(
        BACKUP,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env={"BACKUP_STAMP": "unit", "CALL_LOG": str(call_log)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (backup_dir / "neo4j-unit.dump").read_bytes() == b"valid dump"
    assert (backup_dir / "neo4j-unit.dump").stat().st_mode & 0o777 == 0o600
    calls = _calls(call_log)
    assert _call_index(calls, "stop", "neo4j") < _call_index(calls, "database", "dump")
    assert _call_index(calls, "database", "dump") < _call_index(calls, "up", "neo4j")


def test_backup_failure_restarts_neo4j(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_docker(bin_dir)
    call_log = tmp_path / "docker-calls"
    backup_dir = tmp_path / "backups"
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"SERVER_BACKUP_DIR={backup_dir}\n")

    result = _run_script(
        BACKUP,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env={
            "BACKUP_STAMP": "unit",
            "CALL_LOG": str(call_log),
            "FAIL_DUMP": "1",
        },
    )

    assert result.returncode != 0
    calls = _calls(call_log)
    assert _call_index(calls, "database", "dump") < _call_index(calls, "up", "neo4j")


def test_backup_failed_stop_still_attempts_neo4j_recovery(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_docker(bin_dir)
    call_log = tmp_path / "docker-calls"
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"SERVER_BACKUP_DIR={tmp_path / 'backups'}\n")

    result = _run_script(
        BACKUP,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env={
            "BACKUP_STAMP": "unit",
            "CALL_LOG": str(call_log),
            "FAIL_STOP": "1",
        },
    )

    assert result.returncode != 0
    calls = _calls(call_log)
    assert _call_index(calls, "stop", "neo4j") < _call_index(calls, "up", "neo4j")


def test_backup_refuses_concurrent_operation(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_docker(bin_dir)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / ".neo4j-backup.lock").mkdir()
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"SERVER_BACKUP_DIR={backup_dir}\n")

    result = _run_script(
        BACKUP,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env={"BACKUP_STAMP": "unit", "CALL_LOG": str(tmp_path / "calls")},
    )

    assert result.returncode != 0
    assert "lock" in (result.stdout + result.stderr).lower()


def test_backup_refuses_missing_external_volume(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_docker(bin_dir)
    missing = f"/Volumes/sbir-test-not-mounted-{os.getpid()}/backups"
    env_file = tmp_path / ".env.server"
    env_file.write_text(f"SERVER_BACKUP_DIR={missing}\n")

    result = _run_script(
        BACKUP,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env={"BACKUP_STAMP": "unit", "CALL_LOG": str(tmp_path / "calls")},
    )

    assert result.returncode != 0
    assert "actively mounted" in (result.stdout + result.stderr)


def _install_fake_tailscale(bin_dir: Path) -> None:
    _executable(
        bin_dir / "tailscale",
        r"""
        import json
        import os
        from pathlib import Path
        import sys
        import time

        args = sys.argv[1:]
        state_path = Path(os.environ["STATE_FILE"])
        with Path(os.environ["CALL_LOG"]).open("a") as stream:
            stream.write(json.dumps(args) + "\n")

        if args == ["status"]:
            raise SystemExit(0)
        if args == ["status", "--json"]:
            print(json.dumps({"Self": {"DNSName": "node.test.ts.net."}}))
            raise SystemExit(0)
        if args[:2] == ["serve", "status"]:
            print(state_path.read_text())
            raise SystemExit(0)

        port_arg = next(item for item in args if item.startswith("--https="))
        port = port_arg.split("=", 1)[1]
        if port == "443" and os.environ.get("HANG_443") == "1" and "off" not in args:
            print("Serve is not enabled on your tailnet: https://example.test/consent", flush=True)
            time.sleep(60)
        if port == "8443" and os.environ.get("FAIL_8443") == "1" and "off" not in args:
            print("forced failure", file=sys.stderr)
            raise SystemExit(8)

        state = json.loads(state_path.read_text())
        host_key = f"node.test.ts.net:{port}"
        if "off" in args:
            state.get("TCP", {}).pop(port, None)
            state.get("Web", {}).pop(host_key, None)
            state.get("AllowFunnel", {}).pop(host_key, None)
        else:
            target = args[-1]
            state.setdefault("TCP", {})[port] = {"HTTPS": True}
            state.setdefault("Web", {})[host_key] = {
                "Handlers": {"/": {"Proxy": target}}
            }
        state_path.write_text(json.dumps(state))
        if (
            port == "8443"
            and os.environ.get("APPLY_THEN_FAIL_8443") == "1"
            and "off" not in args
        ):
            print("forced late failure", file=sys.stderr)
            raise SystemExit(8)
        """,
    )


def _serve_state(port: str, target: str) -> dict[str, object]:
    host_key = f"node.test.ts.net:{port}"
    return {
        "TCP": {port: {"HTTPS": True}},
        "Web": {host_key: {"Handlers": {"/": {"Proxy": target}}}},
    }


def _run_tailscale(
    tmp_path: Path,
    command: str,
    state: dict[str, object],
    *,
    fail_8443: bool = False,
    apply_then_fail_8443: bool = False,
    hang_443: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], list[list[str]]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_tailscale(bin_dir)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    call_log = tmp_path / "tailscale-calls"
    env_file = tmp_path / ".env.server"
    env_file.write_text("DAGSTER_PORT=3000\nSBIR_ANALYTICS_API_PORT=8010\n")
    extra = {"CALL_LOG": str(call_log), "STATE_FILE": str(state_file)}
    if fail_8443:
        extra["FAIL_8443"] = "1"
    if apply_then_fail_8443:
        extra["APPLY_THEN_FAIL_8443"] = "1"
    if hang_443:
        extra["HANG_443"] = "1"
        extra["TAILSCALE_SERVE_TIMEOUT"] = "1"
    result = _run_script(
        TAILSCALE,
        command,
        env_file=env_file,
        bin_dir=bin_dir,
        extra_env=extra,
    )
    return result, json.loads(state_file.read_text()), _calls(call_log)


def test_tailscale_down_removes_only_owned_route(tmp_path):
    result, state, calls = _run_tailscale(
        tmp_path,
        "down",
        _serve_state("443", "http://127.0.0.1:3000"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert state.get("TCP", {}) == {}
    assert any("--https=443" in call and "off" in call for call in calls)


def test_tailscale_down_refuses_foreign_route(tmp_path):
    original = _serve_state("443", "http://127.0.0.1:9999")
    result, state, calls = _run_tailscale(tmp_path, "down", original)

    assert result.returncode != 0
    assert state == original
    assert not any("off" in call for call in calls)


def test_tailscale_down_refuses_funnel_enabled_route(tmp_path):
    original = _serve_state("443", "http://127.0.0.1:3000")
    original["AllowFunnel"] = {"node.test.ts.net:443": True}

    result, state, calls = _run_tailscale(tmp_path, "down", original)

    assert result.returncode != 0
    assert state == original
    assert not any("off" in call for call in calls)


def test_tailscale_up_rolls_back_new_route_if_second_fails(tmp_path):
    result, state, calls = _run_tailscale(tmp_path, "up", {}, fail_8443=True)

    assert result.returncode != 0
    assert state.get("TCP", {}) == {}
    configure_443 = _call_index(calls, "serve", "--yes", "--https=443")
    configure_8443 = _call_index(calls, "serve", "--yes", "--https=8443")
    remove_443 = next(
        index for index, call in enumerate(calls) if "--https=443" in call and "off" in call
    )
    assert configure_443 < configure_8443 < remove_443


def test_tailscale_disabled_consent_times_out_without_mutation(tmp_path):
    result, state, _calls = _run_tailscale(tmp_path, "up", {}, hang_443=True)

    assert result.returncode != 0
    assert state == {}
    assert "consent" in (result.stdout + result.stderr).lower()


def test_tailscale_up_rolls_back_route_applied_before_cli_failure(tmp_path):
    result, state, calls = _run_tailscale(
        tmp_path,
        "up",
        {},
        apply_then_fail_8443=True,
    )

    assert result.returncode != 0
    assert state.get("TCP", {}) == {}
    assert any("--https=8443" in call and "off" in call for call in calls)
    assert any("--https=443" in call and "off" in call for call in calls)


def test_server_up_runs_preflight_and_native_base_fallback_first(tmp_path):
    result = subprocess.run(
        ["make", "-n", "server-up", f"SERVER_ENV_FILE={tmp_path / '.env.server'}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout
    assert output.index("check-prerequisites.sh") < output.index("docker pull")
    assert output.index("docker pull") < output.index("Dockerfile.python-base")
    assert output.index("Dockerfile.python-base") < output.index("--profile server up -d --build")
    assert "--wait --wait-timeout 300" in output
