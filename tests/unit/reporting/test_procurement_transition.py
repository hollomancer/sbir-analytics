import json
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.procurement_transition import MonthlyReportBuilder, build_award_cohorts


def _awards(end_date="2026-08-15") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Agency Tracking Number": "A-1",
                "Company": "Drone Co",
                "Award Title": "Autonomous navigation",
                "Agency": "DEFENSE",
                "Branch": "NAVY",
                "Phase": "Phase II",
                "Program": "SBIR",
                "Proposal Award Date": "2026-06-12",
                "Contract End Date": end_date,
                "UEI": "UEI000000001",
                "Award Amount": "$1,000,000",
                "Abstract": "Navigation software that fuses onboard sensors for autonomous flight.",
                "source_url": "https://www.sbir.gov/award/A-1",
            }
        ]
    )


def test_monthly_cohorts_use_calendar_month_and_recorded_end():
    rows = build_award_cohorts(_awards(), pd.DataFrame(), report_month="2026-06")
    assert rows.iloc[0]["newly_observed"]
    assert rows.iloc[0]["awarded_in_period"]
    assert rows.iloc[0]["approaching_recorded_end"]


def test_writes_center_packet_and_manifest(tmp_path):
    cohorts = build_award_cohorts(_awards(), pd.DataFrame(), report_month="2026-06")
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "C-1",
                "signal_class": "directed",
                "prior_award_id": "A-1",
                "target_id": "O-1",
                "candidate_score": 0.8,
                "is_high_confidence": True,
            }
        ]
    )
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Navigation procurement",
                "office": "NAVAIR",
                "office_code": "NAVAIR",
                "response_deadline": "2026-08-01",
                "description": "Integrate autonomous navigation into an unmanned aircraft prototype.",
                "source_url": "https://sam.gov/opp/O-1",
            }
        ]
    )
    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts, candidates=candidates, opportunities=opportunities
    )
    assert (output / "centers" / "navair.md").exists()
    packet = (output / "centers" / "navair.md").read_text()
    assert "# Monthly Procurement Transition Packet — NAVAIR" in packet
    assert "## How to read this packet" in packet
    assert "derives from, extends, or completes" in packet
    assert "Potential directed Phase III path" in packet
    assert "#### What the award funded" in packet
    assert "Navigation software that fuses onboard sensors" in packet
    assert "#### What the solicitation asks for" in packet
    assert "Integrate autonomous navigation" in packet
    assert "#### Technical connection to validate" in packet
    assert "What the public records show:" in packet
    assert "share technical terms: autonomous, navigation" in packet
    assert "[SBIR/STTR award record](https://www.sbir.gov/award/A-1)" in packet
    assert "[SAM.gov solicitation](https://sam.gov/opp/O-1)" in packet
    assert "| Autonomous navigation | Drone Co | Phase II |" in packet
    assert "| Why listed |" in packet
    assert "Newly awarded this month" in packet
    assert (output / "master_candidates.csv").exists()
    assert {
        "award_title",
        "award_abstract",
        "award_source_url",
        "opportunity_title",
        "opportunity_description",
        "opportunity_source_url",
    }.issubset(pd.read_csv(output / "master_candidates.csv").columns)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["candidate_rows"] == 1
    assert manifest["plain_language_passed"] is True
    assert manifest["plain_language_findings"] == 0
    language = json.loads((output / "plain_language.json").read_text())
    assert language["passed"] is True
    assert language["centers"]["navair"]["jargon"] == []

    rendered = (output / "centers" / "navair.html").read_text()
    assert "<h1>Monthly Procurement Transition Packet — NAVAIR</h1>" in rendered
    assert "<table>" in rendered
    assert '<a href="https://sam.gov/opp/O-1">SAM.gov solicitation</a>' in rendered
    assert "**" not in rendered
    assert "<pre>" not in rendered


def test_missing_descriptions_and_unsafe_public_fields_are_explicit(tmp_path):
    awards = _awards()
    awards.loc[0, "Award Title"] = "Navigation <script>alert(1)</script>"
    awards.loc[0, "Abstract"] = "Sensor fusion | autonomous control"
    awards.loc[0, "source_url"] = "javascript:alert(1)"
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "C-1",
                "signal_class": "followon",
                "prior_award_id": "A-1",
                "target_id": "O-1",
                "candidate_score": None,
                "is_high_confidence": pd.NA,
            }
        ]
    )
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Prototype [integration](javascript:alert(1))",
                "description": "Prototype [integration](javascript:alert(1))",
                "office": "NAVAIR",
                "source_url": "javascript:alert(1)",
            }
        ]
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )
    packet = (output / "centers" / "navair.md").read_text()

    assert "Needs more evidence before routing" in packet
    assert "Detailed solicitation text was not retrieved" in packet
    assert "&lt;script&gt;" in packet
    assert "<script>" not in packet
    assert "[integration](javascript:" not in packet
    assert "**Source records:** Not supplied in this input" in packet
    assert "Sensor fusion \\| autonomous control" in packet

    rendered = (output / "centers" / "navair.html").read_text()
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered
    assert "<a " not in rendered  # no link survives when every URL is unsafe
    assert "Sensor fusion | autonomous control" in rendered


def test_connection_facts_surface_same_firm_and_continuation_phrases(tmp_path):
    cohorts = build_award_cohorts(_awards(), pd.DataFrame(), report_month="2026-06")
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "C-1",
                "signal_class": "directed",
                "prior_award_id": "A-1",
                "target_id": "O-1",
                "candidate_score": 0.9,
                "is_high_confidence": True,
                "agency_continuity_score": 0.25,
                "text_similarity_score": 0.0,
                "lineage_language_score": 0.2,
            }
        ]
    )
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Navigation follow-on production",
                "description": (
                    "Notice of intent to sole source follow-on production of the "
                    "autonomous navigation capability."
                ),
                "office": "NAVAIR",
                "awardee_uei": "UEI000000001",
            }
        ]
    )
    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts, candidates=candidates, opportunities=opportunities
    )
    packet = (output / "centers" / "navair.md").read_text()
    assert "The notice names the SBIR/STTR awardee directly (UEI UEI000000001)." in packet
    assert "“follow-on production”, “sole source” and “notice of intent”" in packet
    assert "passed 2 of 3 automated screening checks" in packet
    assert "composite" not in packet.lower()
    assert json.loads((output / "plain_language.json").read_text())["passed"] is True


def test_optional_summaries_are_bounded_and_prioritize_high_scores(tmp_path):
    cohorts = build_award_cohorts(_awards(), pd.DataFrame(), report_month="2026-06")
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "LOWER",
                "signal_class": "directed",
                "prior_award_id": "A-1",
                "target_id": "O-1",
                "candidate_score": 0.75,
                "is_high_confidence": True,
            },
            {
                "candidate_id": "HIGHER",
                "signal_class": "directed",
                "prior_award_id": "A-1",
                "target_id": "O-2",
                "candidate_score": 0.95,
                "is_high_confidence": True,
            },
            {
                "candidate_id": "WATCH",
                "signal_class": "followon",
                "prior_award_id": "A-1",
                "target_id": "O-3",
                "candidate_score": 0.40,
                "is_high_confidence": False,
            },
        ]
    )
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": f"O-{number}",
                "title": f"Navigation procurement {number}",
                "description": f"Integrate navigation capability {number} into a prototype.",
                "office": "NAVAIR",
            }
            for number in range(1, 4)
        ]
    )
    calls = []

    def summarize(row):
        calls.append(row["candidate_id"])
        return "The technical scopes overlap. [SBIR] [SAM]"

    output = MonthlyReportBuilder(
        report_month="2026-06",
        output_root=tmp_path,
        summarizer=summarize,
        max_summaries=1,
    ).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )

    assert calls == ["HIGHER"]
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["ai_summary_attempts"] == 1
    assert manifest["ai_summary_limit"] == 1


def test_army_science_and_technology_example_matches_generated_packet(tmp_path):
    examples = Path(__file__).resolve().parents[3] / "examples"
    cohorts = build_award_cohorts(
        pd.read_csv(examples / "army_science_technology_awards.csv"),
        pd.DataFrame(),
        report_month="2026-06",
    )
    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=pd.read_csv(examples / "army_science_technology_candidates.csv"),
        opportunities=pd.read_csv(examples / "army_science_technology_opportunities.csv"),
    )

    generated = (output / "centers" / "army-st-example.md").read_text()
    expected = (examples / "army_science_technology_report.md").read_text()
    assert generated == expected
