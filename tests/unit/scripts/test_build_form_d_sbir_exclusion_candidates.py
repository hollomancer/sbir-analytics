"""Tests for the candidate-only Form D possible-SBIR contamination audit."""

import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_form_d_sbir_exclusion_candidates.py"


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("build_form_d_sbir_exclusion_candidates", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(
        b"".join(
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode() for row in rows
        )
    )


def _product(path: Path, row_count: int) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.name,
        "row_count": row_count,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _filing(
    cik: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    state: str = "CA",
    zip_code: str = "94105",
    accession: str = "0000000000-20-000001",
) -> dict[str, Any]:
    return {
        "accession_number": accession,
        "cik": cik,
        "filing_date": "2020-01-15",
        "issuer_name": name,
        "issuer_name_aliases": aliases if aliases is not None else [name],
        "source_quarter": "2020Q1",
        "state": state,
        "zip_code": zip_code,
    }


def _control(
    cik: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    filings: list[dict[str, Any]] | None = None,
    state: str = "CA",
) -> dict[str, Any]:
    filing_rows = filings or [_filing(cik, name, aliases=aliases, state=state)]
    return {
        "cik": cik,
        "filing_count": len(filing_rows),
        "filings": filing_rows,
        "firm_key": f"form_d_cik:{cik}",
        "issuer_name": name,
        "issuer_name_aliases": aliases if aliases is not None else [name],
        "state": state,
    }


def _exclusion(cik: str = "900") -> dict[str, Any]:
    return {
        "candidate_exclusion": True,
        "cik": cik,
        "evidence": [{"resolution_method": "candidate_exact_normalized_name"}],
        "evidence_count": 1,
        "firm_key": f"form_d_cik:{cik}",
        "resolution_methods": ["candidate_exact_normalized_name"],
        "schema_version": 1,
    }


def _award(
    company: str,
    *,
    state: str = "CA",
    zip_code: str = "94105",
    year: str = "2018",
    uei: str = "IGNORED-UEI",
    duns: str = "000000001",
) -> dict[str, str]:
    return {
        "Company": company,
        "State": state,
        "Zip": zip_code,
        "Award Year": year,
        "UEI": uei,
        "Duns": duns,
    }


def _fixture(
    tmp_path: Path,
    *,
    controls: list[dict[str, Any]],
    awards: list[dict[str, str]],
    exclusions: list[dict[str, Any]] | None = None,
    stem: str = "source",
) -> dict[str, Path]:
    root = tmp_path / stem
    root.mkdir()
    controls_path = root / "form_d_control_identity_universe.provisional.jsonl"
    exclusions_path = root / "sbir_cik_exclusion_candidates.identity-staging.jsonl"
    awards_path = root / "award_data.csv"
    manifest_path = root / "agency-private-capital-form-d-control-universe.manifest.json"
    output_dir = root / "output"
    exact_exclusions = exclusions if exclusions is not None else [_exclusion()]
    _jsonl(controls_path, controls)
    _jsonl(exclusions_path, exact_exclusions)
    with awards_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Company", "State", "Zip", "Award Year", "UEI", "Duns"]
        )
        writer.writeheader()
        writer.writerows(awards)
    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion": {
            "awards_csv": _product(awards_path, len(awards)),
            "exact_match": {"normalizer_version": "organization-key-v1"},
            "explicit_cik_inputs": [],
        },
        "exclusion_recall": "unknown",
        "identity_only": True,
        "invariants": {
            "control_ciks_unique": True,
            "control_exclusion_overlap_count": 0,
            "exclusion_ciks_unique": True,
            "ready_for_matching_is_false": True,
        },
        "outputs": {
            "candidate_sbir_cik_exclusions": _product(exclusions_path, len(exact_exclusions)),
            "provisional_control_identity_universe": _product(controls_path, len(controls)),
        },
        "ready_for_matching": False,
        "schema_version": 1,
        "source_counts": {
            "excluded_broad_ciks": len(exact_exclusions),
            "provisional_control_ciks": len(controls),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "awards": awards_path,
        "controls": controls_path,
        "exclusions": exclusions_path,
        "manifest": manifest_path,
        "output": output_dir,
    }


def _args(paths: dict[str, Path]) -> list[str]:
    return [
        "--source-manifest",
        str(paths["manifest"]),
        "--provisional-controls",
        str(paths["controls"]),
        "--exact-exclusions",
        str(paths["exclusions"]),
        "--awards-csv",
        str(paths["awards"]),
        "--output-dir",
        str(paths["output"]),
        "--code-version",
        "test-commit",
    ]


def _build(module: Any, paths: dict[str, Path]) -> dict[str, Any]:
    return module.build(module.parse_args(_args(paths)))


def _candidate_product(manifest: dict[str, Any]) -> dict[str, Any]:
    assert len(manifest["outputs"]) == 1
    return next(iter(manifest["outputs"].values()))


def _rows(paths: dict[str, Path], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    product = _candidate_product(manifest)
    data = (paths["output"] / product["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == product["sha256"]
    assert len(data) == product["size_bytes"]
    rows = [json.loads(line) for line in data.splitlines()]
    assert len(rows) == product["row_count"]
    return rows


def test_inclusive_route_boundaries_and_false_gates(module, tmp_path: Path) -> None:
    controls = [
        _control("1", "ALPHAABCDEFGHIJKLMNO", state="New York"),
        _control("2", "GAMMAABCDEFGHIJKLMNO", state="California"),
        _control(
            "3",
            "ALPHAABCDE",
            filings=[_filing("3", "ALPHAABCDE", state="Nevada", zip_code="02139-1234")],
            state="Nevada",
        ),
        _control("4", "GAMMAABCDEFGHIJKLMNO", state="Texas"),
        _control(
            "5",
            "OMEGA MEDICAL DEVICE",
            filings=[_filing("5", "OMEGA MEDICAL DEVICE", zip_code="10001")],
        ),
    ]
    awards = [
        _award("ALPHAABCDEFGHIJKLMNP", state="CA", zip_code="99999"),  # ratio = .95
        _award("GAMMAABCDEFGHIJKLXYZ", state="CA", zip_code="99998"),  # ratio = .85
        _award("ZLPHAXBCDE", state="MA", zip_code="02139"),  # ratio = .80
        _award("GAMMAABCDEFGHIJKXYZQ", state="TX", zip_code="99997"),  # ratio = .80
        _award("OMEGA MEDICAL SYSTEM", state="CA", zip_code="10001"),  # ratio = .75
    ]
    paths = _fixture(tmp_path, controls=controls, awards=awards)

    manifest = _build(module, paths)
    rows = _rows(paths, manifest)

    assert [(row["cik"], row["candidate_routes"]) for row in rows] == [
        ("1", ["strong_name"]),
        ("2", ["state_supported"]),
        ("3", ["zip_supported"]),
    ]
    assert all(row["firm_key"] == f"form_d_cik:{row['cik']}" for row in rows)
    assert all(row["candidate_only"] is True for row in rows)
    assert all(row["adjudication_status"] == "unreviewed" for row in rows)
    assert manifest["complete"] is True
    assert manifest["candidate_only"] is True
    assert manifest["applied_exclusion_count"] == 0
    assert manifest["complete_sbir_exclusion"] is False
    assert manifest["exclusion_recall"] == "unknown"
    assert manifest["covariates_ready"] is False
    assert manifest["ready_for_matching"] is False
    assert manifest["identity_only"] is True
    assert manifest["parameters"]["minimum_normalized_name_length"] == 6
    assert manifest["parameters"]["thresholds"] == {
        "state_supported_ratio": 0.85,
        "strong_name_ratio": 0.95,
        "zip_supported_ratio": 0.8,
    }


def test_historical_aliases_and_filing_geography_are_exhaustive(module, tmp_path: Path) -> None:
    controls = [
        _control(
            "10",
            "UNRELATED HOLDINGS",
            aliases=["UNRELATED HOLDINGS"],
            filings=[
                _filing(
                    "10",
                    "UNRELATED HOLDINGS",
                    aliases=["UNRELATED HOLDINGS", "GAMMAABCDEFGHIJKLMNO"],
                    state="California",
                    zip_code="94105-4410",
                )
            ],
        ),
        _control(
            "11",
            "ANOTHER HOLDING",
            filings=[
                _filing(
                    "11",
                    "ANOTHER HOLDING",
                    aliases=["ANOTHER HOLDING", "ALPHAABCDE"],
                    state="Nevada",
                    zip_code="02139-9999",
                )
            ],
        ),
    ]
    awards = [
        _award("GAMMAABCDEFGHIJKLXYZ", state="CA", zip_code="99999"),
        _award("ZLPHAXBCDE", state="MA", zip_code="02139"),
    ]
    paths = _fixture(tmp_path, controls=controls, awards=awards)

    rows = _rows(paths, _build(module, paths))

    assert [(row["cik"], row["candidate_routes"]) for row in rows] == [
        ("10", ["state_supported"]),
        ("11", ["zip_supported"]),
    ]
    assert rows[0]["issuer_name_normalized"] == "GAMMAABCDEFGHIJKLMNO"
    assert rows[1]["issuer_name_normalized"] == "ALPHAABCDE"


def test_multiline_csv_record_is_one_award_and_all_routes_are_recorded(
    module, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("12", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED\nSYSTEMS")],
    )

    manifest = _build(module, paths)
    rows = _rows(paths, manifest)

    assert manifest["counts"]["sbir_award_rows"] == 1
    assert len(rows) == 1
    assert rows[0]["candidate_routes"] == ["strong_name", "state_supported", "zip_supported"]


def test_best_alias_must_support_a_declared_route(module, tmp_path: Path) -> None:
    control = _control(
        "13",
        "UNRELATED HOLDINGS",
        aliases=[
            "GAMMAABCDEFGHIJKLMNO",  # state-supported at .85
            "XAMMAABCDEFGHIJKLXYZ",  # higher similarity, but wrong retrieval prefix
        ],
    )
    paths = _fixture(
        tmp_path,
        controls=[control],
        awards=[_award("GAMMAABCDEFGHIJKLXYZ", state="CA", zip_code="99999")],
    )

    rows = _rows(paths, _build(module, paths))

    assert len(rows) == 1
    assert rows[0]["candidate_routes"] == ["state_supported"]
    assert rows[0]["issuer_name_normalized"] == "GAMMAABCDEFGHIJKLMNO"
    assert rows[0]["ratio_similarity"] == 0.85


def test_candidate_dedup_best_evidence_and_reordering_determinism(module, tmp_path: Path) -> None:
    filings = [
        _filing(
            "20",
            "BETA QUANTUM LABORATORY",
            aliases=["BETA QUANTUM LABORATORY", "BETA QUANTUM LAB"],
            accession="0000000000-20-000002",
        ),
        _filing(
            "20",
            "BETA QUANTUM LAB",
            aliases=["BETA QUANTUM LAB", "BETA QUANTUM LABORATORY"],
            accession="0000000000-20-000003",
        ),
    ]
    first = _control(
        "20",
        "BETA QUANTUM LABORATORY",
        aliases=["BETA QUANTUM LABORATORY", "BETA QUANTUM LAB"],
        filings=filings,
    )
    second = _control(
        "20",
        "BETA QUANTUM LABORATORY",
        aliases=["BETA QUANTUM LAB", "BETA QUANTUM LABORATORY"],
        filings=list(reversed(filings)),
    )
    awards = [
        _award("BETA QUANTUM LABS", year="2019", uei="ONE", duns="1"),
        _award("BETA QUANTUM LABS", year="2018", uei="TWO", duns="2"),
    ]
    paths_a = _fixture(tmp_path, controls=[first], awards=awards, stem="a")
    paths_b = _fixture(tmp_path, controls=[second], awards=list(reversed(awards)), stem="b")

    rows_a = _rows(paths_a, _build(module, paths_a))
    rows_b = _rows(paths_b, _build(module, paths_b))

    assert rows_a == rows_b
    assert len(rows_a) == 1
    row = rows_a[0]
    expected_id = hashlib.sha256(
        b"form-d-sbir-exclusion-candidate-v1\0" + b"20\0BETA QUANTUM LABS"
    ).hexdigest()
    assert row["candidate_id"] == expected_id
    assert row["issuer_name_normalized"] == "BETA QUANTUM LAB"
    assert set(row) >= {"ratio_similarity", "token_set_similarity", "token_sort_similarity"}
    assert "uei" not in json.dumps(row).lower()
    assert "duns" not in json.dumps(row).lower()


def test_short_geographic_lookalikes_do_not_qualify(module, tmp_path: Path) -> None:
    control = _control(
        "30",
        "ABCDE",
        filings=[_filing("30", "ABCDE", state="CA", zip_code="90210")],
    )
    paths = _fixture(
        tmp_path,
        controls=[control],
        awards=[_award("XBCDE", state="CA", zip_code="90210")],
    )
    assert _rows(paths, _build(module, paths)) == []


@pytest.mark.parametrize("input_name", ["controls", "exclusions", "awards"])
def test_pinned_input_mismatch_fails_closed(module, tmp_path: Path, input_name: str) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("40", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    with paths[input_name].open("ab") as handle:
        handle.write(b"corruption")

    with pytest.raises(module.BuildError, match="(byte|row|SHA|hash|pin)"):
        _build(module, paths)


def test_source_manifest_internal_count_mismatch_fails_closed(module, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("41", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    manifest = json.loads(paths["manifest"].read_text())
    manifest["source_counts"]["provisional_control_ciks"] = 2
    paths["manifest"].write_text(json.dumps(manifest))

    with pytest.raises(module.BuildError, match="control count"):
        _build(module, paths)


def test_source_manifest_exact_exclusion_count_mismatch_fails_closed(
    module, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("410", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    manifest = json.loads(paths["manifest"].read_text())
    manifest["source_counts"]["excluded_broad_ciks"] = 0
    paths["manifest"].write_text(json.dumps(manifest))

    with pytest.raises(module.BuildError, match="exact exclusion count"):
        _build(module, paths)


def test_blank_awards_csv_header_fails_closed(module, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("411", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    paths["awards"].write_text(
        "Company,State,Zip,Award Year,UEI,Duns,\n"
        "ACME ADVANCED SYSTEM,CA,94105,2018,IGNORED-UEI,000000001,\n"
    )
    manifest = json.loads(paths["manifest"].read_text())
    manifest["exclusion"]["awards_csv"] = _product(paths["awards"], 1)
    paths["manifest"].write_text(json.dumps(manifest))

    with pytest.raises(module.BuildError, match="blank column name"):
        _build(module, paths)


def test_boolean_source_gate_does_not_accept_integer_zero(module, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("42", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    manifest = json.loads(paths["manifest"].read_text())
    manifest["ready_for_matching"] = 0
    paths["manifest"].write_text(json.dumps(manifest))

    with pytest.raises(module.BuildError, match="ready_for_matching"):
        _build(module, paths)


def test_exact_exclusion_overlap_is_rejected_and_never_emitted(module, tmp_path: Path) -> None:
    control = _control("50", "ACME ADVANCED SYSTEMS")
    paths = _fixture(
        tmp_path,
        controls=[control],
        awards=[_award("ACME ADVANCED SYSTEM")],
        exclusions=[_exclusion("50")],
    )

    with pytest.raises(module.BuildError, match="(overlap|exclusion)"):
        _build(module, paths)


def test_invalid_control_firm_key_fails_closed(module, tmp_path: Path) -> None:
    control = _control("60", "ACME ADVANCED SYSTEMS")
    control["firm_key"] = "uei:NOT-A-CIK"
    paths = _fixture(
        tmp_path,
        controls=[control],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )

    with pytest.raises(module.BuildError, match="firm_key"):
        _build(module, paths)


def test_publication_failure_preserves_prior_manifest(module, tmp_path: Path, monkeypatch) -> None:
    paths = _fixture(
        tmp_path,
        controls=[_control("70", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
    )
    first = _build(module, paths)
    manifest_path = next(paths["output"].glob("*.manifest.json"))
    original_manifest = manifest_path.read_bytes()
    original_product = _candidate_product(first)
    original_product_path = paths["output"] / original_product["path"]
    assert original_product_path.is_file()

    real_replace = os.replace

    def fail_product_publish(source: str | Path, destination: str | Path) -> None:
        if Path(destination).suffix == ".jsonl":
            raise OSError("injected product publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_product_publish)
    with pytest.raises(OSError, match="injected"):
        _build(module, paths)

    assert manifest_path.read_bytes() == original_manifest
    assert (
        hashlib.sha256(original_product_path.read_bytes()).hexdigest() == original_product["sha256"]
    )


def test_manifest_publication_failure_preserves_prior_generation(
    module, tmp_path: Path, monkeypatch
) -> None:
    first_paths = _fixture(
        tmp_path,
        controls=[_control("80", "ACME ADVANCED SYSTEMS")],
        awards=[_award("ACME ADVANCED SYSTEM")],
        stem="first",
    )
    first = _build(module, first_paths)
    manifest_path = next(first_paths["output"].glob("*.manifest.json"))
    original_manifest = manifest_path.read_bytes()
    original_product = _candidate_product(first)
    original_product_path = first_paths["output"] / original_product["path"]

    second_paths = _fixture(
        tmp_path,
        controls=[_control("81", "BETA ADVANCED SYSTEMS")],
        awards=[_award("BETA ADVANCED SYSTEM")],
        stem="second",
    )
    second_paths["output"] = first_paths["output"]
    real_replace = os.replace

    def fail_manifest_publish(source: str | Path, destination: str | Path) -> None:
        if Path(destination).suffix == ".json":
            raise OSError("injected manifest publication failure")
        real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_manifest_publish)
    with pytest.raises(OSError, match="injected"):
        _build(module, second_paths)

    assert manifest_path.read_bytes() == original_manifest
    assert (
        hashlib.sha256(original_product_path.read_bytes()).hexdigest() == original_product["sha256"]
    )
