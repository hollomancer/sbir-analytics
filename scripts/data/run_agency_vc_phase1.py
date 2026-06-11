#!/usr/bin/env python3
"""Run the SBIR vs. published-baseline (Phase 1) comparison against
SBIR.gov bulk award data, bypassing the Dagster materialization chain.

Usage:
    python scripts/data/run_agency_vc_phase1.py
    python scripts/data/run_agency_vc_phase1.py --agency NSF
    python scripts/data/run_agency_vc_phase1.py --awards-csv /tmp/sbir_awards_full.csv
    python scripts/data/run_agency_vc_phase1.py --headline-vintage 2010-2014

Defaults mirror PR #286's pipeline conventions: the awards CSV defaults to
``/tmp/sbir_awards_full.csv`` (downloaded on first run from SBIR.gov), and
the M&A events JSONL defaults to ``data/sbir_ma_events.jsonl`` (produced by
``scripts/data/detect_sbir_ma_events.py``).

Outputs three artifacts to ``data/processed/agency_vc/<agency_lower>/``:
- agency_cohort_outcomes.parquet
- agency_vs_published_baselines.md
- agency_baseline_comparison.json

This script reproduces the Dagster asset's logic in-process so we can
materialize Phase 1 against real data without wiring the full
``enriched_sbir_awards`` upstream chain. Survival, patent, and transition
metrics will render as ``available=False`` (those signals require
enrichment outputs that aren't read here); graduation and M&A exit rates
will populate.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_analytics.assets.agency_vc.baselines import (
    DEFAULT_REGISTRY_PATH,
    PublishedBaselineRegistry,
)
from sbir_analytics.assets.agency_vc.cohort import AgencyCohortBuilder
from sbir_analytics.assets.agency_vc.outcomes import OutcomeMetricsCalculator
from sbir_analytics.assets.agency_vc.reconcile import ReconciliationNarrative
from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL


DEFAULT_AWARDS_CSV = Path("/tmp/sbir_awards_full.csv")
DEFAULT_MA_EVENTS = Path("data/sbir_ma_events.jsonl")
DEFAULT_HEADLINE_VINTAGE = "2015-2019"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.exceptions.HTTPError)
    ),
    reraise=True,
)
def _download_to(url: str, dest: Path) -> None:
    print(f"Downloading SBIR.gov bulk awards: {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as resp:
        if resp.status_code in (429, 500, 502, 503, 504):
            resp.raise_for_status()
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
    print(f"Downloaded {dest.stat().st_size / 1e6:.1f} MB")


def _ensure_awards_csv(path: Path) -> Path:
    if path.exists():
        return path
    _download_to(SBIR_AWARDS_CSV_URL, path)
    return path


def _load_ma_event_companies(path: Path) -> set[str] | None:
    if not path.exists():
        return None
    keys: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = event.get("company_name")
            if name and str(name).strip():
                keys.add(f"name:{str(name).strip().lower()}")
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agency",
        default="NSF",
        metavar="CODE",
        help="Funding agency code to filter to (default: NSF)",
    )
    parser.add_argument("--awards-csv", type=Path, default=DEFAULT_AWARDS_CSV)
    parser.add_argument("--ma-events", type=Path, default=DEFAULT_MA_EVENTS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--headline-vintage", default=DEFAULT_HEADLINE_VINTAGE)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to data/processed/agency_vc/<agency_lower>/"
            " so different agencies don't clobber each other."
        ),
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Fail rather than download the awards CSV if missing.",
    )
    args = parser.parse_args()

    agency_code: str = args.agency.strip().upper()
    output_dir: Path = args.output_dir or (Path("data/processed/agency_vc") / agency_code.lower())

    if args.skip_download and not args.awards_csv.exists():
        print(f"awards CSV not found at {args.awards_csv}", file=sys.stderr)
        return 2
    awards_path = _ensure_awards_csv(args.awards_csv)

    print(f"Loading awards from {awards_path}")
    awards = pd.read_csv(awards_path, dtype=str, low_memory=False, encoding_errors="replace")
    print(f"Total rows: {len(awards):,}")

    builder = AgencyCohortBuilder(agency_code=agency_code)
    cohort = builder.build(awards)
    print(f"{agency_code} cohort rows: {len(cohort):,}")
    counts = AgencyCohortBuilder.stratum_counts(cohort)
    print(f"Strata: {len(counts)}")
    print(counts.to_string(index=False))

    ma_companies = _load_ma_event_companies(args.ma_events)
    if ma_companies is None:
        print(f"M&A events not found at {args.ma_events} — metric will render as unavailable")
    else:
        print(f"Loaded M&A event company set: n={len(ma_companies):,}")

    calc = OutcomeMetricsCalculator(ma_event_companies=ma_companies)
    outcomes = calc.compute(cohort)

    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "agency_cohort_outcomes.parquet"
    md_path = output_dir / "agency_vs_published_baselines.md"
    json_path = output_dir / "agency_baseline_comparison.json"
    outcomes.to_parquet(parquet_path, index=False)

    registry = PublishedBaselineRegistry.load(args.registry)
    narrative = ReconciliationNarrative(registry=registry)
    records = narrative.reconcile(outcomes, headline_vintage=args.headline_vintage)
    md_path.write_text(
        narrative.to_markdown(records, headline_vintage=args.headline_vintage),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps([r.to_json() for r in records], indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\nWrote {parquet_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
