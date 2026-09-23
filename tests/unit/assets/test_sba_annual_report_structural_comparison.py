import csv
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from sbir_analytics.assets.sba_annual_report_structural_comparison import producer as study
from sbir_etl.extractors.sbir_award_export import (
    SBIR_GOV_SOURCE_COLUMNS,
    ordered_columns_sha256,
)
from sbir_etl.models.award_export import AwardExportSourceMetadata
from sbir_etl.quality.study_manifest import claim_boundary_sha256
from sbir_etl.utils.data.file_io import file_sha256


pytestmark = pytest.mark.fast


@dataclass(frozen=True)
class FixtureBundle:
    inputs: study.ProductionInputs
    population: pd.DataFrame


def _pin(path: Path, reference: str | None = None) -> study.PinnedFile:
    return study.PinnedFile(
        reference=reference or path.relative_to(path.parents[2]).as_posix(),
        path=path,
        sha256=file_sha256(path),
        size_bytes=path.stat().st_size,
    )


def _award_row(**overrides: str) -> list[str]:
    values = dict.fromkeys(SBIR_GOV_SOURCE_COLUMNS, "")
    values.update(
        {
            "Company": "Fixture Co",
            "Award Year": "2020",
            "Program": "SBIR",
            "Phase": "Phase I",
            "State": "Alaska",
        }
    )
    values.update(overrides)
    return [values[column] for column in SBIR_GOV_SOURCE_COLUMNS]


def _population_frame() -> pd.DataFrame:
    jurisdictions = sorted(set(study.JURISDICTION_BY_NAME.values()))
    rows: list[dict[str, object]] = []
    for report_year in study.REPORT_TABLES:
        for jurisdiction in jurisdictions:
            if report_year == 2022 and jurisdiction == "MH":
                continue
            for program in study.PROGRAMS:
                for phase in study.PHASES:
                    for target in ("published_count", "recomputed_count"):
                        rows.append(
                            {
                                "unit_id": ":".join(
                                    (
                                        target,
                                        str(report_year),
                                        jurisdiction,
                                        program,
                                        phase.replace(" ", "_"),
                                    )
                                ),
                                "target": target,
                                "report_year": report_year,
                                "jurisdiction": jurisdiction,
                                "program": program,
                                "phase": phase,
                            }
                        )
    frame = pd.DataFrame(rows, columns=study.POPULATION_COLUMNS)
    assert len(frame) == study.EXPECTED_VALIDATION_VALUE_COUNT
    return frame


def _captured_frame(year: int) -> pd.DataFrame:
    jurisdictions = sorted(set(study.JURISDICTION_BY_NAME.values()))
    if year == 2022:
        jurisdictions.remove("MH")
    rows = []
    for jurisdiction in jurisdictions:
        sbir_p1 = 1 if year == 2020 and jurisdiction == "AK" else 0
        rows.append(
            {
                "state": jurisdiction,
                "sbir_p1_n": sbir_p1,
                "sbir_p1_usd": "not-used-for-classification",
                "sttr_p1_n": 0,
                "sttr_p1_usd": "not-used-for-classification",
                "sbir_p2_n": 0,
                "sbir_p2_usd": "not-used-for-classification",
                "sttr_p2_n": 0,
                "sttr_p2_usd": "not-used-for-classification",
                "sbir_tot_n": sbir_p1,
                "sbir_tot_usd": "not-used-for-classification",
                "sttr_tot_n": 0,
                "sttr_tot_usd": "not-used-for-classification",
                "all_tot_n": sbir_p1,
                "all_tot_usd": "not-used-for-classification",
            }
        )
    return pd.DataFrame(rows, columns=study.CAPTURED_TABLE_COLUMNS)


def _source_manifest(
    *,
    award_export: study.PinnedFile,
    award_export_metadata: study.PinnedFile,
    annual_reports: tuple[study.AnnualReportSource, ...],
    captured_tables: tuple[study.CapturedTableSource, ...],
    allowed: bool = True,
) -> dict[str, object]:
    sources: list[dict[str, object]] = [
        {
            "source_id": study.AWARD_EXPORT_SOURCE_ID,
            "local_path": award_export.reference,
            "metadata_path": award_export_metadata.reference,
            "sha256": award_export.sha256,
            "size_bytes": award_export.size_bytes,
            "row_count": 3,
            "column_count": len(SBIR_GOV_SOURCE_COLUMNS),
            "ordered_header_sha256": ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
            "durable_uri": "https://example.test/award-export.csv?version=fixture",
        }
    ]
    for source in annual_reports:
        sources.append(
            {
                "source_id": study.ANNUAL_REPORT_SOURCE_IDS[source.report_year],
                "local_path": source.file.reference,
                "sha256": source.file.sha256,
                "size_bytes": source.file.size_bytes,
                "page_count": 1,
                "durable_uri": f"https://example.test/FY{source.report_year}.pdf",
            }
        )
    captured = [
        {
            "source_id": study.CAPTURED_TABLE_SOURCE_IDS[source.report_year],
            "path": source.file.reference,
            "sha256": source.file.sha256,
            "size_bytes": source.file.size_bytes,
            "row_count": source.row_count,
            "column_count": len(study.CAPTURED_TABLE_COLUMNS),
            "ordered_header_sha256": ordered_columns_sha256(study.CAPTURED_TABLE_COLUMNS),
        }
        for source in captured_tables
    ]
    return {
        "schema_version": 1,
        "capture_gate": {
            "allowed": allowed,
            "blockers": [] if allowed else ["Fixture capture gate is deliberately closed."],
            "verified_on": "2026-09-21",
            "verification_note": "Synthetic fixture identities were checked.",
        },
        "sources": sources,
        "captured_tables": captured,
        "award_export_ordered_header": list(SBIR_GOV_SOURCE_COLUMNS),
        "captured_table_header": list(study.CAPTURED_TABLE_COLUMNS),
        "header_fingerprint_procedure": study.HEADER_FINGERPRINT_PROCEDURE,
    }


def _fixture_bundle(tmp_path: Path) -> FixtureBundle:
    root = tmp_path / "repo"
    source_dir = root / "sources"
    study_dir = root / "studies" / study.STUDY_ID
    source_dir.mkdir(parents=True)
    study_dir.mkdir(parents=True)

    export_path = source_dir / "award_data.csv"
    rows = [
        _award_row(),
        _award_row(Company="Fixture Co 2"),
        _award_row(Company="Blank State", State=""),
    ]
    with export_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SBIR_GOV_SOURCE_COLUMNS)
        writer.writerows(rows)
    award_export = _pin(export_path, "sources/award_data.csv")

    metadata_path = source_dir / "award_data.meta.json"
    metadata = AwardExportSourceMetadata(
        source_url="https://example.test/award-export.csv?version=fixture",
        retrieved_at=datetime(2026, 9, 17, tzinfo=UTC),
        upstream_date_unknown_reason="Synthetic fixture has no publication date.",
        upstream_object_version="fixture-v1",
        sha256=award_export.sha256,
        size_bytes=award_export.size_bytes,
        row_count=len(rows),
        column_count=len(SBIR_GOV_SOURCE_COLUMNS),
        ordered_schema_sha256=ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
        retrieval_tool="pytest",
        retrieval_tool_version=pytest.__version__,
        operator_identity="automation:test",
        access_license_note="Synthetic fixture.",
    )
    metadata_path.write_text(metadata.to_json(), encoding="utf-8")
    metadata_pin = _pin(metadata_path, "sources/award_data.meta.json")

    annual_reports: list[study.AnnualReportSource] = []
    captured_tables: list[study.CapturedTableSource] = []
    for year, table_number in study.REPORT_TABLES.items():
        pdf_path = source_dir / f"FY{year}.pdf"
        pdf_path.write_bytes(f"%PDF fixture FY{year}\n".encode())
        annual_reports.append(
            study.AnnualReportSource(
                report_year=year,
                table_number=table_number,
                file=_pin(pdf_path, f"sources/FY{year}.pdf"),
            )
        )
        captured_path = source_dir / f"FY{year}.csv"
        captured = _captured_frame(year)
        captured.to_csv(captured_path, index=False, lineterminator="\n")
        captured_tables.append(
            study.CapturedTableSource(
                report_year=year,
                table_number=table_number,
                file=_pin(captured_path, f"sources/FY{year}.csv"),
                row_count=len(captured),
            )
        )

    population_path = study_dir / "validation-population-v1.csv"
    population = _population_frame()
    population.to_csv(population_path, index=False, lineterminator="\n")
    design_path = study_dir / "validation-design-v1.md"
    design_path.write_text("# Frozen fixture design\n", encoding="utf-8")
    implementation_path = root / "producer.py"
    implementation_path.write_text("def produce_count_sidecar():\n    pass\n", encoding="utf-8")

    reports_tuple = tuple(annual_reports)
    captured_tuple = tuple(captured_tables)
    source_manifest_path = study_dir / "source-manifest.json"
    source_manifest_path.write_text(
        json.dumps(
            _source_manifest(
                award_export=award_export,
                award_export_metadata=metadata_pin,
                annual_reports=reports_tuple,
                captured_tables=captured_tuple,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    inputs = study.ProductionInputs(
        source_manifest=_pin(
            source_manifest_path,
            f"studies/{study.STUDY_ID}/source-manifest.json",
        ),
        award_export=award_export,
        award_export_metadata=metadata_pin,
        annual_reports=reports_tuple,
        captured_tables=captured_tuple,
        validation_design=_pin(
            design_path,
            f"studies/{study.STUDY_ID}/validation-design-v1.md",
        ),
        validation_population=_pin(
            population_path,
            f"studies/{study.STUDY_ID}/validation-population-v1.csv",
        ),
        implementation=_pin(implementation_path, "producer.py"),
    )
    return FixtureBundle(inputs=inputs, population=population)


def _page_count(_: Path) -> int:
    return 1


def _repin_source_manifest(
    inputs: study.ProductionInputs, raw: dict[str, object]
) -> study.ProductionInputs:
    inputs.source_manifest.path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return replace(
        inputs,
        source_manifest=_pin(inputs.source_manifest.path, inputs.source_manifest.reference),
    )


def _validation_values(product: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for record in product.to_dict(orient="records"):
        for target in ("published_count", "recomputed_count"):
            published = target == "published_count"
            rows.append(
                {
                    "unit_id": ":".join(
                        (
                            target,
                            str(record["report_year"]),
                            record["jurisdiction"],
                            record["program"],
                            record["phase"].replace(" ", "_"),
                        )
                    ),
                    "target": target,
                    "report_year": record["report_year"],
                    "table_number": record["table_number"] if published else "",
                    "jurisdiction": record["jurisdiction"],
                    "program": record["program"],
                    "phase": record["phase"],
                    "value": record[target],
                    "status": "observed",
                    "source_page": "1" if published else "",
                    "source_locator": "printed cell" if published else "award rows",
                    "missing_reason": "",
                }
            )
    return pd.DataFrame(rows, columns=study.VALIDATION_VALUE_COLUMNS)


def test_builds_all_632_count_cells_with_only_exact_or_unresolved_status(
    tmp_path: Path,
) -> None:
    fixture = _fixture_bundle(tmp_path)

    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )

    assert tuple(product.frame.columns) == study.COUNT_SIDECAR_COLUMNS
    assert len(product.frame) == study.EXPECTED_CELL_COUNT
    assert product.dropped_blank_state_rows == 1
    alaska = product.frame.query(
        "report_year == 2020 and jurisdiction == 'AK' and program == 'SBIR' and phase == 'Phase I'"
    ).iloc[0]
    assert alaska[
        [
            "table_number",
            "published_count",
            "recomputed_count",
            "signed_difference",
            "absolute_difference",
            "comparison_status",
        ]
    ].tolist() == [18, 1, 2, 1, 1, "unresolved"]
    assert set(product.frame["comparison_status"]) == {"exact", "unresolved"}
    assert not any("usd" in column.lower() for column in product.frame)
    assert "structural_check_passed" not in product.frame


@pytest.mark.parametrize("target", ["award_export", "award_export_metadata"])
def test_missing_source_or_sidecar_fails_closed(tmp_path: Path, target: str) -> None:
    fixture = _fixture_bundle(tmp_path)
    pin = getattr(fixture.inputs, target)
    pin.path.unlink()

    with pytest.raises(study.StructuralComparisonError, match="missing"):
        study.build_count_comparison(fixture.inputs, pdf_page_counter=_page_count)


@pytest.mark.parametrize("target", ["award_export", "award_export_metadata"])
def test_tampered_source_or_sidecar_fails_closed(tmp_path: Path, target: str) -> None:
    fixture = _fixture_bundle(tmp_path)
    pin = getattr(fixture.inputs, target)
    pin.path.write_bytes(pin.path.read_bytes() + b"tampered")

    with pytest.raises(study.StructuralComparisonError, match="byte count mismatch"):
        study.build_count_comparison(fixture.inputs, pdf_page_counter=_page_count)


def test_closed_source_capture_gate_blocks_before_source_use(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    raw = json.loads(fixture.inputs.source_manifest.path.read_text(encoding="utf-8"))
    raw["capture_gate"] = {
        "allowed": False,
        "blockers": ["PDFs lack durable exact-byte URIs."],
        "verified_on": "2026-09-21",
        "verification_note": "Synthetic fixture was intentionally closed.",
    }
    inputs = _repin_source_manifest(fixture.inputs, raw)
    inputs.award_export.path.unlink()

    with pytest.raises(study.StructuralComparisonError, match="capture gate is closed"):
        study.build_count_comparison(inputs, pdf_page_counter=_page_count)


def test_tampered_source_manifest_fails_before_discovery(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    fixture.inputs.source_manifest.path.write_bytes(
        fixture.inputs.source_manifest.path.read_bytes() + b"\n"
    )

    with pytest.raises(study.StructuralComparisonError, match="byte count mismatch"):
        study.build_count_comparison(fixture.inputs, pdf_page_counter=_page_count)


@pytest.mark.parametrize(
    "target",
    ["validation_design", "validation_population", "implementation"],
)
def test_tampered_frozen_contract_artifact_fails_closed(tmp_path: Path, target: str) -> None:
    fixture = _fixture_bundle(tmp_path)
    pin = getattr(fixture.inputs, target)
    pin.path.write_bytes(pin.path.read_bytes() + b"tampered")

    with pytest.raises(study.StructuralComparisonError, match="byte count mismatch"):
        study.build_count_comparison(fixture.inputs, pdf_page_counter=_page_count)


@pytest.mark.parametrize("source_kind", ["annual_report", "captured_table"])
def test_missing_report_or_captured_table_fails_closed(tmp_path: Path, source_kind: str) -> None:
    fixture = _fixture_bundle(tmp_path)
    sources = (
        fixture.inputs.annual_reports
        if source_kind == "annual_report"
        else fixture.inputs.captured_tables
    )
    sources[0].file.path.unlink()

    with pytest.raises(study.StructuralComparisonError, match="missing"):
        study.build_count_comparison(fixture.inputs, pdf_page_counter=_page_count)


def test_pdf_page_count_mismatch_is_blocking(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)

    with pytest.raises(study.StructuralComparisonError, match="page-count mismatch"):
        study.build_count_comparison(
            fixture.inputs,
            pdf_page_counter=lambda _: 2,
        )


def test_captured_table_schema_mismatch_is_blocking(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    source = fixture.inputs.captured_tables[0]
    frame = pd.read_csv(source.file.path, dtype=str)
    frame = frame.drop(columns="all_tot_usd")
    frame.to_csv(source.file.path, index=False, lineterminator="\n")
    changed_source = replace(
        source,
        file=_pin(source.file.path, source.file.reference),
    )
    captured = (changed_source, *fixture.inputs.captured_tables[1:])
    raw = _source_manifest(
        award_export=fixture.inputs.award_export,
        award_export_metadata=fixture.inputs.award_export_metadata,
        annual_reports=fixture.inputs.annual_reports,
        captured_tables=captured,
    )
    inputs = _repin_source_manifest(replace(fixture.inputs, captured_tables=captured), raw)

    with pytest.raises(study.StructuralComparisonError, match="schema mismatch"):
        study.build_count_comparison(inputs, pdf_page_counter=_page_count)


def test_captured_table_key_set_mismatch_is_blocking(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    source = fixture.inputs.captured_tables[0]
    frame = pd.read_csv(source.file.path, dtype=str)
    frame.loc[0, "state"] = "ZZ"
    frame.to_csv(source.file.path, index=False, lineterminator="\n")
    changed_source = replace(source, file=_pin(source.file.path, source.file.reference))
    captured = (changed_source, *fixture.inputs.captured_tables[1:])
    raw = _source_manifest(
        award_export=fixture.inputs.award_export,
        award_export_metadata=fixture.inputs.award_export_metadata,
        annual_reports=fixture.inputs.annual_reports,
        captured_tables=captured,
    )
    inputs = _repin_source_manifest(replace(fixture.inputs, captured_tables=captured), raw)

    with pytest.raises(study.StructuralComparisonError, match="key-set mismatch"):
        study.build_count_comparison(inputs, pdf_page_counter=_page_count)


def test_captured_table_row_count_mismatch_is_blocking(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    source = replace(fixture.inputs.captured_tables[0], row_count=52)
    captured = (source, *fixture.inputs.captured_tables[1:])
    raw = _source_manifest(
        award_export=fixture.inputs.award_export,
        award_export_metadata=fixture.inputs.award_export_metadata,
        annual_reports=fixture.inputs.annual_reports,
        captured_tables=captured,
    )
    inputs = _repin_source_manifest(replace(fixture.inputs, captured_tables=captured), raw)

    with pytest.raises(study.StructuralComparisonError, match="row-count mismatch"):
        study.build_count_comparison(inputs, pdf_page_counter=_page_count)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("signed_difference", 999, "incorrect signed difference"),
        ("absolute_difference", 999, "incorrect absolute difference"),
        ("comparison_status", "pipeline_defect", "must label unequal cells unresolved"),
    ],
)
def test_sidecar_arithmetic_and_status_invariants_are_blocking(
    tmp_path: Path,
    column: str,
    value: object,
    message: str,
) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    product.frame.loc[0, column] = value

    with pytest.raises(study.StructuralComparisonError, match=message):
        study.validate_count_sidecar(product.frame, fixture.population)


@pytest.mark.parametrize(
    ("failure", "message"),
    [("missing", "missing"), ("unequal", "disagree")],
)
def test_missing_or_unequal_independent_value_is_blocking(
    tmp_path: Path, failure: str, message: str
) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    values = _validation_values(product.frame)
    values["value"] = values["value"].astype(object)
    if failure == "missing":
        values.loc[0, ["value", "status", "missing_reason"]] = [
            "",
            "missing",
            "Cell could not be read.",
        ]
    else:
        values.loc[0, "value"] = int(values.loc[0, "value"]) + 1
    path = tmp_path / "validation-values.csv"
    values.to_csv(path, index=False, lineterminator="\n")

    with pytest.raises(study.StructuralComparisonError, match=message):
        study.verify_validation_values(path, product.frame)


def _materialization_inputs(
    root: Path,
    fixture: FixtureBundle,
    product: study.CountComparisonProduct,
    *,
    threshold_met: bool = True,
) -> tuple[study.MaterializationInputs, study.Renderer]:
    output_dir = root / "structural-comparison-output"
    output_dir.mkdir()
    production_path = output_dir / "production-counts.csv"
    production_path.write_bytes(study.count_sidecar_bytes(product.frame, fixture.population))
    production_pin = _pin(production_path, "output/production-counts.csv")

    validation_path = output_dir / "validation-values.csv"
    _validation_values(product.frame).to_csv(
        validation_path,
        index=False,
        lineterminator="\n",
    )
    validation_pin = _pin(validation_path, "output/validation-values.csv")

    def renderer(frame: pd.DataFrame) -> bytes:
        return ("count-only\n" + frame.to_csv(index=False, lineterminator="\n")).encode()

    rendered_path = output_dir / "approved.txt"
    rendered_path.write_bytes(renderer(product.frame))
    rendered_pin = _pin(rendered_path, "output/approved.txt")
    approval_path = output_dir / "claim-approval.md"
    approval_path.write_text("Approved for the manifest's permitted claim.\n", encoding="utf-8")
    approval_pin = _pin(approval_path, "reviews/claim-approval.md")
    production_pins = [pin for _, pin in study._production_pins(fixture.inputs)]
    all_pins = [*production_pins, production_pin, validation_pin, rendered_pin, approval_pin]
    design = fixture.inputs.validation_design
    manifest = {
        "schema_version": 1,
        "study_id": study.STUDY_ID,
        "title": "Fixture structural comparison",
        "evidence_status": "approved" if threshold_met else "validated",
        "research_questions": ["B2"],
        "estimand": "Signed and absolute differences for all 632 count cells.",
        "frozen_artifacts": [{"path": pin.reference, "sha256": pin.sha256} for pin in all_pins],
        "implementation": [
            {"path": fixture.inputs.implementation.reference, "symbol": "produce_count_sidecar"}
        ],
        "identity_policy": {
            "strategy": "frozen exact cell keys",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": (
            {"allowed": True, "blockers": []}
            if threshold_met
            else {"allowed": False, "blockers": ["Confirmatory threshold was not met."]}
        ),
        "permitted_claims": ["The frozen sources were transformed faithfully."],
        "limitations": ["The comparison does not adjudicate upstream truth."],
        "validation_design": {
            "addressable_population": "All 1,264 operands for 632 cells.",
            "expected_yield": "1,264 exact values.",
            "decision_threshold": "All 1,264 values agree.",
            "threshold_derivation": "Any changed operand can change the output.",
            "threshold_basis": "count_on_frozen_population",
            "threshold_value": 1264,
            "frozen_population_artifact": fixture.inputs.validation_population.reference,
        },
        "validation_result": {
            "design_path": design.reference,
            "design_sha256": design.sha256,
            "evaluated_on": "2026-09-21",
            "metric": "exact reconciled operands",
            "numerator": 1264 if threshold_met else 1263,
            "denominator": 1264,
            "interval_low": 1.0 if threshold_met else 1263 / 1264,
            "interval_high": 1.0 if threshold_met else 1263 / 1264,
            "interval_method": "exact complete-population point interval; no sampling",
            "threshold_met": threshold_met,
            "confirmatory": True,
            "post_hoc_analyses": [],
        },
    }
    if threshold_met:
        manifest["claim_approval"] = {
            "review_path": approval_pin.reference,
            "review_sha256": approval_pin.sha256,
            "claim_boundary_sha256": claim_boundary_sha256(
                manifest["estimand"], manifest["permitted_claims"], manifest["limitations"]
            ),
            "approved_on": "2026-09-23",
        }
    manifest_path = output_dir / "study.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return (
        study.MaterializationInputs(
            study_manifest=_pin(manifest_path, "studies/structural-comparison/study.yaml"),
            production_sidecar=production_pin,
            validation_values=validation_pin,
            rendered_output=rendered_pin,
        ),
        renderer,
    )


def test_approved_materialization_requires_renderer_round_trip(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    materialization, _ = _materialization_inputs(tmp_path, fixture, product)

    with pytest.raises(study.StructuralComparisonError, match="renderer round-trip mismatch"):
        study.verify_approved_materialization(
            fixture.inputs,
            materialization,
            pdf_page_counter=_page_count,
            renderer=lambda _: b"different bytes",
        )


def test_approved_materialization_returns_verified_counts(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    materialization, renderer = _materialization_inputs(tmp_path, fixture, product)

    record = study.verify_approved_materialization(
        fixture.inputs,
        materialization,
        pdf_page_counter=_page_count,
        renderer=renderer,
    )

    assert record.study_id == study.STUDY_ID
    assert record.cell_count == 632
    assert record.validation_value_count == 1264


def test_approved_materialization_rejects_output_hash_mismatch(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    materialization, renderer = _materialization_inputs(tmp_path, fixture, product)
    materialization.rendered_output.path.write_bytes(b"tampered")

    with pytest.raises(study.StructuralComparisonError, match="byte count mismatch"):
        study.verify_approved_materialization(
            fixture.inputs,
            materialization,
            pdf_page_counter=_page_count,
            renderer=renderer,
        )


def test_approved_materialization_rejects_implementation_manifest_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    materialization, renderer = _materialization_inputs(tmp_path, fixture, product)
    manifest_path = materialization.study_manifest.path
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["implementation"][0]["symbol"] = "wrong_symbol"
    manifest_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    materialization = replace(
        materialization,
        study_manifest=_pin(manifest_path, materialization.study_manifest.reference),
    )

    with pytest.raises(study.StructuralComparisonError, match="producer implementation"):
        study.verify_approved_materialization(
            fixture.inputs,
            materialization,
            pdf_page_counter=_page_count,
            renderer=renderer,
        )


def test_failed_validation_cannot_materialize_approved_output(tmp_path: Path) -> None:
    fixture = _fixture_bundle(tmp_path)
    product = study.build_count_comparison(
        fixture.inputs,
        pdf_page_counter=_page_count,
    )
    materialization, renderer = _materialization_inputs(
        tmp_path,
        fixture,
        product,
        threshold_met=False,
    )

    with pytest.raises(study.StructuralComparisonError, match="evidence_status approved"):
        study.verify_approved_materialization(
            fixture.inputs,
            materialization,
            pdf_page_counter=_page_count,
            renderer=renderer,
        )
