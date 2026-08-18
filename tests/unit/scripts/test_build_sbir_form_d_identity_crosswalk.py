"""Tests for the atomic, candidate-only SBIR ↔ Form D identity crosswalk."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_sbir_form_d_identity_crosswalk.py"
IDENTITY_FIELDS = [
    "issuer_name",
    "street1",
    "street2",
    "city",
    "state",
    "zip_code",
    "issuer_phone",
    "jurisdiction_of_incorporation",
    "year_of_incorporation",
]


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("build_sbir_form_d_identity_crosswalk", SCRIPT)
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
    accession: str | None = None,
) -> dict[str, Any]:
    filing_aliases = aliases if aliases is not None else [name]
    return {
        "accession_number": accession or f"0000000000-20-{int(cik):06d}",
        "cik": cik,
        "city": "Boston",
        "issuer_name": name,
        "issuer_name_aliases": filing_aliases,
        "issuer_phone": "617-555-0100",
        "jurisdiction_of_incorporation": "DE",
        "state": "MA",
        "street1": "1 Main Street",
        "street2": "Suite 2",
        "year_of_incorporation": 2010,
        "zip_code": "02110",
    }


def _issuer(
    cik: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    filings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    filing_rows = filings or [_filing(cik, name, aliases=aliases)]
    aggregate_aliases = sorted(
        {alias for filing in filing_rows for alias in filing["issuer_name_aliases"]}
    )
    return {
        "cik": cik,
        "filing_count": len(filing_rows),
        "filings": filing_rows,
        "firm_key": f"form_d_cik:{cik}",
        "issuer_name": name,
        "issuer_name_aliases": aggregate_aliases,
        "schema_version": 1,
    }


def _award(
    company: str,
    *,
    uei: str = "",
    duns: str = "",
) -> dict[str, str]:
    return {"Company": company, "UEI": uei, "Duns": duns}


def _fixture(
    tmp_path: Path,
    *,
    awards: list[dict[str, str]],
    issuers: list[dict[str, Any]],
    exact_cik_count: int,
    matched_name_count: int,
    stem: str = "source",
) -> dict[str, Path | str]:
    root = tmp_path / stem
    root.mkdir()
    awards_path = root / "award_data.csv"
    broad_path = root / "form_d_issuer_universe.identity-staging.jsonl"
    manifest_path = root / "form_d_control_universe.manifest.json"
    with awards_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company", "UEI", "Duns"])
        writer.writeheader()
        writer.writerows(awards)
    _jsonl(broad_path, sorted(issuers, key=lambda row: row["cik"]))
    quarters = [f"{year}Q{quarter}" for year in range(2009, 2025) for quarter in range(1, 5)]
    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion": {
            "awards_csv": _product(awards_path, len(awards)),
            "exact_match": {
                "candidate_cik_count": exact_cik_count,
                "matched_normalized_name_count": matched_name_count,
                "normalizer_version": "organization-key-v1",
            },
        },
        "exclusion_recall": "unknown",
        "identity_evidence_contract": {
            "fields": IDENTITY_FIELDS,
            "grain": "form_d_filing_accession",
            "historical_aliases_retained": True,
            "source_table": "ISSUERS.tsv",
        },
        "identity_only": True,
        "invariants": {"broad_ciks_unique": True},
        "outputs": {"broad_issuer_universe": _product(broad_path, len(issuers))},
        "parameters": {
            "end_quarter": "2024Q4",
            "quarter_count": 64,
            "quarters": quarters,
            "start_quarter": "2009Q1",
        },
        "ready_for_matching": False,
        "schema_version": 1,
        "source_counts": {"issuer_ciks": len(issuers)},
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_data)
    return {
        "awards": awards_path,
        "broad": broad_path,
        "manifest": manifest_path,
        "manifest_sha": hashlib.sha256(manifest_data).hexdigest(),
        "output": root / "release",
        "root": root,
    }


def _args(paths: dict[str, Path | str], *, output: Path | None = None) -> list[str]:
    return [
        "--control-manifest",
        str(paths["manifest"]),
        "--control-manifest-sha256",
        str(paths["manifest_sha"]),
        "--awards-csv",
        str(paths["awards"]),
        "--output-dir",
        str(output or paths["output"]),
        "--code-version",
        "a" * 40,
    ]


def _build(
    module: Any, paths: dict[str, Path | str], *, output: Path | None = None
) -> dict[str, Any]:
    return module.build(module.parse_args(_args(paths, output=output)))


def _rows(output: Path, product: dict[str, Any]) -> list[dict[str, Any]]:
    data = (output / product["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == product["sha256"]
    assert len(data) == product["size_bytes"]
    rows = [json.loads(line) for line in data.splitlines()]
    assert len(rows) == product["row_count"]
    return rows


def test_multi_cik_and_multi_component_names_expand_atomically(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[
            _award("Acme, Inc.", uei="UEI000000001", duns="000000001"),
            _award("ACME LLC", uei="UEI000000002", duns="000000002"),
            _award("Acme"),
        ],
        issuers=[_issuer("10", "ACME INC"), _issuer("20", "ACME LLC")],
        exact_cik_count=2,
        matched_name_count=1,
    )

    manifest = _build(module, paths)
    output = paths["output"]
    assert isinstance(output, Path)
    ledger = _rows(output, manifest["outputs"]["firm_identity_ledger"])
    edges = _rows(output, manifest["outputs"]["candidate_edges"])

    assert len(ledger) == 3
    assert {row["component_status"] for row in ledger} == {
        "identifier_consistent",
        "name_only",
    }
    assert len(edges) == 6
    assert len({(row["sbir_firm_id"], row["form_d_cik"]) for row in edges}) == 6
    assert {row["form_d_cik"] for row in edges} == {"10", "20"}
    for edge in edges:
        assert edge["decision"] == "candidate_unreviewed"
        assert edge["same_legal_entity"] is None
        assert edge["identity_accepted"] is False
        assert edge["exclusion_eligible"] is False
        assert edge["matching_eligible"] is False
        assert edge["rate_eligible"] is False
        expected_accession = f"0000000000-20-{int(edge['form_d_cik']):06d}"
        assert edge["form_d_source_accessions"] == [expected_accession]
        assert all(
            witness["accession_number"] == expected_accession
            for evidence in edge["name_evidence"]
            for witness in evidence["form_d"]
        )
    assert manifest["counts"]["candidate_edges"] == 6
    assert manifest["counts"]["firms_with_multiple_candidate_ciks"] == 3
    assert manifest["counts"]["form_d_ciks_with_multiple_candidate_firms"] == 2
    assert manifest["identity_accepted"] is False
    assert manifest["covariates_ready"] is False
    assert manifest["identity_only"] is True
    assert manifest["ready_for_matching"] is False


def test_identifier_bridges_and_malformed_values_are_quarantined(
    module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        awards=[
            _award("Bridge Corp", uei="UEI000000001", duns="000000001"),
            _award("Bridge Corporation", uei="UEI000000002", duns="000000001"),
            _award("Bridge Corp", uei="UEI000000001", duns="000000002"),
            _award("Legacy Labs", duns="BAD-DUNS"),
        ],
        issuers=[_issuer("10", "Bridge Corp"), _issuer("20", "Legacy Labs")],
        exact_cik_count=2,
        matched_name_count=2,
    )

    manifest = _build(module, paths)
    output = paths["output"]
    assert isinstance(output, Path)
    ledger = _rows(output, manifest["outputs"]["firm_identity_ledger"])
    by_names = {tuple(row["normalized_names"]): row for row in ledger}

    bridge = by_names[("BRIDGE",)]
    assert bridge["component_status"] == "quarantined_conflict"
    assert bridge["quarantine_reasons"] == ["multiple_duns", "multiple_ueis"]
    legacy = by_names[("LEGACY LABS",)]
    assert legacy["identity_basis"] == "name_key"
    assert legacy["component_status"] == "quarantined_conflict"
    assert legacy["quarantine_reasons"] == ["malformed_duns"]
    assert manifest["counts"]["quarantined_components"] == 2


def test_name_only_identity_stays_separate_from_equal_identifier_name(
    module: Any, tmp_path: Path
) -> None:
    awards = [
        _award("Separate Systems", uei="UEI000000001", duns="000000001"),
        _award("Separate Systems"),
    ]
    paths = _fixture(
        tmp_path,
        awards=awards,
        issuers=[_issuer("10", "Separate Systems")],
        exact_cik_count=1,
        matched_name_count=1,
    )

    first = _build(module, paths)
    output = paths["output"]
    assert isinstance(output, Path)
    ledger = _rows(output, first["outputs"]["firm_identity_ledger"])
    assert len(ledger) == 2
    assert len({row["sbir_firm_id"] for row in ledger}) == 2
    assert {row["identity_basis"] for row in ledger} == {"identifiers", "name_key"}

    reversed_paths = _fixture(
        tmp_path,
        awards=list(reversed(awards)),
        issuers=[_issuer("10", "Separate Systems")],
        exact_cik_count=1,
        matched_name_count=1,
        stem="reversed",
    )
    second = _build(module, reversed_paths)
    reversed_output = reversed_paths["output"]
    assert isinstance(reversed_output, Path)
    reversed_ledger = _rows(reversed_output, second["outputs"]["firm_identity_ledger"])
    assert {row["sbir_firm_id"] for row in reversed_ledger} == {
        row["sbir_firm_id"] for row in ledger
    }


def test_source_record_is_csv_record_ordinal_for_multiline_fields(
    module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Alpha\nLaboratories"), _award("Beta Labs")],
        issuers=[_issuer("10", "Alpha Laboratories"), _issuer("20", "Beta Labs")],
        exact_cik_count=2,
        matched_name_count=2,
    )

    manifest = _build(module, paths)
    output = paths["output"]
    assert isinstance(output, Path)
    ledger = _rows(output, manifest["outputs"]["firm_identity_ledger"])
    assert sorted(
        source["source_record"] for row in ledger for source in row["source_records"]
    ) == [1, 2]
    assert any(
        source["raw_name"] == "Alpha\nLaboratories"
        for row in ledger
        for source in row["source_records"]
    )
    assert manifest["invariants"]["all_sbir_source_records_preserved_once"] is True


def test_identical_runs_are_byte_identical_and_content_addressed(
    module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme", uei="UEI000000001", duns="000000001")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    first = _build(module, paths, output=first_output)
    second = _build(module, paths, output=second_output)

    assert first == second
    assert (first_output / "sbir_form_d_identity_crosswalk.manifest.json").read_bytes() == (
        second_output / "sbir_form_d_identity_crosswalk.manifest.json"
    ).read_bytes()
    for product in first["outputs"].values():
        assert product["sha256"] in product["path"]
        assert (first_output / product["path"]).read_bytes() == (
            second_output / product["path"]
        ).read_bytes()


def test_manifest_pin_drift_fails_before_publication(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    output = paths["output"]
    assert isinstance(output, Path)
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_text("prior release\n")
    args = _args(paths)
    args[args.index("--control-manifest-sha256") + 1] = "0" * 64

    with pytest.raises(module.BuildError, match="external pin"):
        module.build(module.parse_args(args))

    assert sentinel.read_text() == "prior release\n"
    assert list(output.iterdir()) == [sentinel]


def test_code_version_is_an_explicit_reproducibility_input(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    args = _args(paths)
    index = args.index("--code-version")
    del args[index : index + 2]

    with pytest.raises(SystemExit):
        module.parse_args(args)

    invalid_args = _args(paths)
    invalid_args[invalid_args.index("--code-version") + 1] = "not-a-commit"
    with pytest.raises(module.BuildError, match="full lowercase Git commit"):
        module.build(module.parse_args(invalid_args))


def test_output_directory_must_not_contain_a_pinned_input(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    source_root = paths["root"]
    assert isinstance(source_root, Path)

    with pytest.raises(module.BuildError, match="contains a pinned input"):
        _build(module, paths, output=source_root)

    assert Path(paths["manifest"]).is_file()
    assert Path(paths["broad"]).is_file()
    assert Path(paths["awards"]).is_file()


def test_award_or_broad_product_drift_fails_closed(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    awards_path = paths["awards"]
    assert isinstance(awards_path, Path)
    awards_path.write_text(awards_path.read_text() + "DRIFT,,\n")
    with pytest.raises(module.BuildError, match="awards CSV bytes"):
        _build(module, paths)

    broad_paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
        stem="broad-drift",
    )
    broad_path = broad_paths["broad"]
    assert isinstance(broad_path, Path)
    broad_path.write_bytes(broad_path.read_bytes() + b"\n")
    with pytest.raises(module.BuildError, match="byte count"):
        _build(module, broad_paths)


def test_untraceable_alias_and_missing_identity_field_fail(module: Any, tmp_path: Path) -> None:
    issuer = _issuer("10", "Acme")
    issuer["issuer_name_aliases"].append("UNTRACED")
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[issuer],
        exact_cik_count=1,
        matched_name_count=1,
    )
    with pytest.raises(module.BuildError, match="untraceable aggregate aliases"):
        _build(module, paths)

    missing = _issuer("10", "Acme")
    del missing["filings"][0]["street2"]
    missing_paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[missing],
        exact_cik_count=1,
        matched_name_count=1,
        stem="missing-field",
    )
    with pytest.raises(module.BuildError, match="street2"):
        _build(module, missing_paths)


def test_accession_cannot_appear_under_multiple_ciks(module: Any, tmp_path: Path) -> None:
    shared_accession = "0000000000-20-000001"
    paths = _fixture(
        tmp_path,
        awards=[_award("Alpha"), _award("Beta")],
        issuers=[
            _issuer(
                "10",
                "Alpha",
                filings=[_filing("10", "Alpha", accession=shared_accession)],
            ),
            _issuer(
                "20",
                "Beta",
                filings=[_filing("20", "Beta", accession=shared_accession)],
            ),
        ],
        exact_cik_count=2,
        matched_name_count=2,
    )

    with pytest.raises(module.BuildError, match="repeats accession"):
        _build(module, paths)


def test_unsafe_manifest_product_path_is_rejected(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    manifest_path = paths["manifest"]
    assert isinstance(manifest_path, Path)
    manifest = json.loads(manifest_path.read_text())
    manifest["outputs"]["broad_issuer_universe"]["path"] = "../broad.jsonl"
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(data)
    paths["manifest_sha"] = hashlib.sha256(data).hexdigest()

    with pytest.raises(module.BuildError, match="safe filename"):
        _build(module, paths)


def test_publication_failure_restores_previous_release(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    output = paths["output"]
    assert isinstance(output, Path)
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_bytes(b"prior release\n")
    original_replace = module.os.replace

    def fail_release_swap(source: str | Path, destination: str | Path) -> None:
        if Path(source).name.startswith(f".{output.name}.staging-") and Path(destination) == output:
            raise OSError("injected release swap failure")
        original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_release_swap)
    with pytest.raises(OSError, match="injected"):
        _build(module, paths)

    assert sentinel.read_bytes() == b"prior release\n"
    assert list(output.iterdir()) == [sentinel]
    assert not list(output.parent.glob(f".{output.name}.backup-*"))
    assert not list(output.parent.glob(f".{output.name}.staging-*"))


def test_edges_contain_no_offering_amounts(module: Any, tmp_path: Path) -> None:
    paths = _fixture(
        tmp_path,
        awards=[_award("Acme")],
        issuers=[_issuer("10", "Acme")],
        exact_cik_count=1,
        matched_name_count=1,
    )
    manifest = _build(module, paths)
    output = paths["output"]
    assert isinstance(output, Path)
    edges = _rows(output, manifest["outputs"]["candidate_edges"])
    serialized = json.dumps(edges, sort_keys=True)
    assert "total_amount" not in serialized
    assert "offering_amount" not in serialized
    assert "amount_sold" not in serialized
