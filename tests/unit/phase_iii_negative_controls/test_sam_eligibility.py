"""Tests for exact SAM identity envelopes and three-way eligibility."""

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.sam_eligibility import _DisjointSet
from sbir_analytics.assets.phase_iii_negative_controls import (
    IdentityRecoveryError,
    build_sam_eligibility_table,
    exclude_fpds_coded_awardees,
    exclude_phase_ii_awardees,
    require_reliable_sam_eligibility,
    sam_eligibility_gate,
    summarize_sam_eligibility,
    summarize_sam_exclusion_reasons,
)


def _fingerprint(character: str) -> str:
    return character * 64


def _sbir_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source = pd.DataFrame(
        {
            "source_row_sha256": [_fingerprint(value) for value in "abcde"],
            "uei": ["DIRECTUEI001", None, None, None, None],
            "duns": [None, "222222222", None, None, None],
        }
    )
    recovery = pd.DataFrame(
        {
            "source_row_sha256": [_fingerprint(value) for value in "cde"],
            "recovery_status": [
                "resolved_authoritative",
                "unresolved_no_match",
                "unresolved_conflict",
            ],
            "resolved_ueis": [("RECOVERUEI01",), (), ()],
            "resolved_duns": [(), (), ()],
        }
    )
    quarantine = pd.DataFrame(
        {
            "source_row_sha256": [_fingerprint("d"), _fingerprint("e")],
            "name_state_key": ["NAME COLLISION LLC|VA", "SECOND NAME INC|MD"],
            "address_zip_key": ["10 EXACT ROAD|22030", "20 SECOND STREET|20850"],
            "has_name_state_key": [True, True],
            "has_address_zip_key": [True, True],
            "coverage_category": ["both", "both"],
        }
    )
    return source, recovery, quarantine


def _sam_row(
    uei: str,
    *,
    duns: str | None = None,
    cage: str | None = None,
    legal_name: str = "Unrelated Company",
    dba_name: str | None = None,
    line_1: str = "1 Other Way",
    line_2: str | None = None,
    state: str = "DC",
    zip_code: str = "20001",
) -> dict[str, object]:
    return {
        "unique_entity_id": uei,
        "duns_number": duns,
        "cage_code": cage,
        "legal_business_name": legal_name,
        "dba_name": dba_name,
        "physical_address_line_1": line_1,
        "physical_address_line_2": line_2,
        "physical_address_state": state,
        "physical_address_zip_postal_code": zip_code,
    }


def _build(sam: pd.DataFrame, *, links: pd.DataFrame | None = None) -> pd.DataFrame:
    source, recovery, quarantine = _sbir_inputs()
    return build_sam_eligibility_table(
        sam,
        source,
        recovery,
        quarantine,
        identity_links=links,
    )


def _link(*, uei=None, duns=None, cage=None) -> dict[str, object]:
    return {
        "uei": uei,
        "duns": duns,
        "cage": cage,
        "official_record_id": "OFFICIAL-1",
        "source_digest": "f" * 64,
        "snapshot_date": "2026-02-28",
    }


def test_exact_uei_and_duns_intersections_confirm_sbir() -> None:
    result = _build(
        pd.DataFrame(
            [
                _sam_row("DIRECTUEI001"),
                _sam_row("CANDIDATE002", duns="222-222-222"),
            ]
        )
    )

    assert result["eligibility_status"].tolist() == ["confirmed_sbir", "confirmed_sbir"]
    by_uei = {row.candidate_ueis[0]: row for row in result.itertuples(index=False)}
    assert by_uei["DIRECTUEI001"].matched_sbir_ueis == ("DIRECTUEI001",)
    assert by_uei["CANDIDATE002"].matched_sbir_duns == ("222222222",)


def test_disjoint_set_find_handles_a_deep_component_iteratively() -> None:
    identifiers = _DisjointSet()
    for value in range(2_500, 0, -1):
        identifiers.union_all((f"TOKEN:{value:05d}", f"TOKEN:{value - 1:05d}"))

    assert identifiers.find("TOKEN:02500") == "TOKEN:00000"
    assert identifiers.parent["TOKEN:02500"] == "TOKEN:00000"


def test_exact_cage_cooccurrence_can_extend_an_identifier_envelope() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE003", cage="A1B2C")])
    links = pd.DataFrame([_link(duns="222222222", cage="A1B2C")])

    result = _build(sam, links=links)

    assert result.iloc[0].eligibility_status == "confirmed_sbir"
    assert result.iloc[0].candidate_duns == ("222222222",)


def test_disconnected_identifier_does_not_join_candidate() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE004", cage="A1B2C")])
    links = pd.DataFrame([_link(duns="222222222", cage="Z9Y8X")])

    result = _build(sam, links=links)

    assert result.iloc[0].eligibility_status == "eligible_screened_negative"


def test_any_exact_fpds_sbir_sttr_code_conservatively_excludes_candidate() -> None:
    eligibility = _build(pd.DataFrame([_sam_row("CANDIDATE020")]))
    contracts = pd.DataFrame(
        {
            "vendor_uei": ["CANDIDATE020", "CANDIDATE020", "UNRELATED001"],
            "research": ["sr2", None, "ST3"],
        }
    )

    result = exclude_fpds_coded_awardees(eligibility, contracts)

    assert result.iloc[0].eligibility_status == "confirmed_sbir"
    assert result.iloc[0].matched_fpds_sbir_sttr_ueis == ("CANDIDATE020",)
    assert result.iloc[0].exclusion_reasons == ("fpds_sbir_sttr_code_intersection",)


def test_non_sbir_research_code_does_not_change_eligibility() -> None:
    eligibility = _build(pd.DataFrame([_sam_row("CANDIDATE021")]))

    result = exclude_fpds_coded_awardees(
        eligibility,
        pd.DataFrame({"vendor_uei": ["CANDIDATE021"], "research": ["RD"]}),
    )

    assert result.iloc[0].eligibility_status == "eligible_screened_negative"
    assert result.iloc[0].matched_fpds_sbir_sttr_ueis == ()


def test_exact_phase_ii_uei_conservatively_excludes_candidate() -> None:
    eligibility = _build(pd.DataFrame([_sam_row("CANDIDATE022")]))

    result = exclude_phase_ii_awardees(
        eligibility,
        pd.DataFrame({"recipient_uei": ["candidate022", None]}),
    )

    assert result.iloc[0].eligibility_status == "confirmed_sbir"
    assert result.iloc[0].matched_phase_ii_ueis == ("CANDIDATE022",)
    assert result.iloc[0].exclusion_reasons == ("phase_ii_uei_intersection",)


def test_identity_link_without_provenance_fails_closed() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE015", cage="A1B2C")])
    links = pd.DataFrame([{"uei": None, "duns": "222222222", "cage": "A1B2C"}])

    with pytest.raises(IdentityRecoveryError, match="official_record_id"):
        _build(sam, links=links)


def test_identity_link_requires_exact_cooccurrence() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE016", cage="A1B2C")])
    links = pd.DataFrame([_link(duns="222222222")])

    with pytest.raises(IdentityRecoveryError, match="at least two"):
        _build(sam, links=links)


@pytest.mark.parametrize(
    "sam_row",
    [
        _sam_row("CANDIDATE005", legal_name="Name, Collision LLC", state="VA"),
        _sam_row("CANDIDATE006", line_1="10 Exact Road", zip_code="22030-1234"),
        _sam_row("CANDIDATE007", dba_name="Second Name Inc", state="MD"),
    ],
)
def test_exact_name_or_address_collision_is_indeterminate(sam_row) -> None:
    result = _build(pd.DataFrame([sam_row]))

    assert result.iloc[0].eligibility_status == "indeterminate_possible_sbir"


def test_name_collision_never_joins_identity_components() -> None:
    sam = pd.DataFrame(
        [
            _sam_row("CANDIDATE008", legal_name="Same Name LLC", state="VA"),
            _sam_row("CANDIDATE009", legal_name="Same Name LLC", state="VA"),
        ]
    )

    result = _build(sam)

    assert len(result) == 2
    assert result["candidate_ueis"].tolist() == [("CANDIDATE008",), ("CANDIDATE009",)]


def test_confirmed_status_takes_precedence_over_quarantine_collision() -> None:
    sam = pd.DataFrame([_sam_row("DIRECTUEI001", legal_name="Name Collision LLC", state="VA")])

    result = _build(sam)

    assert result.iloc[0].eligibility_status == "confirmed_sbir"
    assert set(result.iloc[0].exclusion_reasons) == {
        "resolved_uei_intersection",
        "unresolved_name_state_collision",
    }


def test_multiple_sam_rows_in_one_component_retain_aliases() -> None:
    sam = pd.DataFrame(
        [
            _sam_row("CANDIDATE010", cage="C1D2E", legal_name="Old Legal Name"),
            _sam_row(
                "CANDIDATE010",
                cage="C1D2E",
                legal_name="Name Collision LLC",
                state="VA",
            ),
        ]
    )

    result = _build(sam)

    assert len(result) == 1
    assert result.iloc[0].sam_source_rows == 2
    assert result.iloc[0].eligibility_status == "indeterminate_possible_sbir"


def test_blank_alias_components_never_match() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE011", legal_name="", line_1="", state="", zip_code="")])

    result = _build(sam)

    assert result.iloc[0].eligibility_status == "indeterminate_possible_sbir"
    assert result.iloc[0].exclusion_reasons == ("missing_comparable_name_state_key",)
    assert result.iloc[0].name_state_keys == ()
    assert result.iloc[0].address_zip_keys == ()
    assert sam_eligibility_gate(result)["passed"] is True
    require_reliable_sam_eligibility(result)


def test_address_only_candidate_is_indeterminate_without_comparable_name_key() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE018", legal_name="", state="")])

    result = _build(sam)

    assert result.iloc[0].eligibility_status == "indeterminate_possible_sbir"
    assert result.iloc[0].name_state_keys == ()
    assert result.iloc[0].address_zip_keys == ("1 OTHER WAY|20001",)
    assert result.iloc[0].exclusion_reasons == ("missing_comparable_name_state_key",)


def test_gate_rejects_screened_negative_without_comparable_name_key() -> None:
    result = _build(
        pd.DataFrame([_sam_row("CANDIDATE019", legal_name="", line_1="", state="", zip_code="")])
    )
    result.loc[0, "eligibility_status"] = "eligible_screened_negative"

    gate = sam_eligibility_gate(result)

    assert gate["passed"] is False
    assert gate["screened_negative_firms_without_comparable_name_state_key"] == 1
    with pytest.raises(IdentityRecoveryError, match="eligibility is unreliable"):
        require_reliable_sam_eligibility(result)


def test_invalid_or_missing_sam_uei_fails_closed() -> None:
    with pytest.raises(IdentityRecoveryError, match="valid UEI"):
        _build(pd.DataFrame([_sam_row("too-short")]))


def test_empty_sam_frame_fails_closed() -> None:
    with pytest.raises(IdentityRecoveryError, match="is empty"):
        _build(pd.DataFrame(columns=_sam_row("CANDIDATE017").keys()))


def test_source_schema_drift_fails_closed() -> None:
    sam = pd.DataFrame([_sam_row("CANDIDATE012")]).drop(columns="dba_name")

    with pytest.raises(IdentityRecoveryError, match="dba_name"):
        _build(sam)


def test_malformed_source_row_fingerprint_fails_closed() -> None:
    """A truncated fingerprint must raise, not screen as a distinct source row.

    The quarantine audit enforces the strict lowercase 64-hex form, so anything
    looser here would pass this screen and then fail to intersect there — the
    silent direction, which drops a real SBIR row out of the exclusion sets.
    """

    source, recovery, quarantine = _sbir_inputs()
    source.loc[0, "source_row_sha256"] = "abc123"

    with pytest.raises(IdentityRecoveryError, match="complete lowercase SHA-256"):
        build_sam_eligibility_table(
            pd.DataFrame([_sam_row("CANDIDATE015")]),
            source,
            recovery,
            quarantine,
        )


def test_quarantine_schema_drift_fails_closed_at_the_boundary() -> None:
    """Columns the downstream gate needs are declared here, not discovered late."""

    source, recovery, quarantine = _sbir_inputs()
    quarantine = quarantine.drop(columns="coverage_category")

    with pytest.raises(IdentityRecoveryError, match="coverage_category"):
        build_sam_eligibility_table(
            pd.DataFrame([_sam_row("CANDIDATE016")]),
            source,
            recovery,
            quarantine,
        )


def test_recovery_must_cover_exact_identifier_poor_source_set() -> None:
    source, recovery, quarantine = _sbir_inputs()
    recovery = recovery.iloc[:-1]

    with pytest.raises(IdentityRecoveryError, match="cover exactly"):
        build_sam_eligibility_table(
            pd.DataFrame([_sam_row("CANDIDATE013")]),
            source,
            recovery,
            quarantine,
        )


def test_status_and_reason_summaries_include_zero_count_categories() -> None:
    result = _build(
        pd.DataFrame(
            [
                _sam_row("DIRECTUEI001"),
                _sam_row("CANDIDATE014", legal_name="Name Collision LLC", state="VA"),
            ]
        )
    )

    statuses = summarize_sam_eligibility(result)
    reasons = summarize_sam_exclusion_reasons(result)

    assert statuses.to_dict("records") == [
        {"eligibility_status": "confirmed_sbir", "candidate_firms": 1},
        {"eligibility_status": "indeterminate_possible_sbir", "candidate_firms": 1},
        {"eligibility_status": "eligible_screened_negative", "candidate_firms": 0},
    ]
    assert reasons.set_index("exclusion_reason")["candidate_firms"].to_dict() == {
        "resolved_uei_intersection": 1,
        "resolved_duns_intersection": 0,
        "unresolved_name_state_collision": 1,
        "unresolved_address_zip_collision": 0,
        "missing_comparable_name_state_key": 0,
    }
