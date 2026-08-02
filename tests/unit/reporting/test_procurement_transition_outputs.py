"""Packet output integrity: award-grain diffs, safe artifacts, and awardee grouping."""

import json

import pandas as pd
import pytest

from sbir_etl.reporting.procurement_transition import (
    MonthlyReportBuilder,
    build_award_cohorts,
    group_candidates_by_awardee,
    normalize_awards,
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


def test_reused_contract_numbers_are_scoped_by_full_award_lineage():
    snapshot = pd.DataFrame(
        [
            _award(**{"Agency Tracking Number": "A-1", "Contract": "SHARED-CONTRACT"}),
            _award(
                Company="Sensor Co",
                UEI="UEI000000002",
                **{
                    "Agency Tracking Number": "A-2",
                    "Contract": "SHARED-CONTRACT",
                    "Award Title": "Radar payload",
                },
            ),
        ]
    )

    normalized = normalize_awards(snapshot)

    assert normalized["award_key"].nunique() == 2
    assert set(normalized["award_id"]) == {"A-1", "A-2"}


def test_award_key_canonicalizes_supported_date_representations():
    keys = [
        normalize_awards(pd.DataFrame([_award(**{"Proposal Award Date": value})])).loc[
            0, "award_key"
        ]
        for value in ("2026-06-12", "06/12/2026", pd.Timestamp("2026-06-12"))
    ]

    assert len(set(keys)) == 1


def test_pre_migration_normalized_snapshot_fails_closed():
    old_snapshot = normalize_awards(pd.DataFrame([_award()])).drop(columns="award_key_version")

    with pytest.raises(ValueError, match="pre-migration award key"):
        build_award_cohorts(old_snapshot, pd.DataFrame(), report_month="2026-06")


def test_a_real_edit_is_still_reported_as_changed():
    previous = pd.DataFrame([_award()])
    current = pd.DataFrame([_award(**{"Award Amount": "$2,000,000"})])

    cohorts = build_award_cohorts(current, previous, report_month="2026-06")

    assert bool(cohorts.iloc[0]["newly_observed"]) is False
    assert bool(cohorts.iloc[0]["changed_since_prior_report"]) is True


def test_mutable_award_edits_do_not_change_award_identity():
    previous = pd.DataFrame([_award()])
    current = pd.DataFrame(
        [
            _award(
                **{
                    "Award Title": "Updated autonomous navigation",
                    "Abstract": "Updated technical description.",
                    "Award Amount": "$2,000,000",
                    "Contract End Date": "2026-10-31",
                }
            )
        ]
    )

    prior = build_award_cohorts(previous, pd.DataFrame(), report_month="2026-06")
    cohorts = build_award_cohorts(current, previous, report_month="2026-06")

    assert cohorts.loc[0, "award_key"] == prior.loc[0, "award_key"]
    assert cohorts.loc[0, "row_hash"] != prior.loc[0, "row_hash"]
    assert bool(cohorts.loc[0, "newly_observed"]) is False
    assert bool(cohorts.loc[0, "changed_since_prior_report"]) is True


def test_multiple_source_editions_collapse_to_one_stable_award():
    raw = pd.DataFrame(
        [
            _award(**{"Award Amount": "$1,000,000", "Contract End Date": "2026-08-15"}),
            _award(**{"Award Amount": "$2,000,000", "Contract End Date": "2027-08-15"}),
        ]
    )

    normalized = normalize_awards(raw)

    assert len(normalized) == 1
    assert normalized.loc[0, "amount"] == 2_000_000
    assert normalized.loc[0, "source_edition_count"] == 2
    assert normalized.loc[0, "source_edition_variants"] == 2


def test_sparse_award_rows_still_receive_a_row_hash():
    raw = pd.DataFrame(
        [
            {
                "Agency Tracking Number": "A-1",
                "Company": "Drone Co",
                "Agency": "DEFENSE",
                "Phase": "Phase II",
            }
        ]
    )
    normalized = normalize_awards(raw)
    cohorts = build_award_cohorts(raw, pd.DataFrame(), report_month="2026-06")

    assert len(normalized.loc[0, "row_hash"]) == 64
    assert bool(cohorts.loc[0, "recent_recorded_end"]) is False
    assert bool(cohorts.loc[0, "approaching_recorded_end"]) is False


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


def test_direct_grouping_resolves_unique_legacy_id_against_keyed_award():
    awards = normalize_awards(pd.DataFrame([_award()]))
    rows = pd.DataFrame(
        [
            {
                "prior_award_id": "A-1",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "target_id": "O-1",
                "opportunity_title": "Navigation procurement",
            }
        ]
    )

    groups = group_candidates_by_awardee(rows, awards)

    assert len(groups) == 1
    assert len(groups[0]["directed"]) == 1


def test_direct_grouping_rejects_ambiguous_legacy_id():
    awards = normalize_awards(
        pd.DataFrame([_award(), _award(**{"Award Title": "Second effort", "Phase": "Phase I"})])
    )
    rows = pd.DataFrame(
        [
            {
                "prior_award_id": "A-1",
                "signal_class": "directed",
                "confidence_bucket": "HIGH",
                "target_id": "O-1",
            }
        ]
    )

    with pytest.raises(ValueError, match="unique award-grain"):
        group_candidates_by_awardee(rows, awards)


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


def test_ambiguous_legacy_award_id_fails_closed(tmp_path):
    awards = pd.DataFrame(
        [
            _award(),
            _award(**{"Award Title": "Second effort", "Phase": "Phase I"}),
        ]
    )

    with pytest.raises(ValueError, match="legacy prior_award_id is ambiguous"):
        _write(tmp_path, awards, _candidates(), _opportunities())


def test_legacy_ambiguity_is_preserved_after_monthly_cohort_filter(tmp_path):
    first = _award(**{"Proposal Award Date": "2020-01-01", "Contract End Date": "2021-01-01"})
    second = {
        **first,
        "Award Title": "Second effort",
        "Phase": "Phase I",
    }
    cohorts = build_award_cohorts(
        pd.DataFrame([first, second]),
        pd.DataFrame([first]),
        report_month="2026-06",
    )

    assert len(cohorts) == 1
    assert cohorts.loc[0, "public_id_award_count"] == 2
    with pytest.raises(ValueError, match="legacy prior_award_id is ambiguous"):
        MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
            award_cohorts=cohorts,
            candidates=_candidates(),
            opportunities=_opportunities(),
        )


def test_report_supports_safe_mixed_key_rollout(tmp_path):
    awards = pd.DataFrame(
        [
            _award(),
            _award(
                **{
                    "Agency Tracking Number": "A-2",
                    "Award Title": "Radar payload",
                    "Proposal Award Date": "2026-06-20",
                }
            ),
        ]
    )
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
    award_2_key = cohorts.loc[cohorts["award_id"] == "A-2", "award_key"].item()
    candidates = pd.DataFrame(
        [
            _candidates().iloc[0].to_dict(),
            {
                **_candidates().iloc[0].to_dict(),
                "candidate_id": "C-2",
                "prior_award_id": "A-2",
                "prior_award_key": award_2_key,
                "target_id": "O-2",
            },
        ]
    )
    opportunities = pd.concat(
        [
            _opportunities(),
            _opportunities().assign(notice_id="O-2", title="Radar procurement"),
        ],
        ignore_index=True,
    )

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=opportunities,
    )
    master = pd.read_csv(output / "master_candidates.csv").set_index("candidate_id")

    assert master.loc["C-1", "award_title"] == "Autonomous navigation"
    assert master.loc["C-2", "award_title"] == "Radar payload"


def test_path_renders_the_award_that_produced_the_candidate(tmp_path):
    awards = pd.DataFrame(
        [
            _award(
                **{
                    "Agency Tracking Number": "A-1",
                    "Abstract": "Award A built radar calibration hardware.",
                    "Contract End Date": "2026-07-01",
                }
            ),
            _award(
                **{
                    "Award Title": "Navigation integration",
                    "Abstract": "Award B built autonomous navigation software.",
                    "Contract End Date": "2026-12-01",
                    "Proposal Award Date": "2026-06-20",
                }
            ),
        ]
    )
    cohorts = build_award_cohorts(awards, pd.DataFrame(), report_month="2026-06")
    award_b_key = cohorts.loc[cohorts["title"] == "Navigation integration", "award_key"].item()
    candidates = _candidates().assign(prior_award_key=award_b_key)

    output = MonthlyReportBuilder(report_month="2026-06", output_root=tmp_path).write(
        award_cohorts=cohorts,
        candidates=candidates,
        opportunities=_opportunities(),
    )
    packet = (output / "centers" / "navair.md").read_text()

    assert "**Built on:** Award B built autonomous navigation software." in packet
    assert "**Built on:** Award A built radar calibration hardware." not in packet
