"""Tests for the exact-name SBIR/Form D filing-proxy audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/audit_sbir_form_d_business_combination_proxy.py"
REPO_ROOT = Path(__file__).parents[3]
TRACKED_MANIFEST = (
    REPO_ROOT
    / "docs/research/agency-private-capital-sbir-form-d-business-combination-proxy-audit.manifest.json"
)
TRACKED_REPORT = (
    REPO_ROOT
    / "docs/research/agency-private-capital-sbir-form-d-business-combination-proxy-audit.md"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "audit_sbir_form_d_business_combination_proxy", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load_module()


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _meta(path: Path, row_count: int) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.name,
        "row_count": row_count,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _candidate(cik: str, name: str, issuer_count: int) -> dict[str, Any]:
    return {
        "candidate_exclusion": True,
        "cik": cik,
        "evidence": [
            {
                "issuer_cik_count_for_normalized_name": issuer_count,
                "normalized_name": name,
                "normalizer_version": "organization-key-v1",
                "resolution_method": "candidate_exact_normalized_name",
            }
        ],
        "firm_key": f"form_d_cik:{cik}",
        "schema_version": 1,
    }


def _coverage(cik: str, snapshot_id: str) -> dict[str, Any]:
    return {
        "coverage_end_date": "2024-12-31",
        "coverage_start_date": "2009-01-01",
        "firm_key": f"form_d_cik:{cik}",
        "metric": audit.EVENT_TYPE,
        "schema_version": 1,
        "source": audit.SOURCE,
        "source_complete": True,
        "source_snapshot_date": "2024-12-31",
        "source_snapshot_id": snapshot_id,
    }


def _event(
    cik: str,
    accession: str,
    filing_date: str,
    snapshot_id: str,
    *,
    amendment: bool = False,
) -> dict[str, Any]:
    month = int(filing_date[5:7])
    return {
        "accession_number": accession,
        "date_basis": "filing_date",
        "event_date": filing_date,
        "event_id": f"form_d_accession:{accession}",
        "event_type": audit.EVENT_TYPE,
        "evidence_kind": "proxy",
        "filing_date": filing_date,
        "firm_key": f"form_d_cik:{cik}",
        "is_amendment": amendment,
        "previous_accession_number": "prior-accession" if amendment else None,
        "schema_version": 1,
        "source": audit.SOURCE,
        "source_quarter": f"{filing_date[:4]}Q{((month - 1) // 3) + 1}",
        "source_snapshot_id": snapshot_id,
        "submission_type": "D/A" if amendment else "D",
    }


def _fixture(tmp_path: Path) -> argparse.Namespace:
    candidates_path = tmp_path / "candidates.jsonl"
    awards_path = tmp_path / "awards.csv"
    control_path = tmp_path / "control.json"
    events_path = tmp_path / "events.jsonl"
    coverage_path = tmp_path / "coverage.jsonl"
    proxy_path = tmp_path / "proxy.json"
    alpha = _candidate("123", "ALPHA LABS", 1)
    alpha["evidence"].append(
        {
            "issuer_cik_count_for_normalized_name": 2,
            "normalized_name": "BETA SYSTEMS",
            "normalizer_version": "organization-key-v1",
            "resolution_method": "candidate_exact_normalized_name",
        }
    )
    _jsonl(
        candidates_path,
        [
            alpha,
            _candidate("456", "BETA SYSTEMS", 2),
            _candidate("789", "DELTA RESEARCH", 1),
        ],
    )
    with awards_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company", "Agency"])
        writer.writeheader()
        writer.writerows(
            [
                {"Company": "Alpha Labs, Inc.", "Agency": "National Science Foundation"},
                {"Company": "Alpha Labs", "Agency": "Department of Energy"},
                {
                    "Company": "Beta Systems LLC",
                    "Agency": "Department of Health and Human Services",
                },
                {"Company": "Delta Research LLC", "Agency": "Department of Defense"},
                {"Company": "Gamma Works Inc.", "Agency": "Unmapped for unlinked name"},
            ]
        )
    awards_ref = _meta(awards_path, 5)
    awards_ref["unique_normalized_company_names"] = 4
    control = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "exclusion": {
            "awards_csv": awards_ref,
            "exact_match": {
                "candidate_cik_count": 3,
                "matched_normalized_name_count": 3,
                "normalized_names_mapping_to_multiple_ciks": 1,
                "normalizer_version": "organization-key-v1",
            },
        },
        "exclusion_recall": "unknown",
        "outputs": {
            "broad_issuer_universe": {
                "path": "issuer-universe.jsonl",
                "row_count": 4,
                "sha256": "a" * 64,
                "size_bytes": 10,
            },
            "candidate_sbir_cik_exclusions": _meta(candidates_path, 3),
        },
        "schema_version": 1,
    }
    _write_json(control_path, control)
    control_data = control_path.read_bytes()
    snapshot_id = (
        f"form_d_control_universe_manifest_sha256:{hashlib.sha256(control_data).hexdigest()}"
    )
    coverage_rows = [_coverage(cik, snapshot_id) for cik in ("123", "456", "789", "999")]
    event_rows = [
        _event("123", "a", "2009-09-30", snapshot_id),
        _event("123", "b", "2009-10-01", snapshot_id),
        _event("456", "c", "2024-09-30", snapshot_id, amendment=True),
        _event("456", "d", "2024-10-01", snapshot_id),
        _event("999", "e", "2020-02-01", snapshot_id),
    ]
    _jsonl(coverage_path, coverage_rows)
    _jsonl(events_path, event_rows)
    proxy = {
        "complete": True,
        "event_type": audit.EVENT_TYPE,
        "inputs": {
            "issuer_universe": control["outputs"]["broad_issuer_universe"],
            "source_manifest": {
                "path": control_path.name,
                "sha256": hashlib.sha256(control_data).hexdigest(),
                "size_bytes": len(control_data),
            },
        },
        "outputs": {
            "coverage": _meta(coverage_path, len(coverage_rows)),
            "events": _meta(events_path, len(event_rows)),
        },
        "counters": {
            "coverage_rows": len(coverage_rows),
            "event_rows": len(event_rows),
        },
        "schema_version": 1,
        "source": {
            "coverage_end_date": "2024-12-31",
            "coverage_start_date": "2009-01-01",
            "source": audit.SOURCE,
            "source_complete": True,
            "source_snapshot_date": "2024-12-31",
            "source_snapshot_id": snapshot_id,
        },
    }
    _write_json(proxy_path, proxy)
    return argparse.Namespace(
        control_manifest=control_path,
        candidate_jsonl=candidates_path,
        proxy_manifest=proxy_path,
        event_jsonl=events_path,
        coverage_jsonl=coverage_path,
        awards_csv=awards_path,
        output_dir=tmp_path / "output",
        audit_manifest=tmp_path / "audit-manifest.json",
        code_version="test-commit",
    )


def _repin_proxy(args: argparse.Namespace) -> None:
    proxy = json.loads(args.proxy_manifest.read_text(encoding="utf-8"))
    proxy["outputs"]["events"] = _meta(
        args.event_jsonl,
        len(args.event_jsonl.read_text(encoding="utf-8").splitlines()),
    )
    proxy["outputs"]["coverage"] = _meta(
        args.coverage_jsonl,
        len(args.coverage_jsonl.read_text(encoding="utf-8").splitlines()),
    )
    proxy["counters"]["event_rows"] = proxy["outputs"]["events"]["row_count"]
    proxy["counters"]["coverage_rows"] = proxy["outputs"]["coverage"]["row_count"]
    _write_json(args.proxy_manifest, proxy)


def test_contract_constants_and_federal_fiscal_year_are_frozen() -> None:
    assert audit.EVENT_TYPE == "form_d_business_combination_filing_proxy"
    assert audit.MATERIALIZED_START_FY == 2010
    assert audit.MATERIALIZED_END_FY == 2024
    assert audit.BOUNDARY_FISCAL_YEARS == {2009, 2025}
    assert audit.federal_fiscal_year(audit.date(2019, 9, 30)) == 2019
    assert audit.federal_fiscal_year(audit.date(2019, 10, 1)) == 2020


def test_build_uses_exact_cik_and_excludes_partial_fiscal_years(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    manifest = audit.build(args)

    assert manifest["counts"]["candidate_ciks"] == 3
    assert manifest["counts"]["complete_filing_fiscal_year_window"] == {
        "end_fy": 2024,
        "proxy_filings": 2,
        "proxy_bearing_ciks": 2,
        "start_fy": 2010,
    }
    assert manifest["counts"]["full_source_join"] == {
        "proxy_filings": 4,
        "proxy_bearing_ciks": 2,
    }
    assert manifest["counts"]["incomplete_boundary_fiscal_years"] == {
        "2009": {"proxy_filings": 1, "proxy_bearing_ciks": 1},
        "2025": {"proxy_filings": 1, "proxy_bearing_ciks": 1},
    }
    product = manifest["outputs"]["filing_evidence_audit"]
    rows = [
        json.loads(line)
        for line in (args.output_dir / product["path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert [row["accession_number"] for row in rows] == ["b", "c"]
    assert rows[0]["agency_tags"] == ["DOE", "HHS", "NSF"]
    assert rows[0]["identity_evidence_class"] == "unique_within_materialized_name_map"
    assert rows[1]["identity_evidence_class"] == "ambiguous_name_only"
    assert rows[1]["submission_type"] == "D/A"
    assert rows[1]["previous_accession_number"] == "prior-accession"

    name_product = manifest["outputs"]["normalized_name_observation"]
    name_rows = [
        json.loads(line)
        for line in (args.output_dir / name_product["path"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    by_name = {row["normalized_sbir_name"]: row for row in name_rows}
    assert list(by_name) == ["ALPHA LABS", "BETA SYSTEMS", "DELTA RESEARCH", "GAMMA WORKS"]
    assert by_name["ALPHA LABS"] == {
        "boundary_proxy_accessions": ["a"],
        "candidate_ciks": ["123"],
        "complete_fy_proxy_accessions": ["b"],
        "exact_name_candidate_link_class": audit.NAME_LINK_UNIQUE,
        "normalized_sbir_name": "ALPHA LABS",
        "observation_status": audit.NAME_STATUS_COMPLETE,
        "raw_sbir_names": ["Alpha Labs", "Alpha Labs, Inc."],
    }
    assert by_name["BETA SYSTEMS"]["candidate_ciks"] == ["123", "456"]
    assert by_name["BETA SYSTEMS"]["complete_fy_proxy_accessions"] == ["b", "c"]
    assert by_name["BETA SYSTEMS"]["boundary_proxy_accessions"] == ["a", "d"]
    assert by_name["BETA SYSTEMS"]["exact_name_candidate_link_class"] == (audit.NAME_LINK_AMBIGUOUS)
    assert by_name["DELTA RESEARCH"]["observation_status"] == audit.NAME_STATUS_COVERED_ZERO
    assert by_name["DELTA RESEARCH"]["complete_fy_proxy_accessions"] == []
    assert by_name["DELTA RESEARCH"]["boundary_proxy_accessions"] == []
    assert by_name["GAMMA WORKS"]["observation_status"] == audit.NAME_STATUS_NO_LINK
    assert by_name["GAMMA WORKS"]["candidate_ciks"] == []
    assert by_name["GAMMA WORKS"]["complete_fy_proxy_accessions"] is None
    assert by_name["GAMMA WORKS"]["boundary_proxy_accessions"] is None
    assert manifest["counts"]["normalized_name_observation"]["observation_statuses"] == {
        audit.NAME_STATUS_COMPLETE: 2,
        audit.NAME_STATUS_BOUNDARY: 0,
        audit.NAME_STATUS_COVERED_ZERO: 1,
        audit.NAME_STATUS_NO_LINK: 1,
    }


def test_build_is_byte_deterministic(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    first = audit.build(args)
    first_manifest = args.audit_manifest.read_bytes()
    first_product = (
        args.output_dir / first["outputs"]["filing_evidence_audit"]["path"]
    ).read_bytes()
    first_name_product = (
        args.output_dir / first["outputs"]["normalized_name_observation"]["path"]
    ).read_bytes()

    args.output_dir = tmp_path / "second-output"
    args.audit_manifest = tmp_path / "second-manifest.json"
    second = audit.build(args)

    assert args.audit_manifest.read_bytes() == first_manifest
    assert (
        args.output_dir / second["outputs"]["filing_evidence_audit"]["path"]
    ).read_bytes() == first_product
    assert (
        args.output_dir / second["outputs"]["normalized_name_observation"]["path"]
    ).read_bytes() == first_name_product


def test_name_observation_fanout_and_boundary_status_are_explicit() -> None:
    candidates = {
        "1": {"matched_normalized_names": ["CURRENT NAME", "FORMER NAME"]},
        "2": {"matched_normalized_names": ["CURRENT NAME"]},
        "3": {"matched_normalized_names": ["BOUNDARY NAME"]},
    }
    award_names = {
        "BOUNDARY NAME": ["Boundary Name LLC"],
        "CURRENT NAME": ["Current Name Inc."],
        "FORMER NAME": ["Former Name Inc."],
        "UNLINKED NAME": ["Unlinked Name LLC"],
    }
    candidate_events = {
        "1": {"boundary": [], "complete_fy": ["complete-a"]},
        "2": {"boundary": [], "complete_fy": ["complete-b"]},
        "3": {"boundary": ["boundary-a"], "complete_fy": []},
    }

    rows = audit._name_observation_rows(candidates, award_names, candidate_events)
    counts = audit._name_observation_counts(rows, candidates, candidate_events)
    by_name = {row["normalized_sbir_name"]: row for row in rows}

    assert by_name["CURRENT NAME"]["candidate_ciks"] == ["1", "2"]
    assert by_name["CURRENT NAME"]["complete_fy_proxy_accessions"] == [
        "complete-a",
        "complete-b",
    ]
    assert by_name["FORMER NAME"]["complete_fy_proxy_accessions"] == ["complete-a"]
    assert by_name["BOUNDARY NAME"]["observation_status"] == audit.NAME_STATUS_BOUNDARY
    assert by_name["UNLINKED NAME"]["observation_status"] == audit.NAME_STATUS_NO_LINK
    assert counts["proxy_cik_to_name_grain_reconciliation"] == {
        "bounded_source_proxy_bearing_candidate_ciks": 3,
        "bounded_source_proxy_observed_linked_normalized_names": 3,
        "complete_fy_proxy_bearing_candidate_ciks": 2,
        "complete_fy_proxy_observed_linked_normalized_names": 2,
        "incomplete_boundary_only_proxy_observed_linked_normalized_names": 1,
        "name_grain_minus_cik_grain_observed_difference": 0,
        "observed_normalized_names_linked_to_multiple_proxy_bearing_ciks": 1,
        "proxy_bearing_cik_name_memberships": 4,
        "proxy_bearing_ciks_linked_to_multiple_normalized_names": 1,
    }


def test_tampered_candidate_product_fails_before_publication(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    args.candidate_jsonl.write_text(
        args.candidate_jsonl.read_text(encoding="utf-8") + "{}\n", encoding="utf-8"
    )

    with pytest.raises(audit.AuditError, match="byte size"):
        audit.build(args)

    assert not args.audit_manifest.exists()
    assert not args.output_dir.exists()


def test_duplicate_event_accession_fails_closed(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    rows = [json.loads(line) for line in args.event_jsonl.read_text().splitlines()]
    duplicate = dict(rows[1])
    duplicate["firm_key"] = "form_d_cik:456"
    rows.append(duplicate)
    _jsonl(args.event_jsonl, rows)
    _repin_proxy(args)

    with pytest.raises(audit.AuditError, match="globally unique"):
        audit.build(args)

    assert not args.audit_manifest.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("firm_key", "form_d_cik:000123", "canonical"),
        ("event_type", "verified_ma", "event contract"),
        ("filing_date", "2025-01-01", "event_date"),
    ],
)
def test_malformed_event_contract_fails_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    args = _fixture(tmp_path)
    rows = [json.loads(line) for line in args.event_jsonl.read_text().splitlines()]
    rows[1][field] = value
    _jsonl(args.event_jsonl, rows)
    _repin_proxy(args)

    with pytest.raises(audit.AuditError, match=message):
        audit.build(args)


def test_missing_candidate_coverage_fails_closed(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    rows = [json.loads(line) for line in args.coverage_jsonl.read_text().splitlines()]
    _jsonl(args.coverage_jsonl, rows[:1])
    _repin_proxy(args)

    with pytest.raises(audit.AuditError, match="lacks proxy coverage"):
        audit.build(args)


def test_manifest_cannot_alias_an_input(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    args.audit_manifest = args.control_manifest

    with pytest.raises(audit.AuditError, match="must not alias"):
        audit.build(args)


def test_existing_manifest_survives_validation_failure(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    args.audit_manifest.write_text("old manifest\n", encoding="utf-8")
    args.event_jsonl.write_text("{}\n", encoding="utf-8")

    with pytest.raises(audit.AuditError):
        audit.build(args)

    assert args.audit_manifest.read_text(encoding="utf-8") == "old manifest\n"


def test_blank_code_version_fails_before_any_output_is_published(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    args.code_version = "   "

    with pytest.raises(audit.AuditError, match="code-version"):
        audit.build(args)

    assert not args.output_dir.exists()
    assert not args.audit_manifest.exists()


def test_mapping_class_is_recomputed_from_complete_name_map(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    rows = [_candidate("123", "SHARED NAME", 1), _candidate("456", "SHARED NAME", 1)]
    _jsonl(path, rows)

    with pytest.raises(audit.AuditError, match="inconsistent issuer-CIK count"):
        audit._load_candidates(
            path,
            expected_rows=2,
            identity_contract={
                "candidate_cik_count": 2,
                "matched_normalized_name_count": 1,
                "ambiguous_normalized_name_count": 1,
            },
        )


def test_duplicate_json_key_fails_strict_parsing(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.jsonl"
    path.write_text('{"cik":"123","cik":"456"}\n', encoding="utf-8")

    with pytest.raises(audit.AuditError, match="duplicate JSON key"):
        list(audit._iter_jsonl(path, label="fixture"))


def test_noncanonical_iso_filing_date_fails_closed(tmp_path: Path) -> None:
    args = _fixture(tmp_path)
    rows = [json.loads(line) for line in args.event_jsonl.read_text().splitlines()]
    rows[1]["filing_date"] = "20091001"
    rows[1]["event_date"] = "20091001"
    _jsonl(args.event_jsonl, rows)
    _repin_proxy(args)

    with pytest.raises(audit.AuditError, match="exact ISO"):
        audit.build(args)


def test_manifest_publish_failure_rolls_back_new_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _fixture(tmp_path)
    prior_manifest = b'{"prior":true}\n'
    args.audit_manifest.write_bytes(prior_manifest)

    def fail_manifest_write(path: Path, data: bytes) -> None:
        raise OSError("manifest publish failed")

    monkeypatch.setattr(audit, "_atomic_write", fail_manifest_write)
    with pytest.raises(OSError, match="manifest publish failed"):
        audit.build(args)

    assert args.audit_manifest.read_bytes() == prior_manifest
    assert not list(args.output_dir.glob("*.jsonl"))


def test_tracked_report_reconciles_to_materialization_manifest() -> None:
    manifest = json.loads(TRACKED_MANIFEST.read_text(encoding="utf-8"))
    report = TRACKED_REPORT.read_text(encoding="utf-8")
    report_words = " ".join(report.split())
    complete = manifest["counts"]["complete_filing_fiscal_year_window"]
    product = manifest["outputs"]["filing_evidence_audit"]

    assert complete == {
        "end_fy": 2024,
        "proxy_bearing_ciks": 212,
        "proxy_filings": 283,
        "start_fy": 2010,
    }
    assert "283 unique Form D accessions across 212 exact Form D CIKs" in report_words
    assert product["row_count"] == 283
    assert (
        f"| Complete-FY filing evidence audit | 283 | 244,696 | `{product['sha256']}` |" in report
    )
    assert manifest["complete_sbir_identity"] is False
    assert manifest["complete_sbir_exclusion"] is False
    assert manifest["covariates_ready"] is False
    assert manifest["ready_for_matching"] is False
    assert manifest["verified_ma"] is False
