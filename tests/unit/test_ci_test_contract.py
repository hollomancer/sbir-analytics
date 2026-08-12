"""Static contracts for the repository's CI test lanes."""

from __future__ import annotations

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"


def _workflow() -> dict:
    return yaml.load(CI_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_ci_has_a_weekly_full_suite_schedule() -> None:
    schedule = _workflow()["on"]["schedule"]

    assert schedule
    assert len(schedule[0]["cron"].split()) == 5


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
