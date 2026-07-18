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
    assert "potential Phase III path" in packet
    assert "| Drone Co | Phase II |" in packet
    assert (output / "master_candidates.csv").exists()
    assert json.loads((output / "manifest.json").read_text())["candidate_rows"] == 1


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
