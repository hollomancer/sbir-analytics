import pandas as pd
import pytest

from sbir_etl.identity.sbir_awards import (
    SBIR_AWARD_KEY_VERSION,
    SbirAwardKeyProfile,
    sbir_award_grain_key,
    sbir_award_public_id,
    stable_sbir_award_id,
)


def _award(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Agency Tracking Number": "TRACK-1",
        "Contract": "CONTRACT-1",
        "Agency": "DEFENSE",
        "Branch": "NAVY",
        "Phase": "Phase II",
        "Program": "SBIR",
        "Proposal Award Date": "2026-06-12",
        "Solicitation Number": "SOL-1",
        "UEI": "UEI000000001",
        "Award Title": "Mutable title",
        "Award Amount": "$1,000,000",
    }
    row.update(overrides)
    return row


def test_profile_name_is_the_persisted_key_version() -> None:
    assert SBIR_AWARD_KEY_VERSION == SbirAwardKeyProfile.SBIR_SOURCE_V2.value


def test_mutable_fields_do_not_change_award_grain() -> None:
    original = sbir_award_grain_key(_award())
    edited = sbir_award_grain_key(
        _award(
            **{
                "Award Title": "Revised title",
                "Abstract": "Revised abstract",
                "Award Amount": "$2,000,000",
                "Contract End Date": "2028-01-01",
            }
        )
    )

    assert edited == original


def test_source_lineage_and_date_forms_define_stable_grain() -> None:
    iso = sbir_award_grain_key(_award())
    us_date = sbir_award_grain_key(_award(**{"Proposal Award Date": "06/12/2026"}))
    timestamp = sbir_award_grain_key(_award(**{"Proposal Award Date": pd.Timestamp("2026-06-12")}))
    different_phase = sbir_award_grain_key(_award(Phase="Phase I"))

    assert iso == us_date == timestamp
    assert different_phase != iso


def test_existing_key_requires_the_exact_profile_version() -> None:
    assert (
        sbir_award_grain_key({"award_key": "EXISTING", "award_key_version": SBIR_AWARD_KEY_VERSION})
        == "EXISTING"
    )
    with pytest.raises(ValueError, match="pre-migration award_key"):
        sbir_award_grain_key({"award_key": "OLD"})


def test_public_id_is_readable_but_not_required_for_grain() -> None:
    row = _award(**{"Agency Tracking Number": None, "Contract": None})

    assert sbir_award_public_id(row) is None
    assert stable_sbir_award_id(row).startswith("sbir-")
