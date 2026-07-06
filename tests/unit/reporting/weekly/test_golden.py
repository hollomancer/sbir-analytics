"""Golden-file test for the weekly awards report (spec: weekly-awards-report-refactor T0).

Runs the report pipeline end-to-end against a small fixture CSV with all
network calls stubbed, then diffs the normalized markdown against
``tests/fixtures/weekly_awards_report/golden.md``. This test pins the
report's exact output through the monolith→library extraction: it must
stay green after every stage of the refactor.

Regenerate the golden file (after an INTENTIONAL output change) with:
    UPDATE_GOLDEN=1 uv run pytest tests/unit/reporting/weekly/test_golden.py -n 0
"""

import importlib.util
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "weekly_awards_report.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "weekly_awards_report"
TEMPLATE_CSV = FIXTURE_DIR / "awards_template.csv"
GOLDEN_MD = FIXTURE_DIR / "golden.md"


def _load_script():
    spec = importlib.util.spec_from_file_location("weekly_awards_report", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def injected_dates() -> list:
    """Three distinct award dates inside the 7-day window, newest first."""
    now = datetime.now(UTC)
    return [(now - timedelta(days=n)).date() for n in (1, 2, 3)]


@pytest.fixture
def fixture_csv(tmp_path, injected_dates) -> Path:
    """Materialize the template CSV with runtime dates inside the window."""
    text = TEMPLATE_CSV.read_text()
    for n, d in enumerate(injected_dates, 1):
        text = text.replace(f"{{{{AWARD_DATE_{n}}}}}", d.isoformat())
    end_date = (injected_dates[0] + timedelta(days=365)).isoformat()
    text = text.replace("{{END_DATE}}", end_date)
    text = text.replace("{{AWARD_YEAR}}", str(injected_dates[0].year))
    csv_path = tmp_path / "award_data.csv"
    csv_path.write_text(text)
    return csv_path


def _normalize(report: str, injected_dates, fixture_csv) -> str:
    """Replace run-dependent strings (dates, timestamps) with sentinels."""
    report = re.sub(r"\*\*Period:\*\* .+? - .+?$", "**Period:** <PERIOD>", report, flags=re.M)
    report = re.sub(
        r"Generated on \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC",
        "Generated on <TIMESTAMP>",
        report,
    )
    for n, d in enumerate(injected_dates, 1):
        report = report.replace(d.isoformat(), f"<AWARD_DATE_{n}>")
    end_date = (injected_dates[0] + timedelta(days=365)).isoformat()
    report = report.replace(end_date, "<END_DATE>")
    report = report.replace(str(fixture_csv), "<CSV_PATH>")
    return report


def test_weekly_report_matches_golden(monkeypatch, tmp_path, fixture_csv, injected_dates):
    from sbir_etl.reporting.weekly import enrichment, fetching

    mod = _load_script()

    # Hermetic data source: fixture CSV, no S3/download.
    monkeypatch.setattr(
        fetching,
        "_resolve_csv_path",
        lambda: fetching.DataSource(path=fixture_csv, origin="local"),
    )
    # Stub every network-touching stage-1 fetch (their absence is a supported
    # degraded mode — the report renders without those sections).
    monkeypatch.setattr(enrichment, "fetch_usaspending_contract_descriptions", lambda awards: {})
    monkeypatch.setattr(enrichment, "lookup_usaspending_recipients", lambda awards: {})
    monkeypatch.setattr(enrichment, "lookup_sam_entities", lambda awards: {})
    monkeypatch.setattr(enrichment, "lookup_opencorporates", lambda awards: {})
    monkeypatch.setattr(enrichment, "poll_press_wire", lambda awards: {})
    # Inflation enrichment can consult the BEA API depending on env; stub for
    # determinism (covered by its own unit tests).
    monkeypatch.setattr(enrichment, "enrich_with_inflation", lambda awards, base_year=None: {})

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out_path = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weekly_awards_report.py",
            "--days",
            "7",
            "--output",
            str(out_path),
            "--no-ai",
            "--skip-sbir-api",
        ],
    )

    mod.main()

    actual = _normalize(out_path.read_text(), injected_dates, fixture_csv)

    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_MD.write_text(actual)
        pytest.skip("golden.md regenerated; rerun without UPDATE_GOLDEN")

    assert GOLDEN_MD.exists(), "golden.md missing — generate it with UPDATE_GOLDEN=1 pytest ..."
    assert actual == GOLDEN_MD.read_text()
