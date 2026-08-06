"""End-to-end render of the weekly awards report from fixture awards.

Hermetic full-document pass over models -> rendering (the unit tests cover the
small helpers piecemeal). Asserts the output contract a reader relies on: the
non-citable banner, the period header, summary and per-award sections, and the
reference links — on populated, escaped, and empty inputs alike.
"""

from __future__ import annotations

import pytest

from sbir_etl.reporting.weekly.rendering import generate_markdown


pytestmark = [pytest.mark.e2e, pytest.mark.timeout(60)]

AGENCIES = ["DOD", "HHS", "NSF", "DOE"]


def _award(i: int) -> dict:
    return {
        "Company": f"Fixture Co {i}",
        "Award Title": f"Adaptive Widget Study {i}",
        "Agency": AGENCIES[i % len(AGENCIES)],
        "Phase": "I" if i % 2 == 0 else "II",
        "Program": "SBIR",
        "Award Amount": str(150000 + i * 10000),
        "Proposal Award Date": f"2026-07-{(i % 28) + 1:02d}",
        "State": "CA",
        "PI Name": f"Casey Researcher {i}",
        "Topic Code": f"T{i:02d}",
        "Solicitation Number": f"SOL-26-{i:03d}",
        "Contract": f"W91{i:04d}",
    }


@pytest.fixture(scope="module")
def awards() -> list[dict]:
    return [_award(i) for i in range(24)]


def test_full_document_contract(awards):
    md = generate_markdown(awards, days=7)

    # Header and the label that must never fall off an exploratory artifact.
    assert md.startswith("# SBIR Weekly Awards Report")
    assert "**Exploratory / non-citable.**" in md
    assert f"**Total new awards:** {len(awards)}" in md

    # Summary and grouping sections.
    assert "## Summary" in md
    assert "## By Agency" in md
    assert "## By Program & Phase" in md
    for agency in AGENCIES:
        assert f"| {agency} |" in md

    # Every award appears with its company and reference links.
    assert "## Awards" in md
    for award in awards:
        assert award["Company"] in md
        assert f"https://www.sbir.gov/awards?keyword={award['Contract']}" in md
    assert md.count("**References:**") == len(awards)
    assert "https://www.usaspending.gov/search" in md


def test_pipe_in_title_keeps_tables_intact(awards):
    hostile = dict(awards[0])
    hostile["Award Title"] = "Adaptive | Widget || Study"
    hostile["Company"] = "Pipe | Co"

    md = generate_markdown([hostile], days=7)

    # Summary table rows must keep their column count; the escaped company
    # renders without introducing new cell separators.
    summary_start = md.index("## Summary")
    summary_block = md[summary_start : md.index("## By Agency")]
    for line in summary_block.splitlines():
        if line.startswith("|") and "Metric" not in line and "---" not in line:
            assert line.count("|") == 3, f"unexpected cell split: {line!r}"
    assert "Pipe" in md and "Widget" in md


def test_empty_awards_keeps_banner():
    md = generate_markdown([], days=7)

    assert "**Exploratory / non-citable.**" in md
    assert "**Total new awards:** 0" in md
    assert "No new awards found for this period." in md


def test_freshness_warnings_rendered(awards):
    md = generate_markdown(
        awards[:3],
        days=7,
        freshness_warnings=["SBIR.gov bulk file is 12 days old"],
    )

    assert "**Data Freshness Warning**" in md
    assert "SBIR.gov bulk file is 12 days old" in md
