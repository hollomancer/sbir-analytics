import json
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.procurement_transition import MonthlyReportBuilder, build_award_cohorts


class _HTMLProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.hrefs: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.hrefs.extend(value for name, value in attrs if name == "href" and value)

    def handle_data(self, data):
        self.text.append(data)


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
                "NAICS": "541715",
                "PSC": "AC13",
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
                "description": (
                    "This Phase III sole source notice will integrate autonomous navigation "
                    "into an unmanned aircraft prototype."
                ),
                "awardee_uei": "UEI000000001",
                "agency": "DEFENSE",
                "naics_code": "541715",
                "psc_code": "AC13",
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
    assert "Potential directed Phase III path" in packet
    assert "#### What the award funded" in packet
    assert "Navigation software that fuses onboard sensors" in packet
    assert "#### What the solicitation asks for" in packet
    assert "integrate autonomous navigation" in packet
    assert "#### Technical connection to validate" in packet
    assert "The notice names the SBIR/STTR awardee (UEI UEI000000001)." in packet
    assert "The award and notice list the same agency (DEFENSE)." in packet
    assert "The notice text contains “Phase III” and “sole source”." in packet
    assert "Both texts mention autonomous and navigation." in packet
    assert "Both records list NAICS code 541715." in packet
    assert "Both records list product/service code (PSC) AC13." in packet
    assert "no written technical comparison is available" not in packet
    assert "agency continuity" not in packet
    assert "topical similarity across codes and text" not in packet
    assert "critical-technology alignment" not in packet
    assert "composite 0.80" not in packet
    assert "## How to read this packet" in packet
    assert "derives from, extends, or completes" in packet
    assert "derives from, extends, or uses" not in packet
    assert "- Awards in this packet:" in packet
    assert "- Award cohort:" not in packet
    assert "[SBIR/STTR award record](https://www.sbir.gov/award/A-1)" in packet
    assert "[SAM.gov solicitation](https://sam.gov/opp/O-1)" in packet
    assert "| Autonomous navigation | Drone Co | Phase II |" in packet
    assert (output / "master_candidates.csv").exists()
    assert {
        "award_title",
        "award_abstract",
        "award_source_url",
        "opportunity_title",
        "opportunity_description",
        "opportunity_source_url",
    }.issubset(pd.read_csv(output / "master_candidates.csv").columns)
    assert json.loads((output / "manifest.json").read_text())["candidate_rows"] == 1

    html_packet = (output / "centers" / "navair.html").read_text()
    probe = _HTMLProbe()
    probe.feed(html_packet)
    assert {"h1", "h2", "strong", "blockquote", "ul", "table", "a"}.issubset(probe.tags)
    assert "pre" not in probe.tags
    assert "## Snapshot" not in html_packet
    assert "**Disposition:**" not in html_packet
    assert "https://www.sbir.gov/award/A-1" in probe.hrefs
    assert "https://sam.gov/opp/O-1" in probe.hrefs


def test_missing_descriptions_and_unsafe_public_fields_are_explicit(tmp_path):
    awards = _awards()
    awards.loc[0, "Award Title"] = "Navigation <script>alert(1)</script>"
    awards.loc[0, "Abstract"] = "C# sensor fusion | autonomous control"
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
    assert "C\\# sensor fusion \\| autonomous control" in packet

    html_packet = (output / "centers" / "navair.html").read_text()
    probe = _HTMLProbe()
    probe.feed(html_packet)
    visible_text = "".join(probe.text)
    assert "C# sensor fusion | autonomous control" in visible_text
    assert "C\\#" not in visible_text
    assert "script" not in probe.tags
    assert not any(href.lower().startswith("javascript:") for href in probe.hrefs)


def test_candidates_without_confidence_default_to_watchlist(tmp_path):
    cohorts = build_award_cohorts(_awards(), pd.DataFrame(), report_month="2026-06")
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "C-1",
                "signal_class": "followon",
                "prior_award_id": "A-1",
                "target_id": "O-1",
                "candidate_score": 0.5,
            }
        ]
    )
    opportunities = pd.DataFrame(
        [{"notice_id": "O-1", "title": "Navigation procurement", "office": "NAVAIR"}]
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )

    master = pd.read_csv(output / "master_candidates.csv")
    assert master.loc[0, "confidence_bucket"] == "WATCHLIST"
    assert "Needs more evidence before routing" in (output / "centers" / "navair.md").read_text()


def test_missing_center_is_routed_to_unassigned(tmp_path):
    awards = _awards()
    awards.loc[0, ["Agency", "Branch"]] = pd.NA
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=pd.DataFrame(),
        opportunities=pd.DataFrame(),
    )

    packet = output / "centers" / "unassigned.md"
    assert packet.exists()
    assert not (output / "centers" / "nan.md").exists()
    assert "# Monthly Procurement Transition Packet — Unassigned" in packet.read_text()


def test_placeholder_values_are_not_rendered_as_public_evidence(tmp_path):
    awards = _awards()
    awards.loc[0, ["UEI", "Agency", "Branch", "NAICS", "PSC"]] = [
        "UNKNOWN",
        "N/A",
        pd.NA,
        "0",
        "N/A",
    ]
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
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
                "title": "Unrelated procurement",
                "description": "Supply administrative office furniture.",
                "office": "NAVAIR",
                "awardee_uei": "UNKNOWN",
                "agency": "N/A",
                "naics_code": "0",
                "psc_code": "N/A",
            }
        ]
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )
    packet = (output / "centers" / "navair.md").read_text()

    assert "notice names the SBIR/STTR awardee" not in packet
    assert "same agency (N/A)" not in packet
    assert "Both records list NAICS" not in packet
    assert "Both records list product/service code" not in packet


def test_award_pipeline_explains_inclusion_and_prioritizes_end_dates(tmp_path):
    awards = pd.DataFrame(
        [
            {
                "award_id": "A-NEW",
                "title": "New award",
                "company": "New Co",
                "agency": "DEFENSE",
                "branch": "NAVY",
                "phase": "Phase I",
                "award_date": "2026-06-20",
                "recorded_end_date": None,
                "amount": 100_000,
                "newly_observed": True,
                "changed_since_prior_report": False,
                "awarded_in_period": True,
                "recent_recorded_end": False,
                "approaching_recorded_end": False,
            },
            {
                "award_id": "A-LATE",
                "title": "Later ending award",
                "company": "Later Co",
                "agency": "DEFENSE",
                "branch": "NAVY",
                "phase": "Phase II",
                "award_date": "2025-01-01",
                "recorded_end_date": "2026-09-30",
                "amount": 200_000,
                "newly_observed": False,
                "changed_since_prior_report": True,
                "awarded_in_period": False,
                "recent_recorded_end": False,
                "approaching_recorded_end": True,
            },
            {
                "award_id": "A-SOON",
                "title": "Sooner ending award",
                "company": "Sooner Co",
                "agency": "DEFENSE",
                "branch": "NAVY",
                "phase": "Phase II",
                "award_date": "2025-02-01",
                "recorded_end_date": "2026-07-15",
                "amount": 300_000,
                "newly_observed": False,
                "changed_since_prior_report": False,
                "awarded_in_period": False,
                "recent_recorded_end": False,
                "approaching_recorded_end": True,
            },
        ]
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=awards,
        candidates=pd.DataFrame(),
        opportunities=pd.DataFrame(),
    )
    packet = (output / "centers" / "navy.md").read_text()

    assert "| Why listed |" in packet
    assert "Newly awarded this month" in packet
    assert "Record changed since last report" in packet
    assert "Recorded end date is within 6 months (2026-07-15)" in packet
    assert packet.index("Sooner ending award") < packet.index("Later ending award")
    assert packet.index("Later ending award") < packet.index("New award")


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
