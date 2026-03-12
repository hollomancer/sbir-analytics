"""Verification pipeline for autonomous development.

Runs the project's quality gates (pytest, ruff, mypy) and reports
pass/fail with structured results. Used by the orchestrator to
decide whether to keep or discard a change.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class CheckResult(StrEnum):
    """Result of a single verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class CheckReport:
    """Report from a single verification check."""

    name: str
    result: CheckResult
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0

    @property
    def passed(self) -> bool:
        return self.result == CheckResult.PASSED


@dataclass
class VerificationReport:
    """Aggregate report from all verification checks."""

    checks: list[CheckReport] = field(default_factory=list)
    total_duration_seconds: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all(c.passed or c.result == CheckResult.SKIPPED for c in self.checks)

    @property
    def failed_checks(self) -> list[CheckReport]:
        return [c for c in self.checks if c.result == CheckResult.FAILED]

    @property
    def summary(self) -> str:
        parts = []
        for check in self.checks:
            icon = "pass" if check.passed else "FAIL"
            parts.append(f"[{icon}] {check.name} ({check.duration_seconds:.1f}s)")
        status = "ALL PASSED" if self.all_passed else "FAILURES DETECTED"
        return f"{status} ({self.total_duration_seconds:.1f}s total)\n" + "\n".join(parts)


def _run_check(
    name: str,
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int = 300,
) -> CheckReport:
    """Run a single verification command and capture results."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.monotonic() - start
        result = CheckResult.PASSED if proc.returncode == 0 else CheckResult.FAILED
        return CheckReport(
            name=name,
            result=result,
            duration_seconds=duration,
            stdout=proc.stdout[-5000:] if len(proc.stdout) > 5000 else proc.stdout,
            stderr=proc.stderr[-2000:] if len(proc.stderr) > 2000 else proc.stderr,
            return_code=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return CheckReport(
            name=name,
            result=CheckResult.ERROR,
            duration_seconds=duration,
            stderr=f"Timed out after {timeout_seconds}s",
            return_code=-1,
        )
    except FileNotFoundError as e:
        return CheckReport(
            name=name,
            result=CheckResult.ERROR,
            duration_seconds=0.0,
            stderr=f"Command not found: {e}",
            return_code=-1,
        )


class Verifier:
    """Runs the project's verification pipeline.

    Executes checks in order of speed: fast lint first, then type checking,
    then tests. Supports early exit on first failure for faster feedback.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        run_tests: bool = True,
        run_lint: bool = True,
        run_typecheck: bool = True,
        test_scope: str = "unit",
        fail_fast: bool = True,
        test_timeout: int = 300,
    ):
        self.project_root = project_root
        self.run_tests = run_tests
        self.run_lint = run_lint
        self.run_typecheck = run_typecheck
        self.test_scope = test_scope
        self.fail_fast = fail_fast
        self.test_timeout = test_timeout

    def verify(self, changed_files: list[Path] | None = None) -> VerificationReport:
        """Run all configured verification checks.

        Args:
            changed_files: If provided, scope checks to these files where possible.

        Returns:
            VerificationReport with results from all checks.
        """
        report = VerificationReport()
        start = time.monotonic()

        checks = self._build_check_list(changed_files)

        for name, cmd in checks:
            check_report = _run_check(name, cmd, self.project_root, self.test_timeout)
            report.checks.append(check_report)

            if self.fail_fast and not check_report.passed:
                break

        report.total_duration_seconds = time.monotonic() - start
        return report

    def _build_check_list(
        self, changed_files: list[Path] | None = None
    ) -> list[tuple[str, list[str]]]:
        """Build ordered list of (name, command) checks to run."""
        checks: list[tuple[str, list[str]]] = []

        if self.run_lint:
            lint_cmd = ["uv", "run", "ruff", "check", "src/", "tests/"]
            if changed_files:
                py_files = [str(f) for f in changed_files if f.suffix == ".py"]
                if py_files:
                    lint_cmd = ["uv", "run", "ruff", "check"] + py_files
            checks.append(("ruff-lint", lint_cmd))
            checks.append(("ruff-format", ["uv", "run", "ruff", "format", "--check", "src/", "tests/"]))

        if self.run_typecheck:
            mypy_cmd = ["uv", "run", "mypy", "src/"]
            checks.append(("mypy", mypy_cmd))

        if self.run_tests:
            test_cmd = self._test_command()
            checks.append(("pytest", test_cmd))

        return checks

    def _test_command(self) -> list[str]:
        """Build the pytest command based on test scope."""
        cmd = ["uv", "run", "pytest"]

        if self.test_scope == "unit":
            cmd.extend(["tests/unit/", "-x", "-q", "--no-header", "-m", "not slow"])
        elif self.test_scope == "fast":
            cmd.extend(["tests/unit/", "-x", "-q", "--no-header", "-m", "fast"])
        elif self.test_scope == "smoke":
            cmd.extend(["tests/", "-x", "-q", "--no-header", "-m", "smoke"])
        elif self.test_scope == "integration":
            cmd.extend(["tests/integration/", "-x", "-q", "--no-header"])
        elif self.test_scope == "all":
            cmd.extend(["tests/", "-x", "-q", "--no-header"])
        else:
            # Default to unit
            cmd.extend(["tests/unit/", "-x", "-q", "--no-header"])

        return cmd
