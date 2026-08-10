#!/usr/bin/env python3
"""Audit descriptive Form D covariate availability and mechanical common support."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROL_MANIFEST = (
    REPO_ROOT / "docs/research/agency-private-capital-form-d-control-universe.manifest.json"
)
DEFAULT_UNIVERSE = (
    REPO_ROOT / "data/processed/agency_private_capital/control_universe/"
    "form_d_issuer_universe.identity-staging.jsonl"
)
DEFAULT_EXCLUSIONS = (
    REPO_ROOT / "data/processed/agency_private_capital/control_universe/"
    "sbir_cik_exclusion_candidates.identity-staging.jsonl"
)
DEFAULT_AUDIT_MANIFEST = (
    REPO_ROOT / "docs/research/agency-private-capital-form-d-matching-covariates.manifest.json"
)
SOURCE_START_DATE = date(2009, 1, 1)
SOURCE_END_DATE = date(2024, 12, 31)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PARTITIONS = ("broad", "exact_name_candidate", "provisional_remainder")
CIK_FIELDS = ("industry_group", "sic_code", "state_or_country_code", "first_filing_year")
FILING_FIELDS = ("industry_group", "sic_code", "state_or_country_code", "filing_date")
EXACT_METHOD = "candidate_exact_normalized_name"
US_STATE_OR_TERRITORY_CODES = frozenset(
    {
        "AK",
        "AL",
        "AR",
        "AS",
        "AZ",
        "CA",
        "CO",
        "CT",
        "DC",
        "DE",
        "FL",
        "GA",
        "GU",
        "HI",
        "IA",
        "ID",
        "IL",
        "IN",
        "KS",
        "KY",
        "LA",
        "MA",
        "MD",
        "ME",
        "MI",
        "MN",
        "MO",
        "MP",
        "MS",
        "MT",
        "NC",
        "ND",
        "NE",
        "NH",
        "NJ",
        "NM",
        "NV",
        "NY",
        "OH",
        "OK",
        "OR",
        "PA",
        "PR",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VA",
        "VI",
        "VT",
        "WA",
        "WI",
        "WV",
        "WY",
    }
)

EXPECTED_REAL_DATA = {
    "partition_ciks": {
        "broad": 311809,
        "exact_name_candidate": 4465,
        "provisional_remainder": 307344,
    },
    "cik_industry_group_present": {
        "broad": 311809,
        "exact_name_candidate": 4465,
        "provisional_remainder": 307344,
    },
    "cik_sic_code_present": {
        "broad": 7041,
        "exact_name_candidate": 431,
        "provisional_remainder": 6610,
    },
    "cik_state_or_country_code_present": {
        "broad": 311807,
        "exact_name_candidate": 4465,
        "provisional_remainder": 307342,
    },
    "cik_first_filing_year_present": {
        "broad": 311809,
        "exact_name_candidate": 4465,
        "provisional_remainder": 307344,
    },
    "multi_industry_group_history_ciks": {
        "broad": 7483,
        "exact_name_candidate": 562,
        "provisional_remainder": 6921,
    },
    "multi_state_or_country_history_ciks": {
        "broad": 8744,
        "exact_name_candidate": 314,
        "provisional_remainder": 8430,
    },
    "filing_rows": 673656,
    "filing_sic_code_present": 26291,
    "filing_state_or_country_code_missing": 4,
    "industry_group_cardinality": 35,
    "pooled_investment_fund_ciks": 146737,
    "candidate_ciks_supported_by_at_least_1_provisional": 4287,
    "candidate_ciks_supported_by_at_least_3_provisional": 3897,
}


class AuditError(RuntimeError):
    """Raised when an input or audit invariant fails closed."""


@dataclass
class PartitionMetrics:
    cik_rows: int = 0
    filing_rows: int = 0
    cik_present: Counter[str] = field(default_factory=Counter)
    filing_present: Counter[str] = field(default_factory=Counter)
    cik_categories: dict[str, set[object]] = field(
        default_factory=lambda: {name: set() for name in CIK_FIELDS}
    )
    filing_categories: dict[str, set[object]] = field(
        default_factory=lambda: {name: set() for name in FILING_FIELDS}
    )
    first_filing_years: Counter[int] = field(default_factory=Counter)
    index_industry_groups: Counter[str] = field(default_factory=Counter)
    index_state_or_country_codes: Counter[str] = field(default_factory=Counter)
    filing_state_or_country_codes: Counter[str] = field(default_factory=Counter)
    multi_industry_group_history_ciks: int = 0
    multi_state_or_country_history_ciks: int = 0
    pooled_investment_fund_ciks: int = 0


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AuditError(f"non-standard JSON constant {value!r}")


def _loads(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            data,
            object_pairs_hook=_json_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
        raise AuditError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{label} must contain a JSON object")
    return value


def _integer(value: object, *, label: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < int(positive):
        qualifier = "positive" if positive else "non-negative"
        raise AuditError(f"{label} must be a {qualifier} integer")
    return value


def _pin(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditError(f"{label} product pin is missing")
    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or SHA256_RE.fullmatch(sha256) is None:
        raise AuditError(f"{label} has an invalid SHA-256")
    return {
        "path": str(value.get("path") or ""),
        "row_count": _integer(value.get("row_count"), label=f"{label} row_count", positive=True),
        "sha256": sha256,
        "size_bytes": _integer(value.get("size_bytes"), label=f"{label} size_bytes", positive=True),
    }


def load_control_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise AuditError(f"control manifest is missing: {path}")
    data = path.read_bytes()
    manifest = _loads(data, label=str(path))
    if manifest.get("schema_version") != 1:
        raise AuditError("control manifest must use schema_version=1")
    required_gates = {
        "complete": True,
        "complete_sbir_exclusion": False,
        "exclusion_recall": "unknown",
        "covariates_ready": False,
        "ready_for_matching": False,
    }
    for key, expected in required_gates.items():
        if manifest.get(key) != expected:
            raise AuditError(f"control manifest must declare {key}={expected!r}")
    parameters = manifest.get("parameters")
    if not isinstance(parameters, Mapping):
        raise AuditError("control manifest parameters are missing")
    if (
        parameters.get("start_quarter") != "2009Q1"
        or parameters.get("end_quarter") != "2024Q4"
        or parameters.get("quarter_count") != 64
    ):
        raise AuditError("control manifest must pin the complete 2009Q1-2024Q4 source window")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, Mapping):
        raise AuditError("control manifest outputs are missing")
    broad_pin = _pin(outputs.get("broad_issuer_universe"), label="broad issuer universe")
    candidate_pin = _pin(
        outputs.get("candidate_sbir_cik_exclusions"), label="exact-name candidate exclusions"
    )
    remainder_pin = _pin(
        outputs.get("provisional_control_identity_universe"),
        label="provisional identity universe",
    )
    source_counts = manifest.get("source_counts")
    if not isinstance(source_counts, Mapping):
        raise AuditError("control manifest source_counts are missing")
    if source_counts.get("issuer_ciks") != broad_pin["row_count"]:
        raise AuditError("control manifest broad CIK count does not reconcile")
    if source_counts.get("excluded_broad_ciks") != candidate_pin["row_count"]:
        raise AuditError("control manifest candidate CIK count does not reconcile")
    if source_counts.get("provisional_control_ciks") != remainder_pin["row_count"]:
        raise AuditError("control manifest provisional CIK count does not reconcile")
    if broad_pin["row_count"] != candidate_pin["row_count"] + remainder_pin["row_count"]:
        raise AuditError("control manifest partition row counts do not reconcile")
    return manifest, data


def _consume_pinned_jsonl(
    path: Path,
    pin: Mapping[str, Any],
    *,
    label: str,
    consume: Any,
) -> None:
    if not path.is_file() or path.is_symlink():
        raise AuditError(f"{label} is missing: {path}")
    if path.stat().st_size != pin["size_bytes"]:
        raise AuditError(f"{label} byte count does not match its pin")
    digest = hashlib.sha256()
    rows = 0
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            digest.update(raw_line)
            if not raw_line.strip():
                raise AuditError(f"{label} contains a blank line at {line_number}")
            rows += 1
            consume(_loads(raw_line, label=f"{path}:{line_number}"), line_number)
    if rows != pin["row_count"]:
        raise AuditError(f"{label} row count does not match its pin")
    if digest.hexdigest() != pin["sha256"]:
        raise AuditError(f"{label} SHA-256 does not match its pin")


def _canonical_cik(record: Mapping[str, Any], *, label: str) -> str:
    cik = record.get("cik")
    if not isinstance(cik, str) or not cik.isdigit() or cik.startswith("0") or len(cik) > 10:
        raise AuditError(f"{label} has an invalid canonical CIK")
    if record.get("firm_key") != f"form_d_cik:{cik}":
        raise AuditError(f"{label} has a noncanonical firm_key")
    return cik


def load_candidate_ciks(path: Path, pin: Mapping[str, Any]) -> set[str]:
    candidates: set[str] = set()

    def consume(record: Mapping[str, Any], line_number: int) -> None:
        cik = _canonical_cik(record, label=f"candidate line {line_number}")
        if cik in candidates:
            raise AuditError(f"candidate exclusions repeat CIK {cik}")
        if record.get("candidate_exclusion") is not True:
            raise AuditError(f"candidate line {line_number} is not marked as candidate evidence")
        if record.get("schema_version") != 1:
            raise AuditError(f"candidate line {line_number} has an unsupported schema_version")
        methods = record.get("resolution_methods")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AuditError(f"candidate line {line_number} has no identity evidence")
        if record.get("evidence_count") != len(evidence):
            raise AuditError(f"candidate line {line_number} evidence_count does not reconcile")
        evidence_methods: set[str] = set()
        for item in evidence:
            method = item.get("resolution_method") if isinstance(item, Mapping) else None
            if not isinstance(method, str) or not method:
                raise AuditError(f"candidate line {line_number} has malformed identity evidence")
            evidence_methods.add(method)
        if methods != sorted(evidence_methods):
            raise AuditError(f"candidate line {line_number} resolution methods do not reconcile")
        if EXACT_METHOD not in evidence_methods:
            raise AuditError(f"candidate line {line_number} has no exact-name evidence")
        candidates.add(cik)

    _consume_pinned_jsonl(path, pin, label="exact-name candidate exclusions", consume=consume)
    return candidates


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AuditError(f"{label} must be a string or null")
    stripped = value.strip()
    return stripped or None


def _iso_date(value: object, *, label: str) -> date:
    if not isinstance(value, str):
        raise AuditError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AuditError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise AuditError(f"{label} must be an exact ISO date")
    return parsed


def _update_metrics(
    metrics: PartitionMetrics,
    *,
    filings: list[dict[str, Any]],
    first: dict[str, Any],
    first_date: date,
) -> None:
    metrics.cik_rows += 1
    metrics.first_filing_years[first_date.year] += 1
    metrics.cik_present["first_filing_year"] += 1
    metrics.cik_categories["first_filing_year"].add(first_date.year)

    histories = {
        "industry_group": {
            value for filing in filings if (value := filing["_industry_group"]) is not None
        },
        "sic_code": {value for filing in filings if (value := filing["_sic_code"]) is not None},
        "state_or_country_code": {
            value for filing in filings if (value := filing["_state_or_country_code"]) is not None
        },
    }
    for field_name, values in histories.items():
        if values:
            metrics.cik_present[field_name] += 1
            metrics.cik_categories[field_name].update(values)
    if len(histories["industry_group"]) > 1:
        metrics.multi_industry_group_history_ciks += 1
    if len(histories["state_or_country_code"]) > 1:
        metrics.multi_state_or_country_history_ciks += 1
    if first["_industry_group"] == "Pooled Investment Fund":
        metrics.pooled_investment_fund_ciks += 1

    index_industry = first["_industry_group"]
    index_state = first["_state_or_country_code"]
    if index_industry is not None:
        metrics.index_industry_groups[index_industry] += 1
    if index_state is not None:
        metrics.index_state_or_country_codes[index_state] += 1

    for filing in filings:
        metrics.filing_rows += 1
        filing_values = {
            "industry_group": filing["_industry_group"],
            "sic_code": filing["_sic_code"],
            "state_or_country_code": filing["_state_or_country_code"],
            "filing_date": filing["_filing_date"].isoformat(),
        }
        for field_name, value in filing_values.items():
            if value is not None:
                metrics.filing_present[field_name] += 1
                metrics.filing_categories[field_name].add(value)
        state_code = filing["_state_or_country_code"]
        if state_code is not None:
            metrics.filing_state_or_country_codes[state_code] += 1


def audit_universe(
    path: Path,
    pin: Mapping[str, Any],
    candidate_ciks: set[str],
) -> tuple[
    dict[str, PartitionMetrics],
    Counter[tuple[int, str, str]],
    list[tuple[int, str, str] | None],
    int,
]:
    metrics = {partition: PartitionMetrics() for partition in PARTITIONS}
    provisional_cells: Counter[tuple[int, str, str]] = Counter()
    candidate_cells: list[tuple[int, str, str] | None] = []
    unseen_candidates = set(candidate_ciks)
    seen_ciks: set[str] = set()
    seen_accessions: set[str] = set()

    def consume(record: Mapping[str, Any], line_number: int) -> None:
        cik = _canonical_cik(record, label=f"universe line {line_number}")
        if cik in seen_ciks:
            raise AuditError(f"broad issuer universe repeats CIK {cik}")
        seen_ciks.add(cik)
        if record.get("schema_version") != 1:
            raise AuditError(f"universe line {line_number} has an unsupported schema_version")
        unseen_candidates.discard(cik)
        filings_raw = record.get("filings")
        if not isinstance(filings_raw, list) or not filings_raw:
            raise AuditError(f"universe line {line_number} has no filing history")
        if record.get("filing_count") != len(filings_raw):
            raise AuditError(f"universe line {line_number} filing_count does not reconcile")

        filings: list[dict[str, Any]] = []
        for filing_number, raw_filing in enumerate(filings_raw, start=1):
            if not isinstance(raw_filing, Mapping):
                raise AuditError(f"universe line {line_number} has a non-object filing")
            if raw_filing.get("cik") != cik:
                raise AuditError(f"universe line {line_number} filing CIK does not match")
            accession = _optional_text(
                raw_filing.get("accession_number"),
                label=f"universe line {line_number} filing {filing_number} accession",
            )
            if accession is None:
                raise AuditError(f"universe line {line_number} filing has no accession")
            if accession in seen_accessions:
                raise AuditError(f"broad issuer universe repeats accession {accession}")
            seen_accessions.add(accession)
            filing_date = _iso_date(
                raw_filing.get("filing_date"),
                label=f"universe line {line_number} filing {filing_number} date",
            )
            if not SOURCE_START_DATE <= filing_date <= SOURCE_END_DATE:
                raise AuditError(
                    f"universe line {line_number} filing date falls outside source coverage"
                )
            source_quarter = _optional_text(
                raw_filing.get("source_quarter"),
                label=f"universe line {line_number} filing {filing_number} source_quarter",
            )
            expected_quarter = f"{filing_date.year}Q{((filing_date.month - 1) // 3) + 1}"
            if source_quarter != expected_quarter:
                raise AuditError(
                    f"universe line {line_number} filing has an inconsistent source quarter"
                )
            filing = dict(raw_filing)
            filing.update(
                {
                    "_accession": accession,
                    "_filing_date": filing_date,
                    "_industry_group": _optional_text(
                        raw_filing.get("industry_group"), label="filing industry_group"
                    ),
                    "_sic_code": _optional_text(
                        raw_filing.get("sic_code"), label="filing sic_code"
                    ),
                    "_state_or_country_code": _optional_text(
                        raw_filing.get("state"), label="filing state_or_country_code"
                    ),
                }
            )
            filings.append(filing)

        first = min(filings, key=lambda item: (item["_filing_date"], item["_accession"]))
        first_date = first["_filing_date"]
        if record.get("first_accession_number") != first["_accession"]:
            raise AuditError(f"universe line {line_number} has inconsistent first accession")
        if record.get("first_filing_date") != first_date.isoformat():
            raise AuditError(f"universe line {line_number} has inconsistent first filing date")
        if record.get("first_filing_year") != first_date.year:
            raise AuditError(f"universe line {line_number} has inconsistent first filing year")

        partition = "exact_name_candidate" if cik in candidate_ciks else "provisional_remainder"
        for target in ("broad", partition):
            _update_metrics(metrics[target], filings=filings, first=first, first_date=first_date)

        index_industry = first["_industry_group"]
        index_state = first["_state_or_country_code"]
        cell = (
            (first_date.year, index_industry, index_state)
            if index_industry is not None and index_state is not None
            else None
        )
        if partition == "exact_name_candidate":
            candidate_cells.append(cell)
        elif cell is not None:
            provisional_cells[cell] += 1

    _consume_pinned_jsonl(path, pin, label="broad issuer universe", consume=consume)
    if unseen_candidates:
        raise AuditError(
            f"{len(unseen_candidates)} exact-name candidate CIK(s) are absent from the universe"
        )
    return metrics, provisional_cells, candidate_cells, len(seen_accessions)


def _sorted_counts(values: Counter[Any]) -> dict[str, int]:
    return {str(key): values[key] for key in sorted(values, key=lambda item: str(item))}


def _serialize_metrics(metrics: Mapping[str, PartitionMetrics]) -> dict[str, Any]:
    def state_code_classes(values: Counter[str]) -> dict[str, int]:
        return {
            "other_sec_code": sum(
                count for code, count in values.items() if code not in US_STATE_OR_TERRITORY_CODES
            ),
            "us_state_or_territory_code": sum(
                count for code, count in values.items() if code in US_STATE_OR_TERRITORY_CODES
            ),
        }

    return {
        "availability": {
            "cik_grain": {
                partition: {
                    "rows": item.cik_rows,
                    **{f"{name}_present": item.cik_present[name] for name in CIK_FIELDS},
                }
                for partition, item in metrics.items()
            },
            "filing_grain": {
                partition: {
                    "rows": item.filing_rows,
                    **{f"{name}_present": item.filing_present[name] for name in FILING_FIELDS},
                }
                for partition, item in metrics.items()
            },
        },
        "category_cardinality": {
            "cik_grain": {
                partition: {name: len(item.cik_categories[name]) for name in CIK_FIELDS}
                for partition, item in metrics.items()
            },
            "filing_grain": {
                partition: {name: len(item.filing_categories[name]) for name in FILING_FIELDS}
                for partition, item in metrics.items()
            },
        },
        "history_diagnostics": {
            partition: {
                "multi_industry_group_history_ciks": item.multi_industry_group_history_ciks,
                "multi_state_or_country_history_ciks": item.multi_state_or_country_history_ciks,
                "pooled_investment_fund_ciks": item.pooled_investment_fund_ciks,
            }
            for partition, item in metrics.items()
        },
        "first_filing_year_distribution": {
            partition: _sorted_counts(item.first_filing_years)
            for partition, item in metrics.items()
        },
        "state_or_country_diagnostics": {
            "index_code_distribution": {
                partition: _sorted_counts(item.index_state_or_country_codes)
                for partition, item in metrics.items()
            },
            "filing_code_distribution": {
                partition: _sorted_counts(item.filing_state_or_country_codes)
                for partition, item in metrics.items()
            },
            "index_code_classification": {
                partition: state_code_classes(item.index_state_or_country_codes)
                for partition, item in metrics.items()
            },
            "filing_code_classification": {
                partition: state_code_classes(item.filing_state_or_country_codes)
                for partition, item in metrics.items()
            },
        },
        "index_industry_group_distribution": {
            partition: _sorted_counts(item.index_industry_groups)
            for partition, item in metrics.items()
        },
    }


def _actual_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    availability = manifest["availability"]
    history = manifest["history_diagnostics"]
    return {
        "partition_ciks": {
            partition: availability["cik_grain"][partition]["rows"] for partition in PARTITIONS
        },
        **{
            f"cik_{field_name}_present": {
                partition: availability["cik_grain"][partition][f"{field_name}_present"]
                for partition in PARTITIONS
            }
            for field_name in CIK_FIELDS
        },
        "multi_industry_group_history_ciks": {
            partition: history[partition]["multi_industry_group_history_ciks"]
            for partition in PARTITIONS
        },
        "multi_state_or_country_history_ciks": {
            partition: history[partition]["multi_state_or_country_history_ciks"]
            for partition in PARTITIONS
        },
        "filing_rows": availability["filing_grain"]["broad"]["rows"],
        "filing_sic_code_present": availability["filing_grain"]["broad"]["sic_code_present"],
        "filing_state_or_country_code_missing": availability["filing_grain"]["broad"]["rows"]
        - availability["filing_grain"]["broad"]["state_or_country_code_present"],
        "industry_group_cardinality": manifest["category_cardinality"]["cik_grain"]["broad"][
            "industry_group"
        ],
        "pooled_investment_fund_ciks": history["broad"]["pooled_investment_fund_ciks"],
        "candidate_ciks_supported_by_at_least_1_provisional": manifest["mechanical_common_support"][
            "candidate_ciks_with_at_least_1_provisional_in_same_cell"
        ],
        "candidate_ciks_supported_by_at_least_3_provisional": manifest["mechanical_common_support"][
            "candidate_ciks_with_at_least_3_provisional_in_same_cell"
        ],
    }


def _assert_real_data_contract(manifest: Mapping[str, Any]) -> None:
    actual = _actual_contract(manifest)
    differences = {
        key: {"expected": expected, "actual": actual.get(key)}
        for key, expected in EXPECTED_REAL_DATA.items()
        if actual.get(key) != expected
    }
    availability = manifest["availability"]["filing_grain"]["broad"]
    if availability["industry_group_present"] != availability["rows"]:
        differences["filing_industry_group_complete"] = {
            "expected": availability["rows"],
            "actual": availability["industry_group_present"],
        }
    if availability["filing_date_present"] != availability["rows"]:
        differences["filing_date_complete"] = {
            "expected": availability["rows"],
            "actual": availability["filing_date_present"],
        }
    if differences:
        raise AuditError(
            f"expected real-data contract failed: {json.dumps(differences, sort_keys=True)}"
        )


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise AuditError("audit manifest target must be a regular file or absent")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _aliases_any(path: Path, inputs: tuple[Path, ...]) -> bool:
    """Reject lexical, symlink, and hard-link aliases of read-only inputs."""

    resolved = path.resolve()
    for input_path in inputs:
        if resolved == input_path.resolve():
            return True
        if path.exists() and input_path.exists() and os.path.samefile(path, input_path):
            return True
    return False


def build(args: argparse.Namespace) -> dict[str, Any]:
    control_path = Path(args.manifest)
    universe_path = Path(args.universe)
    exclusions_path = Path(args.exclusions)
    audit_path = Path(args.audit_manifest)
    input_paths = (control_path, universe_path, exclusions_path)
    if _aliases_any(audit_path, input_paths):
        raise AuditError("audit manifest must not alias an input")
    control, control_data = load_control_manifest(control_path)
    outputs = control["outputs"]
    broad_pin = _pin(outputs["broad_issuer_universe"], label="broad issuer universe")
    candidate_pin = _pin(
        outputs["candidate_sbir_cik_exclusions"], label="exact-name candidate exclusions"
    )
    candidate_ciks = load_candidate_ciks(exclusions_path, candidate_pin)
    metrics, provisional_cells, candidate_cells, filing_rows = audit_universe(
        universe_path, broad_pin, candidate_ciks
    )
    if filing_rows != control["source_counts"]["filings"]:
        raise AuditError("physical filing rows do not reconcile to the control manifest")

    serialized = _serialize_metrics(metrics)
    eligible_candidates = [cell for cell in candidate_cells if cell is not None]
    supported_1 = sum(provisional_cells[cell] >= 1 for cell in eligible_candidates)
    supported_3 = sum(provisional_cells[cell] >= 3 for cell in eligible_candidates)
    common_support = {
        "cell_fields": [
            "first_observed_form_d_year",
            "index_industry_group",
            "index_state_or_country_code",
        ],
        "candidate_ciks": len(candidate_cells),
        "candidate_ciks_missing_any_cell_field": len(candidate_cells) - len(eligible_candidates),
        "candidate_ciks_support_eligible": len(eligible_candidates),
        "candidate_ciks_with_at_least_1_provisional_in_same_cell": supported_1,
        "candidate_ciks_with_at_least_3_provisional_in_same_cell": supported_3,
        "provisional_ciks_support_eligible": sum(provisional_cells.values()),
        "provisional_common_support_cells": len(provisional_cells),
    }
    manifest: dict[str, Any] = {
        "audit_kind": "form_d_matching_covariate_feasibility",
        "code_commit": args.code_version or _git_commit(),
        "complete": True,
        "complete_sbir_exclusion": False,
        "complete_sbir_identity": False,
        "exclusion_recall": "unknown",
        "covariates_ready": False,
        "ready_for_matching": False,
        "inputs": {
            "control_manifest": {
                "path": control_path.name,
                "sha256": hashlib.sha256(control_data).hexdigest(),
                "size_bytes": len(control_data),
            },
            "broad_issuer_universe": {
                **broad_pin,
            },
            "exact_name_candidate_exclusions": {
                **candidate_pin,
            },
        },
        "caveats": [
            "The exact-name candidate identities are not a validated treated cohort.",
            "The provisional remainder is not known to be free of SBIR exposure.",
            "Form D industry_group is not NAICS or a validated substitute for NAICS-2.",
            "First observed Form D year is left-censored at 2009 and is not firm or award vintage.",
            "STATEORCOUNTRY values include foreign and other SEC codes, not only U.S. states.",
            "Mechanical cell support is not balance, comparability, or a match rate.",
        ],
        "definitions": {
            "index_fields": "all taken from the same earliest filing by filing_date/accession",
            "other_sec_code": "a nonmissing STATEORCOUNTRY code outside the enumerated U.S. state/territory codes",
            "provisional_remainder": "broad exact-CIK universe minus exact-name candidate CIKs",
            "state_or_country_code": "the SEC STATEORCOUNTRY field preserved without truncation",
        },
        "partitions": {
            "broad": "all exact-CIK issuer records in the physical universe",
            "exact_name_candidate": "candidate exact-name evidence CIKs",
            "provisional_remainder": "broad CIKs minus exact-name candidate CIKs",
        },
        **serialized,
        "mechanical_common_support": common_support,
        "invariants": {
            "candidate_ciks_are_subset_of_broad": True,
            "partitions_reconcile": metrics["broad"].cik_rows
            == metrics["exact_name_candidate"].cik_rows + metrics["provisional_remainder"].cik_rows,
            "filing_partitions_reconcile": metrics["broad"].filing_rows
            == metrics["exact_name_candidate"].filing_rows
            + metrics["provisional_remainder"].filing_rows,
            "physical_hash_rows_bytes_verified": True,
            "support_uses_one_earliest_filing_per_cik": True,
        },
        "schema_version": 1,
    }
    if not all(manifest["invariants"].values()):
        raise AuditError(f"audit invariant failed: {manifest['invariants']}")
    if args.expected_real_data_contract:
        _assert_real_data_contract(manifest)
    _atomic_json(audit_path, manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_CONTROL_MANIFEST)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    parser.add_argument("--audit-manifest", type=Path, default=DEFAULT_AUDIT_MANIFEST)
    parser.add_argument("--code-version")
    parser.add_argument("--expected-real-data-contract", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except AuditError as exc:
        print(f"error: {exc}")
        return 1
    print(
        "Wrote Form D covariate feasibility manifest with "
        f"{manifest['availability']['cik_grain']['broad']['rows']:,} broad CIKs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
