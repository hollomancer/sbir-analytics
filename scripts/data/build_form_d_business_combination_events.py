#!/usr/bin/env python3
"""Build complete Form D business-combination filing-proxy event coverage.

The input is the broad issuer JSONL pinned by the tracked PR2 Form D source
manifest.  This producer emits filing evidence, not a legal transaction or exit
classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, cast

from sbir_analytics.assets.agency_private_capital.symmetric_event_coverage import EVENT_TYPE


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_MANIFEST = (
    REPO_ROOT / "docs/research/agency-private-capital-form-d-control-universe.manifest.json"
)
DEFAULT_ISSUER_UNIVERSE = (
    REPO_ROOT / "data/processed/agency_private_capital/control_universe/"
    "form_d_issuer_universe.identity-staging.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "data/processed/agency_private_capital/form_d_business_combination_events"
)
START_QUARTER = "2009Q1"
END_QUARTER = "2024Q4"
COVERAGE_START_DATE = date(2009, 1, 1)
SOURCE_SNAPSHOT_DATE = date(2024, 12, 31)
SOURCE = "sec_dera_form_d_quarterly_bulk"
EVIDENCE_KIND = "proxy"
DATE_BASIS = "filing_date"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
EXPECTED_QUARTERS = tuple(
    f"{year}Q{quarter}" for year in range(2009, 2025) for quarter in range(1, 5)
)
EXPECTED_QUARTER_SET = frozenset(EXPECTED_QUARTERS)


class BuildError(RuntimeError):
    """Raised when a source contract or record is incomplete."""


def _expected_quarters() -> list[str]:
    return list(EXPECTED_QUARTERS)


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BuildError(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BuildError(f"{label} must be a positive integer")
    return value


def load_source_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load and validate the closed 64-quarter PR2 source contract."""

    if not path.is_file():
        raise BuildError(f"Required tracked PR2 source manifest is missing: {path}")
    try:
        manifest_data = path.read_bytes()
        manifest = json.loads(manifest_data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"Invalid JSON in source manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise BuildError("Source manifest must be a JSON object")

    expected_quarters = _expected_quarters()
    parameters = manifest.get("parameters")
    if not isinstance(parameters, Mapping):
        raise BuildError("Source manifest has no parameters object")
    if manifest.get("complete") is not True:
        raise BuildError("Source manifest does not declare complete=true")
    if parameters.get("start_quarter") != START_QUARTER:
        raise BuildError(f"Source manifest must start at {START_QUARTER}")
    if parameters.get("end_quarter") != END_QUARTER:
        raise BuildError(f"Source manifest must end at {END_QUARTER}")
    if parameters.get("quarter_count") != len(expected_quarters):
        raise BuildError("Source manifest must declare exactly 64 quarters")
    if parameters.get("quarters") != expected_quarters:
        raise BuildError(
            "Source manifest quarter list is not the complete ordered 2009Q1-2024Q4 set"
        )

    inputs = manifest.get("inputs")
    quarter_metadata = inputs.get("quarters") if isinstance(inputs, Mapping) else None
    if not isinstance(quarter_metadata, Mapping):
        raise BuildError("Source manifest has no quarter metadata")
    missing = [quarter for quarter in expected_quarters if quarter not in quarter_metadata]
    extra = sorted(set(quarter_metadata) - set(expected_quarters))
    if missing:
        raise BuildError(
            f"Source manifest is missing required quarter metadata: {', '.join(missing)}"
        )
    if extra:
        raise BuildError(f"Source manifest has unexpected quarter metadata: {', '.join(extra)}")
    total_emitted_filings = 0
    for quarter in expected_quarters:
        metadata = quarter_metadata[quarter]
        if not isinstance(metadata, Mapping):
            raise BuildError(f"Required source quarter {quarter} has no metadata object")
        headers = metadata.get("headers")
        offering_headers = headers.get("OFFERING.tsv") if isinstance(headers, Mapping) else None
        if (
            not isinstance(offering_headers, list)
            or "ISBUSINESSCOMBINATIONTRANS" not in offering_headers
        ):
            raise BuildError(
                f"Required source quarter {quarter} does not pin "
                "OFFERING.tsv ISBUSINESSCOMBINATIONTRANS"
            )
        counters = metadata.get("counters")
        if not isinstance(counters, Mapping):
            raise BuildError(f"Required source quarter {quarter} has no counters object")
        selected_flagged = _non_negative_int(
            counters.get("selected_business_combination_filings"),
            label=f"{quarter} selected_business_combination_filings",
        )
        selected_unflagged = _non_negative_int(
            counters.get("selected_non_business_combination_filings"),
            label=f"{quarter} selected_non_business_combination_filings",
        )
        emitted_flagged = _non_negative_int(
            counters.get("emitted_business_combination_filings"),
            label=f"{quarter} emitted_business_combination_filings",
        )
        omitted_flagged = _non_negative_int(
            counters.get("omitted_business_combination_filings"),
            label=f"{quarter} omitted_business_combination_filings",
        )
        invalid_flags = _non_negative_int(
            counters.get("invalid_business_combination_flags"),
            label=f"{quarter} invalid_business_combination_flags",
        )
        selected_submissions = _non_negative_int(
            counters.get("selected_submissions"),
            label=f"{quarter} selected_submissions",
        )
        emitted_filings = _non_negative_int(
            counters.get("emitted_filings"), label=f"{quarter} emitted_filings"
        )
        if selected_flagged + selected_unflagged != selected_submissions:
            raise BuildError(
                f"Required source quarter {quarter} does not reconcile all selected "
                "business-combination flags"
            )
        if invalid_flags != 0:
            raise BuildError(
                f"Required source quarter {quarter} has {invalid_flags} invalid "
                "business-combination flag(s)"
            )
        if selected_flagged != emitted_flagged + omitted_flagged:
            raise BuildError(
                f"Required source quarter {quarter} has inconsistent business-combination "
                "filing counters"
            )
        if omitted_flagged != 0:
            raise BuildError(
                f"Required source quarter {quarter} omitted {omitted_flagged} "
                "business-combination filing(s) from the issuer universe"
            )
        if emitted_flagged > emitted_filings or emitted_filings > selected_submissions:
            raise BuildError(
                f"Required source quarter {quarter} has inconsistent emitted filing counters"
            )
        emitted_unflagged = emitted_filings - emitted_flagged
        if emitted_unflagged > selected_unflagged:
            raise BuildError(
                f"Required source quarter {quarter} emits more non-business-combination "
                "filings than were selected"
            )
        total_emitted_filings += emitted_filings

    outputs = manifest.get("outputs")
    product = outputs.get("broad_issuer_universe") if isinstance(outputs, Mapping) else None
    if not isinstance(product, Mapping):
        raise BuildError("Source manifest does not pin the broad issuer universe")
    product_sha = product.get("sha256")
    if not isinstance(product_sha, str) or SHA256_RE.fullmatch(product_sha) is None:
        raise BuildError("Pinned issuer universe has an invalid SHA-256")
    _positive_int(product.get("row_count"), label="Pinned issuer-universe row_count")
    _positive_int(product.get("size_bytes"), label="Pinned issuer-universe size_bytes")

    source_counts = manifest.get("source_counts")
    if not isinstance(source_counts, Mapping):
        raise BuildError("Source manifest has no source_counts object")
    issuer_count = _positive_int(source_counts.get("issuer_ciks"), label="Source issuer-CIK count")
    source_filing_count = _positive_int(source_counts.get("filings"), label="Source filing count")
    if source_filing_count != total_emitted_filings:
        raise BuildError(
            "Source filing count does not equal the sum of per-quarter emitted filings"
        )
    if issuer_count != product.get("row_count"):
        raise BuildError("Source issuer-CIK count does not match the pinned universe row count")
    invariants = manifest.get("invariants")
    if not isinstance(invariants, Mapping) or invariants.get("broad_ciks_unique") is not True:
        raise BuildError("Source manifest does not establish unique broad-universe CIKs")
    return manifest, manifest_data


def _canonical_firm_key(record: Mapping[str, Any], *, line_number: int) -> tuple[str, str]:
    cik = record.get("cik")
    firm_key = record.get("firm_key")
    if not isinstance(cik, str) or not cik.isdigit() or cik.startswith("0") or len(cik) > 10:
        raise BuildError(f"Issuer universe line {line_number} has an invalid canonical CIK")
    expected = f"form_d_cik:{cik}"
    if firm_key != expected:
        raise BuildError(f"Issuer universe line {line_number} must use exact firm_key {expected!r}")
    return cik, expected


def _required_text(value: object, *, field: str, line_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"Issuer universe line {line_number} filing has invalid {field}")
    return value.strip()


def _filing_record(
    filing: Mapping[str, Any],
    *,
    cik: str,
    firm_key: str,
    line_number: int,
    source_snapshot_id: str,
) -> dict[str, Any]:
    if filing.get("cik") != cik:
        raise BuildError(f"Issuer universe line {line_number} filing CIK does not match its issuer")
    accession = _required_text(
        filing.get("accession_number"), field="accession_number", line_number=line_number
    )
    filing_date_raw = _required_text(
        filing.get("filing_date"), field="filing_date", line_number=line_number
    )
    try:
        filing_date = date.fromisoformat(filing_date_raw)
    except ValueError as exc:
        raise BuildError(
            f"Issuer universe line {line_number} filing has invalid filing_date"
        ) from exc
    if not COVERAGE_START_DATE <= filing_date <= SOURCE_SNAPSHOT_DATE:
        raise BuildError(
            f"Issuer universe line {line_number} filing_date falls outside source coverage"
        )
    source_quarter = _required_text(
        filing.get("source_quarter"), field="source_quarter", line_number=line_number
    )
    if source_quarter not in EXPECTED_QUARTER_SET:
        raise BuildError(f"Issuer universe line {line_number} has unknown source_quarter")
    expected_quarter = f"{filing_date.year}Q{((filing_date.month - 1) // 3) + 1}"
    if source_quarter != expected_quarter:
        raise BuildError(
            f"Issuer universe line {line_number} filing source_quarter does not match filing_date"
        )
    is_amendment = filing.get("is_amendment")
    if not isinstance(is_amendment, bool):
        raise BuildError(f"Issuer universe line {line_number} filing has invalid is_amendment")
    previous_accession = filing.get("previous_accession_number")
    if previous_accession is not None and not isinstance(previous_accession, str):
        raise BuildError(
            f"Issuer universe line {line_number} filing has invalid previous_accession_number"
        )
    is_proxy_event = filing.get("is_business_combination")
    if not isinstance(is_proxy_event, bool):
        raise BuildError(
            f"Issuer universe line {line_number} filing has invalid business-combination flag"
        )
    submission_type = _required_text(
        filing.get("submission_type"), field="submission_type", line_number=line_number
    )
    if submission_type not in {"D", "D/A"}:
        raise BuildError(f"Issuer universe line {line_number} filing has invalid submission_type")
    return {
        "accession_number": accession,
        "date_basis": DATE_BASIS,
        "event_date": filing_date.isoformat(),
        "event_id": f"form_d_accession:{accession}",
        "event_type": EVENT_TYPE,
        "evidence_kind": EVIDENCE_KIND,
        "filing_date": filing_date.isoformat(),
        "firm_key": firm_key,
        "is_amendment": is_amendment,
        "previous_accession_number": previous_accession.strip()
        if isinstance(previous_accession, str) and previous_accession.strip()
        else None,
        "schema_version": 1,
        "source": SOURCE,
        "source_quarter": source_quarter,
        "source_snapshot_id": source_snapshot_id,
        "submission_type": submission_type,
        "_is_proxy_event": is_proxy_event,
    }


def _write_jsonl_row(handle: BinaryIO, digest: Any, record: Mapping[str, Any]) -> int:
    data = (
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    handle.write(data)
    digest.update(data)
    return len(data)


def _temporary_output(path: Path) -> tuple[BinaryIO, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w+b", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    return cast(BinaryIO, handle), Path(handle.name)


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_manifest_path = Path(args.source_manifest)
    issuer_universe_path = Path(args.issuer_universe)
    source_manifest, source_manifest_data = load_source_manifest(source_manifest_path)
    product = source_manifest["outputs"]["broad_issuer_universe"]
    expected_filing_rows = int(source_manifest["source_counts"]["filings"])
    source_quarters = source_manifest["inputs"]["quarters"]
    expected_filing_quarters = {
        quarter: int(source_quarters[quarter]["counters"]["emitted_filings"])
        for quarter in EXPECTED_QUARTERS
    }
    expected_event_quarters = {
        quarter: int(source_quarters[quarter]["counters"]["emitted_business_combination_filings"])
        for quarter in EXPECTED_QUARTERS
    }
    expected_event_rows = sum(expected_event_quarters.values())
    if not issuer_universe_path.is_file():
        raise BuildError(f"Pinned issuer universe is missing: {issuer_universe_path}")
    if issuer_universe_path.stat().st_size != product["size_bytes"]:
        raise BuildError("Issuer-universe byte count does not match the source manifest")

    source_manifest_sha = hashlib.sha256(source_manifest_data).hexdigest()
    source_snapshot_id = f"form_d_control_universe_manifest_sha256:{source_manifest_sha}"
    output_dir = Path(args.output_dir)
    event_staging_hint = output_dir / f"{EVENT_TYPE}.events.jsonl"
    coverage_staging_hint = output_dir / f"{EVENT_TYPE}.coverage.jsonl"
    manifest_path = output_dir / f"{EVENT_TYPE}.manifest.json"
    event_handle: BinaryIO | None = None
    coverage_handle: BinaryIO | None = None
    event_temp: Path | None = None
    coverage_temp: Path | None = None
    counters: Counter[str] = Counter()
    filing_quarters: Counter[str] = Counter()
    event_quarters: Counter[str] = Counter()
    input_digest = hashlib.sha256()
    event_digest = hashlib.sha256()
    coverage_digest = hashlib.sha256()
    event_size = 0
    coverage_size = 0
    previous_firm_key: str | None = None
    seen_accessions: set[str] = set()
    seen_event_ids: set[str] = set()
    source_validated = False

    try:
        event_handle, event_temp = _temporary_output(event_staging_hint)
        coverage_handle, coverage_temp = _temporary_output(coverage_staging_hint)
        with issuer_universe_path.open("rb") as source:
            for line_number, raw_line in enumerate(source, start=1):
                input_digest.update(raw_line)
                if not raw_line.strip():
                    raise BuildError(f"Issuer universe contains a blank line at {line_number}")
                counters["issuer_rows"] += 1
                try:
                    record = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BuildError(f"Invalid issuer-universe JSON at line {line_number}") from exc
                if not isinstance(record, Mapping):
                    raise BuildError(f"Issuer universe line {line_number} must be a JSON object")
                cik, firm_key = _canonical_firm_key(record, line_number=line_number)
                if previous_firm_key is not None and firm_key <= previous_firm_key:
                    raise BuildError("Issuer universe firm keys must be unique and ordered")
                previous_firm_key = firm_key
                filings = record.get("filings")
                if not isinstance(filings, list) or not filings:
                    raise BuildError(f"Issuer universe line {line_number} has no filing evidence")
                filing_count = record.get("filing_count")
                if (
                    isinstance(filing_count, bool)
                    or not isinstance(filing_count, int)
                    or filing_count != len(filings)
                ):
                    raise BuildError(
                        f"Issuer universe line {line_number} filing_count does not match filings"
                    )

                validated_filings: list[dict[str, Any]] = []
                for filing in filings:
                    counters["filing_rows"] += 1
                    if not isinstance(filing, Mapping):
                        raise BuildError(
                            f"Issuer universe line {line_number} contains a non-object filing"
                        )
                    validated = _filing_record(
                        filing,
                        cik=cik,
                        firm_key=firm_key,
                        line_number=line_number,
                        source_snapshot_id=source_snapshot_id,
                    )
                    accession = str(validated["accession_number"])
                    if accession in seen_accessions:
                        raise BuildError(f"Issuer universe repeats accession {accession}")
                    seen_accessions.add(accession)
                    filing_quarters[str(validated["source_quarter"])] += 1
                    if validated.pop("_is_proxy_event"):
                        event_id = str(validated["event_id"])
                        if event_id in seen_event_ids:
                            raise BuildError(f"Issuer universe repeats event_id {event_id}")
                        seen_event_ids.add(event_id)
                        validated_filings.append(validated)

                for event in sorted(
                    validated_filings,
                    key=lambda row: (str(row["event_date"]), str(row["event_id"])),
                ):
                    event_size += _write_jsonl_row(event_handle, event_digest, event)
                    counters["event_rows"] += 1
                    event_quarters[str(event["source_quarter"])] += 1
                    if event["is_amendment"]:
                        counters["amendment_event_rows"] += 1
                if validated_filings:
                    counters["firms_with_event"] += 1
                else:
                    counters["firms_without_event"] += 1

                coverage = {
                    "coverage_end_date": SOURCE_SNAPSHOT_DATE.isoformat(),
                    "coverage_start_date": COVERAGE_START_DATE.isoformat(),
                    "firm_key": firm_key,
                    "metric": EVENT_TYPE,
                    "schema_version": 1,
                    "source": SOURCE,
                    "source_complete": True,
                    "source_snapshot_date": SOURCE_SNAPSHOT_DATE.isoformat(),
                    "source_snapshot_id": source_snapshot_id,
                }
                coverage_size += _write_jsonl_row(coverage_handle, coverage_digest, coverage)
                counters["coverage_rows"] += 1

        event_handle.close()
        coverage_handle.close()
        event_handle = None
        coverage_handle = None

        if counters["issuer_rows"] != product["row_count"]:
            raise BuildError("Issuer-universe row count does not match the source manifest")
        if counters["filing_rows"] != expected_filing_rows:
            raise BuildError("Issuer-universe filing count does not match the source manifest")
        if input_digest.hexdigest() != product["sha256"]:
            raise BuildError("Issuer-universe SHA-256 does not match the source manifest")
        if counters["coverage_rows"] != counters["issuer_rows"]:
            raise BuildError("Coverage row count does not equal the verified issuer count")
        if counters["event_rows"] != expected_event_rows:
            raise BuildError(
                "Emitted event count does not match the source manifest's complete flagged count"
            )
        actual_filing_quarters = {
            quarter: filing_quarters.get(quarter, 0) for quarter in EXPECTED_QUARTERS
        }
        if actual_filing_quarters != expected_filing_quarters:
            raise BuildError("Issuer-universe filing counts do not reconcile by source quarter")
        actual_event_quarters = {
            quarter: event_quarters.get(quarter, 0) for quarter in EXPECTED_QUARTERS
        }
        if actual_event_quarters != expected_event_quarters:
            raise BuildError("Emitted event counts do not reconcile by source quarter")
        source_validated = True
    finally:
        if event_handle is not None:
            event_handle.close()
        if coverage_handle is not None:
            coverage_handle.close()
        if not source_validated:
            if event_temp is not None:
                event_temp.unlink(missing_ok=True)
            if coverage_temp is not None:
                coverage_temp.unlink(missing_ok=True)

    event_sha = event_digest.hexdigest()
    coverage_sha = coverage_digest.hexdigest()
    event_path = output_dir / f"{EVENT_TYPE}.events.{event_sha}.jsonl"
    coverage_path = output_dir / f"{EVENT_TYPE}.coverage.{coverage_sha}.jsonl"
    outputs = {
        "coverage": {
            "path": coverage_path.name,
            "row_count": counters["coverage_rows"],
            "sha256": coverage_sha,
            "size_bytes": coverage_size,
        },
        "events": {
            "path": event_path.name,
            "row_count": counters["event_rows"],
            "sha256": event_sha,
            "size_bytes": event_size,
        },
    }
    manifest = {
        "code_commit": args.code_version or _git_commit(),
        "complete": True,
        "counters": dict(sorted(counters.items())),
        "event_counts_by_source_quarter": dict(sorted(event_quarters.items())),
        "event_type": EVENT_TYPE,
        "filing_counts_by_source_quarter": dict(sorted(filing_quarters.items())),
        "inputs": {
            "issuer_universe": {
                "path": issuer_universe_path.name,
                "row_count": product["row_count"],
                "sha256": product["sha256"],
                "size_bytes": product["size_bytes"],
            },
            "source_manifest": {
                "path": source_manifest_path.name,
                "sha256": source_manifest_sha,
                "size_bytes": len(source_manifest_data),
            },
        },
        "invariants": {
            "accessions_unique": len(seen_accessions) == counters["filing_rows"],
            "content_addressed_outputs": True,
            "coverage_equals_verified_issuer_rows": counters["coverage_rows"]
            == counters["issuer_rows"],
            "event_counts_reconcile_by_source_quarter": {
                quarter: event_quarters.get(quarter, 0) for quarter in EXPECTED_QUARTERS
            }
            == expected_event_quarters,
            "event_ids_unique": len(seen_event_ids) == counters["event_rows"],
            "filing_counts_reconcile_by_source_quarter": {
                quarter: filing_quarters.get(quarter, 0) for quarter in EXPECTED_QUARTERS
            }
            == expected_filing_quarters,
            "filing_rows_equal_source_manifest": counters["filing_rows"] == expected_filing_rows,
            "flagged_source_filings_omitted": 0,
            "flagged_source_filings_reconciled": counters["event_rows"] == expected_event_rows,
            "source_input_hash_rows_bytes_verified": True,
            "source_quarters_complete": True,
        },
        "outputs": outputs,
        "schema_version": 1,
        "source": {
            "coverage_end_date": SOURCE_SNAPSHOT_DATE.isoformat(),
            "coverage_start_date": COVERAGE_START_DATE.isoformat(),
            "end_quarter": END_QUARTER,
            "quarter_count": 64,
            "source": SOURCE,
            "source_complete": True,
            "source_snapshot_date": SOURCE_SNAPSHOT_DATE.isoformat(),
            "source_snapshot_id": source_snapshot_id,
            "start_quarter": START_QUARTER,
        },
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=manifest_path.parent, prefix=f".{manifest_path.name}.", delete=False
        ) as handle:
            handle.write(manifest_data)
            manifest_temp = Path(handle.name)
        if event_temp is None or coverage_temp is None:
            raise AssertionError("validated product staging files are missing")
        os.replace(event_temp, event_path)
        event_temp = None
        os.replace(coverage_temp, coverage_path)
        coverage_temp = None
        os.replace(manifest_temp, manifest_path)
        manifest_temp = None
    finally:
        if event_temp is not None:
            event_temp.unlink(missing_ok=True)
        if coverage_temp is not None:
            coverage_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--issuer-universe", type=Path, default=DEFAULT_ISSUER_UNIVERSE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--code-version", help="Pinned producer commit for the build manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except BuildError as exc:
        print(f"error: {exc}")
        return 1
    print(json.dumps({"counters": manifest["counters"], "outputs": manifest["outputs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
