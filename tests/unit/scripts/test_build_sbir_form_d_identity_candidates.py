"""Tests for the bounded SBIR ↔ Form D identity-candidate enrichment release."""

import csv
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).parents[3]
CANDIDATE_SCRIPT = REPO_ROOT / "scripts/data/build_sbir_form_d_identity_candidates.py"
CROSSWALK_SCRIPT = REPO_ROOT / "scripts/data/build_sbir_form_d_identity_crosswalk.py"
CODE_VERSION = "a" * 40
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
AWARD_FIELDS = [
    "Company",
    "UEI",
    "Duns",
    "Address1",
    "City",
    "State",
    "Zip",
    "Contact Phone",
    "PI Phone",
    "Award Amount",
]


def _load_script(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def module() -> Any:
    return _load_script("build_sbir_form_d_identity_candidates", CANDIDATE_SCRIPT)


@pytest.fixture
def crosswalk_module() -> Any:
    return _load_script("build_sbir_form_d_identity_crosswalk_for_candidates", CROSSWALK_SCRIPT)


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


def _award(
    company: str,
    *,
    uei: str = "",
    duns: str = "",
    street1: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
    contact_phone: str = "",
    pi_phone: str = "",
    award_amount: str = "",
) -> dict[str, str]:
    return {
        "Address1": street1,
        "Award Amount": award_amount,
        "City": city,
        "Company": company,
        "Contact Phone": contact_phone,
        "Duns": duns,
        "PI Phone": pi_phone,
        "State": state,
        "UEI": uei,
        "Zip": zip_code,
    }


def _filing(
    cik: str,
    name: str,
    *,
    aliases: list[str] | None = None,
    accession: str | None = None,
    street1: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
    issuer_phone: str = "",
    **extra: Any,
) -> dict[str, Any]:
    filing = {
        "accession_number": accession or f"{int(cik):010d}-20-{int(cik):06d}",
        "cik": cik,
        "city": city,
        "issuer_name": name,
        "issuer_name_aliases": aliases if aliases is not None else [name],
        "issuer_phone": issuer_phone,
        "jurisdiction_of_incorporation": "DE",
        "state": state,
        "street1": street1,
        "street2": "",
        "year_of_incorporation": 2010,
        "zip_code": zip_code,
    }
    filing.update(extra)
    return filing


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


def _fixture(
    tmp_path: Path,
    crosswalk_module: Any,
    *,
    awards: list[dict[str, str]],
    issuers: list[dict[str, Any]],
    stem: str = "source",
) -> dict[str, Any]:
    root = tmp_path / stem
    root.mkdir()
    awards_path = root / "award_data.csv"
    broad_path = root / "form_d_issuer_universe.identity-staging.jsonl"
    control_manifest_path = root / "form_d_control_universe.manifest.json"
    with awards_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AWARD_FIELDS)
        writer.writeheader()
        writer.writerows(awards)
    _jsonl(broad_path, sorted(issuers, key=lambda row: row["cik"]))

    award_names = {
        normalized
        for award in awards
        if (normalized := crosswalk_module._normalizer(award["Company"]))
    }
    matched_names: set[str] = set()
    matched_ciks: set[str] = set()
    for issuer in issuers:
        for filing in issuer["filings"]:
            for alias in filing["issuer_name_aliases"]:
                normalized = crosswalk_module._normalizer(alias)
                if normalized in award_names:
                    matched_names.add(normalized)
                    matched_ciks.add(issuer["cik"])

    manifest = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion": {
            "awards_csv": _product(awards_path, len(awards)),
            "exact_match": {
                "candidate_cik_count": len(matched_ciks),
                "matched_normalized_name_count": len(matched_names),
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
            "quarters": [
                f"{year}Q{quarter}" for year in range(2009, 2025) for quarter in range(1, 5)
            ],
            "start_quarter": "2009Q1",
        },
        "ready_for_matching": False,
        "schema_version": 1,
        "source_counts": {"issuer_ciks": len(issuers)},
    }
    control_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    control_manifest_path.write_bytes(control_data)
    control_sha = hashlib.sha256(control_data).hexdigest()

    crosswalk_output = root / "crosswalk"
    crosswalk_module.build(
        crosswalk_module.parse_args(
            [
                "--control-manifest",
                str(control_manifest_path),
                "--control-manifest-sha256",
                control_sha,
                "--awards-csv",
                str(awards_path),
                "--output-dir",
                str(crosswalk_output),
                "--code-version",
                CODE_VERSION,
            ]
        )
    )
    crosswalk_manifest_path = crosswalk_output / "sbir_form_d_identity_crosswalk.manifest.json"
    crosswalk_data = crosswalk_manifest_path.read_bytes()
    return {
        "awards": awards_path,
        "broad": broad_path,
        "candidate_output": root / "candidates",
        "control_manifest": control_manifest_path,
        "control_sha": control_sha,
        "crosswalk_manifest": crosswalk_manifest_path,
        "crosswalk_output": crosswalk_output,
        "crosswalk_sha": hashlib.sha256(crosswalk_data).hexdigest(),
        "root": root,
    }


def _args(paths: dict[str, Any], *, output: Path | None = None) -> list[str]:
    return [
        "--crosswalk-manifest",
        str(paths["crosswalk_manifest"]),
        "--crosswalk-manifest-sha256",
        paths["crosswalk_sha"],
        "--control-manifest",
        str(paths["control_manifest"]),
        "--control-manifest-sha256",
        paths["control_sha"],
        "--awards-csv",
        str(paths["awards"]),
        "--output-dir",
        str(output or paths["candidate_output"]),
        "--code-version",
        CODE_VERSION,
    ]


def _build(module: Any, paths: dict[str, Any], *, output: Path | None = None) -> dict[str, Any]:
    return module.build(module.parse_args(_args(paths, output=output)))


def _rows(output: Path, product: dict[str, Any]) -> list[dict[str, Any]]:
    data = (output / product["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == product["sha256"]
    assert len(data) == product["size_bytes"]
    rows = [json.loads(line) for line in data.splitlines()]
    assert len(rows) == product["row_count"]
    return rows


def _candidate_rows(module: Any, paths: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = _build(module, paths)
    return _rows(paths["candidate_output"], manifest["outputs"]["identity_candidates"])


def _crosswalk_manifest(paths: dict[str, Any]) -> dict[str, Any]:
    return json.loads(paths["crosswalk_manifest"].read_text())


def _crosswalk_edges(paths: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = _crosswalk_manifest(paths)
    return _rows(paths["crosswalk_output"], manifest["outputs"]["candidate_edges"])


def _repin_crosswalk_product(paths: dict[str, Any], name: str, rows: list[dict[str, Any]]) -> None:
    manifest = _crosswalk_manifest(paths)
    path = paths["crosswalk_output"] / manifest["outputs"][name]["path"]
    _jsonl(path, rows)
    manifest["outputs"][name] = _product(path, len(rows))
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    paths["crosswalk_manifest"].write_bytes(data)
    paths["crosswalk_sha"] = hashlib.sha256(data).hexdigest()


def _directory_bytes(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {
            nested_key for child in value.values() for nested_key in _all_keys(child)
        }
    if isinstance(value, list):
        return {nested_key for child in value for nested_key in _all_keys(child)}
    return set()


def test_inclusive_fuzzy_boundaries_and_route_overlap(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    strong_left = "AB" + "C" * 18
    strong_right = "AB" + "C" * 17 + "D"
    state_left = "CD" + "E" * 18
    state_right = "CD" + "E" * 15 + "FFF"
    zip_left = "GH" + "I" * 8
    zip_right = "JK" + "I" * 8
    overlap_left = "LM" + "N" * 18
    overlap_right = "LM" + "N" * 17 + "O"
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award(strong_left),
            _award(state_left, state="CA"),
            _award(zip_left, zip_code="12345"),
            _award(overlap_left, state="NY", zip_code="10001"),
        ],
        issuers=[
            _issuer("10", strong_right),
            _issuer("20", state_right, filings=[_filing("20", state_right, state="California")]),
            _issuer("30", zip_right, filings=[_filing("30", zip_right, zip_code="12345")]),
            _issuer(
                "40",
                overlap_right,
                filings=[_filing("40", overlap_right, state="NY", zip_code="10001")],
            ),
        ],
    )

    rows = _candidate_rows(module, paths)
    by_name = {row["best_name_evidence"]["sbir_normalized_name"]: row for row in rows}

    assert by_name[strong_left]["best_name_evidence"]["ratio_similarity"] == 0.95
    assert by_name[strong_left]["candidate_routes"] == ["strong_name"]
    assert set(by_name[strong_left]["route_evidence"]) == {"strong_name"}
    assert by_name[strong_left]["route_evidence"]["strong_name"]["route_support"] == {
        "prefix": "AB"
    }
    assert by_name[state_left]["best_name_evidence"]["ratio_similarity"] == 0.85
    assert by_name[state_left]["candidate_routes"] == ["state_supported"]
    assert by_name[state_left]["route_evidence"]["state_supported"]["route_support"]["state"]
    assert by_name[zip_left]["best_name_evidence"]["ratio_similarity"] == 0.8
    assert by_name[zip_left]["candidate_routes"] == ["zip_supported"]
    assert by_name[zip_left]["route_evidence"]["zip_supported"]["route_support"]["zip5"]
    assert by_name[overlap_left]["candidate_routes"] == [
        "strong_name",
        "state_supported",
        "zip_supported",
    ]
    assert set(by_name[overlap_left]["route_evidence"]) == {
        "strong_name",
        "state_supported",
        "zip_supported",
    }


def test_exact_short_name_is_preserved_without_a_fuzzy_route(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("AI")],
        issuers=[_issuer("10", "AI")],
    )
    exact = _crosswalk_edges(paths)

    rows = _candidate_rows(module, paths)

    assert len(rows) == 1
    assert rows[0]["candidate_routes"] == ["exact_normalized_name"]
    assert rows[0]["exact_source_edge"] == exact[0]
    assert rows[0]["route_evidence"] == {
        "exact_normalized_name": {
            "evidence_path": "exact_source_edge.name_evidence[0]",
            "normalized_name": "AI",
            "ratio_similarity": 1.0,
        }
    }
    assert rows[0]["best_name_evidence"]["sbir"] == [{"raw_name": "AI", "source_record": 1}]
    assert rows[0]["best_name_evidence"]["form_d"] == [
        {"accession_number": "0000000010-20-000010", "raw_alias": "AI"}
    ]


def test_shared_exact_name_expands_across_every_firm_and_cik(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award("Shared Labs", uei="UEI000000001", duns="000000001"),
            _award("Shared Labs", uei="UEI000000002", duns="000000002"),
            _award("Shared Labs"),
        ],
        issuers=[_issuer("10", "Shared Labs"), _issuer("20", "Shared Labs")],
    )

    rows = _candidate_rows(module, paths)
    firms = {row["sbir_firm_id"] for row in rows}

    assert len(firms) == 3
    assert len(rows) == 6
    assert {(row["sbir_firm_id"], row["form_d_cik"]) for row in rows} == {
        (firm, cik) for firm in firms for cik in {"10", "20"}
    }
    assert all(row["candidate_routes"] == ["exact_normalized_name"] for row in rows)


def test_exact_pairs_and_nested_historical_provenance_are_preserved_cik_locally(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    legacy = "Legacy Alpha Labs"
    current = "Modern Alpha Labs"
    issuers = []
    expected_accessions: dict[str, set[str]] = {}
    for cik in ("10", "20"):
        old_accession = f"00000000{cik}-20-000001"
        new_accession = f"00000000{cik}-20-000002"
        expected_accessions[cik] = {old_accession, new_accession}
        issuers.append(
            _issuer(
                cik,
                current,
                filings=[
                    _filing(cik, legacy, accession=old_accession),
                    _filing(
                        cik,
                        current,
                        aliases=[current, legacy],
                        accession=new_accession,
                    ),
                ],
            )
        )
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award(legacy, uei="UEI000000001"),
            _award(current, uei="UEI000000001"),
        ],
        issuers=issuers,
    )
    exact_by_pair = {
        (edge["sbir_firm_id"], edge["form_d_cik"]): edge for edge in _crosswalk_edges(paths)
    }

    rows = _candidate_rows(module, paths)
    enriched_by_pair = {(row["sbir_firm_id"], row["form_d_cik"]): row for row in rows}

    assert set(enriched_by_pair) == set(exact_by_pair)
    for pair, exact_edge in exact_by_pair.items():
        enriched = enriched_by_pair[pair]
        assert enriched["edge_id"] == exact_edge["edge_id"]
        assert enriched["exact_source_edge"] == exact_edge
        assert set(enriched["form_d_source_accessions"]) == expected_accessions[pair[1]]
        nested_accessions = {
            witness["accession_number"]
            for evidence in enriched["exact_source_edge"]["name_evidence"]
            for witness in evidence["form_d"]
        }
        assert nested_accessions == expected_accessions[pair[1]]


def test_contact_evidence_enriches_name_pair_but_never_originates_one(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    routed_accession = "0000000010-20-000010"
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award(
                "Routed Research",
                street1="1 Main Street",
                city="Boston",
                state="Massachusetts",
                zip_code="02110-1234",
                contact_phone="1 (617) 555-0100 ext. 9",
            )
        ],
        issuers=[
            _issuer(
                "10",
                "Routed Research",
                filings=[
                    _filing(
                        "10",
                        "Routed Research",
                        accession=routed_accession,
                        street1="1 MAIN STREET",
                        city="BOSTON",
                        state="MA",
                        zip_code="02110",
                        issuer_phone="617.555.0100",
                    )
                ],
            ),
            _issuer(
                "20",
                "Utterly Different Ventures",
                filings=[
                    _filing(
                        "20",
                        "Utterly Different Ventures",
                        street1="1 Main Street",
                        city="Boston",
                        state="MA",
                        zip_code="02110",
                        issuer_phone="617-555-0100",
                    )
                ],
            ),
        ],
    )

    rows = _candidate_rows(module, paths)

    assert len(rows) == 1
    assert rows[0]["form_d_cik"] == "10"
    expected_values = {
        "street1": "1 MAIN STREET",
        "city": "BOSTON",
        "state": "MA",
        "zip5": "02110",
        "phone10": "6175550100",
    }
    for field, value in expected_values.items():
        assert rows[0]["contact_evidence"][field] == [
            {
                "form_d_accessions": [routed_accession],
                "sbir_source_records": [1],
                "value": value,
            }
        ]


def test_malformed_state_zip_and_phone_fail_closed(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    strong_left = "AB" + "C" * 18
    strong_right = "AB" + "C" * 17 + "D"
    state_left = "CD" + "E" * 18
    state_right = "CD" + "E" * 15 + "FFF"
    zip_left = "GH" + "I" * 8
    zip_right = "JK" + "I" * 8
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award(strong_left, state="ZZ", zip_code="1234", contact_phone="555"),
            _award(state_left, state="ZZ"),
            _award(zip_left, zip_code="ABCDE"),
        ],
        issuers=[
            _issuer(
                "10",
                strong_right,
                filings=[
                    _filing(
                        "10",
                        strong_right,
                        state="ZZ",
                        zip_code="1234",
                        issuer_phone="555",
                    )
                ],
            ),
            _issuer("20", state_right, filings=[_filing("20", state_right, state="ZZ")]),
            _issuer("30", zip_right, filings=[_filing("30", zip_right, zip_code="ABCDE")]),
        ],
    )

    rows = _candidate_rows(module, paths)

    assert len(rows) == 1
    assert rows[0]["best_name_evidence"]["sbir_normalized_name"] == strong_left
    assert rows[0]["candidate_routes"] == ["strong_name"]
    assert rows[0]["contact_evidence"]["state"] == []
    assert rows[0]["contact_evidence"]["zip5"] == []
    assert rows[0]["contact_evidence"]["phone10"] == []


def test_exact_edge_pin_drift_fails_without_replacing_prior_release(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    manifest = _crosswalk_manifest(paths)
    edge_path = paths["crosswalk_output"] / manifest["outputs"]["candidate_edges"]["path"]
    edge_path.write_bytes(edge_path.read_bytes() + b"\n")
    output = paths["candidate_output"]
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_bytes(b"prior release\n")

    with pytest.raises(module.BuildError, match="byte count"):
        _build(module, paths)

    assert _directory_bytes(output) == {"prior.txt": b"prior release\n"}


@pytest.mark.parametrize("change", ["mutation", "loss"])
def test_repinned_exact_edge_mutation_or_loss_fails_reconstruction(
    change: str, module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research"), _award("Beta Research")],
        issuers=[_issuer("10", "Alpha Research"), _issuer("20", "Beta Research")],
        stem=change,
    )
    edges = _crosswalk_edges(paths)
    if change == "loss":
        changed_edges = edges[:-1]
    else:
        changed_edges = deepcopy(edges)
        changed_edges[0]["form_d_cik"] = "20"
        changed_edges[0]["edge_id"] = module._edge_id(
            changed_edges[0]["sbir_firm_id"], changed_edges[0]["form_d_cik"]
        )
        changed_edges.sort(key=lambda row: (row["sbir_firm_id"], row["form_d_cik"]))
    _repin_crosswalk_product(paths, "candidate_edges", changed_edges)

    with pytest.raises(module.BuildError, match="Reconstructed exact pairs disagree"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_identical_inputs_produce_byte_identical_release_directories(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    fuzzy_left = "AB" + "C" * 18
    fuzzy_right = "AB" + "C" * 17 + "D"
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("AI"), _award(fuzzy_left)],
        issuers=[_issuer("10", "AI"), _issuer("20", fuzzy_right)],
    )
    first_output = tmp_path / "first-release"
    second_output = tmp_path / "second-release"

    first = _build(module, paths, output=first_output)
    second = _build(module, paths, output=second_output)

    assert first == second
    assert _directory_bytes(first_output) == _directory_bytes(second_output)
    product = first["outputs"]["identity_candidates"]
    assert product["sha256"] in product["path"]


def test_forbidden_amount_fields_are_not_copied_from_inputs(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Amountless Labs", award_amount="987654321")],
        issuers=[
            _issuer(
                "10",
                "Amountless Labs",
                filings=[
                    _filing(
                        "10",
                        "Amountless Labs",
                        total_amount_sold="111111111",
                        total_offering_amount="999999999",
                    )
                ],
            )
        ],
    )

    rows = _candidate_rows(module, paths)
    keys = {key.casefold() for key in _all_keys(rows)}

    assert not keys & module.FORBIDDEN_OUTPUT_KEYS
    assert "987654321" not in json.dumps(rows, sort_keys=True)
    assert "999999999" not in json.dumps(rows, sort_keys=True)


def test_code_version_requires_a_full_lowercase_commit_sha(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    missing = _args(paths)
    index = missing.index("--code-version")
    del missing[index : index + 2]
    with pytest.raises(SystemExit):
        module.parse_args(missing)

    for invalid in ("a" * 39, "A" * 40, "not-a-commit"):
        args = _args(paths)
        args[args.index("--code-version") + 1] = invalid
        with pytest.raises(module.BuildError, match="full lowercase 40-character git commit"):
            module.build(module.parse_args(args))


def test_similarity_backend_version_drift_fails_closed(
    module: Any,
    crosswalk_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    monkeypatch.setattr(module, "distribution_version", lambda _name: "3.14.2")

    with pytest.raises(module.BuildError, match="rapidfuzz==3.14.3"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_similarity_backend_fallback_fails_closed(
    module: Any,
    crosswalk_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    monkeypatch.setattr(module, "company_name_similarity", lambda *_args, **_kwargs: 0.5)

    with pytest.raises(module.BuildError, match="not using the pinned backend"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_unsafe_parent_product_path_fails_closed(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    manifest = _crosswalk_manifest(paths)
    manifest["outputs"]["candidate_edges"]["path"] = ".."
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    paths["crosswalk_manifest"].write_bytes(data)
    paths["crosswalk_sha"] = hashlib.sha256(data).hexdigest()

    with pytest.raises(module.BuildError, match="safe filename"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_repinned_nested_cross_cik_lineage_fails_closed(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research"), _award("Beta Research")],
        issuers=[_issuer("10", "Alpha Research"), _issuer("20", "Beta Research")],
    )
    edges = deepcopy(_crosswalk_edges(paths))
    target = next(edge for edge in edges if edge["form_d_cik"] == "10")
    foreign = next(edge for edge in edges if edge["form_d_cik"] == "20")
    foreign_accession = foreign["form_d_source_accessions"][0]
    target["form_d_source_accessions"] = [foreign_accession]
    target["name_evidence"][0]["form_d"][0]["accession_number"] = foreign_accession
    _repin_crosswalk_product(paths, "candidate_edges", edges)

    with pytest.raises(module.BuildError, match="cross-CIK accession evidence"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_repinned_nested_cross_firm_lineage_fails_closed(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[
            _award("Alpha Research", uei="UEI000000001"),
            _award("Beta Research", uei="UEI000000002"),
        ],
        issuers=[_issuer("10", "Alpha Research"), _issuer("20", "Beta Research")],
    )
    edges = deepcopy(_crosswalk_edges(paths))
    target = next(edge for edge in edges if edge["form_d_cik"] == "10")
    foreign = next(edge for edge in edges if edge["form_d_cik"] == "20")
    target["sbir_source_records"] = list(foreign["sbir_source_records"])
    target["name_evidence"][0]["sbir"] = deepcopy(foreign["name_evidence"][0]["sbir"])
    _repin_crosswalk_product(paths, "candidate_edges", edges)

    with pytest.raises(module.BuildError, match="invalid SBIR lineage|cross-firm SBIR lineage"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_repinned_untraceable_nested_alias_fails_closed(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    edges = deepcopy(_crosswalk_edges(paths))
    edges[0]["name_evidence"][0]["form_d"][0]["raw_alias"] = "Alpha Research, Inc."
    _repin_crosswalk_product(paths, "candidate_edges", edges)

    with pytest.raises(module.BuildError, match="untraceable Form D alias"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


@pytest.mark.parametrize("forbidden_key", ["confidence_label", "preferred_cik", "related_persons"])
def test_forbidden_identity_decision_fields_in_exact_provenance_fail_closed(
    forbidden_key: str, module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
        stem=forbidden_key,
    )
    edges = _crosswalk_edges(paths)
    edges[0][forbidden_key] = "forbidden"
    _repin_crosswalk_product(paths, "candidate_edges", edges)

    with pytest.raises(module.BuildError, match="forbidden field"):
        _build(module, paths)

    assert not paths["candidate_output"].exists()


def test_publication_failure_restores_the_complete_prior_release(
    module: Any,
    crosswalk_module: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    output = paths["candidate_output"]
    (output / "nested").mkdir(parents=True)
    (output / "prior.txt").write_bytes(b"prior release\n")
    (output / "nested/state.bin").write_bytes(b"\x00prior\xff")
    before = _directory_bytes(output)

    def fail_release_swap(_staging: Path, _target: Path) -> None:
        raise OSError("injected release swap failure")

    monkeypatch.setattr(module, "_atomic_exchange_directories", fail_release_swap)

    with pytest.raises(OSError, match="injected release swap failure"):
        _build(module, paths)

    assert _directory_bytes(output) == before
    assert not list(output.parent.glob(f".{output.name}.staging-*"))


def test_existing_release_is_atomically_replaced(
    module: Any, crosswalk_module: Any, tmp_path: Path
) -> None:
    paths = _fixture(
        tmp_path,
        crosswalk_module,
        awards=[_award("Alpha Research")],
        issuers=[_issuer("10", "Alpha Research")],
    )
    output = paths["candidate_output"]
    output.mkdir()
    (output / "prior.txt").write_bytes(b"prior release\n")

    manifest = _build(module, paths)

    assert "prior.txt" not in _directory_bytes(output)
    assert (output / "sbir_form_d_identity_candidates.manifest.json").is_file()
    assert (output / manifest["outputs"]["identity_candidates"]["path"]).is_file()
    assert not list(output.parent.glob(f".{output.name}.staging-*"))
