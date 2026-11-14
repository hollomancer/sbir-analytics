import csv
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from sbir_etl.extractors.sbir_award_export import (
    SBIR_GOV_SOURCE_COLUMNS,
    VerifiedAwardExport,
    ordered_columns_sha256,
)
from sbir_etl.models.award_export import AwardExportSourceMetadata
from scripts.data import sba_annual_report_tables as study


pytestmark = pytest.mark.fast


def _row(**overrides: str) -> list[str]:
    values = dict.fromkeys(SBIR_GOV_SOURCE_COLUMNS, "")
    values.update(
        {
            "Company": "Example Corp",
            "Award Year": "2022",
            "Program": "SBIR",
            "Phase": "Phase I",
            "State": "Virginia",
            "Award Amount": "100",
        }
    )
    values.update(overrides)
    return [values[column] for column in SBIR_GOV_SOURCE_COLUMNS]


def _metadata() -> AwardExportSourceMetadata:
    return AwardExportSourceMetadata(
        source_url="https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
        retrieved_at=datetime(2026, 9, 17, tzinfo=UTC),
        upstream_date_unknown_reason="Test fixture has no upstream publication date.",
        sha256="a" * 64,
        size_bytes=1,
        row_count=2,
        column_count=len(SBIR_GOV_SOURCE_COLUMNS),
        ordered_schema_sha256=ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
        retrieval_tool="pytest",
        retrieval_tool_version=pytest.__version__,
        operator_identity="automation:test",
        access_license_note="Synthetic test fixture.",
    )


def test_study_view_uses_verified_loader_and_declared_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    rows = [_row(), _row(**{"Award Year": "2019", "State": "Maryland"})]
    frame = pd.DataFrame(rows, columns=SBIR_GOV_SOURCE_COLUMNS, dtype="object")
    calls: list[tuple[Path, Path]] = []

    def fake_verified(source_path: Path, metadata_path: Path) -> VerifiedAwardExport:
        calls.append((source_path, metadata_path))
        return VerifiedAwardExport(frame, _metadata(), source_path, metadata_path)

    monkeypatch.setattr(study, "load_verified_award_export", fake_verified)

    selected, metadata = study.load_award_export(export, sidecar, report_years=(2022,))

    assert calls == [(export, sidecar)]
    assert selected["report_year"].tolist() == [2022]
    assert selected["jurisdiction"].tolist() == ["VA"]
    assert metadata.award_grain.value == "export-row-v1"


def test_study_view_rejects_invalid_nonblank_award_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    frame = pd.DataFrame([_row(**{"Award Year": "FY22"})], columns=SBIR_GOV_SOURCE_COLUMNS)

    monkeypatch.setattr(
        study,
        "load_verified_award_export",
        lambda source_path, metadata_path: VerifiedAwardExport(
            frame, _metadata(), source_path, metadata_path
        ),
    )

    with pytest.raises(ValueError, match=r"Award Year.*CSV record 2.*'FY22'"):
        study.load_award_export(export, sidecar)


def test_external_input_reference_is_portable(tmp_path: Path) -> None:
    path = tmp_path / "award_data.csv"

    assert study._repository_relative(path) == "external-input/award_data.csv"


def test_fixture_writer_uses_the_declared_schema(tmp_path: Path) -> None:
    """Keep the fixture contract readable by the canonical CSV parser."""

    path = tmp_path / "award_data.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SBIR_GOV_SOURCE_COLUMNS)
        writer.writerow(_row())

    with path.open(encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == SBIR_GOV_SOURCE_COLUMNS
