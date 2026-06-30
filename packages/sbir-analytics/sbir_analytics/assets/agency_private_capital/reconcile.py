"""Reconciliation narrative.

For each (agency-cohort outcome metric, published baseline) pair, emit a
structured record summarizing the comparison plus a one-line markdown row.
Mirrors the follow-on-multiplier reconciliation pattern: the gate-statement
("X reports A%, the cohort is B%, difference attributable to C") matters
more than the match.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd

from .baselines import BaselineKind, PublishedBaseline, PublishedBaselineRegistry


# Plausible-cause attribution per (metric, baseline) pair. Kept as a
# narrative table rather than a heuristic so the report reads as a
# deliberate human-curated statement.
_ATTRIBUTION: dict[tuple[str, str], str] = {
    ("phase_i_to_ii_graduation", "nvca_seed_to_series_a"): (
        "SBIR Phase I -> Phase II is gated on technical merit and a separate "
        "Phase II proposal; NVCA seed -> Series A is gated on lawyer access, "
        "metric traction, and lead-investor narrative. The two selection "
        "filters differ structurally; magnitudes are descriptive, not causal."
    ),
    ("five_year_survival_proxy", "bls_bed_5yr_survival"): (
        "SBIR Phase II awardees pre-selected on technical merit; BLS BED "
        "covers all new establishments including retail / service. The "
        "survival proxy is federal-dataset presence, which under-counts "
        "firms that survive but exit federal markets."
    ),
    ("phase_ii_to_federal_contract_transition", "lerner_growth_effect"): (
        "Lerner [L10] reports a growth effect vs. matched non-awardees, not "
        "a federal-transition rate. Treat as effect-size context only; "
        "the cohort transition rate is reported separately and should not "
        "be differenced against this number."
    ),
    ("phase_ii_to_federal_contract_transition", "howell_followon_vc"): (
        "Howell [L11] estimates a follow-on-VC probability via DOE RDD, not "
        "a federal-contract transition. Effect-size context only; the "
        "cohort rate is reported separately. (Magnitude was estimated for "
        "DOE awardees — comparability is closest for a DOE cohort and "
        "degrades for agencies with different award mechanics.)"
    ),
    ("phase_i_to_ii_graduation", "itif_seed_fund_framing"): (
        "ITIF [L21] is the qualitative framing this spec quantifies. No "
        "numeric baseline; entry retained for citation completeness."
    ),
}

# Per-pair selection-bias caveat. Required by Phase 1 Requirement 4.
_CAVEAT: dict[tuple[str, str], str] = {
    ("phase_i_to_ii_graduation", "nvca_seed_to_series_a"): (
        "SBIR awardees pre-selected on technical merit and proposal quality; "
        "VC-financed firms self-select on lawyer access and growth narrative."
    ),
    ("five_year_survival_proxy", "bls_bed_5yr_survival"): (
        "The survival proxy uses federal-dataset presence; BLS BED uses "
        "establishment payroll continuation. Definition gap > sampling gap."
    ),
    ("phase_ii_to_federal_contract_transition", "lerner_growth_effect"): (
        "Lerner's comparison group is matched non-awardees, not VC-financed "
        "firms. Effect direction transfers; magnitude does not."
    ),
    ("phase_ii_to_federal_contract_transition", "howell_followon_vc"): (
        "Howell's identification is DOE-specific RDD. Magnitude transfers "
        "best to a DOE cohort; for other agencies treat as framing only."
    ),
    ("phase_i_to_ii_graduation", "itif_seed_fund_framing"): (
        "Framing claim, not a numeric baseline; no caveat applies."
    ),
}


@dataclass(frozen=True)
class ReconciliationRecord:
    """One (agency-cohort metric x baseline) comparison row."""

    cohort_metric: str
    baseline_id: str
    baseline_label: str
    baseline_kind: str
    baseline_point_estimate: float | None
    baseline_effect_description: str | None
    baseline_as_of: str
    baseline_citation: str
    baseline_citation_url: str
    cohort_vintage_bucket: str | None
    cohort_phase_label: str | None
    cohort_numerator: int | None
    cohort_denominator: int | None
    cohort_rate: float | None
    cohort_ci_low: float | None
    cohort_ci_high: float | None
    cohort_available: bool
    delta: float | None
    attribution: str
    caveat: str

    def to_json(self) -> dict:
        d = asdict(self)
        for k in (
            "cohort_rate",
            "cohort_ci_low",
            "cohort_ci_high",
            "delta",
            "baseline_point_estimate",
        ):
            v = d.get(k)
            if isinstance(v, float) and math.isnan(v):
                d[k] = None
        return d


@dataclass(frozen=True)
class ReconciliationNarrative:
    """Build comparison records and a markdown report from outcomes + registry."""

    registry: PublishedBaselineRegistry

    def reconcile(
        self,
        outcomes: pd.DataFrame,
        *,
        headline_vintage: str | None = None,
    ) -> list[ReconciliationRecord]:
        """Pair each baseline with the matching cohort stratum row.

        ``headline_vintage`` selects which vintage stratum to feature when a
        metric has multiple strata. When omitted, the largest-denominator
        stratum is used (most precise comparison).
        """

        records: list[ReconciliationRecord] = []
        for baseline in self.registry:
            metric_rows = outcomes[outcomes["metric"] == baseline.cohort_metric]
            if metric_rows.empty:
                records.append(self._empty_record(baseline))
                continue
            row = self._select_row(metric_rows, headline_vintage)
            records.append(self._build_record(baseline, row))
        return records

    def to_markdown(
        self,
        records: list[ReconciliationRecord],
        *,
        headline_vintage: str | None,
        agency_code: str = "NSF",
    ) -> str:
        lines: list[str] = []
        lines.append(
            f"# {agency_code} SBIR vs. Published Private-Capital / Small-Business Baselines"
        )
        lines.append("")
        lines.append("Descriptive comparison only. Reconciliation matters more than the match.")
        lines.append("")
        if headline_vintage:
            lines.append(f"Headline vintage: **{headline_vintage}**")
        lines.append("")
        lines.append("## Comparison table")
        lines.append("")
        lines.append(
            f"| Metric | Baseline | Baseline value | {agency_code} cohort "
            f"| {agency_code} rate (95% CI) | n |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for r in records:
            lines.append(_format_row(r))
        lines.append("")
        lines.append("## Gate statements")
        lines.append("")
        for r in records:
            lines.append(_gate_statement(r, agency_code=agency_code))
            lines.append("")
        lines.append("## Citations")
        lines.append("")
        for r in records:
            lines.append(
                f"- **{r.baseline_label}** ({r.baseline_as_of}). "
                f"{r.baseline_citation} {r.baseline_citation_url}".rstrip()
            )
        lines.append("")
        return "\n".join(lines)

    def _select_row(self, metric_rows: pd.DataFrame, headline_vintage: str | None) -> pd.Series:
        if headline_vintage is not None:
            match = metric_rows[metric_rows["vintage_bucket"] == headline_vintage]
            if not match.empty:
                return match.iloc[0]
        return metric_rows.sort_values("denominator", ascending=False).iloc[0]

    def _build_record(self, baseline: PublishedBaseline, row: pd.Series) -> ReconciliationRecord:
        cohort_rate = _nan_to_none(row.get("rate"))
        delta: float | None = None
        if (
            baseline.kind is BaselineKind.RATE
            and baseline.point_estimate is not None
            and cohort_rate is not None
        ):
            delta = cohort_rate - baseline.point_estimate
        key = (baseline.cohort_metric, baseline.id)
        return ReconciliationRecord(
            cohort_metric=baseline.cohort_metric,
            baseline_id=baseline.id,
            baseline_label=baseline.label,
            baseline_kind=str(baseline.kind),
            baseline_point_estimate=baseline.point_estimate,
            baseline_effect_description=baseline.effect_description,
            baseline_as_of=baseline.as_of,
            baseline_citation=baseline.citation,
            baseline_citation_url=baseline.citation_url,
            cohort_vintage_bucket=_str_or_none(row.get("vintage_bucket")),
            cohort_phase_label=_str_or_none(row.get("phase_label")),
            cohort_numerator=_int_or_none(row.get("numerator")),
            cohort_denominator=_int_or_none(row.get("denominator")),
            cohort_rate=cohort_rate,
            cohort_ci_low=_nan_to_none(row.get("ci_low")),
            cohort_ci_high=_nan_to_none(row.get("ci_high")),
            cohort_available=bool(row.get("available", False)),
            delta=delta,
            attribution=_ATTRIBUTION.get(key, "No attribution recorded for this pair."),
            caveat=_CAVEAT.get(key, "No caveat recorded for this pair."),
        )

    def _empty_record(self, baseline: PublishedBaseline) -> ReconciliationRecord:
        key = (baseline.cohort_metric, baseline.id)
        return ReconciliationRecord(
            cohort_metric=baseline.cohort_metric,
            baseline_id=baseline.id,
            baseline_label=baseline.label,
            baseline_kind=str(baseline.kind),
            baseline_point_estimate=baseline.point_estimate,
            baseline_effect_description=baseline.effect_description,
            baseline_as_of=baseline.as_of,
            baseline_citation=baseline.citation,
            baseline_citation_url=baseline.citation_url,
            cohort_vintage_bucket=None,
            cohort_phase_label=None,
            cohort_numerator=None,
            cohort_denominator=None,
            cohort_rate=None,
            cohort_ci_low=None,
            cohort_ci_high=None,
            cohort_available=False,
            delta=None,
            attribution=_ATTRIBUTION.get(key, "No attribution recorded for this pair."),
            caveat=_CAVEAT.get(key, "No caveat recorded for this pair."),
        )


def _format_row(r: ReconciliationRecord) -> str:
    if r.baseline_point_estimate is not None:
        baseline_val = f"{r.baseline_point_estimate:.0%}"
    elif r.baseline_effect_description:
        baseline_val = r.baseline_effect_description
    else:
        baseline_val = "(framing only)"
    cohort = (
        f"{r.cohort_vintage_bucket} / Phase {r.cohort_phase_label}"
        if r.cohort_vintage_bucket and r.cohort_phase_label
        else "n/a"
    )
    if r.cohort_available and r.cohort_rate is not None and r.cohort_ci_low is not None:
        rate_str = f"{r.cohort_rate:.1%} ({r.cohort_ci_low:.1%}-{r.cohort_ci_high:.1%})"
    elif r.cohort_denominator and r.cohort_denominator > 0:
        rate_str = "data unavailable"
    else:
        rate_str = "no NSF rows"
    n = r.cohort_denominator if r.cohort_denominator is not None else 0
    return (
        f"| {r.cohort_metric} | {r.baseline_label} | {baseline_val} | {cohort} | {rate_str} | {n} |"
    )


def _gate_statement(r: ReconciliationRecord, agency_code: str = "NSF") -> str:
    label = r.baseline_label
    cohort = (
        f"vintage {r.cohort_vintage_bucket} Phase {r.cohort_phase_label}"
        if r.cohort_vintage_bucket and r.cohort_phase_label
        else f"(no {agency_code} stratum)"
    )
    n = r.cohort_denominator or 0
    if r.baseline_kind == "rate" and r.baseline_point_estimate is not None:
        baseline_part = f"{label} reports {r.baseline_point_estimate:.0%}"
        if r.cohort_available and r.cohort_rate is not None:
            cohort_part = f"{agency_code} is {r.cohort_rate:.1%} on {cohort} (n={n})"
        else:
            cohort_part = f"{agency_code} rate unavailable on {cohort} (n={n})"
    elif r.baseline_kind == "effect_size":
        baseline_part = f"{label}: {r.baseline_effect_description or '(no description)'}"
        if r.cohort_available and r.cohort_rate is not None:
            cohort_part = f"{agency_code} reports {r.cohort_rate:.1%} on {cohort} (n={n})"
        else:
            cohort_part = f"{agency_code} rate unavailable on {cohort} (n={n})"
    else:
        baseline_part = f"{label} (framing claim)"
        cohort_part = f"{agency_code} cohort row: {cohort} (n={n})"
    return (
        f"- **{r.cohort_metric}**: {baseline_part}. {cohort_part}. "
        f"Difference is attributable to: {r.attribution} Caveat: {r.caveat}"
    )


def _str_or_none(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v)
    return s if s else None


def _int_or_none(v: object) -> int | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        return int(v)  # type: ignore[arg-type, call-overload]
    except (TypeError, ValueError):
        return None


def _nan_to_none(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f
