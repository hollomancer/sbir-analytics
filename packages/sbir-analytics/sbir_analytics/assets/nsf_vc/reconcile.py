"""Reconciliation narrative.

For each (NSF outcome metric, published baseline) pair, emit a structured
record summarizing the comparison plus a one-line markdown row. Mirrors
the leverage-ratio reconciliation pattern: the gate-statement ("X reports
A%, NSF is B%, difference attributable to C") matters more than the
match.
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
        "NSF Phase I -> Phase II is gated on technical merit and a separate "
        "Phase II proposal; NVCA seed -> Series A is gated on lawyer access, "
        "metric traction, and lead-investor narrative. The two selection "
        "filters differ structurally; magnitudes are descriptive, not causal."
    ),
    ("five_year_survival_proxy", "bls_bed_5yr_survival"): (
        "NSF Phase II awardees pre-selected on technical merit; BLS BED "
        "covers all new establishments including retail / service. NSF "
        "survival proxy is federal-dataset presence, which under-counts "
        "firms that survive but exit federal markets."
    ),
    ("phase_ii_to_federal_contract_transition", "lerner_growth_effect"): (
        "Lerner [L10] reports a growth effect vs. matched non-awardees, not "
        "a federal-transition rate. Treat as effect-size context only; "
        "the NSF transition rate is reported separately and should not be "
        "differenced against this number."
    ),
    ("phase_ii_to_federal_contract_transition", "howell_followon_vc"): (
        "Howell [L11] estimates a follow-on-VC probability via DOE RDD, not "
        "an NSF federal-contract transition. Effect-size context only; "
        "NSF rate is reported separately."
    ),
    ("phase_i_to_ii_graduation", "itif_seed_fund_framing"): (
        "ITIF [L21] is the qualitative framing this spec quantifies. No "
        "numeric baseline; entry retained for citation completeness."
    ),
}

# Per-pair selection-bias caveat. Required by Phase 1 Requirement 4.
_CAVEAT: dict[tuple[str, str], str] = {
    ("phase_i_to_ii_graduation", "nvca_seed_to_series_a"): (
        "NSF awardees pre-selected on technical merit and proposal quality; "
        "VC-financed firms self-select on lawyer access and growth narrative."
    ),
    ("five_year_survival_proxy", "bls_bed_5yr_survival"): (
        "NSF survival proxy uses federal-dataset presence; BLS BED uses "
        "establishment payroll continuation. Definition gap > sampling gap."
    ),
    ("phase_ii_to_federal_contract_transition", "lerner_growth_effect"): (
        "Lerner's comparison group is matched non-awardees, not VC-financed "
        "firms. Effect direction transfers; magnitude does not."
    ),
    ("phase_ii_to_federal_contract_transition", "howell_followon_vc"): (
        "Howell's identification is DOE-specific RDD. Magnitude not "
        "comparable to NSF; framing only."
    ),
    ("phase_i_to_ii_graduation", "itif_seed_fund_framing"): (
        "Framing claim, not a numeric baseline; no caveat applies."
    ),
}


@dataclass(frozen=True)
class ReconciliationRecord:
    """One (NSF metric x baseline) comparison row."""

    nsf_metric: str
    baseline_id: str
    baseline_label: str
    baseline_kind: str
    baseline_point_estimate: float | None
    baseline_effect_description: str | None
    baseline_as_of: str
    baseline_citation: str
    baseline_citation_url: str
    nsf_vintage_bucket: str | None
    nsf_phase_label: str | None
    nsf_numerator: int | None
    nsf_denominator: int | None
    nsf_rate: float | None
    nsf_ci_low: float | None
    nsf_ci_high: float | None
    nsf_available: bool
    delta: float | None
    attribution: str
    caveat: str

    def to_json(self) -> dict:
        d = asdict(self)
        for k in ("nsf_rate", "nsf_ci_low", "nsf_ci_high", "delta", "baseline_point_estimate"):
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
        """Pair each baseline with the matching NSF stratum row.

        ``headline_vintage`` selects which vintage stratum to feature when a
        metric has multiple strata. When omitted, the largest-denominator
        stratum is used (most precise comparison).
        """

        records: list[ReconciliationRecord] = []
        for baseline in self.registry:
            metric_rows = outcomes[outcomes["metric"] == baseline.nsf_metric]
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
    ) -> str:
        lines: list[str] = []
        lines.append("# NSF SBIR vs. Published VC / Small-Business Baselines")
        lines.append("")
        lines.append("Descriptive comparison only. Reconciliation matters more than the match.")
        lines.append("")
        if headline_vintage:
            lines.append(f"Headline vintage: **{headline_vintage}**")
        lines.append("")
        lines.append("## Comparison table")
        lines.append("")
        lines.append("| Metric | Baseline | Baseline value | NSF cohort | NSF rate (95% CI) | n |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for r in records:
            lines.append(_format_row(r))
        lines.append("")
        lines.append("## Gate statements")
        lines.append("")
        for r in records:
            lines.append(_gate_statement(r))
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
        nsf_rate = _nan_to_none(row.get("rate"))
        delta: float | None = None
        if (
            baseline.kind is BaselineKind.RATE
            and baseline.point_estimate is not None
            and nsf_rate is not None
        ):
            delta = nsf_rate - baseline.point_estimate
        key = (baseline.nsf_metric, baseline.id)
        return ReconciliationRecord(
            nsf_metric=baseline.nsf_metric,
            baseline_id=baseline.id,
            baseline_label=baseline.label,
            baseline_kind=str(baseline.kind),
            baseline_point_estimate=baseline.point_estimate,
            baseline_effect_description=baseline.effect_description,
            baseline_as_of=baseline.as_of,
            baseline_citation=baseline.citation,
            baseline_citation_url=baseline.citation_url,
            nsf_vintage_bucket=_str_or_none(row.get("vintage_bucket")),
            nsf_phase_label=_str_or_none(row.get("phase_label")),
            nsf_numerator=_int_or_none(row.get("numerator")),
            nsf_denominator=_int_or_none(row.get("denominator")),
            nsf_rate=nsf_rate,
            nsf_ci_low=_nan_to_none(row.get("ci_low")),
            nsf_ci_high=_nan_to_none(row.get("ci_high")),
            nsf_available=bool(row.get("available", False)),
            delta=delta,
            attribution=_ATTRIBUTION.get(key, "No attribution recorded for this pair."),
            caveat=_CAVEAT.get(key, "No caveat recorded for this pair."),
        )

    def _empty_record(self, baseline: PublishedBaseline) -> ReconciliationRecord:
        key = (baseline.nsf_metric, baseline.id)
        return ReconciliationRecord(
            nsf_metric=baseline.nsf_metric,
            baseline_id=baseline.id,
            baseline_label=baseline.label,
            baseline_kind=str(baseline.kind),
            baseline_point_estimate=baseline.point_estimate,
            baseline_effect_description=baseline.effect_description,
            baseline_as_of=baseline.as_of,
            baseline_citation=baseline.citation,
            baseline_citation_url=baseline.citation_url,
            nsf_vintage_bucket=None,
            nsf_phase_label=None,
            nsf_numerator=None,
            nsf_denominator=None,
            nsf_rate=None,
            nsf_ci_low=None,
            nsf_ci_high=None,
            nsf_available=False,
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
        f"{r.nsf_vintage_bucket} / Phase {r.nsf_phase_label}"
        if r.nsf_vintage_bucket and r.nsf_phase_label
        else "n/a"
    )
    if r.nsf_available and r.nsf_rate is not None and r.nsf_ci_low is not None:
        rate_str = f"{r.nsf_rate:.1%} ({r.nsf_ci_low:.1%}-{r.nsf_ci_high:.1%})"
    elif r.nsf_denominator and r.nsf_denominator > 0:
        rate_str = "data unavailable"
    else:
        rate_str = "no NSF rows"
    n = r.nsf_denominator if r.nsf_denominator is not None else 0
    return f"| {r.nsf_metric} | {r.baseline_label} | {baseline_val} | {cohort} | {rate_str} | {n} |"


def _gate_statement(r: ReconciliationRecord) -> str:
    label = r.baseline_label
    cohort = (
        f"vintage {r.nsf_vintage_bucket} Phase {r.nsf_phase_label}"
        if r.nsf_vintage_bucket and r.nsf_phase_label
        else "(no NSF stratum)"
    )
    n = r.nsf_denominator or 0
    if r.baseline_kind == "rate" and r.baseline_point_estimate is not None:
        baseline_part = f"{label} reports {r.baseline_point_estimate:.0%}"
        if r.nsf_available and r.nsf_rate is not None:
            nsf_part = f"NSF is {r.nsf_rate:.1%} on {cohort} (n={n})"
        else:
            nsf_part = f"NSF rate unavailable on {cohort} (n={n})"
    elif r.baseline_kind == "effect_size":
        baseline_part = f"{label}: {r.baseline_effect_description or '(no description)'}"
        if r.nsf_available and r.nsf_rate is not None:
            nsf_part = f"NSF reports {r.nsf_rate:.1%} on {cohort} (n={n})"
        else:
            nsf_part = f"NSF rate unavailable on {cohort} (n={n})"
    else:
        baseline_part = f"{label} (framing claim)"
        nsf_part = f"NSF cohort row: {cohort} (n={n})"
    return (
        f"- **{r.nsf_metric}**: {baseline_part}. {nsf_part}. "
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
        return int(v)
    except (TypeError, ValueError):
        return None


def _nan_to_none(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f
