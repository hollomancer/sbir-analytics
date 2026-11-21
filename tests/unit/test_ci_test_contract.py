"""Static contracts for the repository's CI test lanes."""

from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"


def _workflow() -> dict:
    return yaml.load(CI_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_ci_has_a_weekly_full_suite_schedule() -> None:
    workflow = _workflow()

    assert workflow["on"]["schedule"] == [{"cron": "17 8 * * 6"}]


def test_full_suite_and_coverage_gate_run_on_pull_requests() -> None:
    job = _workflow()["jobs"]["test-full"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run full test suite")

    assert "if" not in job
    assert "--cov-fail-under=70" in run_step["run"]


def test_full_suite_checks_python_312_after_merge_only() -> None:
    job = _workflow()["jobs"]["test-full"]

    assert job["strategy"]["matrix"]["python-version"] == (
        "${{ fromJSON(github.event_name == 'pull_request' && '[\"3.11\"]' "
        '|| \'["3.11", "3.12"]\') }}'
    )
    assert job["env"]["UV_PYTHON"] == "${{ matrix.python-version }}"


def test_only_pull_request_runs_cancel_each_other() -> None:
    concurrency = _workflow()["concurrency"]

    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    assert "github.run_id" in concurrency["group"]


def test_duration_refresh_workflow_cannot_push() -> None:
    workflow = yaml.load(
        (REPOSITORY_ROOT / ".github/workflows/test-durations.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request" not in workflow["on"]


def test_study_validation_jobs_fetch_release_history() -> None:
    """Jobs that validate released studies must have their source tags."""
    workflow = _workflow()

    for job_name in ("quality", "test-fast", "test-full", "jev-preflight"):
        checkout = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if step.get("uses") == "actions/checkout@v7"
        )
        assert checkout["with"]["fetch-depth"] == "0", job_name


def test_literature_map_refresh_is_manual_only() -> None:
    workflow = yaml.load(
        (REPOSITORY_ROOT / ".github/workflows/literature-map.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["permissions"]["pull-requests"] == "write"
    run_step = next(
        step
        for step in workflow["jobs"]["refresh"]["steps"]
        if step.get("name") == "Refresh the map"
    )
    assert run_step["run"] == "uv run python scripts/data/update_literature_map.py"


def test_pull_requests_run_the_hermetic_e2e_selection() -> None:
    job = _workflow()["jobs"]["test-e2e"]
    run_step = next(step for step in job["steps"] if step.get("name") == "Run hermetic E2E tests")

    assert job["if"] == "github.event_name == 'pull_request'"
    assert run_step["run"] == ('uv run pytest tests/e2e/ -m "not requires_api and not real_data"')


def test_slow_suite_uses_markers_instead_of_environment_skips() -> None:
    violations = []
    for path in sorted((REPOSITORY_ROOT / "tests/slow").rglob("test_*.py")):
        if "PYTEST_ALLOW_SLOW" in path.read_text(encoding="utf-8"):
            violations.append(path.relative_to(REPOSITORY_ROOT).as_posix())

    assert not violations, "Slow tests hidden behind PYTEST_ALLOW_SLOW:\n" + "\n".join(violations)
