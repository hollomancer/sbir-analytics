import json
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from sbir_etl.reporting.procurement_transition import (
    MonthlyReportBuilder,
    build_award_cohorts,
    group_candidates_by_awardee,
)
from sbir_etl.reporting.procurement_transition.core import _validate_line
from sbir_ml.transition.detection.fusion_scoring import score_pairs_with_fusion


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
    assert "### Drone Co → Navigation procurement — direct-award" in packet
    assert "Navigation software that fuses onboard sensors" in packet
    assert "**Asks for:**" in packet
    assert "integrate autonomous navigation" in packet
    assert "**Why it connects:**" in packet
    assert "The award and notice list the same agency (DEFENSE)." in packet
    assert "The notice text contains “Phase III” and “sole source”." in packet
    assert "Both describe “autonomous navigation”." in packet
    assert "Both records list NAICS code 541715." in packet
    assert "Both records list product/service code (PSC) AC13." in packet
    assert "no written technical comparison is available" not in packet
    assert "agency continuity" not in packet
    assert "topical similarity across codes and text" not in packet
    assert "critical-technology alignment" not in packet
    assert "composite 0.80" not in packet
    assert "## Bottom line" in packet
    assert "## Potential transition paths" in packet
    assert "## Path details" in packet
    assert "relevant open procurement" in packet
    assert "derives from, extends, or completes" in packet
    assert "derives from, extends, or uses" not in packet
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
    assert "## Bottom line" not in html_packet
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

    assert "needs more evidence" in packet
    assert "Detailed solicitation text was not retrieved" in packet
    assert "&lt;script&gt;" in packet
    assert "<script>" not in packet
    assert "[integration](javascript:" not in packet
    assert "**Sources:** Not supplied in this input" in packet
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
    assert "needs more evidence" in (output / "centers" / "navair.md").read_text()


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


def _grouping_rows(records: list[dict]) -> pd.DataFrame:
    columns = {
        "prior_award_id",
        "signal_class",
        "confidence_bucket",
        "candidate_score",
        "opportunity_response_deadline",
        "opportunity_title",
    }
    return pd.DataFrame([{column: record.get(column) for column in columns} for record in records])


def test_group_orders_directed_before_competitive_then_by_deadline():
    awards = pd.DataFrame([{"award_id": "A", "amount": 1_000}])
    rows = _grouping_rows(
        [
            {
                "prior_award_id": "A",
                "signal_class": "followon",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Competitive early",
                "opportunity_response_deadline": "2026-07-01",
            },
            {
                "prior_award_id": "A",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Directed later",
                "opportunity_response_deadline": "2026-09-03",
            },
            {
                "prior_award_id": "A",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Directed sooner",
                "opportunity_response_deadline": "2026-08-15",
            },
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    assert len(groups) == 1
    group = groups[0]
    # Directed sorted by soonest deadline, regardless of the earlier competitive deadline.
    assert [entry["opportunity_title"] for entry in group["directed"]] == [
        "Directed sooner",
        "Directed later",
    ]
    assert [entry["opportunity_title"] for entry in group["competitive"]] == ["Competitive early"]
    assert group["has_directed"] is True


def test_group_orders_awardees_directed_first_then_deadline_then_amount():
    awards = pd.DataFrame(
        [
            {"award_id": "A", "amount": 100},
            {"award_id": "B", "amount": 500},
            {"award_id": "C", "amount": 300},
        ]
    )
    rows = _grouping_rows(
        [
            {
                "prior_award_id": "A",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "A directed",
                "opportunity_response_deadline": "2026-09-01",
            },
            {
                "prior_award_id": "B",
                "signal_class": "followon",
                "confidence_bucket": "HIGH",
                "opportunity_title": "B competitive",
                "opportunity_response_deadline": "2026-08-01",
            },
            {
                "prior_award_id": "C",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "C directed",
                "opportunity_response_deadline": "2026-08-15",
            },
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    # Directed-having awardees first (C sooner than A), then the competitive-only awardee B.
    assert [group["award_id"] for group in groups] == ["C", "A", "B"]


def test_group_keeps_below_threshold_matches_as_watchlist():
    awards = pd.DataFrame([{"award_id": "A", "amount": 100}])
    rows = _grouping_rows(
        [
            {
                "prior_award_id": "A",
                "signal_class": "followon",
                "confidence_bucket": "WATCHLIST",
                "opportunity_title": "Weak match",
                "opportunity_response_deadline": "2026-09-01",
            }
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    assert len(groups) == 1
    group = groups[0]
    assert group["directed"] == []
    assert group["competitive"] == []
    assert [entry["opportunity_title"] for entry in group["watchlist"]] == ["Weak match"]
    assert group["has_directed"] is False


def test_group_emits_awardee_with_no_matched_procurement():
    awards = pd.DataFrame([{"award_id": "A", "amount": 100}])
    groups = group_candidates_by_awardee(pd.DataFrame(), awards)

    assert len(groups) == 1
    group = groups[0]
    assert group["award_id"] == "A"
    assert group["directed"] == []
    assert group["competitive"] == []
    assert group["watchlist"] == []


def _transition_packet(tmp_path, *, abstract_simplifier=None) -> str:
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
                "description": "Integrate autonomous navigation into an unmanned aircraft.",
                "office": "NAVAIR",
                "response_deadline": "2026-08-01",
                "naics_code": "541715",
                "psc_code": "AC13",
            }
        ]
    )
    output = MonthlyReportBuilder(
        report_month="2026-06",
        output_root=tmp_path,
        abstract_simplifier=abstract_simplifier,
    ).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )
    return (output / "centers" / "navair.md").read_text()


def test_transition_paths_table_shows_deterministic_plain_summary(tmp_path):
    packet = _transition_packet(tmp_path)

    assert "## Potential transition paths" in packet
    assert "| Awardee | What they built | Possible next procurement |" in packet
    # Deterministic default: the leading sentence of the real abstract, no AI.
    assert "Navigation software that fuses onboard sensors for autonomous flight." in packet
    assert "Navigation procurement (direct-award)" in packet
    assert "Both records list NAICS code 541715." in packet


def test_transition_paths_table_uses_ai_upgrade_when_provided(tmp_path):
    packet = _transition_packet(
        tmp_path,
        abstract_simplifier=lambda text: "Software that flies a drone by itself.",
    )

    # The AI-plain summary drives the 'what they built' cell; the raw abstract is dropped.
    assert "Software that flies a drone by itself." in packet
    assert "Navigation software that fuses onboard sensors" not in packet


def test_transition_paths_table_deterministic_without_ai(tmp_path):
    packet = _transition_packet(tmp_path)

    # No simplifier: the leading sentence of the real abstract, verbatim.
    assert "Navigation software that fuses onboard sensors for autonomous flight." in packet


def test_path_detail_includes_built_on_context(tmp_path):
    packet = _transition_packet(tmp_path)

    assert "**Built on:** Navigation software that fuses onboard sensors" in packet


def test_path_detail_surfaces_connection_sentence_and_shared_phrases(tmp_path):
    awards = _awards()
    awards.loc[0, "Abstract"] = (
        "Navigation software for small aircraft. The system can fuse onboard radar and "
        "electro-optical sensors to track terrain during autonomous flight. Flight logs "
        "are archived for post-mission analysis."
    )
    awards.loc[0, "CET"] = "Autonomous Systems"
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
                "title": "Navigation integration",
                "description": (
                    "The Navy requires a prototype that can fuse onboard radar and "
                    "electro-optical sensors to track terrain, supporting autonomous "
                    "navigation for unmanned aircraft."
                ),
                "office": "NAVAIR",
                "response_deadline": "2026-08-01",
            }
        ]
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )
    packet = (output / "centers" / "navair.md").read_text()

    # Connection quotes the buried claim, not the abstract's leading sentence.
    assert "**Connection:**" in packet
    assert "The system can fuse onboard radar" in packet
    # Multi-word phrases replace single-token soup.
    assert "Both describe" in packet
    assert "“electro-optical sensors”" in packet
    # CET agreement from the award label + notice vocabulary.
    assert "Both fall in the Autonomous Systems critical-technology area" in packet
    assert "“autonomous navigation”" in packet


def test_validate_line_cites_lineage_phrase_when_present():
    row = pd.Series(
        {
            "opportunity_description": "This Phase III sole source effort extends the prior work.",
        }
    )
    line = _validate_line(row, "directed")

    assert "derives from, extends, or completes" in line
    assert "“Phase III”" in line
    assert "statement of work" in line


def test_group_excludes_notice_that_names_the_awardee():
    # A notice carrying the awardee's own UEI is an award/J&A — the decision is
    # already made, so it is not a forward transition path and must be dropped.
    awards = pd.DataFrame([{"award_id": "A", "amount": 100}])
    rows = pd.DataFrame(
        [
            {
                "prior_award_id": "A",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Already-awarded notice",
                "award_uei": "UEI000000001",
                "opportunity_awardee_uei": "UEI000000001",
            },
            {
                "prior_award_id": "A",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Genuine forward solicitation",
                "opportunity_awardee_uei": None,
            },
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    titles = [entry["opportunity_title"] for entry in groups[0]["directed"]]
    assert titles == ["Genuine forward solicitation"]


def test_validate_line_leads_with_cited_award_number():
    row = pd.Series(
        {
            "prior_award_id": "N00014-20-C-0055",
            "opportunity_description": (
                "Sole source continuation of work under contract N00014-20-C-0055."
            ),
        }
    )
    line = _validate_line(row, "directed")

    assert "cites the awardee's SBIR award number (N00014-20-C-0055)" in line
    assert "strongest forward lineage signal" in line
    # The weaker org-level guidance is superseded, not appended.
    assert "confirm the buying office" not in line


def test_validate_line_flags_missing_link_when_no_shared_fields():
    row = pd.Series({"opportunity_description": "Integrate the capability into a prototype."})
    line = _validate_line(row, "directed")

    assert "no same-firm or same-office link" in line


def test_validate_line_marks_competitive_as_open_competition():
    row = pd.Series({"opportunity_description": "Open competition for a new sensor."})
    line = _validate_line(row, "followon")

    assert "open competition, not a directed award" in line
    assert "derives from, extends, or completes" not in line


def test_transition_paths_table_marks_awardee_without_a_path(tmp_path):
    awards = _awards(end_date="2026-08-31")
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=pd.DataFrame(),
        opportunities=pd.DataFrame(),
    )
    packet = (output / "centers" / "navy.md").read_text()

    assert "— no matched procurement" in packet
    assert "ends 2026-08-31" in packet


def _fusion_rows(records: list[dict]) -> pd.DataFrame:
    """Grouping rows that also carry the text/metadata the fusion ranker scores."""

    columns = {
        "prior_award_id",
        "signal_class",
        "confidence_bucket",
        "candidate_score",
        "opportunity_response_deadline",
        "opportunity_title",
        "opportunity_description",
        "opportunity_naics_code",
        "opportunity_notice_type",
        "award_title",
        "award_abstract",
        "company",
    }
    return pd.DataFrame([{column: record.get(column) for column in columns} for record in records])


_HYPERSONIC_ABSTRACT = (
    "Ablative thermal protection coating for hypersonic leading edges, using a "
    "ceramic matrix composite substrate with an ultra high temperature oxide layer."
)


def _fusion_record(**overrides: object) -> dict:
    record = {
        "prior_award_id": "A",
        "signal_class": "followon",
        "confidence_bucket": "HIGH",
        "company": "Acme Aerospace",
        "award_title": "Hypersonic leading-edge thermal protection",
        "award_abstract": _HYPERSONIC_ABSTRACT,
        "opportunity_naics_code": "336412",
        "opportunity_notice_type": "Solicitation",
    }
    record.update(overrides)
    return record


def test_group_ranks_by_fusion_score_ahead_of_deadline():
    """The packet is a strongest-match-first queue, not a calendar.

    A far-deadline procurement whose text matches the award closely outranks a
    soon-closing one that does not. This is the behaviour change the ranker
    introduced — the pre-ranker contract was deadline order.
    """

    awards = pd.DataFrame([{"award_id": "A", "amount": 1_000}])
    rows = _fusion_rows(
        [
            _fusion_record(
                opportunity_title="Soon but unrelated",
                opportunity_response_deadline="2026-07-01",
                opportunity_description=(
                    "Janitorial and grounds maintenance services for administrative "
                    "office buildings, including custodial supplies and landscaping."
                ),
            ),
            _fusion_record(
                opportunity_title="Later but matching",
                opportunity_response_deadline="2026-12-01",
                opportunity_description=(
                    "Ultra high temperature ceramic matrix composite ablative coating "
                    "for hypersonic vehicle leading edges and thermal protection."
                ),
            ),
        ]
    )

    groups = group_candidates_by_awardee(
        rows,
        awards,
        fusion_scorer=score_pairs_with_fusion,
    )

    assert len(groups) == 1
    entries = groups[0]["competitive"]
    assert [entry["opportunity_title"] for entry in entries] == [
        "Later but matching",
        "Soon but unrelated",
    ]


def test_group_ranks_watchlist_by_fusion_score_too():
    """Watchlist ordering changed with the ranker as well, not just directed/competitive."""

    awards = pd.DataFrame([{"award_id": "A", "amount": 1_000}])
    rows = _fusion_rows(
        [
            _fusion_record(
                confidence_bucket="WATCHLIST",
                opportunity_title="Soon but unrelated",
                opportunity_response_deadline="2026-07-01",
                opportunity_description=(
                    "Janitorial and grounds maintenance services for administrative "
                    "office buildings, including custodial supplies and landscaping."
                ),
            ),
            _fusion_record(
                confidence_bucket="WATCHLIST",
                opportunity_title="Later but matching",
                opportunity_response_deadline="2026-12-01",
                opportunity_description=(
                    "Ultra high temperature ceramic matrix composite ablative coating "
                    "for hypersonic vehicle leading edges and thermal protection."
                ),
            ),
        ]
    )

    groups = group_candidates_by_awardee(
        rows,
        awards,
        fusion_scorer=score_pairs_with_fusion,
    )

    assert [entry["opportunity_title"] for entry in groups[0]["watchlist"]] == [
        "Later but matching",
        "Soon but unrelated",
    ]


def test_group_falls_back_to_deadline_order_when_ranker_unavailable(caplog):
    """An unavailable ranker must be visible, not a silent reversion to deadline order."""

    def _boom(*args: object, **kwargs: object) -> list[float]:
        raise RuntimeError("coefficients missing")

    awards = pd.DataFrame([{"award_id": "A", "amount": 1_000}])
    rows = _fusion_rows(
        [
            _fusion_record(
                opportunity_title="Later but matching",
                opportunity_response_deadline="2026-12-01",
                opportunity_description=(
                    "Ultra high temperature ceramic matrix composite ablative coating "
                    "for hypersonic vehicle leading edges and thermal protection."
                ),
            ),
            _fusion_record(
                opportunity_title="Soon but unrelated",
                opportunity_response_deadline="2026-07-01",
                opportunity_description="Janitorial and grounds maintenance services.",
            ),
        ]
    )

    with caplog.at_level("WARNING"):
        groups = group_candidates_by_awardee(rows, awards, fusion_scorer=_boom)

    assert [entry["opportunity_title"] for entry in groups[0]["competitive"]] == [
        "Soon but unrelated",
        "Later but matching",
    ]
    assert any("Fusion ranking unavailable" in record.message for record in caplog.records)
