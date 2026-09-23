from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sbir_etl.models.award_export import (
    AwardExportSourceMetadata,
    AwardGrain,
    FiscalYearBasis,
)


pytestmark = pytest.mark.fast


def test_only_required_versioned_declarations_exist() -> None:
    assert [(member.name, member.value) for member in AwardGrain] == [
        ("EXPORT_ROW_V1", "export-row-v1")
    ]
    assert [(member.name, member.value) for member in FiscalYearBasis] == [
        ("AWARD_YEAR_FIELD_V1", "award-year-field-v1")
    ]
    assert FiscalYearBasis.AWARD_YEAR_FIELD_V1.field_name == "Award Year"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020", 2020),
        (" 2021 ", 2021),
        (2022, 2022),
        ("+2023", 2023),
        ("-1", -1),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_award_year_field_v1_parses_only_its_source_value(
    value: object, expected: int | None
) -> None:
    basis = FiscalYearBasis.AWARD_YEAR_FIELD_V1

    assert basis.parse(value, row_location=7) == expected


@pytest.mark.parametrize("value", ["2020.0", "FY 2020", "2020-01-01", True, 2020.0])
def test_award_year_field_v1_rejects_non_integer_with_location_and_value(value: object) -> None:
    basis = FiscalYearBasis.AWARD_YEAR_FIELD_V1

    with pytest.raises(ValueError) as exc_info:
        basis.parse(value, row_location="CSV record 19")

    message = str(exc_info.value)
    assert "Award Year" in message
    assert "CSV record 19" in message
    assert repr(value) in message


def _metadata(**overrides: object) -> AwardExportSourceMetadata:
    values: dict[str, object] = {
        "source_url": "https://data.www.sbir.gov/award_data.csv",
        "retrieved_at": datetime(2026, 9, 17, 1, 32, tzinfo=UTC),
        "upstream_published_at": datetime(2026, 9, 1, 5, 42, 41, tzinfo=UTC),
        "sha256": "a" * 64,
        "size_bytes": 10,
        "row_count": 2,
        "column_count": 42,
        "ordered_schema_sha256": "b" * 64,
        "retrieval_tool": "curl",
        "retrieval_tool_version": "8.7.1",
        "operator_identity": "automation:test",
        "access_license_note": "Public HTTPS access; no separate license recorded.",
    }
    values.update(overrides)
    return AwardExportSourceMetadata.model_validate(values)


def test_source_metadata_serialization_is_stable_and_complete() -> None:
    metadata = _metadata(upstream_object_version="version-1")

    assert metadata.to_json() == metadata.to_json()
    assert metadata.to_json().endswith("\n")
    assert '"award_grain": "export-row-v1"' in metadata.to_json()
    assert '"operator_identity": "automation:test"' in metadata.to_json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha256", "short"),
        ("ordered_schema_sha256", "z" * 64),
        ("size_bytes", -1),
        ("row_count", -1),
        ("row_count", True),
        ("retrieved_at", datetime(2026, 9, 17, 1, 32)),
        ("retrieval_tool", "   "),
    ],
)
def test_source_metadata_rejects_invalid_identity(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _metadata(**{field: value})


def test_source_metadata_requires_upstream_date_or_explicit_unknown_reason() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        _metadata(upstream_published_at=None)

    unknown = _metadata(
        upstream_published_at=None,
        upstream_date_unknown_reason="Upstream did not publish a source date.",
    )
    assert unknown.upstream_published_at is None

    with pytest.raises(ValidationError, match="exactly one"):
        _metadata(upstream_date_unknown_reason="conflicts with known date")
