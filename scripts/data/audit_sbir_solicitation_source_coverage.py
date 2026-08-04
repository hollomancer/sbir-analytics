#!/usr/bin/env python3
"""Build a manifested Phase 0 coverage report from a captured SBIR.gov response."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from sbir_etl.extractors.solicitation import (
    SBIR_GOV_SOLICITATION_DOCS_URL,
    SBIR_GOV_SOLICITATION_SOURCE,
    audit_solicitation_schema,
    normalize_solicitations,
)


MANIFEST_SCHEMA_VERSION = "sbir-gov-solicitation-coverage-v1"
MINIMUM_SAMPLE_SIZE = 50


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load a direct list or a ``results``/``data`` API response wrapper."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("results") or payload.get("data") or []
    else:
        raise ValueError("input must be a JSON list or an object containing results/data")

    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ValueError("input response records must all be JSON objects")
    return records


def build_coverage_manifest(
    records: list[dict[str, Any]],
    *,
    input_path: Path,
    analysis_date: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Build the machine-checkable sample manifest and adapter decision."""
    coverage = audit_solicitation_schema(records)
    tables = normalize_solicitations(records, source_url=source_url)

    version_ids = tables.solicitation_versions["solicitation_version_id"]
    topic_ids = tables.topics["topic_id"]
    unknown_fields = coverage["unknown_fields"]
    malformed = coverage["malformed_nested_values"]

    blockers: list[str] = []
    if len(records) < MINIMUM_SAMPLE_SIZE:
        blockers.append(
            f"sample contains {len(records)} records; Phase 0 requires at least "
            f"{MINIMUM_SAMPLE_SIZE}"
        )
    if coverage["retention_rate"] != 1.0:
        blockers.append("not all documented source fields have a normalized retention path")
    unobserved_fields = [
        f"{grain}.{field}"
        for grain, fields in coverage["field_presence"].items()
        for field, counts in fields.items()
        if counts["present_records"] == 0
    ]
    if unobserved_fields:
        blockers.append(
            "sample does not exercise documented fields: " + ", ".join(unobserved_fields)
        )
    if any(unknown_fields.values()):
        blockers.append("unmapped source fields require schema-drift review")
    if any(malformed.values()):
        blockers.append("one or more nested topic/subtopic values have an unsupported shape")
    if version_ids.duplicated().any():
        blockers.append("normalized solicitation-version identifiers are not unique")
    if topic_ids.duplicated().any():
        blockers.append("normalized topic/subtopic identifiers are not unique")

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "analysis_date": analysis_date,
        "source": {
            "system": SBIR_GOV_SOLICITATION_SOURCE,
            "documentation_url": SBIR_GOV_SOLICITATION_DOCS_URL,
            "response_url": source_url,
        },
        "input": {
            "path": str(input_path),
            "sha256": _sha256(input_path),
            "record_count": len(records),
        },
        "coverage": coverage,
        "quality": {
            "minimum_sample_size": MINIMUM_SAMPLE_SIZE,
            "solicitation_version_ids_unique": not version_ids.duplicated().any(),
            "topic_ids_unique": not topic_ids.duplicated().any(),
            "records_with_agency_url": int(
                tables.solicitation_versions["solicitation_agency_url"].notna().sum()
            ),
            "topics_with_source_link": int(tables.topics["sbir_topic_link"].notna().sum()),
        },
        "adapter_decision": {
            "adapter": "sbir_gov_solicitations",
            "status": "go" if not blockers else "no_go",
            "blockers": blockers,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Captured API response JSON")
    parser.add_argument("--output", type=Path, required=True, help="Coverage manifest JSON")
    parser.add_argument("--source-url", help="Exact response URL used for the capture")
    parser.add_argument(
        "--analysis-date",
        default=datetime.now(UTC).date().isoformat(),
        help="Pinned analysis date (YYYY-MM-DD)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(args.input)
    manifest = build_coverage_manifest(
        records,
        input_path=args.input,
        analysis_date=args.analysis_date,
        source_url=args.source_url,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["adapter_decision"], sort_keys=True))
    return 0 if manifest["adapter_decision"]["status"] == "go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
