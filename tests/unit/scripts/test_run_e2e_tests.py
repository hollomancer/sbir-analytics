"""Regression tests for the local E2E scenario runner."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[3] / "scripts" / "run_e2e_tests.py"
SPEC = importlib.util.spec_from_file_location("run_e2e_tests", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_supported_scenarios_are_distinct_and_hermetic() -> None:
    minimal = MODULE.get_test_config("minimal")
    standard = MODULE.get_test_config("standard")

    assert minimal["test_markers"] == "not slow and not requires_api and not real_data"
    assert standard["test_markers"] == "not requires_api and not real_data"
    assert minimal["test_markers"] != standard["test_markers"]


def test_standard_scenario_uses_current_interpreter_and_branch_coverage(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(MODULE, "_is_pytest_timeout_available", lambda: False)
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert MODULE.run_e2e_tests("standard", 60) == 0

    args = captured["args"]
    assert isinstance(args, list)
    assert args[:3] == [sys.executable, "-m", "pytest"]
    assert "--cov-branch" in args
    marker_index = args.index("-m", 3)
    assert args[marker_index + 1] == "not requires_api and not real_data"
