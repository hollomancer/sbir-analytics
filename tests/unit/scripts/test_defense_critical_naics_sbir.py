"""Regression tests for defense-critical NAICS SBIR event construction."""

import json
import sys
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


def test_default_as_of_replays_the_named_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defense_critical_naics_sbir.py",
            "--sbir-awards",
            "sbir.csv",
            "--sam-public-v2",
            "sam.zip",
            "--historical-contracts",
            "historical.parquet",
            "--output-dir",
            "outputs",
        ],
    )

    assert mod.parse_args().as_of == date(2026, 9, 10)


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
    agency: str = "Department of Defense",
    description: str = "Navigation system production",
    generated_award_id: str | None = None,
    naics_code: str = TARGET_NAICS,
    research: str = "",
) -> dict[str, object]:
    return {
        "firm_uei": firm_uei,
        "vendor_name": vendor_name or f"Firm {firm_uei[-1]}",
        "contract_id": award_key,
        "piid": award_key,
        "transaction_unique_id": transaction_id,
        "generated_unique_award_id": generated_award_id or f"GENERATED-{award_key}",
        "award_group_key": award_key,
        "agency": agency,
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
        "description": description,
        "contract_award_type": "A",
        "research": research,
        "naics_code": naics_code,
        "product_or_service_code": "1234",
        "source_fiscal_year": int(action_date[:4]),
    }


def _load_contracts(
    tmp_path: Path,
    cohort: mod.SbirCohort,
    rows: list[dict[str, object]],
    archive_fiscal_years: tuple[int, int] | None = (2009, 2025),
) -> pd.DataFrame:
    path = tmp_path / "target_transactions.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    filter_path = tmp_path / "cohort_ueis.json"
    filter_path.write_text(
        json.dumps({"uei": sorted(cohort.firms["firm_uei"].tolist())}),
        encoding="utf-8",
    )
    manifest = {
        "ok": True,
        "output": {"sha256": mod._sha256(path)},
        "filter": {
            "path": str(filter_path),
            "sha256": mod._sha256(filter_path),
            "target_naics_codes": sorted(mod.TARGET_NAICS),
        },
    }
    if archive_fiscal_years is not None:
        manifest["coverage"] = {"archive_fiscal_years": archive_fiscal_years}
    path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest),
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


def test_historical_text_selection_is_invariant_to_input_row_order(tmp_path: Path) -> None:
    cohort = _cohort(UEI_A)
    rows = [
        _transaction(
            "TX-LATER",
            action_date="2016-02-05",
            obligation_amount=100.0,
            vendor_name="Later Recipient, Inc.",
            agency="Later Agency",
            description="Later description",
            generated_award_id="GENERATED-LATER",
        ),
        _transaction(
            "TX-FIRST",
            action_date="2016-01-05",
            obligation_amount=50.0,
            vendor_name="First Recipient, Inc.",
            agency="First Agency",
            description="First description",
            generated_award_id="GENERATED-FIRST",
        ),
    ]

    in_source_order = _load_contracts(tmp_path, cohort, rows)
    in_reverse_source_order = _load_contracts(tmp_path, cohort, list(reversed(rows)))

    selected_columns = [
        "generated_award_id",
        "recipient_name",
        "awarding_agency",
        "description",
    ]
    assert in_source_order[selected_columns].to_dict("records") == [
        {
            "generated_award_id": "GENERATED-FIRST",
            "recipient_name": "First Recipient, Inc.",
            "awarding_agency": "First Agency",
            "description": "First description",
        }
    ]
    assert in_reverse_source_order[selected_columns].to_dict("records") == in_source_order[
        selected_columns
    ].to_dict("records")


@pytest.mark.parametrize("archive_fiscal_years", [None, (2016, 2025), (2009, 2024)])
def test_historical_ledger_requires_declared_fy2009_archive_coverage(
    tmp_path: Path,
    archive_fiscal_years: tuple[int, int] | None,
) -> None:
    cohort = _cohort(UEI_A)

    with pytest.raises(ValueError, match="archive coverage|archive fiscal years"):
        _load_contracts(
            tmp_path,
            cohort,
            [
                _transaction(
                    "TX-2016-ONLY",
                    action_date="2016-01-05",
                    obligation_amount=100.0,
                )
            ],
            archive_fiscal_years=archive_fiscal_years,
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
    assert (
        firm["first_post_phase_ii_target_origin_award_maximum_award_gross_positive_obligations"]
        == 50.0
    )


def test_zero_post_phase_ii_origin_awards_keep_sensitivity_schema(tmp_path: Path) -> None:
    cohort = _cohort(UEI_A)
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-PRE",
                action_date="2014-06-01",
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

    firm = tables["firm_evidence"].iloc[0]
    assert pd.isna(firm["first_post_phase_ii_target_origin_award_date"])
    assert pd.isna(
        firm["first_post_phase_ii_target_origin_award_maximum_award_gross_positive_obligations"]
    )
    sensitivity = tables["transition_threshold_sensitivity"]
    assert not sensitivity.empty
    assert (sensitivity["entities"] == 0).all()


def test_phase_iii_marker_awards_are_counted_at_award_grain(tmp_path: Path) -> None:
    cohort = _cohort(UEI_A)
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-PHASE-III-ONE",
                award_key="PHASE-III-AWARD",
                action_date="2016-01-05",
                obligation_amount=100.0,
                naics_code=TARGET_NAICS,
                research="SR3",
            ),
            _transaction(
                "TX-PHASE-III-TWO",
                award_key="PHASE-III-AWARD",
                action_date="2016-01-05",
                obligation_amount=100.0,
                naics_code="334419",
                research="SR3",
            ),
        ],
    )

    summary, tables = mod.build_archive_analysis_tables(
        cohort=cohort,
        contracts=contracts,
        sam=_empty_sam(),
        recent=_empty_recent(),
        analysis_date=date(2020, 1, 1),
        coverage_end=pd.Timestamp("2020-01-01"),
    )

    firm = tables["firm_evidence"].iloc[0]
    assert len(contracts) == 2
    assert int(firm["target_prime_awards"]) == 1
    assert int(firm["phase_iii_marker_awards"]) == 1
    assert summary["positive_target_phase_iii_marker_entities"] == 1


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
        "later_legal_event_type": "merger",
        "later_legal_event_date": "2019-01-02",
        "later_legal_event_date_basis": "filed",
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
    assert candidates.loc[0, "later_legal_event_date_basis"] == "filed"
    assert bool(candidates.loc[0, "priority_review_tranche"])
    assert summary["identity_review_candidate_entities"] == 1
    assert summary["identity_reviewed_candidate_entities"] == 1
    assert summary["identity_review_unreviewed_rows"] == 0


def test_temporal_split_review_requires_a_primary_attribution_boundary(
    tmp_path: Path,
) -> None:
    sbir_name = f"Firm {UEI_A[-1]}"
    contract_name = "Successor Corporation"
    review = dict.fromkeys(mod.IDENTITY_CROSSWALK_COLUMNS, "")
    review.update(
        {
            "firm_uei": UEI_A,
            "sbir_name_key": mod._identity_name_key(sbir_name),
            "contract_name_key": mod._identity_name_key(contract_name),
            "sbir_display_name": sbir_name,
            "contract_recipient_name": contract_name,
            "entity_same_firm": "N",
            "corporate_relation": "acquisition",
            "corporate_event_date_basis": "unknown",
            "successor_or_acquirer_name": contract_name,
            "contract_relationship": "not_established",
            "attribution_treatment": "temporal_split_required",
            "review_confidence": "H",
            "evidence_source": "official_company",
            "evidence_locator": "https://example.test/acquisition",
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-09-10",
        }
    )
    crosswalk_path = tmp_path / "identity_crosswalk.csv"
    pd.DataFrame([review], columns=mod.IDENTITY_CROSSWALK_COLUMNS).to_csv(
        crosswalk_path,
        index=False,
    )

    with pytest.raises(ValueError, match="temporal_split_required.*attribution boundary"):
        mod.load_identity_crosswalk(crosswalk_path)


def test_identity_annotations_do_not_merge_successor_uei_dollars_into_exact_headlines(
    tmp_path: Path,
) -> None:
    cohort = _cohort(UEI_A, UEI_B)
    contract_name = "Successor Corporation"
    contracts = _load_contracts(
        tmp_path,
        cohort,
        [
            _transaction(
                "TX-ORIGINAL-UEI",
                firm_uei=UEI_A,
                award_key="ORIGINAL-UEI-AWARD",
                action_date="2016-01-05",
                obligation_amount=100.0,
                vendor_name=contract_name,
            ),
            _transaction(
                "TX-SUCCESSOR-UEI",
                firm_uei=UEI_B,
                award_key="SUCCESSOR-UEI-AWARD",
                action_date="2016-01-05",
                obligation_amount=900.0,
                vendor_name=contract_name,
            ),
        ],
    )
    sbir_name = f"Firm {UEI_A[-1]}"
    review = dict.fromkeys(mod.IDENTITY_CROSSWALK_COLUMNS, "")
    review.update(
        {
            "firm_uei": UEI_A,
            "sbir_name_key": mod._identity_name_key(sbir_name),
            "contract_name_key": mod._identity_name_key(contract_name),
            "sbir_display_name": sbir_name,
            "contract_recipient_name": contract_name,
            "entity_same_firm": "N",
            "corporate_relation": "acquisition",
            "corporate_event_date": "2018-01-01",
            "corporate_event_date_basis": "closed",
            "successor_or_acquirer_name": contract_name,
            "contract_relationship": "not_established",
            "attribution_treatment": "temporal_split_required",
            "review_confidence": "H",
            "evidence_source": "official_company",
            "evidence_locator": "https://example.test/acquisition",
            "reviewer": "test-reviewer",
            "reviewed_at": "2026-09-10",
        }
    )
    crosswalk_path = tmp_path / "identity_crosswalk.csv"
    pd.DataFrame([review], columns=mod.IDENTITY_CROSSWALK_COLUMNS).to_csv(
        crosswalk_path,
        index=False,
    )
    reviews, _ = mod.load_identity_crosswalk(crosswalk_path)

    summary, tables = mod.build_archive_analysis_tables(
        cohort=cohort,
        contracts=contracts,
        sam=_empty_sam(),
        recent=_empty_recent(),
        analysis_date=date(2020, 1, 1),
        coverage_end=pd.Timestamp("2020-01-01"),
        identity_reviews=reviews,
    )

    firm_evidence = tables["firm_evidence"].set_index("firm_uei")
    candidates = tables["identity_review_candidates"].set_index("firm_uei")
    assert firm_evidence.loc[UEI_A, "target_gross_positive_obligations"] == 100.0
    assert firm_evidence.loc[UEI_B, "target_gross_positive_obligations"] == 900.0
    assert "attribution_treatment" not in firm_evidence.columns
    assert summary["gross_positive_target_obligations"] == 1_000.0
    assert candidates.loc[UEI_A, "review_state"] == "reviewed_supported"
    assert candidates.loc[UEI_A, "attribution_treatment"] == "temporal_split_required"


# -- SAM Public V2 strict-width / NUL-repair parser ---------------------------
#
# This path determines every SAM target and 8(a) count, so positional drift
# and parser regressions must fail loudly before they change reported counts.

_SAM_BOF = "BOF PUBLIC V2 20260907 20260907 {rows:07d} 0000001"


def _sam_row(
    uei: str,
    *,
    status: str = "A",
    name: str = "Test Firm",
    primary: str = "334511",
    codes: str = "",
    certs: str = "",
    freetext: str = "plain text",
) -> list[str]:
    fields = [""] * 142
    fields[0] = uei
    fields[5] = status
    fields[11] = name
    fields[20] = freetext
    fields[32] = primary
    fields[34] = codes
    fields[117] = certs
    fields[141] = "!end"
    return fields


def _write_sam_zip(tmp_path: Path, rows: list[list[str]], declared: int | None = None) -> Path:
    import zipfile

    declared_rows = len(rows) if declared is None else declared
    lines = [_SAM_BOF.format(rows=declared_rows)]
    lines.extend("|".join(fields) for fields in rows)
    lines.append(f"EOF PUBLIC V2 20260907 20260907 {declared_rows:07d} 0000001")
    path = tmp_path / "sam_public_v2.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("SAM_PUBLIC_UTF-8.dat", "\n".join(lines) + "\n")
    return path


def test_sam_parser_repairs_quoted_pipes_and_counts_at_the_pinned_width(tmp_path: Path) -> None:
    """A quoted free-text pipe makes the raw row wider than 142 under
    QUOTE_NONE; the NUL repair must bring it back to the pinned width, and
    the audit must record exactly one repaired row. Target, non-target,
    expired, and non-SBIR rows must land in the right counters.
    """

    rows = [
        # Active SBIR firm in a target code, 8(a) history with a future exit
        # date (current), and a NUL-quoted literal pipe in free text.
        _sam_row(
            UEI_A,
            certs="A6~A620270101",
            freetext="\x00Sales | Engineering\x00",
        ),
        # Expired SBIR firm in a target code: any-status but not active.
        _sam_row(UEI_B, status="E", primary="336414"),
        # Active SBIR firm with no target code: matched, no evidence record.
        _sam_row("YZABCDEFGHIJ", primary="541715"),
        # Non-SBIR UEI in a target code: skipped entirely.
        _sam_row("AAAABBBBCCCC", primary="332992"),
    ]
    path = _write_sam_zip(tmp_path, rows)

    result = mod.load_sam_target_evidence(path, {UEI_A, UEI_B, "YZABCDEFGHIJ"})

    audit = result.audit
    assert audit["declared_rows"] == audit["observed_rows"] == 4
    assert audit["nul_quoted_pipe_rows_repaired"] == 1
    # The quoted row shows up over-width raw (143 fields) and repaired to 142.
    assert audit["raw_pipe_field_counts"]["143"] == 1
    assert audit["repaired_field_counts"]["142"] == 4
    assert audit["exact_uei_sbir_firms_in_sam"] == 3
    assert audit["exact_uei_sbir_firms_in_active_sam"] == 2
    assert audit["target_sbir_firms_any_status"] == 2
    assert audit["target_sbir_firms_active"] == 1
    assert audit["target_sbir_firms_active_with_8a_history_indicator"] == 1
    assert audit["target_sbir_firms_active_with_current_8a_indicator"] == 1

    evidence = result.evidence.set_index("firm_uei")
    assert set(evidence.index) == {UEI_A, UEI_B}
    assert bool(evidence.loc[UEI_A, "sam_8a_history_indicator"]) is True
    assert evidence.loc[UEI_A, "sam_8a_exit_dates"] == "20270101"


def test_sam_parser_raises_on_positional_drift(tmp_path: Path) -> None:
    """A row that is one field short must raise, not shift every later
    column silently. Same for a row whose end marker moved."""

    short = _sam_row(UEI_A)[:-1]
    path = _write_sam_zip(tmp_path, [short])
    with pytest.raises(ValueError, match="expected 142"):
        mod.load_sam_target_evidence(path, {UEI_A})

    unmarked = _sam_row(UEI_A)
    unmarked[141] = "not-the-marker"
    path = _write_sam_zip(tmp_path, [unmarked])
    with pytest.raises(ValueError, match="end marker"):
        mod.load_sam_target_evidence(path, {UEI_A})


def test_sam_parser_raises_on_declared_row_count_mismatch(tmp_path: Path) -> None:
    path = _write_sam_zip(tmp_path, [_sam_row(UEI_A)], declared=2)
    with pytest.raises(ValueError, match="row count mismatch"):
        mod.load_sam_target_evidence(path, {UEI_A})
