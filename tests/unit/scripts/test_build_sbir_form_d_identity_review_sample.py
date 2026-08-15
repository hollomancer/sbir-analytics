"""Tests for the private SBIR↔Form D organizational-identity review instrument."""

import csv
import hashlib
import importlib.util
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).parents[3]
SCRIPT = REPO_ROOT / "scripts/data/build_sbir_form_d_identity_review_sample.py"
CODE_VERSION = "a" * 40
ROUTES = (
    "exact_normalized_name",
    "strong_name",
    "state_supported",
    "zip_supported",
)
AWARD_FIELDS = [
    "Company",
    "Proposal Award Date",
    "Award Year",
    "Address1",
    "Address2",
    "City",
    "State",
    "Zip",
    "Contact Phone",
    "Award Amount",
    "Contact Name",
    "Contact Email",
    "Company Website",
]


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_sbir_form_d_identity_review_sample", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def module() -> Any:
    return _load_script()


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


def _manifest(path: Path, value: dict[str, Any]) -> tuple[str, int]:
    data = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest(), len(data)


def _firm(label: str) -> str:
    return f"sbir_firm:{hashlib.sha256(label.encode()).hexdigest()}"


def _edge(module: Any, firm_id: str, cik: str) -> str:
    material = "\0".join((module.EDGE_ID_CONTRACT, firm_id, cik))
    return f"sbir_form_d_edge:{hashlib.sha256(material.encode()).hexdigest()}"


def _candidate(
    module: Any,
    firm_id: str,
    cik: str,
    routes: list[str],
    *,
    source_records: list[int],
    quarantined: bool = False,
) -> dict[str, Any]:
    return {
        "candidate_contract": module.CANDIDATE_CONTRACT,
        "candidate_only": True,
        "candidate_routes": routes,
        "complete_sbir_exclusion": False,
        "component_status": "quarantined_conflict" if quarantined else "identifier_consistent",
        "covariates_ready": False,
        "decision": "candidate_unreviewed",
        "edge_id": _edge(module, firm_id, cik),
        "edge_id_contract": module.EDGE_ID_CONTRACT,
        "exclusion_eligible": False,
        "exclusion_recall": "unknown",
        "form_d_cik": cik,
        "form_d_source_accessions": [f"{int(cik):010d}-24-000001"],
        "identity_accepted": False,
        "matching_eligible": False,
        "rate_eligible": False,
        "same_legal_entity": None,
        "sbir_firm_id": firm_id,
        "sbir_source_records": source_records,
        "schema_version": 2,
    }


def _fixture(tmp_path: Path, module: Any) -> dict[str, Any]:
    source = tmp_path / "source"
    source.mkdir()
    awards_path = source / "award_data.csv"
    ledger_path = source / "firm_ledger.jsonl"
    broad_path = source / "broad.jsonl"
    candidates_path = source / "candidates.jsonl"
    crosswalk_path = source / "crosswalk.manifest.json"
    control_path = source / "control.manifest.json"
    candidate_manifest_path = source / "candidates.manifest.json"

    definitions: list[dict[str, Any]] = []
    next_cik = 1_000_000
    for route in ROUTES:
        for index in range(101):
            routes = [route]
            if route == "strong_name" and index == 0:
                routes = ["strong_name", "state_supported", "zip_supported"]
            elif route == "state_supported" and index == 0:
                routes = ["state_supported", "zip_supported"]
            definitions.append(
                {
                    "cik": str(next_cik),
                    "firm_id": _firm(f"{route}-{index}"),
                    "quarantined": False,
                    "routes": routes,
                }
            )
            next_cik += 1

    fanout_firm = _firm("firm-fanout")
    definitions.extend(
        [
            {
                "cik": str(next_cik),
                "firm_id": fanout_firm,
                "quarantined": False,
                "routes": ["exact_normalized_name"],
            },
            {
                "cik": str(next_cik + 1),
                "firm_id": fanout_firm,
                "quarantined": True,
                "routes": ["exact_normalized_name"],
            },
        ]
    )
    shared_cik = str(next_cik + 2)
    definitions.extend(
        [
            {
                "cik": shared_cik,
                "firm_id": _firm("cik-fanout-a"),
                "quarantined": False,
                "routes": ["state_supported"],
            },
            {
                "cik": shared_cik,
                "firm_id": _firm("cik-fanout-b"),
                "quarantined": False,
                "routes": ["state_supported"],
            },
            {
                "cik": str(next_cik + 3),
                "firm_id": _firm("quarantine-only"),
                "quarantined": True,
                "routes": ["zip_supported"],
            },
        ]
    )

    firms = sorted({item["firm_id"] for item in definitions})
    firm_sources: dict[str, list[int]] = {}
    award_rows: list[dict[str, str]] = []
    ledger_rows: list[dict[str, Any]] = []
    for firm_id in firms:
        label = f"Organization {firm_id[-10:]}"
        source_records: list[int] = []
        source_lineage: list[dict[str, Any]] = []
        for date in ("01/02/2020", "01/02/2021"):
            source_record = len(award_rows) + 1
            source_records.append(source_record)
            source_lineage.append(
                {
                    "raw_name": label,
                    "source_record": source_record,
                }
            )
            award_rows.append(
                {
                    "Address1": "1 Main Street",
                    "Address2": "Suite 2",
                    "Award Amount": "999999",
                    "Award Year": date[-4:],
                    "City": "Boston",
                    "Company": label,
                    "Company Website": "https://forbidden.example",
                    "Contact Email": "forbidden@example.com",
                    "Contact Name": "Forbidden Person",
                    "Contact Phone": "617-555-0100",
                    "Proposal Award Date": date,
                    "State": "MA",
                    "Zip": "02110",
                }
            )
        firm_sources[firm_id] = source_records
        ledger_rows.append(
            {
                "award_row_count": 2,
                "component_status": "identifier_consistent",
                "firm_id_contract": module.FIRM_ID_CONTRACT,
                "ledger_contract": module.LEDGER_CONTRACT,
                "sbir_firm_id": firm_id,
                "schema_version": 1,
                "source_record_count": 2,
                "source_records": source_lineage,
            }
        )
    with awards_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AWARD_FIELDS)
        writer.writeheader()
        writer.writerows(award_rows)
    _jsonl(ledger_path, ledger_rows)

    ciks = sorted({item["cik"] for item in definitions}, key=int)
    broad_rows: list[dict[str, Any]] = []
    for cik in ciks:
        aliases = [f"Organization {cik}", f"Former Organization {cik}"]
        filings = []
        for sequence, date in enumerate(("2020-03-01", "2021-03-01"), start=1):
            filings.append(
                {
                    "accession_number": f"{int(cik):010d}-24-{sequence:06d}",
                    "cik": cik,
                    "city": "Boston",
                    "filing_date": date,
                    "issuer_name": aliases[0],
                    "issuer_name_aliases": aliases,
                    "issuer_phone": "617-555-0100",
                    "jurisdiction_of_incorporation": "DE",
                    "people": ["Forbidden Person"],
                    "state": "MA",
                    "street1": "1 Main Street",
                    "street2": "Suite 2",
                    "total_amount_sold": 1_000_000,
                    "website": "https://forbidden.example",
                    "year_of_incorporation": 2010,
                    "zip_code": "02110",
                }
            )
        broad_rows.append(
            {
                "cik": cik,
                "filing_count": 2,
                "filings": filings,
                "firm_key": f"form_d_cik:{cik}",
                "schema_version": 1,
            }
        )
    _jsonl(broad_path, broad_rows)

    candidates = [
        _candidate(
            module,
            item["firm_id"],
            item["cik"],
            item["routes"],
            source_records=firm_sources[item["firm_id"]],
            quarantined=item["quarantined"],
        )
        for item in definitions
    ]
    candidates.sort(key=lambda row: (row["sbir_firm_id"], row["form_d_cik"]))
    _jsonl(candidates_path, candidates)

    award_product = _product(awards_path, len(award_rows))
    ledger_product = _product(ledger_path, len(ledger_rows))
    broad_product = _product(broad_path, len(broad_rows))
    candidate_product = _product(candidates_path, len(candidates))
    closed = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "ready_for_matching": False,
        "schema_version": 1,
    }
    control = {
        **closed,
        "exclusion": {"awards_csv": award_product},
        "outputs": {"broad_issuer_universe": broad_product},
    }
    control_sha, control_size = _manifest(control_path, control)
    crosswalk = {
        **closed,
        "inputs": {"sbir_awards_csv": award_product},
        "outputs": {"firm_identity_ledger": ledger_product},
    }
    crosswalk_sha, crosswalk_size = _manifest(crosswalk_path, crosswalk)
    candidate_manifest = {
        **closed,
        "candidate_only": True,
        "decision_contract": {
            "decision": "candidate_unreviewed",
            "same_legal_entity": "unknown",
        },
        "exclusion_eligible": False,
        "identity_accepted": False,
        "inputs": {
            "broad_issuer_universe": broad_product,
            "control_manifest": {
                "path": control_path.name,
                "sha256": control_sha,
                "size_bytes": control_size,
            },
            "crosswalk_manifest": {
                "path": crosswalk_path.name,
                "sha256": crosswalk_sha,
                "size_bytes": crosswalk_size,
            },
            "firm_identity_ledger": ledger_product,
            "sbir_awards_csv": award_product,
        },
        "matching_eligible": False,
        "outputs": {"identity_candidates": candidate_product},
        "parameters": {"candidate_contract": module.CANDIDATE_CONTRACT},
        "rate_eligible": False,
    }
    candidate_sha, _candidate_size = _manifest(candidate_manifest_path, candidate_manifest)
    return {
        "awards": awards_path,
        "candidate_manifest": candidate_manifest_path,
        "candidate_sha": candidate_sha,
        "control_manifest": control_path,
        "control_sha": control_sha,
        "crosswalk_manifest": crosswalk_path,
        "crosswalk_sha": crosswalk_sha,
    }


def _args(paths: dict[str, Any], output: Path) -> list[str]:
    return [
        "--candidate-manifest",
        str(paths["candidate_manifest"]),
        "--candidate-manifest-sha256",
        paths["candidate_sha"],
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
        str(output),
        "--code-version",
        CODE_VERSION,
    ]


def _rows(output: Path, product: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = (output / product["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == product["sha256"]
    assert len(data) == product["size_bytes"]
    rows = [json.loads(line) for line in data.splitlines()]
    assert len(rows) == product["row_count"]
    return rows


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in _all_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in _all_keys(child)}
    return set()


def _directory_bytes(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in sorted(path.iterdir()) if item.is_file()}


def test_builds_deterministic_route_masked_instrument_with_full_graph_exclusions(
    module: Any, tmp_path: Path
) -> None:
    paths = _fixture(tmp_path, module)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"

    first = module.build(module.parse_args(_args(paths, first_output)))
    second = module.build(module.parse_args(_args(paths, second_output)))

    assert first == second
    assert _directory_bytes(first_output) == _directory_bytes(second_output)
    assert first["counts"] == {
        "candidate_pairs": 409,
        "eligible_pairs": 404,
        "eligible_pairs_by_exclusive_stratum": dict.fromkeys(ROUTES, 101),
        "either_fanout_pairs": 4,
        "excluded_pairs": 5,
        "exclusion_reason_pair_counts": {
            "cik_to_multiple_firms": 2,
            "firm_to_multiple_ciks": 2,
            "quarantined_conflict": 2,
        },
        "population_pairs_by_exclusive_stratum": {
            "exact_normalized_name": 103,
            "state_supported": 103,
            "strong_name": 101,
            "zip_supported": 102,
        },
        "selected_pairs": 400,
        "selected_pairs_by_exclusive_stratum": dict.fromkeys(ROUTES, 100),
    }
    packet = _rows(first_output, first["outputs"]["private_review_packet"])
    case_map = _rows(first_output, first["outputs"]["private_case_map"])
    assert [row["case_id"] for row in packet] == [f"case_{index:04d}" for index in range(1, 401)]
    assert [row["case_id"] for row in case_map] == [row["case_id"] for row in packet]
    assert Counter(row["exclusive_stratum"] for row in case_map) == Counter(
        dict.fromkeys(ROUTES, 100)
    )
    packet_keys = _all_keys(packet)
    assert (
        not {
            "accession_number",
            "amount",
            "candidate_routes",
            "cik",
            "edge_id",
            "email",
            "form_d_cik",
            "people",
            "route",
            "score",
            "sbir_firm_id",
            "source_record",
            "website",
        }
        & packet_keys
    )
    sample_a = packet[0]["organization_a_history"]
    sample_b = packet[0]["organization_b_history"]
    assert sample_a[0]["observation_count"] == 2
    assert sample_a[0]["first_observed_date"] == "2020-01-02"
    assert sample_a[0]["last_observed_date"] == "2021-01-02"
    assert sample_a[0]["organization_phone"] is None
    assert sample_b[0]["observation_count"] == 2
    assert sample_b[0]["first_observed_date"] == "2020-03-01"
    assert sample_b[0]["last_observed_date"] == "2021-03-01"
    assert sample_b[0]["organization_phone"] == "617-555-0100"
    assert first["exclusive_route_validation_passed"] == dict.fromkeys(ROUTES, False)
    assert first["human_labels_present"] is False
    for gate in (
        "complete_sbir_exclusion",
        "covariates_ready",
        "exclusion_eligible",
        "identity_accepted",
        "matching_eligible",
        "rate_eligible",
        "ready_for_matching",
    ):
        assert first[gate] is False


def test_selection_is_independent_of_candidate_row_order(module: Any, tmp_path: Path) -> None:
    paths = _fixture(tmp_path, module)
    first_output = tmp_path / "first"
    first = module.build(module.parse_args(_args(paths, first_output)))

    candidate_manifest = json.loads(paths["candidate_manifest"].read_text())
    product = candidate_manifest["outputs"]["identity_candidates"]
    candidate_path = paths["candidate_manifest"].parent / product["path"]
    rows = [json.loads(line) for line in candidate_path.read_bytes().splitlines()]
    _jsonl(candidate_path, list(reversed(rows)))
    candidate_manifest["outputs"]["identity_candidates"] = _product(candidate_path, len(rows))
    paths["candidate_sha"], _size = _manifest(paths["candidate_manifest"], candidate_manifest)

    second_output = tmp_path / "second"
    second = module.build(module.parse_args(_args(paths, second_output)))

    for output_name in ("private_review_packet", "private_case_map"):
        first_product = first["outputs"][output_name]
        second_product = second["outputs"][output_name]
        assert first_product == second_product
        assert (first_output / first_product["path"]).read_bytes() == (
            second_output / second_product["path"]
        ).read_bytes()


def test_external_manifest_pin_drift_fails_closed(module: Any, tmp_path: Path) -> None:
    paths = _fixture(tmp_path, module)
    args = _args(paths, tmp_path / "output")
    args[args.index("--candidate-manifest-sha256") + 1] = "0" * 64

    with pytest.raises(module.BuildError, match="external pin"):
        module.build(module.parse_args(args))


def test_invalid_stable_edge_id_fails_before_sampling(module: Any, tmp_path: Path) -> None:
    paths = _fixture(tmp_path, module)
    candidate_manifest = json.loads(paths["candidate_manifest"].read_text())
    product = candidate_manifest["outputs"]["identity_candidates"]
    candidate_path = paths["candidate_manifest"].parent / product["path"]
    rows = [json.loads(line) for line in candidate_path.read_bytes().splitlines()]
    rows[0]["edge_id"] = f"sbir_form_d_edge:{'0' * 64}"
    _jsonl(candidate_path, rows)
    candidate_manifest["outputs"]["identity_candidates"] = _product(candidate_path, len(rows))
    paths["candidate_sha"], _size = _manifest(paths["candidate_manifest"], candidate_manifest)

    with pytest.raises(module.BuildError, match="invalid edge ID"):
        module.build(module.parse_args(_args(paths, tmp_path / "output")))


def test_relative_cli_script_path_resolves_for_producer_pin(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path, module)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(
        module,
        "__file__",
        "scripts/data/build_sbir_form_d_identity_review_sample.py",
    )

    manifest = module.build(module.parse_args(_args(paths, tmp_path / "output")))

    assert manifest["producer"]["path"] == (
        "scripts/data/build_sbir_form_d_identity_review_sample.py"
    )
