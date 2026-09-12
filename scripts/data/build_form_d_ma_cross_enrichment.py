#!/usr/bin/env python3
"""Build provenance-aware Form D/M&A-candidate relationship and crosswalk artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from sbir_etl.capital_events.cross_enrichment import (
    CANDIDATE_STATUS,
    DEFAULT_LINK_WINDOW_DAYS,
    FORM_D_AMOUNT_SOLD_MEASURE,
    enrich_form_d_and_ma,
    read_jsonl,
    relationship_source_classes,
    write_jsonl,
)


def file_metadata(path: Path) -> dict[str, object]:
    """Return deterministic file provenance metadata."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form-d", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument("--ma", type=Path, default=Path("data/enriched_sbir_ma_events.jsonl"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/reports/form_d_ma_cross_enrichment")
    )
    parser.add_argument("--link-window-days", type=int, default=DEFAULT_LINK_WINDOW_DAYS)
    args = parser.parse_args(argv)

    missing = [path for path in (args.form_d, args.ma) if not path.is_file()]
    if missing:
        parser.error("missing input(s): " + ", ".join(map(str, missing)))

    enriched, relationships, crosswalk = enrich_form_d_and_ma(
        read_jsonl(args.form_d),
        read_jsonl(args.ma),
        link_window_days=args.link_window_days,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "enriched_ma_events": args.output_dir / "enriched_ma_events.jsonl",
        "corporate_relationships": args.output_dir / "corporate_relationships.jsonl",
        "form_d_ma_crosswalk": args.output_dir / "form_d_ma_crosswalk.jsonl",
    }
    counts = {
        "enriched_ma_events": write_jsonl(output_paths["enriched_ma_events"], enriched),
        "corporate_relationships": write_jsonl(
            output_paths["corporate_relationships"], relationships
        ),
        "form_d_ma_crosswalk": write_jsonl(output_paths["form_d_ma_crosswalk"], crosswalk),
    }
    source_classes = Counter(
        source for row in relationships for source in relationship_source_classes(row)
    )
    manifest = {
        "epistemic_tier": "exploratory",
        "citable": False,
        "candidate_status": CANDIDATE_STATUS,
        "interpretation": {
            "legal_event_validated": False,
            "deal_terms_captured": False,
            "enterprise_value_observed": False,
            "form_d_amount_sold_measure": FORM_D_AMOUNT_SOLD_MEASURE,
            "form_d_amount_sold_is_deal_value": False,
        },
        "link_window_days": args.link_window_days,
        "inputs": {"form_d": file_metadata(args.form_d), "ma": file_metadata(args.ma)},
        "outputs": {
            name: {**file_metadata(path), "rows": counts[name]}
            for name, path in output_paths.items()
        },
        "counts": counts,
        "relationship_source_classes": dict(sorted(source_classes.items())),
        "same_source_only_relationships": sum(
            bool(row.get("same_source_only")) for row in relationships
        ),
        "relationships_with_non_form_d_evidence": sum(
            bool(row.get("independent_of_form_d")) for row in relationships
        ),
        "multi_source_relationships": sum(
            len(row.get("evidence_sources", [])) >= 2 for row in relationships
        ),
        "auto_merged_aliases": 0,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
