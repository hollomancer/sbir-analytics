#!/usr/bin/env python3
"""Build an exploratory headcount-at-award readout from SBIR.gov awards.

Epistemic tier: exploratory / non-citable.

This script:
1. Materializes the canonical SBIR.gov source parquet from the checked-in
   ``data/raw/sbir/award_data.csv`` snapshot.
2. Profiles the employee-count field coverage in the actual materialized schema.
3. Rolls awards to firms using the repository's existing canonical merge policy
   (UEI primary, DUNS fallback, normalized-name last).
4. Writes CSV artifacts, a Markdown readout, and a two-panel histogram figure.
"""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sbir_analytics.assets.phase_transition.sbir_gov_source import (
    materialize_sbir_gov_history,
    verify_sbir_gov_materialization,
)
from sbir_etl.identity import (
    CanonicalMergePolicy,
    CompanyNameProfile,
    build_canonical_company_map,
    normalize_company_name,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_SBIR_PATH = REPO_ROOT / "data/raw/sbir/award_data.csv"
MATERIALIZED_SBIR_PATH = REPO_ROOT / "data/processed/phase_iii_census_sbir_awards.parquet"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/reports/headcount_at_award"
FIGURE_NAME = "headcount_at_award_distribution.svg"
MARKDOWN_NAME = "headcount_at_award_readout.md"
SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
ANALYSIS_DATE = "2026-08-20"

NONPROFIT_NAME_TOKENS: tuple[str, ...] = (
    "UNIVERS",
    "COLLEGE",
    "FOUNDATION",
    "HOSPITAL",
    "INSTITUTE",
    "INSTITUTION",
    "LABORATORY",
    "LABORATORIES",
    "NONPROFIT",
    "NON PROFIT",
    "SCHOOL",
)

PHASE_SORT_ORDER = {"I": 1, "IB": 2, "II": 3, "IIB": 4, "III": 5}
PHASE1_FAMILY = frozenset({"PHASE I", "I", "PHASE IB", "IB"})
PHASE23_FAMILY = frozenset({"PHASE II", "II", "PHASE IIB", "IIB", "PHASE III", "III"})


@dataclass(frozen=True)
class OutputPaths:
    root: Path

    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

    def csv(self, name: str) -> Path:
        return self.root / f"{name}.csv"

    @property
    def figure(self) -> Path:
        return self.analysis_dir / FIGURE_NAME

    @property
    def markdown(self) -> Path:
        return self.root / MARKDOWN_NAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-sbir", type=Path, default=RAW_SBIR_PATH)
    parser.add_argument("--materialized-sbir", type=Path, default=MATERIALIZED_SBIR_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "<na>"} else text


def _parse_headcount(value: object) -> int | None:
    """Mirror the repository's employee-count coercion deterministically."""

    text = _clean_text(value)
    if not text:
        return None
    cleaned = text.replace(",", "")
    try:
        parsed = float(cleaned)
    except ValueError:
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        return int(digits) if digits else None
    if parsed < 0:
        return None
    return round(parsed)


def _parse_money(value: object) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_year(value: object) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else None


def _normalize_matching_name(value: object) -> str:
    return normalize_company_name(value, profile=CompanyNameProfile.MATCHING_V1)


def _original_company_key(row: pd.Series) -> str:
    uei = _clean_text(row.get("company_uei"))
    if uei:
        return f"UEI:{uei}"
    duns = _clean_text(row.get("company_duns"))
    if duns:
        return f"DUNS:{duns}"
    return f"NAME:{_normalize_matching_name(row.get('company_name'))}"


def _canonical_firm_frame(frame: pd.DataFrame) -> pd.DataFrame:
    canonical_map = build_canonical_company_map(frame, policy=CanonicalMergePolicy.PRELOAD_V1)
    enriched = frame.copy()
    enriched["firm_original_key"] = enriched.apply(_original_company_key, axis=1)
    enriched["firm_key"] = (
        enriched["firm_original_key"].map(canonical_map).fillna(enriched["firm_original_key"])
    )
    enriched["firm_key_basis"] = enriched["firm_key"].str.split(":", n=1).str[0]
    enriched["firm_canonical_uei"] = enriched["firm_key"].where(
        enriched["firm_key"].str.startswith("UEI:")
    )
    enriched["firm_canonical_uei"] = enriched["firm_canonical_uei"].str.removeprefix("UEI:")
    enriched["firm_canonical_duns"] = enriched["firm_key"].where(
        enriched["firm_key"].str.startswith("DUNS:")
    )
    enriched["firm_canonical_duns"] = enriched["firm_canonical_duns"].str.removeprefix("DUNS:")
    enriched["firm_canonical_name_key"] = enriched["firm_key"].where(
        enriched["firm_key"].str.startswith("NAME:")
    )
    enriched["firm_canonical_name_key"] = enriched["firm_canonical_name_key"].str.removeprefix(
        "NAME:"
    )
    return enriched


def _phase_sort_key(value: object) -> tuple[int, str]:
    text = _clean_text(value).upper()
    return (PHASE_SORT_ORDER.get(text, 999), text)


def _joined_unique(values: pd.Series) -> str:
    unique = sorted({_clean_text(value) for value in values if _clean_text(value)})
    return "; ".join(unique)


def _phase_mix(values: pd.Series) -> str:
    counter = Counter(_clean_text(value).upper() for value in values if _clean_text(value))
    ordered = sorted(counter.items(), key=lambda item: (_phase_sort_key(item[0]), item[0]))
    return "; ".join(f"{phase}={count}" for phase, count in ordered)


def _representative_name(values: pd.Series) -> str:
    counter = Counter(_clean_text(value) for value in values if _clean_text(value))
    if not counter:
        return ""
    max_count = max(counter.values())
    return sorted(name for name, count in counter.items() if count == max_count)[0]


def _summarize_firms(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby("firm_key", sort=False, dropna=False)
    for firm_key, group in grouped:
        award_years = group["award_year"].dropna().astype(int)
        headcounts = group["headcount"].dropna().astype(int)
        amount_sum = float(group["award_amount_numeric"].fillna(0.0).sum())
        rows.append(
            {
                "firm_key": firm_key,
                "firm": _representative_name(group["company_name"]),
                "uei": _clean_text(group["firm_canonical_uei"].iloc[0]),
                "duns": _clean_text(group["firm_canonical_duns"].iloc[0]),
                "name_key": _clean_text(group["firm_canonical_name_key"].iloc[0]),
                "firm_key_basis": _clean_text(group["firm_key_basis"].iloc[0]),
                "max_headcount": int(headcounts.max()) if not headcounts.empty else pd.NA,
                "award_count": int(len(group)),
                "headcount_observation_count": int(headcounts.notna().sum()),
                "first_award_year": int(award_years.min()) if not award_years.empty else pd.NA,
                "last_award_year": int(award_years.max()) if not award_years.empty else pd.NA,
                "agencies": _joined_unique(group["agency"]),
                "phase_mix": _phase_mix(group["phase"]),
                "total_award_dollars": amount_sum,
            }
        )
    firms = pd.DataFrame(rows)
    if not firms.empty:
        firms = firms.sort_values(
            ["max_headcount", "award_count", "total_award_dollars", "firm_key"],
            ascending=[False, False, False, True],
            na_position="last",
            kind="stable",
        ).reset_index(drop=True)
    return firms


def _is_nonprofit_name_flag(company_name: object, ri_name: object) -> bool:
    haystacks = [f" {_clean_text(company_name).upper()} ", f" {_clean_text(ri_name).upper()} "]
    return any(token in haystack for haystack in haystacks for token in NONPROFIT_NAME_TOKENS)


def _mark_single_award_spikes(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(False, index=frame.index)
    for _, group in frame.groupby("firm_key", sort=False):
        observed = group[group["headcount"].notna()].copy()
        if len(observed) < 3:
            continue
        observed = observed.sort_values(
            ["award_sort_date", "award_year", "phase_sort_key", "award_record_key"],
            kind="stable",
        )
        observed["prev_headcount"] = observed["headcount"].shift(1)
        observed["next_headcount"] = observed["headcount"].shift(-1)
        mask = (
            observed["headcount"].gt(500)
            & observed["prev_headcount"].lt(100)
            & observed["next_headcount"].lt(100)
        )
        if mask.any():
            result.loc[observed.index[mask]] = True
    return result


def _build_crosscheck_summary() -> pd.DataFrame:
    rows = [
        {
            "population": "top_100",
            "source": "fpds_or_sam_employee_counts",
            "materialized_source_available": False,
            "matched_rows": 0,
            "agree_count": 0,
            "disagree_count": 0,
            "note": (
                "No materialized FPDS/SAM employee-count table was present in this checkout on "
                "2026-08-20."
            ),
        },
        {
            "population": "anomalies",
            "source": "fpds_or_sam_employee_counts",
            "materialized_source_available": False,
            "matched_rows": 0,
            "agree_count": 0,
            "disagree_count": 0,
            "note": (
                "No materialized FPDS/SAM employee-count table was present in this checkout on "
                "2026-08-20."
            ),
        },
    ]
    return pd.DataFrame(rows)


def _format_pct(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "0.0%"
    return f"{100 * float(numerator) / float(denominator):.1f}%"


def _format_int(value: int | float) -> str:
    return f"{int(round(float(value))):,}"


def _render_histogram_panel(
    *,
    values: pd.Series,
    bins: list[int],
    title: str,
    color: str,
    cap_value: int,
    x: int,
    y: int,
    width: int,
    height: int,
) -> str:
    chart_left = x + 70
    chart_right = x + width - 20
    chart_top = y + 45
    chart_bottom = y + height - 55
    chart_width = chart_right - chart_left
    chart_height = chart_bottom - chart_top

    counts, edges = np.histogram(values.to_numpy(dtype=float), bins=np.array(bins, dtype=float))
    max_count = max(int(counts.max()), 1)

    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="white" stroke="#d0d7de"/>',
        (
            f'<text x="{x + width / 2:.1f}" y="{y + 24}" text-anchor="middle" '
            'font-size="18" font-family="Menlo, Consolas, monospace" fill="#111827">'
            f"{escape(title)}</text>"
        ),
        f'<line x1="{chart_left}" y1="{chart_bottom}" x2="{chart_right}" y2="{chart_bottom}" stroke="#111827" stroke-width="1.5"/>',
        f'<line x1="{chart_left}" y1="{chart_top}" x2="{chart_left}" y2="{chart_bottom}" stroke="#111827" stroke-width="1.5"/>',
        (
            f'<text x="{x + width / 2:.1f}" y="{y + height - 12}" text-anchor="middle" '
            'font-size="12" font-family="Menlo, Consolas, monospace" fill="#374151">'
            "Reported headcount at award</text>"
        ),
        (
            f'<text x="{x + 18}" y="{y + height / 2:.1f}" text-anchor="middle" '
            'font-size="12" font-family="Menlo, Consolas, monospace" fill="#374151" '
            f'transform="rotate(-90 {x + 18} {y + height / 2:.1f})">Award records</text>'
        ),
        (
            f'<text x="{chart_right - 4}" y="{chart_top + 16}" text-anchor="end" '
            'font-size="12" font-family="Menlo, Consolas, monospace" fill="#b22222">'
            "500-employee cap</text>"
        ),
    ]

    for count, left_edge, right_edge in zip(counts, edges[:-1], edges[1:], strict=True):
        x0 = chart_left + ((left_edge - edges[0]) / (edges[-1] - edges[0])) * chart_width
        x1 = chart_left + ((right_edge - edges[0]) / (edges[-1] - edges[0])) * chart_width
        bar_width = max(x1 - x0 - 1, 1)
        bar_height = 0 if count == 0 else (float(count) / max_count) * chart_height
        y0 = chart_bottom - bar_height
        parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" '
            f'fill="{color}" opacity="0.88"/>'
        )

    cap_x = chart_left + ((cap_value - edges[0]) / (edges[-1] - edges[0])) * chart_width
    if chart_left <= cap_x <= chart_right:
        parts.append(
            f'<line x1="{cap_x:.2f}" y1="{chart_top}" x2="{cap_x:.2f}" y2="{chart_bottom}" '
            'stroke="#b22222" stroke-width="2" stroke-dasharray="6 4"/>'
        )

    for tick_index in range(5):
        ratio = tick_index / 4
        tick_x = chart_left + ratio * chart_width
        tick_value = edges[0] + ratio * (edges[-1] - edges[0])
        parts.append(
            f'<line x1="{tick_x:.2f}" y1="{chart_bottom}" x2="{tick_x:.2f}" y2="{chart_bottom + 6}" '
            'stroke="#111827" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{tick_x:.2f}" y="{chart_bottom + 22}" text-anchor="middle" '
            'font-size="11" font-family="Menlo, Consolas, monospace" fill="#374151">'
            f"{escape(_format_int(tick_value))}</text>"
        )

    for tick_index in range(5):
        ratio = tick_index / 4
        tick_y = chart_bottom - ratio * chart_height
        tick_value = round(ratio * max_count)
        parts.append(
            f'<line x1="{chart_left - 6}" y1="{tick_y:.2f}" x2="{chart_left}" y2="{tick_y:.2f}" '
            'stroke="#111827" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{chart_left - 10}" y="{tick_y + 4:.2f}" text-anchor="end" '
            'font-size="11" font-family="Menlo, Consolas, monospace" fill="#374151">'
            f"{tick_value:,}</text>"
        )

    return "\n".join(parts)


def _write_figure(headcounts: pd.Series, output_path: Path) -> None:
    full_bins = list(range(0, int(max(625, math.ceil(headcounts.max() / 25) * 25)) + 25, 25))
    zoom_bins = list(range(300, 625, 10))
    zoom_values = headcounts[(headcounts >= 300) & (headcounts <= 600)]

    width = 1400
    height = 560
    panel_width = 650
    panel_height = 460

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect x="0" y="0" width="{width}" height="{height}" fill="#f8fafc"/>
<text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="22" font-family="Menlo, Consolas, monospace" fill="#111827">SBIR.gov Headcount At Award Distribution</text>
<text x="{width / 2:.1f}" y="48" text-anchor="middle" font-size="12" font-family="Menlo, Consolas, monospace" fill="#374151">Exploratory / non-citable. Vertical line marks the 500-employee SBIR eligibility cap.</text>
{_render_histogram_panel(values=headcounts, bins=full_bins, title="Full Distribution", color="#2f6f91", cap_value=500, x=35, y=70, width=panel_width, height=panel_height)}
{_render_histogram_panel(values=zoom_values, bins=zoom_bins, title="300-600 Zoom", color="#4d8f5b", cap_value=500, x=715, y=70, width=panel_width, height=panel_height)}
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")


def _materialize_source(raw_path: Path, output_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = materialize_sbir_gov_history(raw_path, output_path, source_url=SOURCE_URL)
    frame = pd.read_parquet(output_path)
    verify_sbir_gov_materialization(output_path, frame)
    return frame, manifest


def _distribution_summary(headcounts: pd.Series) -> pd.DataFrame:
    metrics = {
        "metric": [
            "award_records_with_headcount",
            "median",
            "p90",
            "p99",
            "pct_ge_350",
            "pct_ge_500",
        ],
        "value": [
            int(headcounts.size),
            float(headcounts.quantile(0.50)),
            float(headcounts.quantile(0.90)),
            float(headcounts.quantile(0.99)),
            float((headcounts >= 350).mean()),
            float((headcounts >= 500).mean()),
        ],
    }
    return pd.DataFrame(metrics)


def _safe_corr(x: pd.Series, y: pd.Series, method: str) -> float | pd.NA:
    valid = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(valid) < 2 or valid["x"].nunique() < 2 or valid["y"].nunique() < 2:
        return pd.NA
    return float(valid["x"].corr(valid["y"], method=method))


def _year_fixed_effect_corr(
    frame: pd.DataFrame, x_column: str, y_column: str, year_column: str, method: str
) -> float | pd.NA:
    valid = frame[[x_column, y_column, year_column]].dropna().copy()
    if len(valid) < 2 or valid[x_column].nunique() < 2 or valid[y_column].nunique() < 2:
        return pd.NA

    if method == "spearman":
        valid[x_column] = valid[x_column].rank(method="average")
        valid[y_column] = valid[y_column].rank(method="average")
    elif method != "pearson":
        raise ValueError(f"Unsupported correlation method: {method}")

    x_residual = valid[x_column] - valid.groupby(year_column)[x_column].transform("mean")
    y_residual = valid[y_column] - valid.groupby(year_column)[y_column].transform("mean")
    if x_residual.nunique() < 2 or y_residual.nunique() < 2:
        return pd.NA
    return float(x_residual.corr(y_residual, method="pearson"))


def _all_firm_repeat_proxy(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for firm_key, group in frame.groupby("firm_key", sort=False):
        ordered = group.sort_values(
            ["award_sort_date", "award_year", "phase_sort_key", "award_record_key"],
            kind="stable",
        )
        observed = ordered[ordered["headcount"].notna()]
        if observed.empty:
            continue

        first_observed = observed.iloc[0]
        first_position = int(ordered.index.get_loc(first_observed.name))
        later_awards = ordered.iloc[first_position + 1 :]
        rows.append(
            {
                "firm_key": firm_key,
                "firm": _representative_name(ordered["company_name"]),
                "uei": _clean_text(ordered["firm_canonical_uei"].iloc[0]),
                "first_headcount_award_id": _clean_text(first_observed["award_id"]),
                "first_headcount_award_year": first_observed["award_year"],
                "first_headcount_agency": _clean_text(first_observed["agency"]),
                "first_headcount_phase": _clean_text(first_observed["phase"]),
                "first_headcount": float(first_observed["headcount"]),
                "first_headcount_position": first_position,
                "first_award_has_headcount": first_position == 0,
                "repeat_award_proxy": int(len(later_awards) > 0),
                "later_award_count": int(len(later_awards)),
                "award_count": int(len(ordered)),
                "phase2_or_3_share": float(
                    ordered["phase"].str.upper().isin(PHASE23_FAMILY).mean()
                ),
            }
        )

    firms = pd.DataFrame(rows).sort_values("firm_key", kind="stable").reset_index(drop=True)
    outcomes = (
        ("repeat_award_proxy", "ever_received_later_award"),
        ("award_count", "total_observed_award_count"),
        ("phase2_or_3_share", "phase2_or_3_award_share"),
    )

    summary = pd.DataFrame(
        [
            {
                "outcome": label,
                "firms": int(len(firms)),
                "pearson": _safe_corr(firms["first_headcount"], firms[column], "pearson"),
                "spearman": _safe_corr(firms["first_headcount"], firms[column], "spearman"),
            }
            for column, label in outcomes
        ]
    )

    bands = pd.cut(
        firms["first_headcount"],
        bins=[-1, 9, 24, 49, 99, 199, 349, 500, 10**9],
        labels=["0-9", "10-24", "25-49", "50-99", "100-199", "200-349", "350-500", "501+"],
    )
    band_summary = (
        firms.assign(headcount_band=bands)
        .groupby("headcount_band", observed=False)
        .agg(
            firms=("firm_key", "size"),
            repeat_award_rate=("repeat_award_proxy", "mean"),
            mean_award_count=("award_count", "mean"),
            mean_later_award_count=("later_award_count", "mean"),
        )
        .reset_index()
    )

    maximum_award_year = int(frame["award_year"].dropna().max())
    mature_cutoff = maximum_award_year - 6
    sensitivity_frames = (
        (
            "strict_first_award_has_headcount",
            firms[firms["first_award_has_headcount"]],
            "Requires the first chronological award itself to carry headcount.",
        ),
        (
            f"mature_cohort_through_{mature_cutoff}",
            firms[firms["first_headcount_award_year"].le(mature_cutoff)],
            "Allows at least five complete subsequent calendar years before the partial snapshot year.",
        ),
    )
    sensitivity_rows: list[dict[str, Any]] = []
    for analysis, cohort, note in sensitivity_frames:
        for column, label in outcomes:
            sensitivity_rows.append(
                {
                    "analysis": analysis,
                    "outcome": label,
                    "firms": int(len(cohort)),
                    "pearson": _safe_corr(cohort["first_headcount"], cohort[column], "pearson"),
                    "spearman": _safe_corr(cohort["first_headcount"], cohort[column], "spearman"),
                    "note": note,
                }
            )

    year_note = "Residualizes values (or global ranks) within first-headcount award year."
    for column, label in outcomes:
        sensitivity_rows.append(
            {
                "analysis": "within_first_headcount_year_fixed_effects",
                "outcome": label,
                "firms": int(firms["first_headcount_award_year"].notna().sum()),
                "pearson": _year_fixed_effect_corr(
                    firms,
                    "first_headcount",
                    column,
                    "first_headcount_award_year",
                    "pearson",
                ),
                "spearman": _year_fixed_effect_corr(
                    firms,
                    "first_headcount",
                    column,
                    "first_headcount_award_year",
                    "spearman",
                ),
                "note": year_note,
            }
        )

    return firms, summary, band_summary, pd.DataFrame(sensitivity_rows)


def _phase1_proxy_by_agency(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for (agency, firm_key), group in frame.groupby(["agency", "firm_key"], sort=False):
        ordered = group.sort_values(
            ["award_sort_date", "award_year", "phase_sort_key", "award_record_key"],
            kind="stable",
        )
        phase1_rows = ordered[ordered["phase"].str.upper().isin(PHASE1_FAMILY)]
        if phase1_rows.empty:
            continue
        first_phase1 = phase1_rows.iloc[0]
        if pd.isna(first_phase1["headcount"]):
            continue
        first_phase1_position = int(ordered.index.get_loc(first_phase1.name))
        later_awards = ordered.iloc[first_phase1_position + 1 :]
        rows.append(
            {
                "agency": agency,
                "firm_key": firm_key,
                "firm": _representative_name(ordered["company_name"]),
                "uei": _clean_text(ordered["firm_canonical_uei"].iloc[0]),
                "first_phase1_award_year": first_phase1["award_year"],
                "first_phase1_headcount": float(first_phase1["headcount"]),
                "repeat_award_proxy": int(len(later_awards) > 0),
                "award_count": int(len(ordered)),
                "phase2_or_3_share": float(
                    ordered["phase"].str.upper().isin(PHASE23_FAMILY).mean()
                ),
            }
        )

    firm_agency = pd.DataFrame(rows)
    if firm_agency.empty:
        return firm_agency, pd.DataFrame()

    summary_rows: list[dict[str, Any]] = []
    for agency, group in firm_agency.groupby("agency", sort=False):
        summary_rows.append(
            {
                "agency": agency,
                "firms": int(len(group)),
                "median_first_phase1_headcount": float(group["first_phase1_headcount"].median()),
                "repeat_award_rate": float(group["repeat_award_proxy"].mean()),
                "mean_award_count": float(group["award_count"].mean()),
                "mean_phase2_or_3_share": float(group["phase2_or_3_share"].mean()),
                "pearson_repeat_award_proxy": _safe_corr(
                    group["first_phase1_headcount"], group["repeat_award_proxy"], "pearson"
                ),
                "spearman_repeat_award_proxy": _safe_corr(
                    group["first_phase1_headcount"], group["repeat_award_proxy"], "spearman"
                ),
                "pearson_award_count": _safe_corr(
                    group["first_phase1_headcount"], group["award_count"], "pearson"
                ),
                "spearman_award_count": _safe_corr(
                    group["first_phase1_headcount"], group["award_count"], "spearman"
                ),
                "pearson_phase2_or_3_share": _safe_corr(
                    group["first_phase1_headcount"], group["phase2_or_3_share"], "pearson"
                ),
                "spearman_phase2_or_3_share": _safe_corr(
                    group["first_phase1_headcount"], group["phase2_or_3_share"], "spearman"
                ),
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values(
        ["firms", "agency"], ascending=[False, True], kind="stable"
    )

    bands = pd.cut(
        firm_agency["first_phase1_headcount"],
        bins=[-1, 9, 24, 49, 99, 199, 349, 500, 10**9],
        labels=["0-9", "10-24", "25-49", "50-99", "100-199", "200-349", "350-500", "501+"],
    )
    band_summary = (
        firm_agency.assign(headcount_band=bands)
        .groupby(["agency", "headcount_band"], observed=False)
        .agg(
            firms=("firm_key", "size"),
            median_headcount=("first_phase1_headcount", "median"),
            repeat_award_rate=("repeat_award_proxy", "mean"),
            mean_award_count=("award_count", "mean"),
            mean_phase2_or_3_share=("phase2_or_3_share", "mean"),
        )
        .reset_index()
        .sort_values(["agency", "headcount_band"], kind="stable")
    )
    return summary.reset_index(drop=True), band_summary.reset_index(drop=True)


def _build_markdown(
    manifest: dict[str, Any],
    schema: pd.DataFrame,
    coverage_agency: pd.DataFrame,
    coverage_agency_year: pd.DataFrame,
    distribution: pd.DataFrame,
    top_100: pd.DataFrame,
    near_cap: pd.DataFrame,
    anomalies: pd.DataFrame,
    anomaly_counts: pd.DataFrame,
    trajectory: pd.DataFrame,
    crosscheck_summary: pd.DataFrame,
    repeat_proxy_summary: pd.DataFrame,
    repeat_proxy_bands: pd.DataFrame,
    repeat_proxy_sensitivity: pd.DataFrame,
    phase1_agency_proxy: pd.DataFrame,
    figure_path: Path,
) -> str:
    employee_schema_row = schema.loc[schema["is_employee_field"]]
    employee_column = (
        employee_schema_row["column_name"].iloc[0] if not employee_schema_row.empty else "UNKNOWN"
    )
    distribution_metrics = dict(zip(distribution["metric"], distribution["value"], strict=True))

    top_agency_lines = []
    for _, row in (
        coverage_agency.sort_values(
            ["parsed_populated_pct", "row_count", "agency"],
            ascending=[False, False, True],
            kind="stable",
        )
        .head(10)
        .iterrows()
    ):
        top_agency_lines.append(
            f"- {row['agency']}: {int(row['parsed_populated_count']):,}/{int(row['row_count']):,} "
            f"parsed ({row['parsed_populated_pct']:.1f}%)."
        )

    anomaly_lines = []
    for _, row in anomaly_counts.iterrows():
        anomaly_lines.append(f"- {row['bucket']}: {int(row['record_count']):,} records.")

    crosscheck_lines = []
    for _, row in crosscheck_summary.iterrows():
        status = "not run" if not row["materialized_source_available"] else "run"
        crosscheck_lines.append(
            f"- {row['population']}: {status}; agree={int(row['agree_count'])}, "
            f"disagree={int(row['disagree_count'])}. {row['note']}"
        )

    agency_proxy_lines = []
    for _, row in phase1_agency_proxy.head(10).iterrows():
        agency_proxy_lines.append(
            f"- {row['agency']}: n={int(row['firms']):,}, repeat-rate={row['repeat_award_rate']:.1%}, "
            f"Spearman(headcount, repeat-proxy)={row['spearman_repeat_award_proxy']:.3f}, "
            f"Spearman(headcount, award-count)={row['spearman_award_count']:.3f}."
        )

    repeat_proxy_lines = []
    for _, row in repeat_proxy_summary.iterrows():
        repeat_proxy_lines.append(
            f"- {row['outcome']}: n={int(row['firms']):,}, Pearson={row['pearson']:.4f}, "
            f"Spearman={row['spearman']:.4f}."
        )

    repeat_band_lines = [
        "| First headcount | Firms | Later-award rate | Mean total awards |",
        "|---|---:|---:|---:|",
    ]
    for _, row in repeat_proxy_bands.iterrows():
        repeat_band_lines.append(
            f"| {row['headcount_band']} | {int(row['firms']):,} | "
            f"{row['repeat_award_rate']:.1%} | {row['mean_award_count']:.2f} |"
        )

    repeat_sensitivity_lines = []
    repeat_outcome = "ever_received_later_award"
    for _, row in repeat_proxy_sensitivity.loc[
        repeat_proxy_sensitivity["outcome"].eq(repeat_outcome)
    ].iterrows():
        repeat_sensitivity_lines.append(
            f"- {row['analysis']}: n={int(row['firms']):,}, Pearson={row['pearson']:.4f}, "
            f"Spearman={row['spearman']:.4f}. {row['note']}"
        )

    schema_list = "\n".join(
        f"{int(row['ordinal_position']):02d}. {row['column_name']}"
        + ("  <-- employee-count field" if bool(row["is_employee_field"]) else "")
        for _, row in schema.iterrows()
    )

    top_100_count = int(len(top_100))
    near_cap_count = int(len(near_cap))
    anomaly_record_count = int(len(anomalies))
    trajectory_count = int(len(trajectory))
    coverage_grid_count = int(len(coverage_agency_year))

    markdown = f"""# Headcount At Award Readout

> **Exploratory / non-citable.** Generated on {ANALYSIS_DATE} from the checked-in SBIR.gov bulk snapshot and repository primitives. Do not cite outside the repository.

## Scope

- **Question:** descriptive readout of awardee headcount at time of award, focused on the top of the distribution.
- **Source snapshot:** `{manifest["source_provenance"]["path"]}`
- **Canonical materialized source:** `{manifest["output"]["path"]}`
- **Source URL recorded in provenance:** {manifest["source_provenance"]["url"]}

## Deterministic criteria

- **Employee-count field:** actual materialized column name is `{employee_column}`.
- **Population for coverage:** every retained SBIR.gov source row in the canonical materialized parquet.
- **Population for distributional summaries:** rows with parsed non-null headcount after deterministic coercion.
- **Headcount parse rule:** blank -> null; numeric strings, commas, and floats are coerced; text with embedded digits uses the digits; negative values are dropped.
- **Firm grain:** repository canonical merge policy `CanonicalMergePolicy.PRELOAD_V1`, keyed `UEI:` first, then `DUNS:`, then `NAME:<MATCHING_V1 normalized name>`.
- **Near-cap band:** firms with any parsed award-time headcount in `[350, 500]`.
- **Anomaly population:** award records with parsed headcount `>500`.
- **STTR research-institution flag:** `program == STTR` and `ri_name` non-blank.
- **Nonprofit name flag:** company or RI name contains one of `{", ".join(NONPROFIT_NAME_TOKENS)}`.
- **Single-award spike flag:** one `>500` record bracketed by both adjacent observed headcounts `<100` within the same firm's chronological award history.
- **Cross-check rule:** FPDS/SAM employee-count joins were attempted only against already materialized local tables.
- **Repeat-award proxy anchor:** each firm's first chronological award with parsed headcount.
- **Repeat-award proxy outcome:** at least one later SBIR.gov award record for the same canonical firm; this is not an application win rate.

## Actual Materialized Schema

```text
{schema_list}
```

The canonical materialized parquet has `{manifest["output"]["column_count"]}` columns and `{manifest["output"]["rows"]:,}` retained rows after collapsing `{manifest["source_grain"]["exact_duplicate_rows_collapsed"]:,}` exact source duplicates.

## Coverage

Parsed headcount coverage by agency-year was written for `{coverage_grid_count:,}` agency-year cells. Top agencies by parsed coverage:

{chr(10).join(top_agency_lines)}

## Distribution

- Award records with parsed headcount: `{int(distribution_metrics["award_records_with_headcount"]):,}`.
- Median headcount: `{distribution_metrics["median"]:.0f}`.
- P90 headcount: `{distribution_metrics["p90"]:.0f}`.
- P99 headcount: `{distribution_metrics["p99"]:.0f}`.
- Share `>=350`: `{distribution_metrics["pct_ge_350"]:.1%}`.
- Share `>=500`: `{distribution_metrics["pct_ge_500"]:.1%}`.
- Figure: `{figure_path}`

## Top Tail Outputs

- TOP-100 firms table rows: `{top_100_count}`.
- Near-cap band firms rows: `{near_cap_count}`.
- Anomaly records (`>500`): `{anomaly_record_count}`.
- Multi-award trajectory rows (`>=5` awards): `{trajectory_count}`.

Anomaly bucket counts:

{chr(10).join(anomaly_lines)}

## Cross-check Availability

{chr(10).join(crosscheck_lines)}

Note: FPDS/SAM employee counts are self-certified business-size fields when present, and SBA's August 2026 NPRM (RIN 3245-AI67, footnote 26) states that SAM size data can be outdated or inaccurate.

## All-Firm Repeat-Award Proxy

This checkout does not include applications or unsuccessful proposals, so no true win rate is identified. The award-history proxy relates headcount on a firm's first headcount-bearing award to later observed awards under the same firm-collapse policy.

{chr(10).join(repeat_proxy_lines)}

{chr(10).join(repeat_band_lines)}

The repeat-award pattern is positive but not monotonic in every band. The upper-tail rates are especially imprecise because the `501+` band contains few firms.

Chronology and award-vintage sensitivities for the later-award outcome:

{chr(10).join(repeat_sensitivity_lines)}

These checks preserve a positive, modest relationship. They do not resolve selection into the winner-only dataset or turn the proxy into a causal estimate.

## Phase I Agency Proxy

This checkout does not include application/proposal denominators, so no true agency-level win rate was computed. The by-agency proxy instead uses firms with an observed headcount on their first **Phase I-family** award in that agency (`Phase I` + `Phase IB`) and measures whether they ever receive another SBIR award in the same agency.

{chr(10).join(agency_proxy_lines)}

## Cap-Removal Extrapolation

The award-only data do not identify how removing the 500-employee cap would change application win rates. They omit unsuccessful applicants, firms deterred from applying, affiliate-adjusted headcount, and the number and quality of firms that would enter above the cap.

With a fixed number of awards, removing the cap expands the applicant denominator: if current applicants and awards are `A` and `W`, and `B` newly eligible firms apply, the aggregate rate changes mechanically from `W/A` to `W/(A+B)`, which is lower. The aggregate rate rises only if additional awards `dW` grow proportionally faster than the applicant pool (`dW/W > B/A`). Award reallocation can improve access for newly eligible firms while reducing incumbent applicants' rate. None of `B`, `dW`, or the allocation response is observed here, so a numerical cap-removal effect would be assumption-driven rather than estimated from this source.

## Confounds

- Self-reported application-time headcount, not independently validated.
- Affiliate treatment is unknown from the SBIR.gov award extract.
- Any SAM-based cross-check would inherit SAM staleness / inaccuracy concerns.
- Award-time headcount is right-censored relative to current firm size.
- Repeat-award outcomes are right-censored by award vintage; recent firms have less follow-up.
- Award histories condition on having won at least once and contain no unsuccessful applications.
- `>500` records are not interpreted here as eligibility violations.
"""
    return markdown


def main() -> int:
    args = _parser().parse_args()
    output_paths = OutputPaths(args.output_dir)
    output_paths.ensure()

    materialized, manifest = _materialize_source(args.raw_sbir, args.materialized_sbir)

    schema = pd.DataFrame(
        {
            "ordinal_position": range(1, len(materialized.columns) + 1),
            "column_name": materialized.columns,
            "dtype": [str(dtype) for dtype in materialized.dtypes],
        }
    )
    schema["is_employee_field"] = schema["column_name"].str.contains(
        "employee", case=False, regex=False
    )

    employee_columns = schema.loc[schema["is_employee_field"], "column_name"].tolist()
    if len(employee_columns) != 1:
        raise ValueError(
            f"Expected exactly one employee-count column in the materialized schema, found {employee_columns}"
        )
    employee_column = employee_columns[0]

    frame = materialized.copy()
    frame["headcount_raw"] = frame[employee_column]
    frame["headcount"] = frame["headcount_raw"].map(_parse_headcount)
    frame["headcount_populated_raw"] = frame["headcount_raw"].map(
        lambda value: bool(_clean_text(value))
    )
    frame["award_year"] = frame["Award Year"].map(_parse_year)
    frame["award_amount_numeric"] = frame["award_amount"].map(_parse_money)
    frame["award_date_sort"] = pd.to_datetime(frame["award_date"], errors="coerce")
    frame["award_sort_date"] = frame["award_date_sort"]
    award_year_mask = frame["award_sort_date"].isna() & frame["award_year"].notna()
    frame.loc[award_year_mask, "award_sort_date"] = pd.to_datetime(
        frame.loc[award_year_mask, "award_year"].astype(int).astype(str) + "-01-01",
        errors="coerce",
    )
    frame["company_name"] = frame["company_name"].map(_clean_text)
    frame["agency"] = frame["agency"].map(_clean_text)
    frame["phase"] = frame["phase"].map(_clean_text)
    frame["program"] = frame["program"].map(_clean_text)
    frame["ri_name"] = frame["ri_name"].map(_clean_text)
    frame["company_uei"] = frame["company_uei"].map(_clean_text)
    frame["company_duns"] = frame["company_duns"].map(_clean_text)
    frame["phase_sort_key"] = frame["phase"].map(lambda value: _phase_sort_key(value)[0])
    frame["award_record_key"] = (
        frame["award_id"].map(_clean_text)
        + "|"
        + frame["phase"].map(_clean_text)
        + "|"
        + frame["source_row_sha256"].map(_clean_text)
    )
    frame = _canonical_firm_frame(frame)

    coverage_agency_year = (
        frame.groupby(["agency", "award_year"], dropna=False)
        .agg(
            row_count=("award_record_key", "size"),
            populated_raw_count=("headcount_populated_raw", "sum"),
            parsed_populated_count=("headcount", lambda values: int(values.notna().sum())),
        )
        .reset_index()
        .sort_values(["agency", "award_year"], kind="stable")
        .reset_index(drop=True)
    )
    coverage_agency_year["populated_raw_pct"] = (
        100 * coverage_agency_year["populated_raw_count"] / coverage_agency_year["row_count"]
    )
    coverage_agency_year["parsed_populated_pct"] = (
        100 * coverage_agency_year["parsed_populated_count"] / coverage_agency_year["row_count"]
    )

    coverage_agency = (
        frame.groupby("agency", dropna=False)
        .agg(
            row_count=("award_record_key", "size"),
            populated_raw_count=("headcount_populated_raw", "sum"),
            parsed_populated_count=("headcount", lambda values: int(values.notna().sum())),
        )
        .reset_index()
        .sort_values("agency", kind="stable")
        .reset_index(drop=True)
    )
    coverage_agency["populated_raw_pct"] = (
        100 * coverage_agency["populated_raw_count"] / coverage_agency["row_count"]
    )
    coverage_agency["parsed_populated_pct"] = (
        100 * coverage_agency["parsed_populated_count"] / coverage_agency["row_count"]
    )

    headcounts = frame.loc[frame["headcount"].notna(), "headcount"].astype(int)
    if headcounts.empty:
        raise ValueError(
            "No parseable headcount values were found in the materialized SBIR.gov source."
        )

    distribution = _distribution_summary(headcounts)

    firms = _summarize_firms(frame)
    firms_with_headcount = firms[firms["max_headcount"].notna()].copy()
    top_100 = firms_with_headcount.head(100).reset_index(drop=True)
    near_cap_keys = set(
        frame.loc[frame["headcount"].between(350, 500, inclusive="both"), "firm_key"]
    )
    near_cap = (
        firms_with_headcount[firms_with_headcount["firm_key"].isin(near_cap_keys)]
        .sort_values(
            ["max_headcount", "award_count", "total_award_dollars", "firm_key"],
            ascending=[False, False, False, True],
            na_position="last",
            kind="stable",
        )
        .reset_index(drop=True)
    )

    anomalies = frame.loc[frame["headcount"] > 500].copy()
    anomalies["sttr_research_institution_flag"] = anomalies["program"].str.upper().eq(
        "STTR"
    ) & anomalies["ri_name"].ne("")
    anomalies["nonprofit_name_flag"] = anomalies.apply(
        lambda row: _is_nonprofit_name_flag(row["company_name"], row["ri_name"]), axis=1
    )
    all_spikes = _mark_single_award_spikes(frame)
    anomalies["single_award_spike_flag"] = all_spikes.reindex(anomalies.index, fill_value=False)
    anomalies["classification_labels"] = anomalies.apply(
        lambda row: "; ".join(
            label
            for label, flag in (
                ("sttr_research_institution", row["sttr_research_institution_flag"]),
                ("nonprofit_name_flag", row["nonprofit_name_flag"]),
                ("single_award_spike", row["single_award_spike_flag"]),
            )
            if bool(flag)
        )
        or "unclassified",
        axis=1,
    )
    anomalies = anomalies.merge(
        firms[
            [
                "firm_key",
                "firm",
                "uei",
                "award_count",
                "agencies",
                "phase_mix",
                "total_award_dollars",
            ]
        ].rename(columns={"uei": "firm_uei"}),
        on="firm_key",
        how="left",
        validate="many_to_one",
    )
    anomalies_output = anomalies[
        [
            "firm",
            "firm_uei",
            "firm_key",
            "award_id",
            "agency",
            "award_year",
            "phase",
            "program",
            "headcount_raw",
            "headcount",
            "ri_name",
            "sttr_research_institution_flag",
            "nonprofit_name_flag",
            "single_award_spike_flag",
            "classification_labels",
            "award_count",
            "agencies",
            "phase_mix",
            "total_award_dollars",
            "source_row_sha256",
        ]
    ].sort_values(
        ["headcount", "award_year", "agency", "award_id"],
        ascending=[False, True, True, True],
        kind="stable",
    )
    anomalies_output = anomalies_output.rename(columns={"firm_uei": "uei"})

    anomaly_counts = pd.DataFrame(
        [
            {
                "bucket": "sttr_research_institution",
                "record_count": int(anomalies_output["sttr_research_institution_flag"].sum()),
            },
            {
                "bucket": "nonprofit_name_flag",
                "record_count": int(anomalies_output["nonprofit_name_flag"].sum()),
            },
            {
                "bucket": "single_award_spike",
                "record_count": int(anomalies_output["single_award_spike_flag"].sum()),
            },
            {
                "bucket": "unclassified",
                "record_count": int(
                    (anomalies_output["classification_labels"] == "unclassified").sum()
                ),
            },
        ]
    )

    trajectory_rows: list[dict[str, Any]] = []
    for _, group in frame.groupby("firm_key", sort=False):
        if len(group) < 5:
            continue
        ordered = group.sort_values(
            ["award_sort_date", "award_year", "phase_sort_key", "award_record_key"],
            kind="stable",
        )
        observed = ordered[ordered["headcount"].notna()].copy()
        if observed.empty:
            continue
        trajectory_rows.append(
            {
                "firm_key": ordered["firm_key"].iloc[0],
                "firm": _representative_name(ordered["company_name"]),
                "uei": _clean_text(ordered["firm_canonical_uei"].iloc[0]),
                "award_count": int(len(ordered)),
                "headcount_observation_count": int(len(observed)),
                "first_award_year": ordered["award_year"].iloc[0],
                "first_award_headcount": ordered["headcount"].iloc[0],
                "max_headcount": int(observed["headcount"].max()),
                "latest_award_year": ordered["award_year"].iloc[-1],
                "latest_award_headcount": ordered["headcount"].iloc[-1],
                "crossed_350": bool(
                    observed["headcount"].lt(350).any() and observed["headcount"].ge(350).any()
                ),
                "agencies": _joined_unique(ordered["agency"]),
                "phase_mix": _phase_mix(ordered["phase"]),
                "total_award_dollars": float(ordered["award_amount_numeric"].fillna(0.0).sum()),
            }
        )
    trajectory = pd.DataFrame(trajectory_rows)
    if not trajectory.empty:
        trajectory = trajectory.sort_values(
            ["crossed_350", "max_headcount", "award_count", "firm_key"],
            ascending=[False, False, False, True],
            kind="stable",
        ).reset_index(drop=True)

    crosscheck_summary = _build_crosscheck_summary()
    repeat_proxy_firms, repeat_proxy_summary, repeat_proxy_bands, repeat_proxy_sensitivity = (
        _all_firm_repeat_proxy(frame)
    )
    phase1_agency_proxy, phase1_agency_proxy_bands = _phase1_proxy_by_agency(frame)

    _write_figure(headcounts, output_paths.figure)

    schema.to_csv(output_paths.csv("schema"), index=False)
    coverage_agency.to_csv(output_paths.csv("employee_coverage_by_agency"), index=False)
    coverage_agency_year.to_csv(output_paths.csv("employee_coverage_by_agency_year"), index=False)
    distribution.to_csv(output_paths.csv("distribution_summary"), index=False)
    top_100.to_csv(output_paths.csv("top_100_firms"), index=False)
    near_cap.to_csv(output_paths.csv("near_cap_band_firms"), index=False)
    anomalies_output.to_csv(output_paths.csv("anomalies_over_500"), index=False)
    anomaly_counts.to_csv(output_paths.csv("anomaly_bucket_counts"), index=False)
    trajectory.to_csv(output_paths.csv("trajectory_multi_award_firms"), index=False)
    crosscheck_summary.to_csv(output_paths.csv("crosscheck_summary"), index=False)
    repeat_proxy_firms.to_csv(output_paths.csv("repeat_award_proxy_firms"), index=False)
    repeat_proxy_summary.to_csv(output_paths.csv("repeat_award_proxy_summary"), index=False)
    repeat_proxy_bands.to_csv(output_paths.csv("repeat_award_proxy_by_headcount_band"), index=False)
    repeat_proxy_sensitivity.to_csv(output_paths.csv("repeat_award_proxy_sensitivity"), index=False)
    phase1_agency_proxy.to_csv(output_paths.csv("phase1_repeat_proxy_by_agency"), index=False)
    phase1_agency_proxy_bands.to_csv(
        output_paths.csv("phase1_repeat_proxy_by_agency_band"), index=False
    )

    markdown = _build_markdown(
        manifest=manifest,
        schema=schema,
        coverage_agency=coverage_agency,
        coverage_agency_year=coverage_agency_year,
        distribution=distribution,
        top_100=top_100,
        near_cap=near_cap,
        anomalies=anomalies_output,
        anomaly_counts=anomaly_counts,
        trajectory=trajectory,
        crosscheck_summary=crosscheck_summary,
        repeat_proxy_summary=repeat_proxy_summary,
        repeat_proxy_bands=repeat_proxy_bands,
        repeat_proxy_sensitivity=repeat_proxy_sensitivity,
        phase1_agency_proxy=phase1_agency_proxy,
        figure_path=output_paths.figure,
    )
    output_paths.markdown.write_text(markdown, encoding="utf-8")

    print(f"Wrote schema: {output_paths.csv('schema')}")
    print(f"Wrote coverage: {output_paths.csv('employee_coverage_by_agency_year')}")
    print(f"Wrote distribution: {output_paths.csv('distribution_summary')}")
    print(f"Wrote top 100: {output_paths.csv('top_100_firms')}")
    print(f"Wrote near-cap band: {output_paths.csv('near_cap_band_firms')}")
    print(f"Wrote anomalies: {output_paths.csv('anomalies_over_500')}")
    print(f"Wrote trajectory: {output_paths.csv('trajectory_multi_award_firms')}")
    print(f"Wrote cross-check summary: {output_paths.csv('crosscheck_summary')}")
    print(f"Wrote repeat-award firms: {output_paths.csv('repeat_award_proxy_firms')}")
    print(f"Wrote repeat-award summary: {output_paths.csv('repeat_award_proxy_summary')}")
    print(f"Wrote repeat-award bands: {output_paths.csv('repeat_award_proxy_by_headcount_band')}")
    print(f"Wrote repeat-award sensitivity: {output_paths.csv('repeat_award_proxy_sensitivity')}")
    print(f"Wrote Phase I agency proxy: {output_paths.csv('phase1_repeat_proxy_by_agency')}")
    print(f"Wrote figure: {output_paths.figure}")
    print(f"Wrote readout: {output_paths.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
