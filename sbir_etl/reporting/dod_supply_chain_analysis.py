"""Initial descriptive analysis for the DoD SBIR award-concentration baseline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

_LATEST_PERIOD = "latest_complete_window"
_SCORE_BINS = (0.0, 54.999, 69.999, float("inf"))
_SCORE_LABELS = ("screening_50_54", "medium_55_69", "high_70_plus")


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _stable_rank(value: object, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def _money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    return f"${value / 1_000_000:.1f}M"


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _label(value: object) -> str:
    return str(value).replace("_", " ").title()


def _markdown_table(frame: pd.DataFrame, columns: list[tuple[str, str]]) -> str:
    headers = [heading for _, heading in columns]
    rows = [[str(row[column]) for column, _ in columns] for _, row in frame.iterrows()]
    separator = ["---"] * len(headers)
    return "\n".join(
        [
            f"| {' | '.join(headers)} |",
            f"| {' | '.join(separator)} |",
            *(f"| {' | '.join(row)} |" for row in rows),
        ]
    )


def _crosswalk_rollup(frame: pd.DataFrame, column: str, total_dollars: float) -> pd.DataFrame:
    exploded = frame[[column, "cet_area", "award_dollars"]].explode(column)
    exploded = exploded.loc[exploded[column].notna() & exploded[column].ne("")]
    rolled = (
        exploded.groupby(column, as_index=False)
        .agg(cet_areas=("cet_area", "nunique"), associated_dollars=("award_dollars", "sum"))
        .sort_values("associated_dollars", ascending=False)
    )
    rolled["target"] = rolled[column].map(_label)
    rolled["dollars"] = rolled["associated_dollars"].map(_money)
    rolled["portfolio_share"] = (rolled["associated_dollars"] / total_dollars).map(_percent)
    return rolled


def _round_robin_sample(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    count: int,
    seed: int,
) -> pd.DataFrame:
    if frame.empty or count <= 0:
        return frame.head(0).copy()
    ranked = frame.copy()
    ranked["_sample_rank"] = ranked["award_id"].map(lambda value: _stable_rank(value, seed))
    ranked = ranked.sort_values([*group_columns, "_sample_rank"])
    groups = [group for _, group in ranked.groupby(group_columns, dropna=False, sort=True)]
    selected: list[pd.Series] = []
    offset = 0
    while len(selected) < min(count, len(ranked)):
        added = False
        for group in groups:
            if offset < len(group):
                selected.append(group.iloc[offset])
                added = True
                if len(selected) == count:
                    break
        if not added:
            break
        offset += 1
    return pd.DataFrame(selected).drop(columns="_sample_rank").reset_index(drop=True)


def build_classifier_validation_sample(
    awards: pd.DataFrame,
    classifications: pd.DataFrame,
    *,
    classified_per_cet: int = 6,
    unclassified_count: int = 100,
    seed: int = 20260723,
) -> pd.DataFrame:
    """Build a deterministic review set spanning CETs, score bands, and negative cases."""
    _require_columns(
        awards,
        {"award_id", "title", "abstract", "topic_code", "branch", "phase", "award_year"},
        "awards",
    )
    _require_columns(
        classifications,
        {"award_id", "primary_cet", "primary_score", "evidence", "classifier_version"},
        "classifications",
    )
    award_columns = [
        "award_id",
        "title",
        "abstract",
        "topic_code",
        "branch",
        "phase",
        "award_year",
    ]
    joined = classifications.merge(
        awards[award_columns], on="award_id", how="inner", validate="one_to_one"
    )
    joined["score_band"] = pd.cut(
        joined["primary_score"],
        bins=_SCORE_BINS,
        labels=_SCORE_LABELS,
        include_lowest=True,
    ).astype("string")
    joined["sample_stratum"] = (
        "classified:" + joined["primary_cet"].astype(str) + ":" + joined["score_band"]
    )

    positive_parts: list[pd.DataFrame] = []
    for _, group in joined.groupby("primary_cet", sort=True):
        sampled = _round_robin_sample(
            group,
            group_columns=["score_band"],
            count=classified_per_cet,
            seed=seed,
        )
        sampled["classifier_decision"] = "classified"
        positive_parts.append(sampled)

    positive = pd.concat(positive_parts, ignore_index=True)
    negative_pool = awards.loc[
        ~awards["award_id"].isin(classifications["award_id"]), award_columns
    ].copy()
    negative_pool["primary_cet"] = ""
    negative_pool["primary_score"] = pd.NA
    negative_pool["score_band"] = "unclassified"
    negative_pool["evidence"] = "[]"
    negative_pool["classifier_version"] = classifications["classifier_version"].iloc[0]
    negative_pool["classifier_decision"] = "unclassified"
    negative_pool["sample_stratum"] = (
        "unclassified:"
        + negative_pool["branch"].fillna("unknown").astype(str)
        + ":"
        + negative_pool["phase"].fillna("unknown").astype(str)
    )
    negative = _round_robin_sample(
        negative_pool,
        group_columns=["branch", "phase"],
        count=unclassified_count,
        seed=seed,
    )
    sample = pd.concat([positive, negative], ignore_index=True)
    population_strata = pd.concat(
        [joined[["sample_stratum"]], negative_pool[["sample_stratum"]]],
        ignore_index=True,
    )["sample_stratum"].value_counts()
    sample_strata = sample["sample_stratum"].value_counts()
    sample["population_stratum_size"] = sample["sample_stratum"].map(population_strata)
    sample["sample_stratum_size"] = sample["sample_stratum"].map(sample_strata)
    sample["sample_weight"] = sample["population_stratum_size"] / sample["sample_stratum_size"]
    sample["abstract"] = sample["abstract"].fillna("").astype(str).str.slice(0, 1_500)
    sample["reviewer_primary_cet"] = ""
    sample["reviewer_secondary_cets"] = ""
    sample["reviewer_confidence"] = ""
    sample["reviewer_notes"] = ""
    sample["_review_rank"] = sample["award_id"].map(lambda value: _stable_rank(value, seed + 1))
    sample = sample.sort_values("_review_rank").reset_index(drop=True)
    sample.insert(0, "review_id", [f"CETVAL-{index:04d}" for index in range(1, len(sample) + 1)])
    output_columns = [
        "review_id",
        "award_id",
        "sample_stratum",
        "population_stratum_size",
        "sample_stratum_size",
        "sample_weight",
        "classifier_decision",
        "primary_cet",
        "primary_score",
        "score_band",
        "title",
        "topic_code",
        "abstract",
        "branch",
        "phase",
        "award_year",
        "evidence",
        "classifier_version",
        "reviewer_primary_cet",
        "reviewer_secondary_cets",
        "reviewer_confidence",
        "reviewer_notes",
    ]
    return sample[output_columns]


def split_classifier_validation_sample(
    sample: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate blinded review fields from predictions and sampling weights."""
    review_columns = [
        "review_id",
        "award_id",
        "title",
        "topic_code",
        "abstract",
        "branch",
        "phase",
        "award_year",
        "reviewer_primary_cet",
        "reviewer_secondary_cets",
        "reviewer_confidence",
        "reviewer_notes",
    ]
    key_columns = [
        "review_id",
        "award_id",
        "sample_stratum",
        "population_stratum_size",
        "sample_stratum_size",
        "sample_weight",
        "classifier_decision",
        "primary_cet",
        "primary_score",
        "score_band",
        "evidence",
        "classifier_version",
    ]
    _require_columns(sample, set(review_columns + key_columns), "validation sample")
    return sample[review_columns].copy(), sample[key_columns].copy()


def build_initial_analysis_markdown(
    facts: pd.DataFrame,
    metrics: pd.DataFrame,
    run_metadata: Mapping[str, object],
    classifier_manifest: Mapping[str, object],
) -> str:
    """Render a cautious, reproducible first analysis from baseline artifacts."""
    _require_columns(
        facts,
        {"award_id", "fiscal_year", "award_amount", "cet_area", "dod_component"},
        "facts",
    )
    _require_columns(
        metrics,
        {
            "period_type",
            "period_start_fy",
            "period_end_fy",
            "cet_area",
            "award_count",
            "distinct_firms",
            "award_dollars",
            "dollar_hhi",
            "top1_dollar_share",
            "top3_dollar_share",
            "state_dollar_hhi",
            "entrant_firm_share",
            "dod_cta14",
            "dod_sc8",
        },
        "metrics",
    )
    latest = metrics.loc[metrics["period_type"] == _LATEST_PERIOD].copy()
    if latest.empty:
        raise ValueError(f"metrics contains no {_LATEST_PERIOD!r} rows")

    start_fy = int(latest["period_start_fy"].min())
    end_fy = int(latest["period_end_fy"].max())
    latest_awards = int(latest["award_count"].sum())
    latest_dollars = float(latest["award_dollars"].sum())
    coverage = float(cast(Any, classifier_manifest["classification_coverage"]))

    funding = latest.nlargest(10, "award_dollars").copy()
    funding["area"] = funding["cet_area"].map(_label)
    funding["dollars"] = funding["award_dollars"].map(_money)
    funding["share"] = (funding["award_dollars"] / latest_dollars).map(_percent)
    funding["firms"] = funding["distinct_firms"].astype(int)
    funding["awards"] = funding["award_count"].astype(int)

    concentration = latest.nlargest(10, "dollar_hhi").copy()
    concentration["area"] = concentration["cet_area"].map(_label)
    concentration["hhi"] = concentration["dollar_hhi"].map(lambda value: f"{value:.3f}")
    concentration["top1"] = concentration["top1_dollar_share"].map(_percent)
    concentration["top3"] = concentration["top3_dollar_share"].map(_percent)
    concentration["firms"] = concentration["distinct_firms"].astype(int)
    concentration["awards"] = concentration["award_count"].astype(int)

    entrants = latest.nlargest(10, "entrant_firm_share").copy()
    entrants["area"] = entrants["cet_area"].map(_label)
    entrants["entrant_share"] = entrants["entrant_firm_share"].map(_percent)
    entrants["firms"] = entrants["distinct_firms"].astype(int)
    entrants["awards"] = entrants["award_count"].astype(int)

    geography = latest.nlargest(10, "state_dollar_hhi").copy()
    geography["area"] = geography["cet_area"].map(_label)
    geography["state_hhi"] = geography["state_dollar_hhi"].map(lambda value: f"{value:.3f}")
    geography["firms"] = geography["distinct_firms"].astype(int)
    geography["awards"] = geography["award_count"].astype(int)

    latest_facts = facts.loc[facts["fiscal_year"].between(start_fy, end_fy)]
    components = (
        latest_facts.groupby("dod_component", as_index=False, dropna=False)
        .agg(award_count=("award_id", "nunique"), award_dollars=("award_amount", "sum"))
        .sort_values("award_dollars", ascending=False)
    )
    components["component"] = components["dod_component"].fillna("Unknown").map(_label)
    components["dollars"] = components["award_dollars"].map(_money)
    components["share"] = (components["award_dollars"] / latest_dollars).map(_percent)
    components["awards"] = components["award_count"].astype(int)

    dod_cta14 = _crosswalk_rollup(latest, "dod_cta14", latest_dollars)
    dod_sc8 = _crosswalk_rollup(latest, "dod_sc8", latest_dollars)

    annual = (
        facts.groupby("fiscal_year", as_index=False)
        .agg(award_count=("award_id", "nunique"), award_dollars=("award_amount", "sum"))
        .sort_values("fiscal_year")
    )
    annual["fy"] = annual["fiscal_year"].astype(int)
    annual["dollars"] = annual["award_dollars"].map(_money)
    annual["awards"] = annual["award_count"].astype(int)

    top_funding = funding.iloc[0]
    top_concentration = concentration.iloc[0]
    classifier_version = ", ".join(
        map(str, cast(list[object], run_metadata["classifier_versions"]))
    )
    taxonomy_version = ", ".join(map(str, cast(list[object], run_metadata["taxonomy_versions"])))
    source_hash = classifier_manifest.get("source_sha256", "not recorded")

    return f"""# Initial DoD SBIR industrial-base concentration analysis

**Status:** exploratory descriptive baseline
**As of:** {run_metadata["as_of_date"]}
**Retained fiscal years:** FY{run_metadata["min_fiscal_year"]}–FY{end_fy}
**Headline window:** FY{start_fy}–FY{end_fy}

## Executive readout

The classified FY{start_fy}–FY{end_fy} portfolio contains **{latest_awards:,} awards**
and **{_money(latest_dollars)}** across 21 CET areas. {_label(top_funding["area"])}
is the largest classified area by dollars at **{top_funding["dollars"]}**
({top_funding["share"]} of the window).

The highest observed dollar concentration is in **{top_concentration["area"]}**
(HHI {top_concentration["hhi"]}, {top_concentration["firms"]} observed firms,
top-firm share {top_concentration["top1"]}). This is a screening signal, not evidence
of a sole-source physical dependency. Small portfolios can rank highly because a few
awards account for a large share of their dollars.

The current classifier assigned a CET to **{coverage:.1%}** of the {int(cast(Any, classifier_manifest["award_rows"])):,}
candidate DoD awards. Consequently, comparisons describe the rule-classified
subset. They should not be generalized to the unclassified half until validation quantifies
false-negative and area-specific coverage bias.

## Portfolio by DoD component, FY{start_fy}–FY{end_fy}

{_markdown_table(components, [("component", "DoD component"), ("dollars", "Award dollars"), ("share", "Portfolio share"), ("awards", "Classified awards")])}

## Largest CET portfolios, FY{start_fy}–FY{end_fy}

{_markdown_table(funding, [("area", "CET area"), ("dollars", "Award dollars"), ("share", "Portfolio share"), ("awards", "Awards"), ("firms", "Observed firms")])}

## Highest dollar concentration, FY{start_fy}–FY{end_fy}

{_markdown_table(concentration, [("area", "CET area"), ("hhi", "Dollar HHI"), ("top1", "Top firm"), ("top3", "Top 3 firms"), ("awards", "Awards"), ("firms", "Observed firms")])}

HHI is calculated from observed award dollars by resolved or normalized firm identity.
It measures concentration inside this SBIR award corpus; it does not measure subcontractor,
bill-of-material, import, mineral, or production dependency.

## Highest geographic concentration, FY{start_fy}–FY{end_fy}

{_markdown_table(geography, [("area", "CET area"), ("state_hhi", "State dollar HHI"), ("awards", "Awards"), ("firms", "Observed firms")])}

State HHI is a screen for geographic narrowness in award dollars. It does not establish
where production occurs, and headquarters or award addresses may differ from performance
locations.

## Highest new-entrant shares, FY{start_fy}–FY{end_fy}

{_markdown_table(entrants, [("area", "CET area"), ("entrant_share", "Entrant firm share"), ("firms", "Observed firms"), ("awards", "Awards")])}

An entrant is a firm's first observed DoD SBIR/STTR award in the retained FY2012+
corpus. The measure is left-censored: firms active before FY2012 can be misidentified
as entrants when their first retained award occurs later.

## Defense-policy crosswalk overlays

### DoD Critical Technology Areas

{_markdown_table(dod_cta14, [("target", "DoD-14 area"), ("cet_areas", "Mapped CET areas"), ("dollars", "Associated dollars"), ("portfolio_share", "Associated share")])}

### 2022 defense-critical supply-chain focus areas and enablers

{_markdown_table(dod_sc8, [("target", "Repository target"), ("cet_areas", "Mapped CET areas"), ("dollars", "Associated dollars"), ("portfolio_share", "Associated share")])}

These are many-to-many contextual overlays. Dollar amounts are repeated when a CET maps to
multiple targets, so rows are **not additive** and are not funding allocations. Mapping
strengths include direct, partial, and enabling relationships. `DOD-SC-8-2022` is a
repository label derived from the 2022 report, not an official NDIS taxonomy.

## Classified portfolio by fiscal year

{_markdown_table(annual, [("fy", "Fiscal year"), ("awards", "Classified awards"), ("dollars", "Award dollars")])}

Changes over time can reflect classification coverage, award-record timing, and incomplete
identity resolution as well as true portfolio change. The table is descriptive and is not
an estimate of causal program effects.

## What this baseline can support

- CET portfolio composition and time trends in the classified subset.
- Award-dollar and award-count concentration, top-firm shares, and observed base thickness.
- Geographic concentration screens and first-observed entrant participation.
- Exploratory rollups through the cited DoD-14 and defense supply-chain crosswalk.

## What it cannot yet support

- Phase II-to-III transition rates or transition-thinness; transition status is
  **{run_metadata["transition_status"]}**.
- Physical or sub-tier supply-chain dependency, production capacity, material dependency,
  or import exposure.
- Official DoD policy mappings. `DOD-SC-8-2022` is a repository label for an analyst
  crosswalk, not an official NDIS taxonomy.
- Causal, predictive, FOCI, beneficial-ownership, M&A, UCC, patent-citation, or subaward claims.
- A definitive assertion that an observed dominant awardee is a sole-source supplier.

## Data quality and reproducibility

- Source: public SBIR.gov bulk award CSV.
- Source SHA-256: `{source_hash}`.
- Taxonomy: `{taxonomy_version}`.
- Classifier: `{classifier_version}`.
- Classified award facts: {int(cast(Any, run_metadata["award_fact_rows"])):,}.
- Classification coverage: {coverage:.3%}.
- Minimum retained primary-CET score: {float(cast(Any, run_metadata["minimum_primary_cet_score"])):.1f}.
- Identity policy: {run_metadata["identity_policy"]}.
- Crosswalk version: {run_metadata["defense_crosswalk_version"]}.

## Required validation before decision-grade use

Review `data/reference/cet_classifier_validation_sample_2026q3.csv`, which intentionally
hides the classifier decision. Use canonical identifiers from `config/cet/taxonomy.yaml`;
use `none` when no CET is supported and record genuinely multi-area awards rather than
forcing a single label. After review, join on `review_id` to the separately generated
`cet_classifier_validation_key_2026q3.csv`. Classified records estimate precision by CET
and score band; unclassified records estimate false-negative prevalence and coverage bias.
The key includes inverse sampling weights for estimates over the differently sized strata.

The validation result should decide the next step:

1. Tune rules if errors are concentrated in a small number of terms or score bands.
2. Train a supervised multi-label classifier if errors are semantic, cross-area, or pervasive.
3. Retain abstention for records without sufficient textual evidence.
"""


def write_initial_analysis(
    report: str,
    blinded_sample: pd.DataFrame,
    validation_key: pd.DataFrame,
    *,
    report_path: Path,
    validation_path: Path,
    validation_key_path: Path,
) -> None:
    """Write the report, blinded review set, and held-out classifier key."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_key_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    blinded_sample.to_csv(validation_path, index=False)
    validation_key.to_csv(validation_key_path, index=False)


def read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from disk."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


__all__ = [
    "build_classifier_validation_sample",
    "build_initial_analysis_markdown",
    "read_json",
    "split_classifier_validation_sample",
    "write_initial_analysis",
]
