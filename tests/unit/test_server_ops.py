"""Behavioral tests for Tailscale and server startup helpers."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast, pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
TAILSCALE = REPO_ROOT / "scripts" / "server" / "tailscale-serve.sh"
TAILSCALE_ROUTE_STATE = REPO_ROOT / "scripts" / "server" / "tailscale-route-state.py"
MAKEFILE = REPO_ROOT / "Makefile"


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
    for key in ("DAGSTER_PORT",):
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


def test_tailscale_route_helper_defers_annotations_for_host_python_compatibility():
    source = TAILSCALE_ROUTE_STATE.read_text()

    assert "from __future__ import annotations" in source


def test_server_rebuild_removes_services_retired_from_compose():
    makefile = MAKEFILE.read_text()
    rebuild = makefile.split("server-rebuild:", 1)[1].split(".PHONY: server-up", 1)[0]

    assert "up -d --remove-orphans --wait" in rebuild


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
    hang_443: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], list[list[str]]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_tailscale(bin_dir)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    call_log = tmp_path / "tailscale-calls"
    env_file = tmp_path / ".env.server"
    env_file.write_text("DAGSTER_PORT=3000\n")
    extra = {"CALL_LOG": str(call_log), "STATE_FILE": str(state_file)}
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


def test_tailscale_up_removes_retired_api_route(tmp_path):
    result, state, calls = _run_tailscale(
        tmp_path,
        "up",
        _serve_state("8443", "http://127.0.0.1:8010"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "8443" not in state["TCP"]
    assert "node.test.ts.net:8443" not in state.get("Web", {})
    assert any("--https=8443" in call and "off" in call for call in calls)
    assert "Removed the retired analytics API route" in result.stdout


def test_tailscale_up_preserves_reassigned_8443_route(tmp_path):
    result, state, calls = _run_tailscale(
        tmp_path,
        "up",
        _serve_state("8443", "http://127.0.0.1:9000"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert state["Web"]["node.test.ts.net:8443"]["Handlers"]["/"]["Proxy"] == (
        "http://127.0.0.1:9000"
    )
    assert not any("--https=8443" in call and "off" in call for call in calls)
    assert "port 8443 has another target; leaving it untouched" in result.stdout


def test_tailscale_disabled_consent_times_out_without_mutation(tmp_path):
    result, state, _calls = _run_tailscale(tmp_path, "up", {}, hang_443=True)

    assert result.returncode != 0
    assert state == {}
    assert "consent" in (result.stdout + result.stderr).lower()


def test_tailscale_up_configures_only_dagster_route(tmp_path):
    result, state, calls = _run_tailscale(tmp_path, "up", {})

    assert result.returncode == 0, result.stdout + result.stderr
    assert set(state["TCP"]) == {"443"}
    assert state["Web"]["node.test.ts.net:443"]["Handlers"]["/"]["Proxy"] == (
        "http://127.0.0.1:3000"
    )
    assert any("--https=443" in call and "--bg" in call for call in calls)
    assert all(not any(arg.startswith("--tls-terminated-tcp=") for arg in call) for call in calls)
    assert "Dagster: https://node.test.ts.net/" in result.stdout


def test_server_up_runs_preflight_before_locked_image_build(tmp_path):
    result = subprocess.run(
        ["make", "-n", "server-up", f"SERVER_ENV_FILE={tmp_path / '.env.server'}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout
    assert output.index("check-prerequisites.sh") < output.index("--profile server up -d --build")
    assert "Dockerfile.python-base" not in output
    assert "--wait --wait-timeout 300" in output
