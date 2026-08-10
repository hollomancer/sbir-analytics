import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/data/audit_form_d_matching_covariates.py"
REPO_ROOT = Path(__file__).resolve().parents[3]
TRACKED_MANIFEST = (
    REPO_ROOT / "docs/research/agency-private-capital-form-d-matching-covariates.manifest.json"
)
TRACKED_REPORT = REPO_ROOT / "docs/research/agency-private-capital-form-d-matching-covariates.md"
SPEC = importlib.util.spec_from_file_location("audit_form_d_matching_covariates", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows
    )


def _write_jsonl(path: Path, rows: list[dict]) -> dict[str, object]:
    data = _jsonl_bytes(rows)
    path.write_bytes(data)
    return {
        "path": path.name,
        "row_count": len(rows),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _filing(
    cik: str,
    accession: str,
    filing_date: str,
    *,
    industry: str | None = "Technology",
    sic: str | None = None,
    state: str | None = "CA",
) -> dict:
    month = int(filing_date[5:7])
    return {
        "accession_number": accession,
        "cik": cik,
        "filing_date": filing_date,
        "industry_group": industry,
        "sic_code": sic,
        "source_quarter": f"{filing_date[:4]}Q{((month - 1) // 3) + 1}",
        "state": state,
    }


def _issuer(cik: str, filings: list[dict]) -> dict:
    first = min(filings, key=lambda item: (item["filing_date"], item["accession_number"]))
    return {
        "cik": cik,
        "filing_count": len(filings),
        "filings": filings,
        "firm_key": f"form_d_cik:{cik}",
        "first_accession_number": first["accession_number"],
        "first_filing_date": first["filing_date"],
        "first_filing_year": int(first["filing_date"][:4]),
        "schema_version": 1,
    }


def _candidate(cik: str) -> dict:
    return {
        "candidate_exclusion": True,
        "cik": cik,
        "evidence": [{"resolution_method": MODULE.EXACT_METHOD}],
        "evidence_count": 1,
        "firm_key": f"form_d_cik:{cik}",
        "resolution_methods": [MODULE.EXACT_METHOD],
        "schema_version": 1,
    }


def _default_rows() -> tuple[list[dict], list[dict]]:
    broad = [
        _issuer(
            "1",
            [
                _filing("1", "A2", "2021-01-01", industry="Pooled Investment Fund", state="NY"),
                _filing("1", "A1", "2020-01-01", sic="7372"),
            ],
        ),
        _issuer("2", [_filing("2", "B1", "2020-02-01")]),
        _issuer("3", [_filing("3", "C1", "2020-03-01")]),
        _issuer("4", [_filing("4", "D1", "2020-04-01")]),
        _issuer("5", [_filing("5", "E1", "2020-05-01", state=None)]),
    ]
    return broad, [_candidate("1")]


def _write_fixture(
    tmp_path: Path,
    *,
    broad: list[dict] | None = None,
    candidates: list[dict] | None = None,
) -> tuple[argparse.Namespace, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    default_broad, default_candidates = _default_rows()
    broad = default_broad if broad is None else broad
    candidates = default_candidates if candidates is None else candidates
    universe = tmp_path / "universe.jsonl"
    exclusions = tmp_path / "exclusions.jsonl"
    broad_pin = _write_jsonl(universe, broad)
    candidate_pin = _write_jsonl(exclusions, candidates)
    remainder_count = len(broad) - len(candidates)
    assert remainder_count > 0
    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "exclusion_recall": "unknown",
        "covariates_ready": False,
        "ready_for_matching": False,
        "schema_version": 1,
        "outputs": {
            "broad_issuer_universe": broad_pin,
            "candidate_sbir_cik_exclusions": candidate_pin,
            "provisional_control_identity_universe": {
                "path": "remainder.jsonl",
                "row_count": remainder_count,
                "sha256": "a" * 64,
                "size_bytes": 1,
            },
        },
        "parameters": {
            "start_quarter": "2009Q1",
            "end_quarter": "2024Q4",
            "quarter_count": 64,
        },
        "source_counts": {
            "issuer_ciks": len(broad),
            "excluded_broad_ciks": len(candidates),
            "provisional_control_ciks": remainder_count,
            "filings": sum(len(row["filings"]) for row in broad),
        },
    }
    manifest_path = tmp_path / "control-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    args = argparse.Namespace(
        audit_manifest=tmp_path / "audit-manifest.json",
        code_version="test-commit",
        exclusions=exclusions,
        expected_real_data_contract=False,
        manifest=manifest_path,
        universe=universe,
    )
    return args, manifest


def test_builds_reconciled_feasibility_tables_and_common_support(tmp_path: Path) -> None:
    args, _ = _write_fixture(tmp_path)

    result = MODULE.build(args)

    cik = result["availability"]["cik_grain"]
    filing = result["availability"]["filing_grain"]
    assert {partition: cik[partition]["rows"] for partition in MODULE.PARTITIONS} == {
        "broad": 5,
        "exact_name_candidate": 1,
        "provisional_remainder": 4,
    }
    assert cik["broad"]["industry_group_present"] == 5
    assert cik["broad"]["sic_code_present"] == 1
    assert cik["broad"]["state_or_country_code_present"] == 4
    assert cik["broad"]["first_filing_year_present"] == 5
    assert filing["broad"]["rows"] == 6
    assert filing["broad"]["sic_code_present"] == 1
    assert filing["broad"]["state_or_country_code_present"] == 5
    assert result["history_diagnostics"]["broad"] == {
        "multi_industry_group_history_ciks": 1,
        "multi_state_or_country_history_ciks": 1,
        "pooled_investment_fund_ciks": 0,
    }
    assert result["first_filing_year_distribution"]["broad"] == {"2020": 5}
    assert result["category_cardinality"]["cik_grain"]["broad"]["industry_group"] == 2
    support = result["mechanical_common_support"]
    assert support["candidate_ciks_support_eligible"] == 1
    assert support["candidate_ciks_with_at_least_1_provisional_in_same_cell"] == 1
    assert support["candidate_ciks_with_at_least_3_provisional_in_same_cell"] == 1
    assert support["provisional_ciks_support_eligible"] == 3
    assert result["complete_sbir_exclusion"] is False
    assert result["exclusion_recall"] == "unknown"
    assert result["covariates_ready"] is False
    assert result["ready_for_matching"] is False


def test_common_support_uses_fields_from_same_earliest_filing(tmp_path: Path) -> None:
    broad, candidates = _default_rows()
    broad[0] = _issuer(
        "1",
        [
            _filing("1", "LATER", "2021-01-01", industry="Technology", state="CA"),
            _filing("1", "EARLY", "2020-01-01", industry=None, state="CA"),
        ],
    )
    args, _ = _write_fixture(tmp_path, broad=broad, candidates=candidates)

    result = MODULE.build(args)

    support = result["mechanical_common_support"]
    assert support["candidate_ciks_missing_any_cell_field"] == 1
    assert support["candidate_ciks_support_eligible"] == 0
    assert support["candidate_ciks_with_at_least_1_provisional_in_same_cell"] == 0


def test_same_date_tie_uses_accession_and_preserves_foreign_sec_code(tmp_path: Path) -> None:
    broad, candidates = _default_rows()
    broad[0] = _issuer(
        "1",
        [
            _filing("1", "A2", "2020-01-01", industry="Technology", state="CA"),
            _filing("1", "A1", "2020-01-01", industry="Other", state="X1"),
        ],
    )
    broad[1] = _issuer("2", [_filing("2", "B1", "2020-01-01", industry="Other", state="X1")])
    args, _ = _write_fixture(tmp_path, broad=broad, candidates=candidates)

    result = MODULE.build(args)

    assert (
        result["mechanical_common_support"][
            "candidate_ciks_with_at_least_1_provisional_in_same_cell"
        ]
        == 1
    )
    state_diagnostics = result["state_or_country_diagnostics"]
    assert state_diagnostics["index_code_distribution"]["exact_name_candidate"] == {"X1": 1}
    assert state_diagnostics["index_code_classification"]["exact_name_candidate"] == {
        "other_sec_code": 1,
        "us_state_or_territory_code": 0,
    }


@pytest.mark.parametrize("product", ["broad_issuer_universe", "candidate_sbir_cik_exclusions"])
@pytest.mark.parametrize("field", ["sha256", "size_bytes", "row_count"])
def test_physical_product_hash_bytes_and_rows_are_verified(
    tmp_path: Path, product: str, field: str
) -> None:
    args, manifest = _write_fixture(tmp_path)
    pin = manifest["outputs"][product]
    pin[field] = "0" * 64 if field == "sha256" else pin[field] + 1
    Path(args.manifest).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(MODULE.AuditError):
        MODULE.build(args)

    assert not Path(args.audit_manifest).exists()


def test_candidate_ciks_must_be_unique_exact_and_subset_of_broad(tmp_path: Path) -> None:
    broad, _ = _default_rows()
    args, _ = _write_fixture(tmp_path, broad=broad, candidates=[_candidate("9")])
    with pytest.raises(MODULE.AuditError, match="absent from the universe"):
        MODULE.build(args)

    bad = _candidate("1")
    bad["resolution_methods"] = ["fuzzy_name"]
    bad["evidence"] = [{"resolution_method": "fuzzy_name"}]
    args, _ = _write_fixture(tmp_path / "bad", broad=broad, candidates=[bad])
    with pytest.raises(MODULE.AuditError, match="no exact-name evidence"):
        MODULE.build(args)

    unsupported = _candidate("1")
    unsupported.pop("evidence")
    args, _ = _write_fixture(tmp_path / "unsupported", broad=broad, candidates=[unsupported])
    with pytest.raises(MODULE.AuditError, match="no identity evidence"):
        MODULE.build(args)


@pytest.mark.parametrize(
    ("duplicate_kind", "message"), [("cik", "repeats CIK"), ("accession", "repeats accession")]
)
def test_duplicate_ciks_and_accessions_fail_closed(
    tmp_path: Path, duplicate_kind: str, message: str
) -> None:
    broad, candidates = _default_rows()
    if duplicate_kind == "cik":
        broad.append(copy.deepcopy(broad[0]))
    else:
        broad[1]["filings"][0]["accession_number"] = "A1"
    args, _ = _write_fixture(tmp_path, broad=broad, candidates=candidates)

    with pytest.raises(MODULE.AuditError, match=message):
        MODULE.build(args)


def test_malformed_record_and_inconsistent_first_filing_fields_fail(tmp_path: Path) -> None:
    broad, candidates = _default_rows()
    broad[0]["first_filing_year"] = 1999
    args, _ = _write_fixture(tmp_path, broad=broad, candidates=candidates)
    with pytest.raises(MODULE.AuditError, match="inconsistent first filing year"):
        MODULE.build(args)

    args, manifest = _write_fixture(tmp_path / "malformed")
    Path(args.universe).write_bytes(b'{"cik":\n')
    product = manifest["outputs"]["broad_issuer_universe"]
    data = Path(args.universe).read_bytes()
    product.update({"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)})
    Path(args.manifest).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(MODULE.AuditError, match="invalid JSON"):
        MODULE.build(args)


def test_normal_fixture_is_not_subject_to_real_data_assertions(tmp_path: Path) -> None:
    args, _ = _write_fixture(tmp_path)
    assert MODULE.build(args)["complete"] is True

    args.expected_real_data_contract = True
    with pytest.raises(MODULE.AuditError, match="expected real-data contract failed"):
        MODULE.build(args)


def test_output_is_deterministic_and_has_no_forbidden_structural_fields(tmp_path: Path) -> None:
    args, _ = _write_fixture(tmp_path)
    MODULE.build(args)
    first = Path(args.audit_manifest).read_bytes()
    MODULE.build(args)
    second = Path(args.audit_manifest).read_bytes()

    assert first == second
    lowered = first.lower()
    assert b'"naics' not in lowered
    assert b'"vintage' not in lowered
    assert b'"rate"' not in lowered


def test_manifest_bytes_use_pinned_product_paths_not_local_copy_names(tmp_path: Path) -> None:
    args, _ = _write_fixture(tmp_path)
    MODULE.build(args)
    first = Path(args.audit_manifest).read_bytes()
    copied_universe = tmp_path / "renamed-universe.jsonl"
    copied_exclusions = tmp_path / "renamed-exclusions.jsonl"
    shutil.copyfile(args.universe, copied_universe)
    shutil.copyfile(args.exclusions, copied_exclusions)
    args.universe = copied_universe
    args.exclusions = copied_exclusions

    MODULE.build(args)

    assert Path(args.audit_manifest).read_bytes() == first


def test_atomic_publish_failure_preserves_prior_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _ = _write_fixture(tmp_path)
    prior = b'{"prior":true}\n'
    Path(args.audit_manifest).write_bytes(prior)

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("publish failed")

    monkeypatch.setattr(MODULE.os, "replace", fail_replace)
    with pytest.raises(OSError, match="publish failed"):
        MODULE.build(args)

    assert Path(args.audit_manifest).read_bytes() == prior
    assert not list(Path(args.audit_manifest).parent.glob(f".{Path(args.audit_manifest).name}.*"))


def test_hard_link_output_alias_is_rejected_without_touching_input(tmp_path: Path) -> None:
    args, _ = _write_fixture(tmp_path)
    original = Path(args.universe).read_bytes()
    args.audit_manifest = tmp_path / "audit-hard-link.json"
    os.link(args.universe, args.audit_manifest)

    with pytest.raises(MODULE.AuditError, match="must not alias an input"):
        MODULE.build(args)

    assert Path(args.universe).read_bytes() == original


def test_tracked_report_reconciles_to_real_data_manifest() -> None:
    manifest = json.loads(TRACKED_MANIFEST.read_text(encoding="utf-8"))
    report = " ".join(TRACKED_REPORT.read_text(encoding="utf-8").split())
    cik = manifest["availability"]["cik_grain"]
    support = manifest["mechanical_common_support"]

    assert cik["broad"]["rows"] == 311_809
    assert cik["broad"]["sic_code_present"] == 7_041
    assert manifest["history_diagnostics"]["broad"]["pooled_investment_fund_ciks"] == 146_737
    assert support["candidate_ciks_with_at_least_1_provisional_in_same_cell"] == 4_287
    assert support["candidate_ciks_with_at_least_3_provisional_in_same_cell"] == 3_897
    assert "present for 7,041 of 311,809 issuer CIKs" in report
    assert "Of those, 4,287 share a cell with at least one" in report
    assert "and 3,897 share a cell with at least three" in report
    assert manifest["complete_sbir_identity"] is False
    assert manifest["complete_sbir_exclusion"] is False
    assert manifest["covariates_ready"] is False
    assert manifest["ready_for_matching"] is False
