"""Dagster asset wiring for the NSF SBIR vs. published-baseline comparison.

The asset reads NSF SBIR awards (filter applied via ``NSFCohortBuilder``),
optionally consumes upstream transition scores, M&A events, PATLINK output,
and a federal-activity company set, then emits three artifacts:

- ``data/processed/nsf_vc/nsf_cohort_outcomes.parquet`` — long-format
  per-stratum metric table.
- ``data/processed/nsf_vc/nsf_vs_published_baselines.md`` — human-readable
  reconciliation report.
- ``data/processed/nsf_vc/nsf_baseline_comparison.json`` — structured
  comparison records.

Per project convention: ``from __future__ import annotations`` is NOT used
here because Dagster's runtime context type-validation requires concrete
type names.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from .baselines import DEFAULT_REGISTRY_PATH, PublishedBaselineRegistry
from .cohort import NSFCohortBuilder
from .outcomes import OutcomeMetricsCalculator
from .reconcile import ReconciliationNarrative


DEFAULT_OUTPUT_DIR = Path("data/processed/nsf_vc")
DEFAULT_MA_EVENTS_PATH = Path("data/sbir_ma_events.jsonl")
DEFAULT_HEADLINE_VINTAGE = "2015-2019"


@asset(
    name="nsf_vc_published_baseline_comparison",
    group_name="nsf_vc",
    compute_kind="pandas",
    description=(
        "NSF SBIR cohort outcomes (Phase I->II graduation, transitions, survival, "
        "patents, M&A) compared to published seed-VC and small-business baselines. "
        "Descriptive comparison + reconciliation narrative; not a causal estimate."
    ),
)
def nsf_vc_published_baseline_comparison(
    context: AssetExecutionContext,
    enriched_sbir_awards: pd.DataFrame,
    transformed_transition_scores: pd.DataFrame,
) -> Output[str]:
    output_dir = DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "nsf_cohort_outcomes.parquet"
    md_path = output_dir / "nsf_vs_published_baselines.md"
    json_path = output_dir / "nsf_baseline_comparison.json"

    cohort = NSFCohortBuilder().build(enriched_sbir_awards)
    counts = NSFCohortBuilder.stratum_counts(cohort)
    context.log.info(
        "NSF cohort built",
        extra={
            "rows": int(len(cohort)),
            "strata": int(len(counts)),
            "stratum_counts": counts.to_dict("records"),
        },
    )

    ma_event_companies = _load_ma_event_companies(DEFAULT_MA_EVENTS_PATH)
    if ma_event_companies is not None:
        context.log.info("Loaded M&A event company set", extra={"n": len(ma_event_companies)})

    calc = OutcomeMetricsCalculator(
        transition_scores=(
            transformed_transition_scores
            if transformed_transition_scores is not None and not transformed_transition_scores.empty
            else None
        ),
        ma_event_companies=ma_event_companies,
    )
    outcomes = calc.compute(cohort)
    outcomes.to_parquet(parquet_path, index=False)

    registry = PublishedBaselineRegistry.load(DEFAULT_REGISTRY_PATH)
    narrative = ReconciliationNarrative(registry=registry)
    records = narrative.reconcile(outcomes, headline_vintage=DEFAULT_HEADLINE_VINTAGE)
    md_text = narrative.to_markdown(records, headline_vintage=DEFAULT_HEADLINE_VINTAGE)
    md_path.write_text(md_text, encoding="utf-8")
    json_path.write_text(
        json.dumps([r.to_json() for r in records], indent=2, default=str),
        encoding="utf-8",
    )

    metadata: dict[str, Any] = {
        "outcomes_path": str(parquet_path),
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "cohort_rows": int(len(cohort)),
        "stratum_counts": MetadataValue.json(counts.to_dict("records")),
        "headline_vintage": DEFAULT_HEADLINE_VINTAGE,
        "baseline_count": int(len(registry)),
        "ma_events_loaded": ma_event_companies is not None,
    }
    return Output(str(md_path), metadata=metadata)


def _load_ma_event_companies(path: Path) -> set[str] | None:
    """Read PR #286's M&A events JSONL and return a set of company keys.

    Each event has a ``company_name`` field; we normalize to ``name:<lower>``
    so it joins against the cohort's ``_company_key`` (which falls back to a
    name-based key when UEI/DUNS are absent). Returns ``None`` if the file
    is missing so the calculator can render the metric as unavailable.
    """

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
