"""Regression tests for defense-critical NAICS SBIR event construction."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.data import defense_critical_naics_sbir as mod


pytestmark = pytest.mark.fast

UEI_A = "ABCDEFGHIJKL"
UEI_B = "MNOPQRSTUVWX"
TARGET_NAICS = "334511"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("SR1", "SR1"),
        ("SR2", "SR2"),
        ("SR3", "SR3"),
        ("ST1", "ST1"),
        ("ST2", "ST2"),
        ("ST3", "ST3"),
        ("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE I ACTION", "SR1"),
        ("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION", "SR2"),
        ("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE III ACTION", "SR3"),
        ("SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE I", "ST1"),
        ("SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE II", "ST2"),
        ("SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE III", "ST3"),
    ],
)
def test_research_labels_normalize_to_compact_codes(label: str, expected: str) -> None:
    assert mod._normalize_research_code(label) == expected


def test_phase_ii_anchor_rejects_end_before_award_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    awards = pd.DataFrame(
        [
            {
                "source_edition_count": 1,
                "company": "Example Research, Inc.",
                "contract_number": "FAKE-001",
                "recorded_end_date": "2020-08-31",
                "amount": 1_000_000,
                "award_date": "2020-09-01",
                "award_year": 2020,
                "phase": "Phase II",
                "uei": UEI_A,
                "award_key": "AWARD-1",
                "agency_tracking_number": "TRACK-1",
                "award_id": "AWARD-1",
                "award_key_version": "test-v1",
            }
        ]
    )
    monkeypatch.setattr(mod, "load_sbir_awards_csv", lambda _path: awards)
    monkeypatch.setattr(
        mod,
        "validate_sbir_awards",
        lambda *_args, **_kwargs: SimpleNamespace(failing_row_indices=[]),
    )

    cohort = mod.load_sbir_cohort(Path("unused.csv"), cutoff=date(2021, 1, 1))

    assert pd.isna(cohort.awards.loc[0, "usable_phase_ii_end"])
    assert pd.isna(cohort.firms.loc[0, "first_phase_ii_end"])
    assert cohort.source_audit["phase_ii_rows_with_unusable_end"] == 1


def _cohort(*ueis: str) -> mod.SbirCohort:
    firms = pd.DataFrame(
        [
            {
                "firm_uei": uei,
                "first_sbir_year": 2012,
                "last_sbir_year": 2015,
                "sbir_awards": 2,
                "phase_i_awards": 1,
                "phase_ii_awards": 1,
                "sbir_dollars": 1_000_000.0,
                "phase_i_dollars": 100_000.0,
                "phase_ii_dollars": 900_000.0,
                "first_phase_ii_end": pd.Timestamp("2015-01-01"),
                "display_name": f"Firm {uei[-1]}",
                "state": "VA",
            }
            for uei in ueis
        ]
    )
    return mod.SbirCohort(
        awards=pd.DataFrame(),
        firms=firms,
        source_audit={},
        known_sbir_contracts=set(),
    )


def _transaction(
    transaction_id: str,
    *,
    firm_uei: str = UEI_A,
    award_key: str = "AWARD-A",
    action_date: str,
    obligation_amount: float,
    target_origin: bool = True,
    vendor_name: str | None = None,
) -> dict[str, object]:
    return {
        "firm_uei": firm_uei,
        "vendor_name": vendor_name or f"Firm {firm_uei[-1]}",
        "contract_id": award_key,
        "piid": award_key,
        "transaction_unique_id": transaction_id,
        "generated_unique_award_id": f"GENERATED-{award_key}",
        "award_group_key": award_key,
        "agency": "Department of Defense",
        "sub_agency": "Department of the Air Force",
        "action_date": action_date,
        "start_date": action_date,
        "end_date": "2020-12-31",
        "award_first_action_date": action_date,
        "award_start_date": action_date,
        "award_has_observed_base_transaction": target_origin,
        "award_left_censored": not target_origin,
        "first_target_action_date": action_date,
        "target_naics_on_first_observed_action": target_origin,
        "obligation_amount": obligation_amount,
        "description": "Navigation system production",
        "contract_award_type": "A",
        "research": "",
        "naics_code": TARGET_NAICS,
        "product_or_service_code": "1234",
        "source_fiscal_year": int(action_date[:4]),
    }


def _load_contracts(
    tmp_path: Path,
    cohort: mod.SbirCohort,
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    path = tmp_path / "target_transactions.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    filter_path = tmp_path / "cohort_ueis.json"
    filter_path.write_text(
        json.dumps({"uei": sorted(cohort.firms["firm_uei"].tolist())}),
        encoding="utf-8",
    )
    path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "output": {"sha256": mod._sha256(path)},
                "filter": {
                    "path": str(filter_path),
                    "sha256": mod._sha256(filter_path),
                    "target_naics_codes": sorted(mod.TARGET_NAICS),
                },
            }
        ),
        encoding="utf-8",
    )
    return mod.load_historical_contract_evidence(path, cohort).evidence


def _empty_sam() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "firm_uei",
            "registration_status",
            "primary_naics",
            "primary_target_codes",
            "target_codes",
            "has_primary_target",
            "sam_8a_history_indicator",
            "sam_current_8a_indicator",
            "sam_8a_exit_dates",
        ]
    )


def _empty_recent() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "firm_uei",
            "naics_code",
            "generated_unique_award_id",
            "first_action_date",
            "last_action_date",
            "net_obligations",
        ]
    )


def test_first_positive_post_phase_ii_event_uses_a_positive_transaction(
    tmp_path: Path,
) -> None:
    cohort = _cohort(UEI_A)
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-NEGATIVE",
                action_date="2016-01-05",
                obligation_amount=-100.0,
            ),
            _transaction(
                "TX-POSITIVE",
                action_date="2016-02-05",
                obligation_amount=50.0,
            ),
        ],
    )

    assert contracts.loc[0, "first_positive_target_action_after_phase_ii"] == pd.Timestamp(
        "2016-02-05"
    )
    _, tables = mod.build_archive_analysis_tables(
        cohort=cohort,
        contracts=contracts,
        sam=_empty_sam(),
        recent=_empty_recent(),
        analysis_date=date(2020, 1, 1),
        coverage_end=pd.Timestamp("2020-01-01"),
    )
    firm = tables["firm_evidence"].iloc[0]
    assert firm["first_post_phase_ii_positive_non_phase_i_ii_action_date"] == pd.Timestamp(
        "2016-02-05"
    )


def test_clean_pre_index_and_literal_first_target_entry_flags_remain_distinct(
    tmp_path: Path,
) -> None:
    cohort = _cohort(UEI_A, UEI_B)
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-A-EARLY",
                award_key="AWARD-A-EARLY",
                action_date="2016-01-05",
                obligation_amount=50.0,
                target_origin=False,
            ),
            _transaction(
                "TX-A-ORIGIN",
                award_key="AWARD-A-ORIGIN",
                action_date="2017-01-05",
                obligation_amount=100.0,
            ),
            _transaction(
                "TX-B-ORIGIN",
                firm_uei=UEI_B,
                award_key="AWARD-B-ORIGIN",
                action_date="2016-06-05",
                obligation_amount=100.0,
            ),
        ],
    )

    _, tables = mod.build_archive_analysis_tables(
        cohort=cohort,
        contracts=contracts,
        sam=_empty_sam(),
        recent=_empty_recent(),
        analysis_date=date(2020, 1, 1),
        coverage_end=pd.Timestamp("2020-01-01"),
    )
    firms = tables["firm_evidence"].set_index("firm_uei")

    assert bool(firms.loc[UEI_A, "clean_pre_index_qualifying_target_origin_award"])
    assert not bool(firms.loc[UEI_A, "literal_first_observed_target_entry"])
    assert bool(firms.loc[UEI_B, "clean_pre_index_qualifying_target_origin_award"])
    assert bool(firms.loc[UEI_B, "literal_first_observed_target_entry"])


def test_identity_review_candidates_are_low_continuity_and_reviewable(
    tmp_path: Path,
) -> None:
    cohort = _cohort(UEI_A, UEI_B)
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-A",
                firm_uei=UEI_A,
                action_date="2016-01-05",
                obligation_amount=1_000.0,
                vendor_name="Acquiring Prime Corporation",
            ),
            _transaction(
                "TX-B",
                firm_uei=UEI_B,
                action_date="2016-01-05",
                obligation_amount=100.0,
            ),
        ],
    )
    sbir_name = f"Firm {UEI_A[-1]}"
    contract_name = "Acquiring Prime Corporation"
    review = {
        "firm_uei": UEI_A,
        "sbir_name_key": mod._identity_name_key(sbir_name),
        "contract_name_key": mod._identity_name_key(contract_name),
        "sbir_display_name": sbir_name,
        "contract_recipient_name": contract_name,
        "entity_same_firm": "unsure",
        "corporate_relation": "acquisition",
        "corporate_event_date": "2018-01-01",
        "corporate_event_date_basis": "closed",
        "successor_or_acquirer_name": contract_name,
        "contract_relationship": "not_established",
        "attribution_treatment": "temporal_split_required",
        "review_confidence": "H",
        "evidence_source": "official_company",
        "evidence_locator": "https://example.test/acquisition",
        "secondary_evidence_locator": "",
        "reviewer": "test-reviewer",
        "reviewed_at": "2026-09-10",
        "review_notes": "Corporate event only; no novation evidence.",
    }
    crosswalk_path = tmp_path / "identity_crosswalk.csv"
    pd.DataFrame([review], columns=mod.IDENTITY_CROSSWALK_COLUMNS).to_csv(
        crosswalk_path,
        index=False,
    )
    reviews, audit = mod.load_identity_crosswalk(crosswalk_path)

    summary, tables = mod.build_archive_analysis_tables(
        cohort=cohort,
        contracts=contracts,
        sam=_empty_sam(),
        recent=_empty_recent(),
        analysis_date=date(2020, 1, 1),
        coverage_end=pd.Timestamp("2020-01-01"),
        identity_reviews=reviews,
    )
    candidates = tables["identity_review_candidates"]

    assert audit["reviewed_supported_rows"] == 1
    assert candidates["firm_uei"].tolist() == [UEI_A]
    assert candidates.loc[0, "review_state"] == "reviewed_supported"
    assert candidates.loc[0, "candidate_reason"] == "name_similarity_below_threshold"
    assert bool(candidates.loc[0, "priority_review_tranche"])
    assert summary["identity_review_candidate_entities"] == 1
    assert summary["identity_reviewed_candidate_entities"] == 1
    assert summary["identity_review_unreviewed_rows"] == 0
