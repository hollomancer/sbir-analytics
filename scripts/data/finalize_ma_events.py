#!/usr/bin/env python3
"""Produce the capital-events builder input from the refined M&A events.

Epistemic tier: exploratory.

``sbir_etl.enrichers.ma_discovery.press`` used to write
``data/enriched_sbir_ma_events.jsonl``. It did two jobs: it polled live RSS
feeds for press mentions, and it produced the file the capital-events builder
reads. The first job was removed -- a live poll cannot sit in a pipelines-tier
path, and every one of its 18 matches was a false positive from unanchored
substring matching. The second job is still needed, so it lives here.

This step is exploratory. It copies each event through unchanged and stamps a
git description plus the input file's SHA-256 and row count. It declares no
cut, so it is not a pipelines producer -- the hash lets a later run be traced
to the input that produced it, nothing more.

**Running this changes the builder's population.** The historical file was
produced in April 2026 by a chain that reproduces from no commit; the file this
writes comes from the current detect and refine steps. The difference is not
press enrichment -- press contributed two metadata fields and no rows. It is
the accumulated corrections to the events themselves. Diff the two before
promoting the output, and record what moved.

Usage::

    python scripts/data/finalize_ma_events.py \
        --events data/sbir_ma_events.jsonl \
        --output data/enriched_sbir_ma_events.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


EPISTEMIC_TIER = "exploratory"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str | None:
    """Hex digest of a file's bytes, or None if it does not exist."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_version() -> str:
    """Git description of this checkout, with a dirty flag. Never raises."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return f"{sha}{'-dirty' if dirty else ''}"


def finalize(
    events: list[dict[str, Any]],
    *,
    code_version: str,
    input_sha256: str | None,
    input_row_count: int,
) -> list[dict[str, Any]]:
    """Stamp provenance on each event. Row content is otherwise untouched."""
    out: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        row["finalized_by"] = "finalize_ma_events"
        row["finalized_code_version"] = code_version
        row["finalized_input_sha256"] = input_sha256
        row["finalized_input_row_count"] = input_row_count
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/enriched_sbir_ma_events.jsonl"))
    args = parser.parse_args(argv)

    if not args.events.is_file():
        raise SystemExit(f"events file not found: {args.events}")

    events = [
        json.loads(line)
        for line in args.events.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    finalized = finalize(
        events,
        code_version=_code_version(),
        input_sha256=_sha256(args.events),
        input_row_count=len(events),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in finalized:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    tiers = Counter(e.get("confidence") for e in finalized)
    keep = tiers["high"] + tiers["medium"]
    print(f"Finalized {len(finalized):,} events -> {args.output}")
    print(f"  high {tiers['high']:,}   medium {tiers['medium']:,}   low {tiers['low']:,}")
    print(f"  {keep:,} pass the builder's high-or-medium filter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
