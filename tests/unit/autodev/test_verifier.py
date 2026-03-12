"""Tests for the verification pipeline."""

from pathlib import Path


from src.autodev.verifier import CheckReport, CheckResult, VerificationReport, Verifier


class TestCheckReport:
    def test_passed(self):
        report = CheckReport(name="test", result=CheckResult.PASSED)
        assert report.passed is True

    def test_failed(self):
        report = CheckReport(name="test", result=CheckResult.FAILED)
        assert report.passed is False


class TestVerificationReport:
    def test_all_passed(self):
        report = VerificationReport(checks=[
            CheckReport("lint", CheckResult.PASSED),
            CheckReport("test", CheckResult.PASSED),
        ])
        assert report.all_passed is True

    def test_one_failed(self):
        report = VerificationReport(checks=[
            CheckReport("lint", CheckResult.PASSED),
            CheckReport("test", CheckResult.FAILED),
        ])
        assert report.all_passed is False
        assert len(report.failed_checks) == 1

    def test_skipped_counts_as_passed(self):
        report = VerificationReport(checks=[
            CheckReport("lint", CheckResult.PASSED),
            CheckReport("mypy", CheckResult.SKIPPED),
        ])
        assert report.all_passed is True

    def test_summary(self):
        report = VerificationReport(
            checks=[CheckReport("lint", CheckResult.PASSED, duration_seconds=1.5)],
            total_duration_seconds=1.5,
        )
        summary = report.summary
        assert "ALL PASSED" in summary
        assert "lint" in summary


class TestVerifier:
    def test_build_check_list_all(self):
        v = Verifier(Path("/tmp/test"), test_scope="unit")
        checks = v._build_check_list()
        names = [name for name, _cmd in checks]
        assert "ruff-lint" in names
        assert "mypy" in names
        assert "pytest" in names

    def test_build_check_list_no_tests(self):
        v = Verifier(Path("/tmp/test"), run_tests=False)
        checks = v._build_check_list()
        names = [name for name, _cmd in checks]
        assert "pytest" not in names

    def test_build_check_list_no_lint(self):
        v = Verifier(Path("/tmp/test"), run_lint=False)
        checks = v._build_check_list()
        names = [name for name, _cmd in checks]
        assert "ruff-lint" not in names

    def test_test_command_scopes(self):
        for scope in ["unit", "fast", "smoke", "integration", "all"]:
            v = Verifier(Path("/tmp/test"), test_scope=scope)
            cmd = v._test_command()
            assert "pytest" in cmd[-1] or "pytest" in " ".join(cmd)

    def test_changed_files_scoping(self):
        v = Verifier(Path("/tmp/test"))
        checks = v._build_check_list(changed_files=[Path("src/foo.py")])
        lint_cmd = next(cmd for name, cmd in checks if name == "ruff-lint")
        assert "src/foo.py" in " ".join(str(c) for c in lint_cmd)
