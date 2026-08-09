#!/usr/bin/env python3
"""Run the SBIR vs. published-baseline (Phase 1) comparison against
SBIR.gov bulk award data, bypassing the Dagster materialization chain.

Usage:
    python scripts/archive/data/run_agency_private_capital_phase1.py
    python scripts/archive/data/run_agency_private_capital_phase1.py --agency NSF
    python scripts/archive/data/run_agency_private_capital_phase1.py --awards-csv /tmp/sbir_awards_full.csv
    python scripts/archive/data/run_agency_private_capital_phase1.py --headline-vintage 2010-2014

Defaults mirror PR #286's pipeline conventions: the awards CSV defaults to
``/tmp/sbir_awards_full.csv`` (downloaded on first run from SBIR.gov), and
the M&A events JSONL defaults to ``data/sbir_ma_events.jsonl`` (produced by
``scripts/archive/data/detect_sbir_ma_events.py``).

Outputs four artifacts to ``data/processed/agency_private_capital/<agency_lower>/``:
- agency_cohort_outcomes.parquet
- agency_vs_published_baselines.md
- agency_baseline_comparison.json
- run_manifest.json

This script reproduces the Dagster asset's logic in-process so we can
materialize Phase 1 against real data without wiring the full
``enriched_sbir_awards`` upstream chain. Survival, patent, and transition
metrics will render as ``available=False`` (those signals require
enrichment outputs that aren't read here). Graduation will populate; M&A
exit rates populate only when the optional events file is present. The report
and manifest explicitly retain the package's exploratory, non-citable
epistemic label.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_analytics.assets.agency_private_capital import EPISTEMIC_TIER
from sbir_analytics.assets.agency_private_capital.baselines import (
    DEFAULT_REGISTRY_PATH,
    PublishedBaselineRegistry,
)
from sbir_analytics.assets.agency_private_capital.cohort import AgencyCohortBuilder
from sbir_analytics.assets.agency_private_capital.outcomes import OutcomeMetricsCalculator
from sbir_analytics.assets.agency_private_capital.reconcile import ReconciliationNarrative
from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL


DEFAULT_AWARDS_CSV = Path("/tmp/sbir_awards_full.csv")
DEFAULT_MA_EVENTS = Path("data/sbir_ma_events.jsonl")
DEFAULT_HEADLINE_VINTAGE = "2015-2019"
DEFAULT_GRADUATION_HORIZON_YEARS = 5

_METRICS = (
    "phase_i_to_ii_graduation",
    "phase_ii_to_federal_contract_transition",
    "five_year_survival_proxy",
    "ma_exit_rate",
    "patent_rate",
)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty_line_count(path: Path) -> int:
    with path.open(encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def _file_provenance(
    path: Path,
    *,
    source: str,
    row_count: int | None,
    schema: dict[str, object],
) -> dict[str, object]:
    """Describe an input without persisting a machine-specific absolute path."""

    available = path.is_file()
    return {
        "available": available,
        "path": path.name,
        "row_count": row_count if available else None,
        "schema": schema,
        "sha256": _sha256_file(path) if available else None,
        "size_bytes": path.stat().st_size if available else None,
        "source": source,
    }


def _metric_availability(
    outcomes: pd.DataFrame,
    *,
    ma_events_loaded: bool,
) -> dict[str, dict[str, object]]:
    unavailable_reasons = {
        "phase_i_to_ii_graduation": "No qualifying Phase I cohort rows were available.",
        "phase_ii_to_federal_contract_transition": (
            "Transition-score enrichment is not read by this standalone runner."
        ),
        "five_year_survival_proxy": (
            "Federal recipient/vendor activity is not read by this standalone runner."
        ),
        "ma_exit_rate": (
            "The M&A events input was not found."
            if not ma_events_loaded
            else "No qualifying cohort rows were available."
        ),
        "patent_rate": "PATLINK is deferred to Phase 2 and is not read by this runner.",
    }
    availability: dict[str, dict[str, object]] = {}
    for metric in _METRICS:
        rows = outcomes[outcomes["metric"] == metric] if not outcomes.empty else outcomes
        available = bool(not rows.empty and rows["available"].fillna(False).any())
        availability[metric] = {
            "available": available,
            "reason": None if available else unavailable_reasons[metric],
        }
    return availability


def _annotate_report(
    markdown: str,
    *,
    metric_availability: dict[str, dict[str, object]],
    graduation_horizon_years: int,
) -> str:
    unavailable = [
        f"`{metric}` ({details['reason']})"
        for metric, details in metric_availability.items()
        if not details["available"]
    ]
    unavailable_text = "; ".join(unavailable) if unavailable else "None."
    title, separator, remainder = markdown.partition("\n")
    banner = (
        "> **Exploratory / non-citable.** This standalone analysis has not earned "
        "publication-quality validation.\n>\n"
        f"> **Phase I -> Phase II graduation horizon:** {graduation_horizon_years} years.\n>\n"
        f"> **Unavailable metrics in this run:** {unavailable_text}"
    )
    if not separator:
        return f"{title}\n\n{banner}\n"
    return f"{title}\n\n{banner}\n{remainder}"


def _build_run_manifest(
    *,
    awards_path: Path,
    awards_row_count: int,
    awards_columns: list[str],
    ma_events_path: Path,
    ma_events_row_count: int | None,
    registry_path: Path,
    registry_row_count: int,
    parameters: dict[str, object],
    metric_availability: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Build deterministic provenance for a standalone exploratory run."""

    return {
        "citable": False,
        "epistemic_tier": EPISTEMIC_TIER,
        "inputs": {
            "awards_csv": _file_provenance(
                awards_path,
                source="sbir_gov_bulk_awards",
                row_count=awards_row_count,
                schema={"columns": awards_columns, "format": "csv"},
            ),
            "ma_events_jsonl": _file_provenance(
                ma_events_path,
                source="sbir_ma_events",
                row_count=ma_events_row_count,
                schema={"company_key": "company_name", "format": "jsonl"},
            ),
            "published_baselines_yaml": _file_provenance(
                registry_path,
                source="published_baseline_registry",
                row_count=registry_row_count,
                schema={"collection": "baselines", "format": "yaml"},
            ),
        },
        "limitations": [
            "Standalone runner omits transition-score and federal-activity enrichment inputs.",
            "Patent rate is deferred to Phase 2.",
            "Results are exploratory and non-citable.",
        ],
        "metric_availability": metric_availability,
        "parameters": parameters,
        "schema_version": 1,
    }


def _write_run_manifest(output_dir: Path, manifest: dict[str, object]) -> Path:
    path = output_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


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
        "--graduation-horizon-years",
        type=int,
        default=DEFAULT_GRADUATION_HORIZON_YEARS,
        help=(
            "Maximum inclusive years from Phase I to a qualifying Phase II "
            f"(default: {DEFAULT_GRADUATION_HORIZON_YEARS})"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to data/processed/agency_private_capital/<agency_lower>/"
            " so different agencies don't clobber each other."
        ),
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Fail rather than download the awards CSV if missing.",
    )
    args = parser.parse_args()
    if args.graduation_horizon_years < 0:
        parser.error("--graduation-horizon-years must be non-negative")

    agency_code: str = args.agency.strip().upper()
    output_dir: Path = args.output_dir or (
        Path("data/processed/agency_private_capital") / agency_code.lower()
    )

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
    ma_event_row_count = _nonempty_line_count(args.ma_events) if args.ma_events.is_file() else None
    if ma_companies is None:
        print(f"M&A events not found at {args.ma_events} — metric will render as unavailable")
    else:
        print(f"Loaded M&A event company set: n={len(ma_companies):,}")

    calc = OutcomeMetricsCalculator(
        graduation_horizon_years=args.graduation_horizon_years,
        ma_event_companies=ma_companies,
    )
    outcomes = calc.compute(cohort)
    metric_availability = _metric_availability(
        outcomes,
        ma_events_loaded=ma_companies is not None,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "agency_cohort_outcomes.parquet"
    md_path = output_dir / "agency_vs_published_baselines.md"
    json_path = output_dir / "agency_baseline_comparison.json"
    outcomes.to_parquet(parquet_path, index=False)

    registry = PublishedBaselineRegistry.load(args.registry)
    narrative = ReconciliationNarrative(registry=registry)
    records = narrative.reconcile(outcomes, headline_vintage=args.headline_vintage)
    md_text = _annotate_report(
        narrative.to_markdown(
            records,
            headline_vintage=args.headline_vintage,
            agency_code=args.agency,
        ),
        metric_availability=metric_availability,
        graduation_horizon_years=args.graduation_horizon_years,
    )
    md_path.write_text(
        md_text,
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps([r.to_json() for r in records], indent=2, default=str),
        encoding="utf-8",
    )
    manifest = _build_run_manifest(
        awards_path=awards_path,
        awards_row_count=len(awards),
        awards_columns=[str(column) for column in awards.columns],
        ma_events_path=args.ma_events,
        ma_events_row_count=ma_event_row_count,
        registry_path=args.registry,
        registry_row_count=len(registry),
        parameters={
            "agency_code": agency_code,
            "graduation_horizon_years": args.graduation_horizon_years,
            "headline_vintage": args.headline_vintage,
            "survival_horizon_years": calc.survival_horizon_years,
            "transition_score_threshold": calc.transition_score_threshold,
            "vintage_bucket_size": builder.vintage_size,
        },
        metric_availability=metric_availability,
    )
    manifest_path = _write_run_manifest(output_dir, manifest)

    unavailable_metrics = [
        metric for metric, details in metric_availability.items() if not details["available"]
    ]
    print("\nEpistemic status: exploratory / non-citable")
    print(f"Graduation horizon: {args.graduation_horizon_years} years")
    print(f"Unavailable metrics: {', '.join(unavailable_metrics) or 'none'}")
    print(f"\nWrote {parquet_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
