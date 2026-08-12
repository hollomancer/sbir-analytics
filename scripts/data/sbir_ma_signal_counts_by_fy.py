#!/usr/bin/env python3
"""Count fingerprinted SBIR M&A signal records by federal fiscal year.

This is a descriptive diagnostic over an existing ``sbir_ma_events.jsonl``
artifact. It does not calculate acquisition, exit, or match rates.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Sequence
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from stat import S_IMODE
from typing import Any


DEFAULT_INPUT = Path("data/sbir_ma_events.jsonl")
DEFAULT_CSV_OUTPUT = Path("reports/sbir_ma_signal_counts_by_fy.csv")
DEFAULT_MARKDOWN_OUTPUT = Path("reports/sbir_ma_signal_counts_by_fy.md")
DEFAULT_START_FY = 2015
DEFAULT_END_FY = 2024
CONFIDENCE_TIERS = ("high", "medium", "low")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
CSV_COLUMNS = (
    "fiscal_year",
    "high_signal_name_keys",
    "medium_signal_name_keys",
    "high_medium_signal_name_keys",
    "low_sensitivity_signal_name_keys",
    "total_signal_name_keys",
)
DATE_CATEGORIES = ("in_window", "valid_out_of_window", "missing", "invalid")


class InputValidationError(ValueError):
    """Raised when the supplied JSONL artifact violates the input contract."""


@dataclass(frozen=True)
class SignalRecord:
    """One record at the normalized company-name-key grain."""

    company_key: str
    confidence: str
    event_date: date | None
    date_status: str
    date_identity: tuple[str, str]
    source_line: int


@dataclass(frozen=True)
class SignalDataset:
    """Validated, deduplicated input plus its byte-level provenance."""

    source_path: Path
    source_sha256: str
    source_bytes: int
    input_rows: int
    duplicate_rows: int
    records: tuple[SignalRecord, ...]


@dataclass(frozen=True)
class CountResult:
    """FY rows and reconciled diagnostics for a validated dataset."""

    rows: tuple[dict[str, int], ...]
    missing_date_keys: int
    invalid_date_keys: int
    valid_out_of_window_keys: int
    in_window_keys: int
    distinct_tier_counts: dict[str, int]
    date_status_by_tier: dict[str, dict[str, int]]


def fiscal_year(value: date) -> int:
    """Return the federal fiscal year for an observation date."""

    return value.year + 1 if value.month >= 10 else value.year


def normalize_company_name(value: str) -> str:
    """Normalize only leading/trailing whitespace and letter case."""

    return value.strip().casefold()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputValidationError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise InputValidationError(f"non-standard JSON constant {value!r}")


def _parse_event_date(
    payload: dict[str, Any], line_number: int
) -> tuple[date | None, str, tuple[str, str]]:
    if "event_date" not in payload or payload["event_date"] is None:
        return None, "missing", ("missing", "")

    raw_value = payload["event_date"]
    if not isinstance(raw_value, str):
        raise InputValidationError(
            f"line {line_number}: event_date must be a string, null, or absent"
        )
    if raw_value == "":
        return None, "missing", ("missing", "")
    if not ISO_DATE.fullmatch(raw_value):
        return None, "invalid", ("invalid", raw_value)

    try:
        parsed = date.fromisoformat(raw_value)
    except ValueError:
        return None, "invalid", ("invalid", raw_value)
    return parsed, "valid", ("valid", parsed.isoformat())


def _parse_record(line: str, line_number: int) -> SignalRecord:
    if not line.strip():
        raise InputValidationError(f"line {line_number}: blank JSONL lines are not allowed")

    try:
        payload = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except (json.JSONDecodeError, InputValidationError) as exc:
        raise InputValidationError(f"line {line_number}: invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise InputValidationError(f"line {line_number}: each JSONL value must be an object")

    company_name = payload.get("company_name")
    if not isinstance(company_name, str) or not company_name.strip():
        raise InputValidationError(f"line {line_number}: company_name must be a non-empty string")
    company_key = normalize_company_name(company_name)

    confidence = payload.get("confidence")
    if confidence not in CONFIDENCE_TIERS:
        allowed = ", ".join(CONFIDENCE_TIERS)
        raise InputValidationError(
            f"line {line_number}: confidence must be exactly one of: {allowed}"
        )

    parsed_date, date_status, date_identity = _parse_event_date(payload, line_number)
    return SignalRecord(
        company_key=company_key,
        confidence=confidence,
        event_date=parsed_date,
        date_status=date_status,
        date_identity=date_identity,
        source_line=line_number,
    )


def load_signal_dataset(path: Path) -> SignalDataset:
    """Read, strictly validate, and deduplicate a JSONL signal artifact."""

    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise InputValidationError(f"input does not exist: {path}") from exc
    except OSError as exc:
        raise InputValidationError(f"cannot read input {path}: {exc}") from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputValidationError(f"input is not valid UTF-8: {path}") from exc

    records_by_key: dict[str, SignalRecord] = {}
    input_rows = 0
    duplicate_rows = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        input_rows += 1
        record = _parse_record(line, line_number)
        prior = records_by_key.get(record.company_key)
        if prior is None:
            records_by_key[record.company_key] = record
            continue

        if prior.confidence != record.confidence or prior.date_identity != record.date_identity:
            raise InputValidationError(
                "conflicting duplicate company key "
                f"{record.company_key!r} at lines {prior.source_line} and {line_number}: "
                "event_date and confidence must agree"
            )
        duplicate_rows += 1

    if input_rows == 0:
        raise InputValidationError(f"input contains zero JSONL records: {path}")

    return SignalDataset(
        source_path=path,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),
        input_rows=input_rows,
        duplicate_rows=duplicate_rows,
        records=tuple(records_by_key.values()),
    )


def build_counts(dataset: SignalDataset, start_fy: int, end_fy: int) -> CountResult:
    """Build FY rows and fail if any internal reconciliation is violated."""

    if start_fy > end_fy:
        raise ValueError("start fiscal year must not be after end fiscal year")

    by_fy = {
        fiscal_year_value: Counter(dict.fromkeys(CONFIDENCE_TIERS, 0))
        for fiscal_year_value in range(start_fy, end_fy + 1)
    }
    date_status_counts: Counter[str] = Counter()
    distinct_tier_counts: Counter[str] = Counter()
    date_status_by_tier = {
        tier: Counter(dict.fromkeys(DATE_CATEGORIES, 0)) for tier in CONFIDENCE_TIERS
    }
    valid_out_of_window_keys = 0

    for record in dataset.records:
        distinct_tier_counts[record.confidence] += 1
        date_status_counts[record.date_status] += 1
        if record.date_status != "valid":
            date_status_by_tier[record.confidence][record.date_status] += 1
            continue
        if record.event_date is None:  # Defensive invariant for static and runtime checking.
            raise RuntimeError("valid date status without a parsed event date")
        record_fy = fiscal_year(record.event_date)
        if record_fy not in by_fy:
            valid_out_of_window_keys += 1
            date_status_by_tier[record.confidence]["valid_out_of_window"] += 1
            continue
        by_fy[record_fy][record.confidence] += 1
        date_status_by_tier[record.confidence]["in_window"] += 1

    rows: list[dict[str, int]] = []
    for fiscal_year_value, tiers in by_fy.items():
        high = tiers["high"]
        medium = tiers["medium"]
        low = tiers["low"]
        high_medium = high + medium
        total = high_medium + low
        row = {
            "fiscal_year": fiscal_year_value,
            "high_signal_name_keys": high,
            "medium_signal_name_keys": medium,
            "high_medium_signal_name_keys": high_medium,
            "low_sensitivity_signal_name_keys": low,
            "total_signal_name_keys": total,
        }
        if (
            row["high_medium_signal_name_keys"]
            != row["high_signal_name_keys"] + row["medium_signal_name_keys"]
        ):
            raise RuntimeError("high+medium reconciliation failed")
        if (
            row["total_signal_name_keys"]
            != row["high_medium_signal_name_keys"] + row["low_sensitivity_signal_name_keys"]
        ):
            raise RuntimeError("total tier reconciliation failed")
        rows.append(row)

    in_window_keys = sum(row["total_signal_name_keys"] for row in rows)
    missing_date_keys = date_status_counts["missing"]
    invalid_date_keys = date_status_counts["invalid"]
    if in_window_keys + valid_out_of_window_keys + missing_date_keys + invalid_date_keys != len(
        dataset.records
    ):
        raise RuntimeError("date-status reconciliation failed")
    if sum(distinct_tier_counts.values()) != len(dataset.records):
        raise RuntimeError("distinct tier reconciliation failed")
    for tier in CONFIDENCE_TIERS:
        if sum(date_status_by_tier[tier].values()) != distinct_tier_counts[tier]:
            raise RuntimeError(f"date-status reconciliation failed for {tier} tier")

    return CountResult(
        rows=tuple(rows),
        missing_date_keys=missing_date_keys,
        invalid_date_keys=invalid_date_keys,
        valid_out_of_window_keys=valid_out_of_window_keys,
        in_window_keys=in_window_keys,
        distinct_tier_counts={tier: distinct_tier_counts[tier] for tier in CONFIDENCE_TIERS},
        date_status_by_tier={
            tier: {category: date_status_by_tier[tier][category] for category in DATE_CATEGORIES}
            for tier in CONFIDENCE_TIERS
        },
    )


def render_csv(result: CountResult) -> str:
    """Render deterministic CSV bytes (after UTF-8 encoding)."""

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(result.rows)
    return output.getvalue()


def render_markdown(
    dataset: SignalDataset,
    result: CountResult,
    start_fy: int,
    end_fy: int,
) -> str:
    """Render a deterministic narrative with source and interpretation boundaries."""

    lines = [
        f"# SBIR M&A signal records by federal fiscal year, FY{start_fy}–FY{end_fy}",
        "",
        "## Source provenance",
        "",
        f"- Input: `{dataset.source_path}`",
        f"- SHA-256: `{dataset.source_sha256}`",
        f"- Bytes: {dataset.source_bytes:,}",
        f"- Input rows: {dataset.input_rows:,}",
        f"- Distinct normalized company-name keys: {len(dataset.records):,}",
        f"- Duplicate rows collapsed: {dataset.duplicate_rows:,}",
        "",
        "## Counts",
        "",
        "| Fiscal year | High | Medium | High + medium | Low sensitivity | Total |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result.rows:
        lines.append(
            "| "
            f"FY{row['fiscal_year']} | {row['high_signal_name_keys']:,} | "
            f"{row['medium_signal_name_keys']:,} | "
            f"{row['high_medium_signal_name_keys']:,} | "
            f"{row['low_sensitivity_signal_name_keys']:,} | "
            f"{row['total_signal_name_keys']:,} |"
        )

    lines.extend(
        [
            "",
            "## Date diagnostics",
            "",
            f"- Distinct keys with valid in-window dates: {result.in_window_keys:,}",
            f"- Distinct keys with missing dates: {result.missing_date_keys:,}",
            f"- Distinct keys with invalid dates: {result.invalid_date_keys:,}",
            "- Distinct keys with valid dates outside the selected window: "
            f"{result.valid_out_of_window_keys:,}",
            "",
            "The four date categories above reconcile to the distinct normalized-key count. "
            "Within every FY row, high + medium equals the combined column, and high + medium "
            "+ low sensitivity equals total.",
            "",
            "| Tier | In window | Valid out of window | Missing date | Invalid date | Distinct keys |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for tier in CONFIDENCE_TIERS:
        statuses = result.date_status_by_tier[tier]
        lines.append(
            f"| {tier.title()} | {statuses['in_window']:,} | "
            f"{statuses['valid_out_of_window']:,} | {statuses['missing']:,} | "
            f"{statuses['invalid']:,} | {result.distinct_tier_counts[tier]:,} |"
        )

    lines.extend(
        [
            "",
            "## Method",
            "",
            "Federal fiscal year is assigned from the top-level `event_date`: October 1 through "
            "December 31 map to the following FY; January 1 through September 30 map to the "
            "calendar year. The field is treated only as a signal-observation date, not a "
            "transaction or close date.",
            "",
            "Company keys use `company_name.strip().casefold()` only. The script does not normalize "
            "punctuation, legal suffixes, or internal whitespace. Repeated keys are collapsed only "
            "when their top-level date and exact `high`, `medium`, or `low` tier agree; conflicts "
            "fail validation.",
            "",
            "The high, medium, and low boundaries are upstream classifications. High + medium is "
            "shown as the primary descriptive subtotal. Low-confidence records are shown only as "
            "a sensitivity tier. No award denominator is used.",
            "",
            "## Source limitations",
            "",
            "- The artifact contains SBIR-only detected name records. Its rows are not verified "
            "firms, deals, acquisitions, or exits.",
            "- The top-level date is a hybrid selected by the tracked producer: the earliest valid "
            "Form D business-combination filing date versus the aggregate latest EFTS mention "
            "date. It may not align with the signal supporting the winning confidence tier.",
            "- SEC visibility is incomplete, including for private parties and evidence outside the "
            "upstream scan.",
            "- The script reports the tier values in this fingerprinted artifact. The final "
            "published tier counts are not reproducible from the tracked producer because the "
            "refinement/apply-back artifacts are absent; this report does not assert those totals.",
            "- These are descriptive signal-record counts. They are not incidence estimates, "
            "comparisons, or causal findings.",
            "",
        ]
    )
    return "\n".join(lines)


def _paths_alias(first: Path, second: Path) -> bool:
    if first.resolve(strict=False) == second.resolve(strict=False):
        return True
    if not first.exists() or not second.exists():
        return False
    try:
        return first.samefile(second)
    except OSError:
        return False


def _validate_report_paths(source: Path, csv_output: Path, markdown_output: Path) -> None:
    labeled_paths = (
        ("input", source),
        ("CSV output", csv_output),
        ("Markdown output", markdown_output),
    )
    for label, path in labeled_paths[1:]:
        if path.is_symlink():
            raise InputValidationError(f"{label} must not be a symbolic link: {path}")
        if path.exists() and not path.is_file():
            raise InputValidationError(f"{label} must be a regular file or not exist: {path}")

    for index, (first_label, first_path) in enumerate(labeled_paths):
        for second_label, second_path in labeled_paths[index + 1 :]:
            if _paths_alias(first_path, second_path):
                raise InputValidationError(
                    f"{first_label} and {second_label} paths must be distinct: {first_path}"
                )


def _stage_text(destination: Path, content: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        mode = S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
        temp_path.chmod(mode)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _backup_existing(destination: Path) -> Path | None:
    if not destination.exists():
        return None
    fd, raw_backup_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".backup",
    )
    os.close(fd)
    backup_path = Path(raw_backup_path)
    try:
        shutil.copy2(destination, backup_path)
    except BaseException:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


def _publish_staged_reports(staged: tuple[tuple[Path, Path], ...]) -> None:
    backups: dict[Path, Path | None] = {}
    try:
        for _, destination in staged:
            backups[destination] = _backup_existing(destination)
    except BaseException:
        for temp_path, _ in staged:
            temp_path.unlink(missing_ok=True)
        for backup_path in backups.values():
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
        raise

    replaced: list[Path] = []
    try:
        for temp_path, destination in staged:
            os.replace(temp_path, destination)
            replaced.append(destination)
    except OSError as publish_error:
        rollback_errors: list[str] = []
        for destination in reversed(replaced):
            backup_path = backups[destination]
            try:
                if backup_path is None:
                    destination.unlink(missing_ok=True)
                else:
                    os.replace(backup_path, destination)
                    backups[destination] = None
            except OSError as rollback_error:
                rollback_errors.append(f"{destination}: {rollback_error}")
        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise OSError(
                f"report publication failed and rollback was incomplete: {details}"
            ) from publish_error
        raise
    finally:
        for temp_path, _ in staged:
            temp_path.unlink(missing_ok=True)
        for backup_path in backups.values():
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)


def write_reports(
    dataset: SignalDataset,
    result: CountResult,
    csv_output: Path,
    markdown_output: Path,
    start_fy: int,
    end_fy: int,
) -> None:
    """Publish a distinct, internally consistent report pair."""

    _validate_report_paths(dataset.source_path, csv_output, markdown_output)
    csv_text = render_csv(result)
    markdown_text = render_markdown(dataset, result, start_fy, end_fy)
    staged_paths: list[tuple[Path, Path]] = []
    try:
        staged_paths.append((_stage_text(csv_output, csv_text), csv_output))
        staged_paths.append((_stage_text(markdown_output, markdown_text), markdown_output))
    except BaseException:
        for temp_path, _ in staged_paths:
            temp_path.unlink(missing_ok=True)
        raise
    _publish_staged_reports(tuple(staged_paths))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Count fingerprinted SBIR M&A signal records by federal fiscal year."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--start-fy", type=int, default=DEFAULT_START_FY)
    parser.add_argument("--end-fy", type=int, default=DEFAULT_END_FY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.start_fy > args.end_fy:
        print("error: --start-fy must not be after --end-fy", file=sys.stderr)
        return 2

    try:
        dataset = load_signal_dataset(args.input)
        result = build_counts(dataset, args.start_fy, args.end_fy)
        write_reports(
            dataset,
            result,
            args.csv_output,
            args.markdown_output,
            args.start_fy,
            args.end_fy,
        )
    except InputValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not write reports: {exc}", file=sys.stderr)
        return 1

    print(
        f"Wrote {args.csv_output} and {args.markdown_output} "
        f"from {len(dataset.records):,} distinct keys ({dataset.source_sha256})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
