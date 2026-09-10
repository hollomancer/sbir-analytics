#!/usr/bin/env python3
"""Apply complete directional-refinement records to the M&A event artifact.

Epistemic tier: exploratory.

This is the deterministic bridge between ``refine_ma_medium_tier.py`` and the
final event file consumed by downstream analyses. It fails closed when a
direction-sensitive event lacks exactly one complete refinement record.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.archive.data.refine_ma_medium_tier import (
    confidence_after_directional_refinement,
    needs_directional_refinement,
)


EPISTEMIC_TIER = "exploratory"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load object-only JSONL, failing on malformed or blank records."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"blank JSONL record at {path}:{line_number}")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSON at {path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            rows.append(row)
    return rows


def _index_unique(rows: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        name = str(row.get("company_name") or "").strip()
        if not name:
            raise ValueError(f"{label} row is missing company_name")
        if name in indexed:
            duplicates.add(name)
        indexed[name] = row
    if duplicates:
        names = ", ".join(sorted(duplicates)[:5])
        raise ValueError(f"duplicate {label} company_name values: {names}")
    return indexed


def apply_refinements(
    events: list[dict[str, Any]],
    refinements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Return one final row per event using the frozen direction-aware rules."""
    events_by_name = _index_unique(events, label="event")
    refinements_by_name = _index_unique(refinements, label="refinement")
    required = {name for name, row in events_by_name.items() if needs_directional_refinement(row)}
    supplied = set(refinements_by_name)
    missing = required - supplied
    unexpected = supplied - required
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing_count={len(missing)} examples={sorted(missing)[:5]}")
        if unexpected:
            details.append(f"unexpected_count={len(unexpected)} examples={sorted(unexpected)[:5]}")
        raise ValueError("refinement coverage mismatch: " + "; ".join(details))

    output: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    for event in events:
        row = dict(event)
        name = str(row["company_name"]).strip()
        refinement = refinements_by_name.get(name)
        if refinement is None:
            output.append(row)
            stats[f"unchanged_{row.get('confidence')}"] += 1
            continue

        direction = str(refinement.get("direction") or "").strip()
        context_complete = refinement.get("context_classification_complete")
        if not isinstance(context_complete, bool):
            raise ValueError(f"refinement for {name!r} lacks typed context completeness")
        raw_reasons = refinement.get("context_incomplete_reasons")
        reasons = [] if raw_reasons is None else raw_reasons
        if not isinstance(reasons, list) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError(f"refinement for {name!r} has invalid incomplete reasons")
        if context_complete and reasons:
            raise ValueError(f"complete refinement for {name!r} carries incomplete reasons")
        if not context_complete and not reasons:
            raise ValueError(f"incomplete refinement for {name!r} lacks a reason")
        if context_complete == (direction == "context_incomplete"):
            raise ValueError(
                f"refinement for {name!r} has inconsistent direction and context completeness"
            )

        previous_confidence = str(row.get("confidence") or "")
        row["direction"] = direction
        row["context_classification_complete"] = context_complete
        if reasons:
            row["context_incomplete_reasons"] = sorted(set(reasons))
        else:
            row.pop("context_incomplete_reasons", None)
        row["confidence"] = confidence_after_directional_refinement(
            row,
            direction=direction,
            context_complete=context_complete,
        )
        row["directional_refinement_applied"] = True
        stats[f"{previous_confidence}_to_{row['confidence']}"] += 1
        stats[f"direction_{direction}"] += 1
        output.append(row)

    if len(output) != len(events) or len({row["company_name"] for row in output}) != len(output):
        raise RuntimeError("final event output lost its one-row-per-company grain")
    return output, stats


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically replace *path* with deterministic JSONL content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument(
        "--refinements", type=Path, default=Path("data/sbir_ma_medium_refined.jsonl")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    events = load_jsonl(args.events)
    refinements = load_jsonl(args.refinements)
    output, stats = apply_refinements(events, refinements)
    write_jsonl_atomic(args.output, output)

    print(f"Applied {len(refinements):,} refinements to {len(events):,} events")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]:,}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
