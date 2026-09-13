#!/usr/bin/env python3
"""Compute bootstrap intervals for two Form D leverage-ratio interpretations.

The ``form-d-fundraising`` study is currently retired and its materialization
gate is closed. This command refuses to run while that gate is closed and also
refuses unversioned or stale match tiers. Historical v1 headline values are not
defaults or validation targets.

A second interpretation — the **per-matched-firm** leverage — divides Form D $
only by the SBIR $ of firms that actually match in Form D. These two ratios
answer different questions:

- **Program-level:**
  Numerator = sum of Form D ``total_amount_sold`` from matched-cohort firms
  (after year + industry filters).
  Denominator = sum of ALL federal SBIR ``Award Amount`` in the year window
  (across the entire 219K-award bulk file, NOT just matched firms).
  Interpretation: "What fraction of total SBIR program $ is followed by
  Form-D-detected private capital across the matched-firm cohort?"

- **Per-matched-firm:**
  Numerator = same Form D total as above.
  Denominator = sum of SBIR award $ ONLY for firms in the matched cohort
  (inner join on company name).
  Interpretation: "For SBIR awardees who go on to raise Form-D-detected
  private capital, what's their leverage per SBIR dollar received?"

Bootstrap methodology:
- Resampling unit: firm. Each iteration draws N firms with replacement
  from the matched cohort (N = cohort size), then recomputes both ratios.
- For the program-level ratio, the denominator is held fixed at the
  pre-computed program total. Only the numerator is resampled, since
  the denominator does not depend on which firms are in the matched cohort.
- For the per-matched-firm ratio, both numerator and denominator depend
  on the resample; both move together.

Cohort definitions and filters:
- Tier filter: ``high`` only and ``high + medium``
- Industry exclusions: ``EXCLUDED_INDUSTRY_GROUPS`` applied at offering level
- Year window: 2009-2024 (excludes 2025 partial year)

Inputs:
  data/form_d_details.jsonl       (Form D matches with tier, offerings)
  data/raw/sbir/award_data.csv    (SBIR.gov bulk awards, 219K rows)

Outputs (default):
  reports/ml/form_d_leverage_ci.json   (full bootstrap results)
  reports/ml/form_d_leverage_ci.md     (human-readable summary)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_VERSION,
    require_form_d_tier_rule,
)
from sbir_etl.quality.study_manifest import load_study_manifest


YEAR_MIN = 2009
YEAR_MAX = 2024
STUDY_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "studies" / "form-d-fundraising" / "study.yaml"
)

EXCLUDED_INDUSTRY_GROUPS = frozenset(
    {
        "Insurance",
        "Lodging and Conventions",
        "Other Travel",
        "Pooled Investment Fund",
        "Restaurants",
        "Retailing",
        "Tourism and Travel Services",
    }
)


def _norm_name(s: str | None) -> str:
    return (s or "").strip().upper()


def _parse_amount(s: str | None) -> float | None:
    """Parse SBIR/Form D dollar amount strings defensively.

    SBIR.gov bulk file historically uses plain numeric strings, but other
    sources (and older bulk exports) include leading ``$`` and thousands-
    separator commas. Match the convention in
    ``sbir_etl/enrichers/award_history.py`` and ``inflation_adjuster.py``
    by stripping both before float-converting. Returns None on parse
    failure so the caller can decide whether to skip or zero-fill.
    """
    if s is None:
        return None
    cleaned = str(s).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def require_materialization_allowed(path: Path = STUDY_MANIFEST_PATH) -> None:
    """Fail closed when the study contract does not authorize a result run."""

    manifest = load_study_manifest(path)
    if manifest.materialization.allowed:
        return
    blockers = "; ".join(manifest.materialization.blockers)
    raise RuntimeError(f"Study {manifest.study_id!r} materialization is blocked: {blockers}")


def load_form_d_per_firm(
    path: Path,
    year_min: int,
    year_max: int,
    *,
    expected_rule_version: str = FORM_D_TIER_RULE_VERSION,
) -> dict[str, dict[str, Any]]:
    """Aggregate Form D ``total_amount_sold`` per firm with year + industry filters."""
    per_firm: dict[str, dict[str, Any]] = {}
    for line in open(path):
        r = json.loads(line)
        name = _norm_name(r.get("company_name"))
        confidence = require_form_d_tier_rule(
            r.get("match_confidence"),
            expected_rule_version=expected_rule_version,
            context=f"Form D record {name or '<unnamed>'!r}",
        )
        tier = confidence.get("tier")
        if not name or not tier:
            continue
        raised = 0.0
        n_off = 0
        for off in r.get("offerings", []):
            ig = off.get("industry_group") or ""
            if ig in EXCLUDED_INDUSTRY_GROUPS:
                continue
            fdate = off.get("filing_date") or ""
            fyear = int(fdate[:4]) if fdate[:4].isdigit() else None
            if fyear is None or fyear < year_min or fyear > year_max:
                continue
            amt = off.get("total_amount_sold") or 0.0
            try:
                raised += float(amt)
            except (TypeError, ValueError):
                continue
            n_off += 1
        per_firm[name] = {"raised": raised, "tier": tier, "n_offerings": n_off}

    print(f"  Form D firms loaded: {len(per_firm):,}", file=sys.stderr)
    return per_firm


def load_sbir_program_and_per_firm(
    path: Path, year_min: int, year_max: int
) -> tuple[float, dict[str, dict[str, Any]], dict[str, float]]:
    """Returns (program_total_$, per_firm_dict, per_agency_program_total)."""
    program_total = 0.0
    per_firm: dict[str, dict[str, Any]] = {}
    per_agency: dict[str, float] = defaultdict(float)

    with open(path) as f:
        for row in csv.DictReader(f):
            name = _norm_name(row.get("Company"))
            try:
                year = int(row.get("Award Year") or 0)
            except ValueError:
                continue
            if year < year_min or year > year_max:
                continue
            amt = _parse_amount(row.get("Award Amount"))
            if amt is None or amt <= 0:
                continue
            agency = (row.get("Agency") or "Unknown").strip()
            program_total += amt
            per_agency[agency] += amt
            if not name:
                continue
            entry = per_firm.setdefault(name, {"award_total": 0.0, "agencies": defaultdict(float)})
            entry["award_total"] += amt
            entry["agencies"][agency] += amt

    for e in per_firm.values():
        if e["agencies"]:
            e["dominant_agency"] = max(e["agencies"].items(), key=lambda kv: kv[1])[0]
            e["agencies"] = dict(e["agencies"])
        else:
            e["dominant_agency"] = "Unknown"

    print(
        f"  SBIR program total: ${program_total / 1e9:.2f}B  "
        f"({len(per_firm):,} firms, {len(per_agency)} agencies)",
        file=sys.stderr,
    )
    return program_total, per_firm, dict(per_agency)


def build_cohort(
    form_d: dict[str, dict[str, Any]], sbir: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Left-join: keep ALL Form D matches; attach SBIR info where available.

    The published doc's program-level ratio includes Form D activity from
    matched firms regardless of whether the firm has SBIR awards in the
    year window (a firm matched on a 2005 SBIR award still counts its
    2015 Form D filing). This matches that semantic.

    Firms without SBIR awards in window get ``award_total = 0`` and
    ``dominant_agency = None``. They contribute to the program-level
    numerator and to the all-matched cohort sizing. They are excluded
    from per-agency cohorts (no dominant agency). The per-matched-firm
    ratio is only computed on the inner-joined subset
    (``has_sbir_in_window=True``) because mixing time-window semantics
    in the per-firm ratio (Form D from all matched, SBIR from the
    subset) would produce a hybrid number that doesn't cleanly answer
    either of the framing questions in the published doc.
    """
    cohort = []
    for name, fd in form_d.items():
        sb = sbir.get(name)
        cohort.append(
            {
                "name": name,
                "raised": fd["raised"],
                "tier": fd["tier"],
                "award_total": (sb["award_total"] if sb else 0.0),
                "dominant_agency": (sb["dominant_agency"] if sb else None),
                "has_sbir_in_window": (sb is not None and sb["award_total"] > 0),
            }
        )
    n_matched = sum(1 for r in cohort if r["has_sbir_in_window"])
    print(
        f"  Cohort: {len(cohort):,} Form D matches "
        f"({n_matched:,} have SBIR awards in window; {len(cohort) - n_matched:,} do not)",
        file=sys.stderr,
    )
    return cohort


def bootstrap_two_views(
    raised: np.ndarray,
    sbir_matched: np.ndarray,
    program_denominator: float,
    n_iter: int,
    rng: np.random.Generator,
    compute_per_firm: bool = True,
) -> dict[str, Any]:
    """Bootstrap program-level and (optionally) per-matched-firm ratios.

    Args:
      raised: Per-firm Form D dollars (cohort length N).
      sbir_matched: Per-firm SBIR dollars from the same N firms. Used as
        denominator for the per-matched-firm ratio. Should be sums of
        ONLY in-window SBIR (otherwise per-firm ratio is undefined for
        zero-SBIR firms).
      program_denominator: Fixed total program SBIR $ in window.
      n_iter: Bootstrap iterations.
      rng: Seeded numpy Generator.
      compute_per_firm: If False, the per-matched-firm ratio is omitted
        (used for the all-matched cohort, where zero-SBIR firms would
        make per-firm semantics a meaningless hybrid).
    """
    n = len(raised)
    out: dict[str, Any] = {
        "n_firms": int(n),
        "raised_total_usd": float(raised.sum()),
        "matched_sbir_total_usd": float(sbir_matched.sum()),
        "program_sbir_total_usd": float(program_denominator),
        "bootstrap_iterations": n_iter,
    }
    if n == 0:
        out["program_level"] = _zero_result()
        if compute_per_firm:
            out["per_matched_firm"] = _zero_result()
        return out

    out["program_level"] = {
        "point_estimate": float(raised.sum() / program_denominator)
        if program_denominator > 0
        else 0.0
    }
    if compute_per_firm:
        out["per_matched_firm"] = {
            "point_estimate": float(raised.sum() / sbir_matched.sum())
            if sbir_matched.sum() > 0
            else 0.0
        }

    program_ratios = np.empty(n_iter)
    perfirm_ratios = np.empty(n_iter) if compute_per_firm else None
    for i in range(n_iter):
        idx = rng.integers(0, n, size=n)
        raised_sum = raised[idx].sum()
        program_ratios[i] = (raised_sum / program_denominator) if program_denominator > 0 else 0.0
        if compute_per_firm:
            sbir_sum = sbir_matched[idx].sum()
            perfirm_ratios[i] = (raised_sum / sbir_sum) if sbir_sum > 0 else 0.0

    out["program_level"].update(
        {
            "median": float(np.median(program_ratios)),
            "ci_lo": float(np.percentile(program_ratios, 2.5)),
            "ci_hi": float(np.percentile(program_ratios, 97.5)),
        }
    )
    if compute_per_firm:
        out["per_matched_firm"].update(
            {
                "median": float(np.median(perfirm_ratios)),
                "ci_lo": float(np.percentile(perfirm_ratios, 2.5)),
                "ci_hi": float(np.percentile(perfirm_ratios, 97.5)),
            }
        )
    return out


def _zero_result() -> dict[str, float]:
    return {"point_estimate": 0.0, "median": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}


def cohort_arrays(
    cohort: list[dict[str, Any]],
    tier_filter: set[str],
    require_sbir: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    rows = [
        r
        for r in cohort
        if r["tier"] in tier_filter and (not require_sbir or r["has_sbir_in_window"])
    ]
    raised = np.array([r["raised"] for r in rows], dtype=float)
    sbir = np.array([r["award_total"] for r in rows], dtype=float)
    return raised, sbir


def by_agency(
    cohort: list[dict[str, Any]],
    tier_filter: set[str],
    agency_program_totals: dict[str, float],
    n_iter: int,
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Per-dominant-agency bootstrap. Requires firms have SBIR awards in window
    (otherwise no dominant_agency is assigned). Uses per-agency program total
    as denominator for program-level ratio."""
    bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in cohort:
        if r["tier"] in tier_filter and r["has_sbir_in_window"] and r["dominant_agency"]:
            bucket[r["dominant_agency"]].append(r)

    results = []
    for agency, rows in bucket.items():
        raised = np.array([r["raised"] for r in rows], dtype=float)
        sbir = np.array([r["award_total"] for r in rows], dtype=float)
        program = agency_program_totals.get(agency, 0.0)
        if program == 0:
            continue
        res = bootstrap_two_views(raised, sbir, program, n_iter, rng)
        res["agency"] = agency
        res["n_with_form_d"] = int((raised > 0).sum())
        results.append(res)

    results.sort(key=lambda r: -r["program_sbir_total_usd"])
    return results


def write_markdown(snapshot: dict[str, Any], path: Path) -> None:
    lines = [
        "# Form D leverage ratio — bootstrap intervals",
        "",
        f"**Source:** {snapshot['form_d_path']} + {snapshot['sbir_path']}",
        f"**Form D tier rule:** `{snapshot['form_d_tier_rule_version']}`",
        f"**Year window:** {snapshot['year_min']}-{snapshot['year_max']}",
        f"**Bootstrap iterations:** {snapshot['bootstrap_iterations']:,}",
        "**Resampling unit:** firm",
        f"**RNG seed:** {snapshot['seed']}",
        "",
        "> These intervals cover firm resampling only. They do not validate match identity, ",
        "> same-filing corroboration, CIK aggregation, Form D reporting, or missing private capital.",
        "",
        "## Two ratio interpretations",
        "",
        "- **Program-level:** Form D dollars divided by all SBIR dollars in the window.",
        "- **Per-matched-firm:** Form D dollars divided by in-window SBIR dollars for matched firms.",
        "",
        f"Program SBIR denominator: **${snapshot['program_total_sbir_usd'] / 1e9:.2f}B**.",
        "",
        "## All matched records",
        "",
        "| Cohort | Firms | Form D $ | Program-level ratio (95% bootstrap interval) |",
        "|---|---:|---:|---:|",
    ]
    for key, label in [
        ("high_only_all_matched", "High only"),
        ("high_plus_medium_all_matched", "High + medium"),
    ]:
        result = snapshot[key]
        program = result["program_level"]
        lines.append(
            f"| {label} | {result['n_firms']:,} | ${result['raised_total_usd'] / 1e9:.2f}B | "
            f"{program['point_estimate']:.3f}x "
            f"[{program['ci_lo']:.3f}, {program['ci_hi']:.3f}] |"
        )

    lines.extend(
        [
            "",
            "## Records with in-window SBIR awards",
            "",
            ("| Cohort | Firms | Form D $ | Matched SBIR $ | Program-level | Per-matched-firm |"),
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for key, label in [
        ("high_only_sbir_in_window", "High only"),
        ("high_plus_medium_sbir_in_window", "High + medium"),
    ]:
        result = snapshot[key]
        program = result["program_level"]
        per_firm = result["per_matched_firm"]
        lines.append(
            f"| {label} | {result['n_firms']:,} | ${result['raised_total_usd'] / 1e9:.2f}B | "
            f"${result['matched_sbir_total_usd'] / 1e9:.2f}B | "
            f"{program['point_estimate']:.3f}x "
            f"[{program['ci_lo']:.3f}, {program['ci_hi']:.3f}] | "
            f"{per_firm['point_estimate']:.3f}x "
            f"[{per_firm['ci_lo']:.3f}, {per_firm['ci_hi']:.3f}] |"
        )

    lines.extend(
        [
            "",
            "## Per-agency high-tier results",
            "",
            "Each firm is assigned to its dominant SBIR agency by award dollars.",
            "",
            (
                "| Agency | Firms (positive Form D) | Agency SBIR $B | Form D $B | "
                "Program-level | Per-matched-firm |"
            ),
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for result in snapshot["by_agency_high_only"]:
        program = result["program_level"]
        per_firm = result["per_matched_firm"]
        lines.append(
            f"| {result['agency']} | {result['n_firms']:,} ({result['n_with_form_d']:,}) | "
            f"{result['program_sbir_total_usd'] / 1e9:.2f} | "
            f"{result['raised_total_usd'] / 1e9:.2f} | "
            f"{program['point_estimate']:.3f}x "
            f"[{program['ci_lo']:.3f}, {program['ci_hi']:.3f}] | "
            f"{per_firm['point_estimate']:.3f}x "
            f"[{per_firm['ci_lo']:.3f}, {per_firm['ci_hi']:.3f}] |"
        )

    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- Form D amounts are self-reported and are not verified by the SEC.",
            "- The intervals do not include identity or amount-reporting error.",
            "- A company-level confidence record may pool signals across filings or CIKs.",
            "- Non-detection is not zero private capital.",
            "- Program-level and per-matched-firm ratios answer different questions.",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--form-d-path", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument("--sbir-path", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--year-min", type=int, default=YEAR_MIN)
    parser.add_argument("--year-max", type=int, default=YEAR_MAX)
    parser.add_argument("--n-iter", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-json", type=Path, default=Path("reports/ml/form_d_leverage_ci.json")
    )
    parser.add_argument("--output-md", type=Path, default=Path("reports/ml/form_d_leverage_ci.md"))
    args = parser.parse_args()

    require_materialization_allowed()

    if not args.form_d_path.exists() or not args.sbir_path.exists():
        print("ERROR: input file(s) not found", file=sys.stderr)
        return 2

    print("Loading data...", file=sys.stderr)
    form_d = load_form_d_per_firm(args.form_d_path, args.year_min, args.year_max)
    program_total, sbir_per_firm, agency_program = load_sbir_program_and_per_firm(
        args.sbir_path, args.year_min, args.year_max
    )
    cohort = build_cohort(form_d, sbir_per_firm)

    rng = np.random.default_rng(args.seed)

    print(f"\nBootstrapping with {args.n_iter:,} iterations...", file=sys.stderr)

    # All-matched cohort: program-level only. A per-firm ratio here would be a
    # hybrid that mixes time-window semantics; see build_cohort's docstring.
    raised_h, sbir_h = cohort_arrays(cohort, {"high"}, require_sbir=False)
    high_only_program = bootstrap_two_views(
        raised_h, sbir_h, program_total, args.n_iter, rng, compute_per_firm=False
    )

    raised_hm, sbir_hm = cohort_arrays(cohort, {"high", "medium"}, require_sbir=False)
    h_plus_m_program = bootstrap_two_views(
        raised_hm, sbir_hm, program_total, args.n_iter, rng, compute_per_firm=False
    )

    # Inner-join cohort: program-level AND per-matched-firm
    raised_h_inner, sbir_h_inner = cohort_arrays(cohort, {"high"}, require_sbir=True)
    high_only_perfirm = bootstrap_two_views(
        raised_h_inner, sbir_h_inner, program_total, args.n_iter, rng
    )

    raised_hm_inner, sbir_hm_inner = cohort_arrays(cohort, {"high", "medium"}, require_sbir=True)
    h_plus_m_perfirm = bootstrap_two_views(
        raised_hm_inner, sbir_hm_inner, program_total, args.n_iter, rng
    )

    per_agency = by_agency(cohort, {"high"}, agency_program, args.n_iter, rng)

    snapshot = {
        "schema_version": "4",
        "form_d_tier_rule_version": FORM_D_TIER_RULE_VERSION,
        "form_d_path": str(args.form_d_path),
        "sbir_path": str(args.sbir_path),
        "year_min": args.year_min,
        "year_max": args.year_max,
        "bootstrap_iterations": args.n_iter,
        "seed": args.seed,
        "program_total_sbir_usd": program_total,
        "high_only_all_matched": high_only_program,
        "high_plus_medium_all_matched": h_plus_m_program,
        "high_only_sbir_in_window": high_only_perfirm,
        "high_plus_medium_sbir_in_window": h_plus_m_perfirm,
        "by_agency_high_only": per_agency,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(snapshot, f, indent=2)
    write_markdown(snapshot, args.output_md)

    # Quick console summary
    for label, key in [
        ("High only (all matched, doc cohort)", "high_only_all_matched"),
        ("High + Medium (all matched, doc cohort)", "high_plus_medium_all_matched"),
        ("High only (SBIR in window, per-firm)", "high_only_sbir_in_window"),
        ("High + Medium (SBIR in window, per-firm)", "high_plus_medium_sbir_in_window"),
    ]:
        r = snapshot[key]
        pl = r["program_level"]
        print(f"\n  {label} (n={r['n_firms']:,}):", file=sys.stderr)
        print(
            f"    program-level: {pl['point_estimate']:.3f}x [{pl['ci_lo']:.3f}, {pl['ci_hi']:.3f}]",
            file=sys.stderr,
        )
        if "per_matched_firm" in r:
            pf = r["per_matched_firm"]
            print(
                f"    per-firm:      {pf['point_estimate']:.3f}x [{pf['ci_lo']:.3f}, {pf['ci_hi']:.3f}]",
                file=sys.stderr,
            )

    print(f"\nWrote {args.output_json} and {args.output_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
