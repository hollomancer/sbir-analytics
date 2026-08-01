"""Packet output integrity: award-grain diffs, safe artifacts, and awardee grouping."""

import json

import pandas as pd

from sbir_etl.reporting.procurement_transition import (
    MonthlyReportBuilder,
    build_award_cohorts,
    group_candidates_by_awardee,
)


def _award(**overrides) -> dict:
    row = {
        "Agency Tracking Number": "A-1",
        "Company": "Drone Co",
        "Award Title": "Autonomous navigation",
        "Agency": "DEFENSE",
        "Branch": "NAVY",
        "Phase": "Phase II",
        "Program": "SBIR",
        "Proposal Award Date": "2026-06-12",
        "Contract End Date": "2026-08-15",
        "UEI": "UEI000000001",
        "Award Amount": "$1,000,000",
        "Abstract": "Navigation software that fuses onboard sensors.",
    }
    row.update(overrides)
    return row


def test_duplicate_tracking_numbers_are_not_collapsed_across_snapshots():
    # The public snapshot reuses tracking numbers across distinct awards; keying
    # the diff on the bare number marks unchanged rows as changed.
    snapshot = pd.DataFrame(
        [
            _award(),
            _award(Company="Drone Co", **{"Award Title": "Second effort", "Phase": "Phase I"}),
        ]
    )
    cohorts = build_award_cohorts(snapshot, snapshot.copy(), report_month="2026-06")

    assert not cohorts["changed_since_prior_report"].any()
    assert not cohorts["newly_observed"].any()
    assert cohorts["award_key"].nunique() == 2


def test_a_real_edit_is_still_reported_as_changed():
    previous = pd.DataFrame([_award()])
    current = pd.DataFrame([_award(**{"Award Amount": "$2,000,000"})])

    cohorts = build_award_cohorts(current, previous, report_month="2026-06")

    assert bool(cohorts.iloc[0]["newly_observed"]) is True


def test_missing_identifiers_do_not_become_the_literal_na_token():
    cohorts = build_award_cohorts(
        pd.DataFrame([_award(**{"Agency Tracking Number": pd.NA})]),
        pd.DataFrame(),
        report_month="2026-06",
    )
    assert str(cohorts.iloc[0]["award_id"]).lower() not in {"<na>", "nan", "none"}
    assert str(cohorts.iloc[0]["award_id"]).startswith("sbir-")


def _write(tmp_path, awards: pd.DataFrame, candidates: pd.DataFrame, opportunities) -> object:
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
    return MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts, candidates=candidates, opportunities=opportunities
    )


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
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


def _opportunities(description: str = "Integrate autonomous navigation.") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Navigation procurement",
                "description": description,
                "office": "NAVAIR",
                "response_deadline": "2026-08-01",
            }
        ]
    )


def test_exported_csv_neutralizes_spreadsheet_formulas(tmp_path):
    output = _write(
        tmp_path,
        pd.DataFrame([_award()]),
        _candidates(),
        _opportunities(description='=HYPERLINK("http://evil","click")'),
    )

    master = (output / "master_candidates.csv").read_text()
    assert "=HYPERLINK" not in master.replace("'=HYPERLINK", "")
    assert "'=HYPERLINK" in master
    # The raw value stays available in the non-spreadsheet artifact.
    records = [json.loads(line) for line in (output / "evidence.ndjson").read_text().splitlines()]
    assert any(str(record.get("opportunity_description", "")).startswith("=") for record in records)


def test_evidence_ndjson_is_standards_compliant(tmp_path):
    output = _write(tmp_path, pd.DataFrame([_award()]), _candidates(), _opportunities())

    text = (output / "evidence.ndjson").read_text()
    assert "NaN" not in text
    for line in text.splitlines():
        json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def test_rerunning_a_month_replaces_the_center_output(tmp_path):
    _write(tmp_path, pd.DataFrame([_award()]), _candidates(), _opportunities())
    stale = tmp_path / "2026-06" / "centers" / "withdrawn-center.md"
    stale.write_text("obsolete packet")

    output = _write(tmp_path, pd.DataFrame([_award()]), _candidates(), _opportunities())

    assert not stale.exists()
    assert list((output / "centers").glob("*.md"))


def test_awardee_with_several_awards_is_one_section():
    awards = pd.DataFrame(
        [
            {"award_id": "A-1", "uei": "UEI000000001", "company": "Drone Co", "amount": 100},
            {"award_id": "A-2", "uei": "UEI000000001", "company": "Drone Co", "amount": 200},
        ]
    )
    rows = pd.DataFrame(
        [
            {
                "prior_award_id": "A-1",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Shared procurement",
                "target_id": "O-1",
                "opportunity_response_deadline": "2026-09-01",
            },
            {
                "prior_award_id": "A-2",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "opportunity_title": "Shared procurement",
                "target_id": "O-1",
                "opportunity_response_deadline": "2026-09-01",
            },
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    # One firm, one section — and the procurement it reaches through two awards
    # is listed once.
    assert len(groups) == 1
    assert sorted(groups[0]["award_ids"]) == ["A-1", "A-2"]
    assert len(groups[0]["directed"]) == 1


def test_unmatched_awardees_at_a_matched_center_are_still_listed(tmp_path):
    awards = pd.DataFrame(
        [
            _award(),
            _award(
                **{
                    "Agency Tracking Number": "A-2",
                    "Company": "Sensor Co",
                    "UEI": "UEI000000002",
                    "Branch": "NAVAIR",
                }
            ),
        ]
    )
    output = _write(tmp_path, awards, _candidates(), _opportunities())

    packet = (output / "centers" / "navair.md").read_text()
    assert "Drone Co" in packet
    # The unmatched awardee at the same center is not dropped from the packet.
    assert "Sensor Co" in packet
    assert "| — no matched procurement" in packet


def test_a_matched_award_is_not_repeated_as_unmatched_elsewhere(tmp_path):
    # The award's branch (NAVY) differs from the notice's office (NAVAIR), so the
    # cohort seeds a second center. The matched award belongs only to the center
    # that matched it — it must not reappear there as "no matched procurement".
    output = _write(tmp_path, pd.DataFrame([_award()]), _candidates(), _opportunities())

    packets = {path.name: path.read_text() for path in (output / "centers").glob("*.md")}
    assert "navy.md" in packets
    unmatched = [name for name, text in packets.items() if "| — no matched procurement" in text]
    assert unmatched == []
