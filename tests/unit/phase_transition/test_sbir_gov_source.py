import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_transition.phase_ii import _prepare_sbir_gov_rows
from sbir_analytics.assets.phase_transition.sbir_gov_source import (
    SBIR_GOV_SOURCE_COLUMNS,
    SbirGovSourceError,
    canonicalize_sbir_gov_rows,
    materialize_sbir_gov_history,
    sha256_file,
    verify_sbir_gov_materialization,
)


pytestmark = pytest.mark.fast


def _row(**overrides: str | None) -> dict[str, str | None]:
    row: dict[str, str | None] = dict.fromkeys(SBIR_GOV_SOURCE_COLUMNS, "")
    row.update(
        {
            "Company": "Example Corp",
            "Award Title": "Example work",
            "Agency": "Department of Defense",
            "Branch": "Navy",
            "Phase": "Phase II",
            "Program": "SBIR",
            "Agency Tracking Number": "TRACK-1",
            "Award Year": "2020",
            "Award Amount": "100.0000",
        }
    )
    row.update(overrides)
    return row


def _frame(*rows: dict[str, str | None]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SBIR_GOV_SOURCE_COLUMNS, dtype="object")


def _expected_digest(row: dict[str, str | None]) -> str:
    values = [row[column] for column in SBIR_GOV_SOURCE_COLUMNS]
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_exact_duplicates_only_are_collapsed() -> None:
    original = _row()
    distinct = _row(**{"Contact Phone": "202-555-0100"})

    result, stats = canonicalize_sbir_gov_rows(_frame(original, original.copy(), distinct))

    assert len(result) == 2
    assert stats["raw_rows"] == 3
    assert stats["retained_rows"] == 2
    assert stats["exact_duplicate_rows_collapsed"] == 1
    assert set(result["source_row_sha256"]) == {
        _expected_digest(original),
        _expected_digest(distinct),
    }


def test_cross_phase_reuse_keeps_original_source_id() -> None:
    phase_i = _row(**{"Phase": "Phase I"})
    phase_ii = _row(**{"Phase": "Phase II"})

    result, stats = canonicalize_sbir_gov_rows(_frame(phase_i, phase_ii))

    assert result["award_id"].tolist() == ["TRACK-1", "TRACK-1"]
    assert stats["collision_groups"] == 0
    assert stats["generated_id_rows"] == 0


def test_same_base_phase_and_blank_base_get_full_fingerprints() -> None:
    first = _row(**{"Company": "Argon", "Agency Tracking Number": "Navy38356"})
    second = _row(**{"Company": "Alphatech", "Agency Tracking Number": "NAVY38356"})
    blank = _row(**{"Company": "No source ID", "Agency Tracking Number": "", "Contract": ""})

    result, stats = canonicalize_sbir_gov_rows(_frame(first, second, blank))
    by_company = result.set_index("company_name")

    for source in (first, second):
        value = by_company.loc[source["Company"], "award_id"]
        assert value == f"SBIRGOV:NAVY38356:{_expected_digest(source)}"
        assert len(value.rsplit(":", 1)[1]) == 64
    blank_id = by_company.loc["No source ID", "award_id"]
    assert blank_id == f"SBIRGOV:MISSING:{_expected_digest(blank)}"
    assert pd.isna(by_company.loc["No source ID", "source_award_id"])
    assert stats["blank_base_rows"] == 1
    assert stats["collision_groups"] == 1
    assert stats["collision_rows"] == 2
    assert stats["generated_id_rows"] == 3


def test_canonicalization_is_row_order_independent() -> None:
    rows = [
        _row(**{"Company": "Argon", "Agency Tracking Number": "Navy38356"}),
        _row(**{"Company": "Alphatech", "Agency Tracking Number": "NAVY38356"}),
        _row(**{"Company": "Unique", "Agency Tracking Number": "UNIQUE"}),
    ]

    forward, forward_stats = canonicalize_sbir_gov_rows(_frame(*rows))
    reverse, reverse_stats = canonicalize_sbir_gov_rows(_frame(*reversed(rows)))

    pd.testing.assert_frame_equal(forward, reverse)
    assert forward_stats == reverse_stats


def test_case_and_whitespace_changes_change_source_digest() -> None:
    exact = _row(**{"Company": "Example Corp"})
    changed = _row(**{"Company": " example corp "})

    result, _ = canonicalize_sbir_gov_rows(_frame(exact, changed))

    assert set(result["source_row_sha256"]) == {
        _expected_digest(exact),
        _expected_digest(changed),
    }
    assert result["source_row_sha256"].nunique() == 2


def _write_csv(path: Path, rows: list[dict[str, str | None]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(SBIR_GOV_SOURCE_COLUMNS)
        for row in rows:
            writer.writerow([row[column] for column in SBIR_GOV_SOURCE_COLUMNS])


def test_manifest_verifier_rejects_checksum_and_schema_tampering(tmp_path: Path) -> None:
    source_path = tmp_path / "award_data.csv"
    output_path = tmp_path / "awards.parquet"
    _write_csv(source_path, [_row()])
    materialize_sbir_gov_history(source_path, output_path)
    frame = pd.read_parquet(output_path)

    verified = verify_sbir_gov_materialization(output_path, frame)
    assert verified["ok"] is True

    checks_path = output_path.with_suffix(".checks.json")
    original = json.loads(checks_path.read_text(encoding="utf-8"))
    checksum_tamper = {**original, "output": {**original["output"], "sha256": "0" * 64}}
    checks_path.write_text(json.dumps(checksum_tamper), encoding="utf-8")
    with pytest.raises(SbirGovSourceError, match="checksum"):
        verify_sbir_gov_materialization(output_path, frame)

    schema_tamper = {**original, "schema_version": "unsupported"}
    checks_path.write_text(json.dumps(schema_tamper), encoding="utf-8")
    with pytest.raises(SbirGovSourceError, match="unsupported schema"):
        verify_sbir_gov_materialization(output_path, frame)

    grain_tamper = json.loads(json.dumps(original))
    grain_tamper["source_grain"]["fingerprint"]["digest_hex_characters"] = 12
    checks_path.write_text(json.dumps(grain_tamper), encoding="utf-8")
    with pytest.raises(SbirGovSourceError, match="fingerprint contract"):
        verify_sbir_gov_materialization(output_path, frame)

    assert original["output"]["sha256"] == sha256_file(output_path)


@pytest.mark.parametrize(
    "tamper",
    [
        [],
        {"source_provenance": []},
        {"source_grain": None},
        {"output": "not-an-object"},
    ],
)
def test_manifest_verifier_rejects_non_object_structure(tmp_path: Path, tamper) -> None:
    source_path = tmp_path / "award_data.csv"
    output_path = tmp_path / "awards.parquet"
    _write_csv(source_path, [_row()])
    manifest = materialize_sbir_gov_history(source_path, output_path)
    frame = pd.read_parquet(output_path)

    invalid = tamper if isinstance(tamper, list) else {**manifest, **tamper}
    output_path.with_suffix(".checks.json").write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(SbirGovSourceError, match="JSON object"):
        verify_sbir_gov_materialization(output_path, frame)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("source_provenance", "bytes"),
        ("source_grain", "raw_rows"),
        ("output", "rows"),
    ],
)
def test_manifest_verifier_rejects_boolean_counts(tmp_path: Path, section: str, field: str) -> None:
    source_path = tmp_path / "award_data.csv"
    output_path = tmp_path / "awards.parquet"
    _write_csv(source_path, [_row()])
    manifest = materialize_sbir_gov_history(source_path, output_path)
    frame = pd.read_parquet(output_path)
    manifest[section][field] = True
    output_path.with_suffix(".checks.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SbirGovSourceError, match="invalid"):
        verify_sbir_gov_materialization(output_path, frame)


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("company_uei", "TAMPEREDUEI1"),
        ("company_duns", "000000000"),
        ("contract_end_date", "2099-12-31"),
        ("data_source", "other"),
        ("data_source_url", "https://example.invalid/awards.csv"),
    ],
)
def test_manifest_verifier_rejects_tampered_derived_fields(
    tmp_path: Path, field: str, tampered_value: str
) -> None:
    source_path = tmp_path / "award_data.csv"
    output_path = tmp_path / "awards.parquet"
    source = _row(
        **{
            "UEI": "ABCDEFGHIJKL",
            "Duns": "123456789",
            "Contract End Date": "2024-06-30",
        }
    )
    _write_csv(source_path, [source])
    manifest = materialize_sbir_gov_history(source_path, output_path)
    frame = pd.read_parquet(output_path)
    frame.loc[:, field] = tampered_value
    frame.to_parquet(output_path, index=False)
    manifest["output"]["sha256"] = sha256_file(output_path)
    manifest["output"]["bytes"] = output_path.stat().st_size
    output_path.with_suffix(".checks.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SbirGovSourceError, match="invalid"):
        verify_sbir_gov_materialization(output_path, frame)


def test_blank_base_stays_null_in_phase_ii_integration() -> None:
    blank = _row(**{"Agency Tracking Number": "", "Contract": "", "UEI": "ABCDEFGHIJKL"})
    canonical, _ = canonicalize_sbir_gov_rows(_frame(blank))

    prepared = _prepare_sbir_gov_rows(canonical)

    assert len(prepared) == 1
    assert prepared.iloc[0]["award_id"].startswith("SBIRGOV:MISSING:")
    assert pd.isna(prepared.iloc[0]["source_award_id"])
    assert prepared.iloc[0]["source_row_sha256"] == _expected_digest(blank)
