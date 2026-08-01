"""Deterministic SBIR.gov source-row materialization for Phase II inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


SBIR_GOV_SOURCE_COLUMNS: tuple[str, ...] = (
    "Company",
    "Award Title",
    "Agency",
    "Branch",
    "Phase",
    "Program",
    "Agency Tracking Number",
    "Contract",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Number",
    "Solicitation Year",
    "Solicitation Close Date",
    "Proposal Receipt Date",
    "Date of Notification",
    "Topic Code",
    "Award Year",
    "Award Amount",
    "UEI",
    "Duns",
    "HUBZone Owned",
    "Socially and Economically Disadvantaged",
    "Woman Owned",
    "Number Employees",
    "Company Website",
    "Address1",
    "Address2",
    "City",
    "State",
    "Zip",
    "Abstract",
    "Contact Name",
    "Contact Title",
    "Contact Phone",
    "Contact Email",
    "PI Name",
    "PI Title",
    "PI Phone",
    "PI Email",
    "RI Name",
    "RI POC Name",
    "RI POC Phone",
)

SBIR_GOV_SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
SBIR_GOV_PROVENANCE_VERSION = 1
_NULL_KEY_TOKENS = frozenset({"", "<NA>", "NAN", "NONE", "NULL", r"\N"})

# Match the existing raw_sbir_awards projection where it is already established. The
# tracking number gets an audit name because ``award_id`` is now the canonical key.
_OUTPUT_NAMES: dict[str, str] = {
    "Company": "company_name",
    "Award Title": "award_title",
    "Agency": "agency",
    "Branch": "branch",
    "Phase": "phase",
    "Program": "program",
    "Agency Tracking Number": "agency_tracking_number",
    "Contract": "contract",
    "Proposal Award Date": "award_date",
    "Award Amount": "award_amount",
    "UEI": "uei",
    "Duns": "duns",
    "Address1": "address1",
    "Address2": "address2",
    "City": "city",
    "State": "state",
    "Zip": "zip",
    "Abstract": "abstract",
    "HUBZone Owned": "hubzone_owned",
    "Woman Owned": "woman_owned",
    "Socially and Economically Disadvantaged": "socially_and_economically_disadvantaged",
    "Number Employees": "number_employees",
    "PI Name": "pi_name",
    "PI Email": "pi_email",
    "RI Name": "ri_name",
}


class SbirGovSourceError(ValueError):
    """Raised when the SBIR.gov source-row contract is not reproducible."""


def _source_value(value: Any) -> str | None:
    """Return one parsed source value without case or whitespace normalization."""

    if value is None or value is pd.NA or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value if isinstance(value, str) else str(value)


def _normalize_key(value: Any) -> str:
    source = _source_value(value)
    if source is None:
        return ""
    normalized = source.strip().upper()
    return "" if normalized in _NULL_KEY_TOKENS else normalized


def _normalize_phase(value: Any) -> str:
    normalized = _normalize_key(value)
    if normalized.startswith("PHASE "):
        normalized = normalized.removeprefix("PHASE ").strip()
    return normalized if normalized in {"I", "II", "III"} else ""


def _row_json(values: list[str | None]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _row_sha256(values: list[str | None]) -> str:
    return hashlib.sha256(_row_json(values).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ordered_columns_sha256(columns: tuple[str, ...] | list[str]) -> str:
    payload = json.dumps(list(columns), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_sbir_gov_csv(path: Path) -> pd.DataFrame:
    """Read the exact 42-field SBIR.gov CSV as strings in declared order."""

    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SbirGovSourceError("SBIR.gov CSV is empty") from exc
        if tuple(header) != SBIR_GOV_SOURCE_COLUMNS:
            raise SbirGovSourceError(
                "SBIR.gov CSV header does not match the required ordered 42-column schema"
            )
        for record_number, row in enumerate(reader, start=2):
            if len(row) != len(SBIR_GOV_SOURCE_COLUMNS):
                raise SbirGovSourceError(
                    f"SBIR.gov CSV record {record_number} has {len(row)} fields; "
                    f"expected {len(SBIR_GOV_SOURCE_COLUMNS)}"
                )
            rows.append(row)
    return pd.DataFrame(rows, columns=SBIR_GOV_SOURCE_COLUMNS, dtype="object")


def canonicalize_sbir_gov_rows(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the frozen exact-row and canonical-ID construction."""

    if tuple(raw.columns) != SBIR_GOV_SOURCE_COLUMNS:
        raise SbirGovSourceError(
            "SBIR.gov source frame does not match the required ordered 42-column schema"
        )

    source = raw.copy()
    for column in SBIR_GOV_SOURCE_COLUMNS:
        source[column] = source[column].map(_source_value)

    raw_rows = len(source)
    retained = source.drop_duplicates(subset=list(SBIR_GOV_SOURCE_COLUMNS), keep="first").copy()
    exact_duplicates = raw_rows - len(retained)

    source_values = retained.loc[:, list(SBIR_GOV_SOURCE_COLUMNS)].values.tolist()
    fingerprints = pd.Series(
        [_row_sha256(values) for values in source_values], index=retained.index, dtype="object"
    )
    contract_keys = retained["Contract"].map(_normalize_key)
    use_contract = contract_keys.ne("")
    base_values = retained["Agency Tracking Number"].copy()
    base_values.loc[use_contract] = retained.loc[use_contract, "Contract"]
    base_values = base_values.where(base_values.map(_normalize_key).ne(""), None)
    normalized_base = base_values.map(_normalize_key)
    normalized_phase = retained["Phase"].map(_normalize_phase)

    grain = pd.DataFrame({"base": normalized_base, "phase": normalized_phase}, index=retained.index)
    group_sizes = grain.groupby(["base", "phase"], dropna=False)["base"].transform("size")
    generated = normalized_base.eq("") | group_sizes.gt(1)
    labels = normalized_base.where(normalized_base.ne(""), "MISSING")
    canonical_ids = base_values.astype("object").copy()
    if bool(generated.any()):
        canonical_ids.loc[generated] = [
            f"SBIRGOV:{label}:{fingerprint}"
            for label, fingerprint in zip(
                labels.loc[generated].tolist(),
                fingerprints.loc[generated].tolist(),
                strict=True,
            )
        ]

    collision_groups = int(grain.loc[normalized_base.ne("")].value_counts().gt(1).sum())
    collision_rows = int((generated & normalized_base.ne("")).sum())
    blank_base_rows = int(normalized_base.eq("").sum())

    enriched = retained.rename(columns=_OUTPUT_NAMES).copy()
    enriched["award_id"] = canonical_ids
    enriched["source_award_id"] = base_values
    enriched["source_row_sha256"] = fingerprints
    enriched["company_uei"] = enriched["uei"]
    enriched["company_duns"] = enriched["duns"]
    enriched["contract_end_date"] = enriched["Contract End Date"]
    enriched["data_source"] = "sbir.gov"

    phase_key = enriched["phase"].map(_normalize_phase)
    canonical_key = enriched["award_id"].map(_normalize_key)
    if canonical_key.eq("").any():
        raise SbirGovSourceError("Canonical SBIR.gov award_id must never be blank")
    if pd.DataFrame({"award_id": canonical_key, "phase": phase_key}).duplicated().any():
        raise SbirGovSourceError("Canonical SBIR.gov award_id + phase keys are not unique")
    if fingerprints.duplicated().any():
        raise SbirGovSourceError("Exact duplicate SBIR.gov source rows survived canonicalization")

    enriched = (
        enriched.assign(_phase_key=phase_key, _award_key=canonical_key)
        .sort_values(["_phase_key", "_award_key", "source_row_sha256"], kind="stable")
        .drop(columns=["_phase_key", "_award_key"])
        .reset_index(drop=True)
    )
    stats = {
        "raw_rows": raw_rows,
        "retained_rows": int(len(retained)),
        "exact_duplicate_rows_collapsed": exact_duplicates,
        "blank_base_rows": blank_base_rows,
        "collision_groups": collision_groups,
        "collision_rows": collision_rows,
        "generated_id_rows": int(generated.sum()),
    }
    return enriched, stats


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def materialize_sbir_gov_history(
    input_path: Path,
    output_path: Path,
    *,
    source_url: str = SBIR_GOV_SOURCE_URL,
) -> dict[str, Any]:
    """Materialize and document the complete deterministic SBIR.gov history."""

    raw = read_sbir_gov_csv(input_path)
    output, stats = canonicalize_sbir_gov_rows(raw)
    output["data_source_url"] = source_url

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        output.to_parquet(temporary, index=False)
        temporary.replace(output_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    output_sha256 = sha256_file(output_path)
    manifest: dict[str, Any] = {
        "ok": True,
        "schema_version": "phase-transition-sbir-input-v2",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_provenance": {
            "system": "SBIR.gov bulk award_data.csv",
            "path": str(input_path.resolve()),
            "url": source_url,
            "sha256": sha256_file(input_path),
            "bytes": input_path.stat().st_size,
            "provenance_version": SBIR_GOV_PROVENANCE_VERSION,
        },
        "source_grain": {
            "ordered_columns": list(SBIR_GOV_SOURCE_COLUMNS),
            "ordered_columns_sha256": ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
            "column_count": len(SBIR_GOV_SOURCE_COLUMNS),
            "exact_duplicate_key": "all_42_parsed_source_values",
            "base_source_id_order": ["Contract", "Agency Tracking Number"],
            "collision_partition": ["normalized_base_source_id", "normalized_phase"],
            "fingerprint": {
                "algorithm": "sha256",
                "encoding": "utf-8",
                "payload": "JSON array of 42 parsed source values in declared header order",
                "json_ensure_ascii": False,
                "json_separators": [",", ":"],
                "null_encoding": "json-null",
                "case_or_whitespace_normalization": False,
                "digest_hex_characters": 64,
            },
            **stats,
        },
        "output": {
            "path": str(output_path.resolve()),
            "sha256": output_sha256,
            "bytes": output_path.stat().st_size,
            "rows": int(len(output)),
            "column_count": len(output.columns),
            "ordered_columns": list(output.columns),
            "ordered_columns_sha256": ordered_columns_sha256(list(output.columns)),
        },
    }
    _write_json_atomic(output_path.with_suffix(".checks.json"), manifest)
    return manifest


def verify_sbir_gov_materialization(path: Path, frame: pd.DataFrame) -> dict[str, Any]:
    """Fail closed unless a materialized input and its manifest satisfy the contract."""

    checks_path = path.with_suffix(".checks.json")
    if not checks_path.is_file():
        raise SbirGovSourceError(f"SBIR.gov input has no provenance manifest: {checks_path}")
    try:
        manifest = json.loads(checks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SbirGovSourceError(f"SBIR.gov provenance manifest is unreadable: {exc}") from exc

    if not isinstance(manifest, dict):
        raise SbirGovSourceError("SBIR.gov provenance manifest must be a JSON object")
    source = manifest.get("source_provenance")
    grain = manifest.get("source_grain")
    output = manifest.get("output")
    if not isinstance(source, dict):
        raise SbirGovSourceError("SBIR.gov provenance manifest sections must be JSON objects")
    if not isinstance(grain, dict):
        raise SbirGovSourceError("SBIR.gov provenance manifest sections must be JSON objects")
    if not isinstance(output, dict):
        raise SbirGovSourceError("SBIR.gov provenance manifest sections must be JSON objects")
    expected_columns_sha = ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS)
    if manifest.get("ok") is not True or manifest.get("schema_version") != (
        "phase-transition-sbir-input-v2"
    ):
        raise SbirGovSourceError("SBIR.gov provenance manifest has an unsupported schema")
    if (
        not isinstance(source.get("provenance_version"), int)
        or isinstance(source["provenance_version"], bool)
        or source["provenance_version"] != SBIR_GOV_PROVENANCE_VERSION
    ):
        raise SbirGovSourceError("SBIR.gov provenance manifest has an unsupported version")
    if source.get("system") != "SBIR.gov bulk award_data.csv":
        raise SbirGovSourceError("SBIR.gov manifest has the wrong source system")
    if not isinstance(source.get("path"), str) or not source["path"]:
        raise SbirGovSourceError("SBIR.gov manifest has an invalid source path")
    if not isinstance(source.get("url"), str) or not source["url"]:
        raise SbirGovSourceError("SBIR.gov manifest has an invalid source URL")
    for label, value in (("source", source.get("sha256")), ("output", output.get("sha256"))):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise SbirGovSourceError(f"SBIR.gov manifest has an invalid {label} SHA-256")
    if (
        not isinstance(source.get("bytes"), int)
        or isinstance(source["bytes"], bool)
        or source["bytes"] < 0
    ):
        raise SbirGovSourceError("SBIR.gov manifest has an invalid source byte count")
    recorded_source_path = Path(source["path"])
    if recorded_source_path.is_file() and (
        recorded_source_path.stat().st_size != source["bytes"]
        or sha256_file(recorded_source_path) != source["sha256"]
    ):
        raise SbirGovSourceError("SBIR.gov raw source does not match its manifest")
    if grain.get("ordered_columns") != list(SBIR_GOV_SOURCE_COLUMNS):
        raise SbirGovSourceError("SBIR.gov manifest has the wrong ordered source columns")
    if (
        not isinstance(grain.get("column_count"), int)
        or isinstance(grain["column_count"], bool)
        or grain["column_count"] != len(SBIR_GOV_SOURCE_COLUMNS)
    ):
        raise SbirGovSourceError("SBIR.gov manifest has the wrong source column count")
    if grain.get("ordered_columns_sha256") != expected_columns_sha:
        raise SbirGovSourceError("SBIR.gov manifest source-column fingerprint is invalid")
    for field in ("rows", "bytes", "column_count"):
        if (
            not isinstance(output.get(field), int)
            or isinstance(output[field], bool)
            or output[field] < 0
        ):
            raise SbirGovSourceError(f"SBIR.gov manifest has an invalid output {field}")
    if output.get("rows") != len(frame) or output.get("ordered_columns") != list(frame.columns):
        raise SbirGovSourceError("SBIR.gov parquet shape does not match its manifest")
    if output.get("column_count") != len(frame.columns):
        raise SbirGovSourceError("SBIR.gov parquet column count does not match its manifest")
    if output.get("bytes") != path.stat().st_size:
        raise SbirGovSourceError("SBIR.gov parquet byte count does not match its manifest")
    if output.get("ordered_columns_sha256") != ordered_columns_sha256(list(frame.columns)):
        raise SbirGovSourceError("SBIR.gov parquet columns do not match their fingerprint")
    if output.get("sha256") != sha256_file(path):
        raise SbirGovSourceError("SBIR.gov parquet checksum does not match its manifest")

    expected_fingerprint = {
        "algorithm": "sha256",
        "encoding": "utf-8",
        "payload": "JSON array of 42 parsed source values in declared header order",
        "json_ensure_ascii": False,
        "json_separators": [",", ":"],
        "null_encoding": "json-null",
        "case_or_whitespace_normalization": False,
        "digest_hex_characters": 64,
    }
    if grain.get("exact_duplicate_key") != "all_42_parsed_source_values":
        raise SbirGovSourceError("SBIR.gov manifest has the wrong exact-duplicate key")
    if grain.get("base_source_id_order") != ["Contract", "Agency Tracking Number"]:
        raise SbirGovSourceError("SBIR.gov manifest has the wrong base source-ID order")
    if grain.get("collision_partition") != [
        "normalized_base_source_id",
        "normalized_phase",
    ]:
        raise SbirGovSourceError("SBIR.gov manifest has the wrong collision partition")
    if grain.get("fingerprint") != expected_fingerprint:
        raise SbirGovSourceError("SBIR.gov manifest has the wrong fingerprint contract")

    count_fields = (
        "raw_rows",
        "retained_rows",
        "exact_duplicate_rows_collapsed",
        "blank_base_rows",
        "collision_groups",
        "collision_rows",
        "generated_id_rows",
    )
    if any(
        not isinstance(grain.get(field), int) or isinstance(grain[field], bool) or grain[field] < 0
        for field in count_fields
    ):
        raise SbirGovSourceError("SBIR.gov manifest has invalid source-grain counts")
    if grain["retained_rows"] != len(frame) or output.get("rows") != grain["retained_rows"]:
        raise SbirGovSourceError("SBIR.gov retained-row count does not match the parquet")
    if grain["raw_rows"] - grain["retained_rows"] != grain["exact_duplicate_rows_collapsed"]:
        raise SbirGovSourceError("SBIR.gov exact-duplicate count identity is invalid")
    if grain["generated_id_rows"] != grain["blank_base_rows"] + grain["collision_rows"]:
        raise SbirGovSourceError("SBIR.gov generated-ID count identity is invalid")

    required = {"award_id", "source_award_id", "source_row_sha256", "phase"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SbirGovSourceError(f"SBIR.gov parquet is missing source-grain fields: {missing}")
    digests = frame["source_row_sha256"].astype("string")
    valid_digest = digests.str.fullmatch(r"[0-9a-f]{64}", na=False)
    if not bool(valid_digest.all()) or digests.duplicated().any():
        raise SbirGovSourceError("SBIR.gov source-row fingerprints are invalid or duplicate")
    keys = pd.DataFrame(
        {
            "award_id": frame["award_id"].map(_normalize_key),
            "phase": frame["phase"].map(_normalize_phase),
        }
    )
    if keys["award_id"].eq("").any() or keys.duplicated().any():
        raise SbirGovSourceError("SBIR.gov canonical award_id + phase keys are invalid")

    output_source_columns = [
        _OUTPUT_NAMES.get(column, column) for column in SBIR_GOV_SOURCE_COLUMNS
    ]
    missing_source = sorted(set(output_source_columns) - set(frame.columns))
    if missing_source:
        raise SbirGovSourceError(
            f"SBIR.gov parquet is missing fingerprint source fields: {missing_source}"
        )
    reconstructed = frame.loc[:, output_source_columns].copy()
    reconstructed.columns = SBIR_GOV_SOURCE_COLUMNS
    expected, expected_stats = canonicalize_sbir_gov_rows(reconstructed)
    derived_aliases = {
        "company_uei": "uei",
        "company_duns": "duns",
        "contract_end_date": "Contract End Date",
    }
    missing_aliases = sorted(
        {column for pair in derived_aliases.items() for column in pair} - set(frame.columns)
    )
    if missing_aliases:
        raise SbirGovSourceError(
            f"SBIR.gov parquet is missing derived source fields: {missing_aliases}"
        )
    for alias, source_column in derived_aliases.items():
        try:
            pd.testing.assert_series_equal(
                frame[alias],
                frame[source_column],
                check_names=False,
                check_dtype=False,
            )
        except AssertionError as exc:
            raise SbirGovSourceError(f"SBIR.gov parquet has an invalid derived {alias}") from exc
    if "data_source" not in frame.columns or not bool(
        frame["data_source"].eq("sbir.gov").fillna(False).all()
    ):
        raise SbirGovSourceError("SBIR.gov parquet has an invalid data_source")
    if "data_source_url" not in frame.columns or not bool(
        frame["data_source_url"].eq(source["url"]).fillna(False).all()
    ):
        raise SbirGovSourceError("SBIR.gov parquet has an invalid data_source_url")
    for column in ("award_id", "source_award_id", "source_row_sha256"):
        actual_by_digest = frame.set_index("source_row_sha256", drop=False)[column].sort_index()
        expected_by_digest = expected.set_index("source_row_sha256", drop=False)[
            column
        ].sort_index()
        try:
            pd.testing.assert_series_equal(
                actual_by_digest,
                expected_by_digest,
                check_names=False,
                check_dtype=False,
                check_index_type=False,
            )
        except AssertionError as exc:
            raise SbirGovSourceError(
                f"SBIR.gov parquet has an invalid recomputed {column}"
            ) from exc
    for field, value in expected_stats.items():
        if field in {"raw_rows", "exact_duplicate_rows_collapsed"}:
            # Exact duplicates are absent from the parquet by construction; their count is
            # verified through the manifest identity above.
            continue
        if grain.get(field) != value:
            raise SbirGovSourceError(
                f"SBIR.gov manifest {field} does not match the recomputed parquet grain"
            )
    return manifest


__all__ = [
    "SBIR_GOV_PROVENANCE_VERSION",
    "SBIR_GOV_SOURCE_COLUMNS",
    "SBIR_GOV_SOURCE_URL",
    "SbirGovSourceError",
    "canonicalize_sbir_gov_rows",
    "materialize_sbir_gov_history",
    "ordered_columns_sha256",
    "read_sbir_gov_csv",
    "sha256_file",
    "verify_sbir_gov_materialization",
]
