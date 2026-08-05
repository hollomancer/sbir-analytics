import pandas as pd
import pytest

from scripts.data.extract_phase_iii_nih_identities import (
    HHS_AGENCY,
    _identifier_poor_hhs_rows,
)


pytestmark = pytest.mark.fast


def _award(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_row_sha256": "a" * 64,
        "agency": HHS_AGENCY,
        "contract": "1R43CA123456-01",
        "agency_tracking_number": "1R43CA123456-01",
        "Award Year": "2020",
        "uei": None,
        "duns": None,
    }
    row.update(overrides)
    return row


def test_identifier_poor_hhs_rows_rejects_missing_source_schema() -> None:
    frame = pd.DataFrame([_award()]).drop(columns="agency_tracking_number")

    with pytest.raises(
        ValueError,
        match=r"SBIR award artifact is missing columns: \['agency_tracking_number'\]",
    ):
        _identifier_poor_hhs_rows(frame)


def test_identifier_poor_hhs_rows_rejects_duplicate_fingerprints() -> None:
    frame = pd.DataFrame([_award(), _award()])

    with pytest.raises(
        ValueError,
        match="Identifier-poor HHS SBIR source-row fingerprints are not unique",
    ):
        _identifier_poor_hhs_rows(frame)


def test_identifier_poor_hhs_rows_selects_only_unidentified_hhs_awards() -> None:
    selected = _award()
    identified = _award(
        source_row_sha256="b" * 64,
        uei="ABC123DEF4G5",
    )
    other_agency = _award(
        source_row_sha256="c" * 64,
        agency="Department of Defense",
    )

    result = _identifier_poor_hhs_rows(pd.DataFrame([selected, identified, other_agency]))

    assert result["source_row_sha256"].tolist() == ["a" * 64]
    assert result["award_year"].tolist() == ["2020"]
    assert "Award Year" not in result.columns
