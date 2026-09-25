#!/usr/bin/env python3
"""Offline migration for stored Form D match-confidence tiers.

The migration reads only signal values already present in
``form_d_details.jsonl``. It performs no SEC or other network requests. Output
is deterministic, and publication uses an atomic same-directory replace so a
parse, validation, serialization, or replace failure leaves an existing target
untouched.

This remains exploratory: changing a tier is a contestable identity decision.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_VERSION,
    FORM_D_TIER_RULE_VERSIONS,
    assign_form_d_tier,
    describe_form_d_signal_scope,
)

EPISTEMIC_TIER = "exploratory"


class FormDRescoreError(ValueError):
    """A stored Form D record cannot be migrated without guessing."""


def _optional_score(value: object, *, field: str, line_number: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormDRescoreError(
            f"line {line_number}: match_confidence.{field} must be a number or null"
        )
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise FormDRescoreError(
            f"line {line_number}: match_confidence.{field} must be between 0 and 1"
        )
    return score


def rescore_record(
    record: dict[str, Any],
    *,
    rule_version: str = FORM_D_TIER_RULE_VERSION,
    line_number: int = 1,
) -> dict[str, Any]:
    """Return a copy with its tier recomputed from stored signal values."""

    confidence = record.get("match_confidence")
    if not isinstance(confidence, dict):
        raise FormDRescoreError(f"line {line_number}: match_confidence must be an object")

    migrated = copy.deepcopy(record)
    migrated_confidence = migrated["match_confidence"]
    migrated_confidence["tier"] = assign_form_d_tier(
        person_score=_optional_score(
            confidence.get("person_score"), field="person_score", line_number=line_number
        ),
        address_score=_optional_score(
            confidence.get("address_score"), field="address_score", line_number=line_number
        ),
        state_score=_optional_score(
            confidence.get("state_score"), field="state_score", line_number=line_number
        ),
        rule_version=rule_version,
    )
    migrated_confidence["rule_version"] = rule_version

    offerings = migrated.get("offerings")
    if offerings is None:
        offerings = []
    if not isinstance(offerings, list) or not all(isinstance(item, dict) for item in offerings):
        raise FormDRescoreError(f"line {line_number}: offerings must be a list of objects")
    migrated["match_confidence_scope"] = describe_form_d_signal_scope(offerings)
    return migrated


def rescore_jsonl(
    input_path: Path,
    output_path: Path,
    *,
    rule_version: str = FORM_D_TIER_RULE_VERSION,
) -> dict[str, object]:
    """Rescore JSONL records and atomically publish the complete output."""

    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if rule_version not in FORM_D_TIER_RULE_VERSIONS:
        supported = ", ".join(sorted(FORM_D_TIER_RULE_VERSIONS))
        raise FormDRescoreError(
            f"unsupported Form D tier rule {rule_version!r}; expected one of {supported}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    rule_versions_before: Counter[str] = Counter()
    multi_filing_records = 0
    multi_cik_records = 0
    record_count = 0
    temporary_path: Path | None = None

    try:
        with (
            input_path.open(encoding="utf-8") as source,
            tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as target,
        ):
            temporary_path = Path(target.name)
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise FormDRescoreError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
                if not isinstance(record, dict):
                    raise FormDRescoreError(f"line {line_number}: record must be a JSON object")

                confidence = record.get("match_confidence")
                if not isinstance(confidence, dict):
                    raise FormDRescoreError(
                        f"line {line_number}: match_confidence must be an object"
                    )
                before[str(confidence.get("tier") or "missing")] += 1
                rule_versions_before[str(confidence.get("rule_version") or "unversioned")] += 1

                migrated = rescore_record(
                    record,
                    rule_version=rule_version,
                    line_number=line_number,
                )
                after[str(migrated["match_confidence"]["tier"])] += 1
                scope = migrated["match_confidence_scope"]
                multi_filing_records += int(bool(scope["signals_may_span_filings"]))
                multi_cik_records += int(bool(scope["signals_may_span_ciks"]))
                record_count += 1
                target.write(json.dumps(migrated, sort_keys=True, separators=(",", ":")))
                target.write("\n")
            target.flush()
            os.fsync(target.fileno())

        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return {
        "record_count": record_count,
        "target_rule_version": rule_version,
        "tiers_before": dict(sorted(before.items())),
        "tiers_after": dict(sorted(after.items())),
        "rule_versions_before": dict(sorted(rule_versions_before.items())),
        "multi_filing_records": multi_filing_records,
        "multi_cik_records": multi_cik_records,
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path. Defaults to an atomic in-place migration of --input.",
    )
    parser.add_argument(
        "--rule-version",
        choices=sorted(FORM_D_TIER_RULE_VERSIONS),
        default=FORM_D_TIER_RULE_VERSION,
    )
    args = parser.parse_args()
    summary = rescore_jsonl(
        args.input,
        args.output or args.input,
        rule_version=args.rule_version,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
