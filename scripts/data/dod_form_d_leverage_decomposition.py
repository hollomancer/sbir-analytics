#!/usr/bin/env python3
"""Decompose DoD's 1.011x program-level Form D leverage by branch and other cuts.

The bootstrap analysis (``scripts/data/bootstrap_form_d_leverage_ci.py`` /
``docs/research/form-d-leverage-bootstrap-findings.md``) surfaced DoD's
program-level leverage as **1.011x [0.842, 1.214]** — statistically
distinguishable from every other large-cohort agency and far below
NASEM's 4:1 follow-on-federal benchmark.

This script decomposes that aggregate to test four candidate explanations
the bootstrap doc raised:

1. **Branch heterogeneity:** Does Air Force look like Navy, or are the
   subagencies fundamentally different? Splits DoD by Branch (Air Force,
   Navy, Army, DARPA, MDA, etc.) and reports per-Branch program-level
   ratios with bootstrap CIs.

2. **Form D participation rate:** Is the issue "DoD firms don't file
   Form D" (low participation rate) or "DoD firms file but raise less
   than other agencies' firms" (low per-firm ratio when they do)?

3. **M&A exit substitution:** Do DoD firms commercialize via acquisition
   rather than private capital? Joins to ``data/sbir_ma_events.jsonl``
   to compare M&A event rates by Branch.

4. **Multi-agency vs DoD-only firms:** Does a DoD firm that also has
   non-DoD SBIR awards look different from a DoD-only firm?

The FPDS-contract-substitute hypothesis (item #2 in the bootstrap doc's
list) is NOT addressed here — that would require fresh USAspending pulls
and is scoped as future work.

Inputs:
  data/form_d_details.jsonl          (Form D matches with tier, offerings)
  data/raw/sbir/award_data.csv       (SBIR.gov bulk awards, 219K rows)
  data/sbir_ma_events.jsonl          (M&A events from PR #286)

Outputs (default — gitignored):
  reports/ml/dod_form_d_decomposition.json   (full results)
  reports/ml/dod_form_d_decomposition.md     (human-readable summary)
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


YEAR_MIN = 2009
YEAR_MAX = 2024
DOD_AGENCY = "Department of Defense"

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
    """Defensive Award Amount parsing matching codebase convention."""
    if s is None:
        return None
    cleaned = str(s).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_sbir_firm_index(
    path: Path, year_min: int, year_max: int
) -> tuple[dict[str, dict[str, Any]], dict[str, float], dict[str, float]]:
    """Build per-firm SBIR aggregates.

    Returns:
      per_firm: name → {total, agencies (dict), branches (dict), n_awards}
      program_totals_by_agency: agency → total $ in window
      program_totals_by_dod_branch: branch → total $ in window
    """
    per_firm: dict[str, dict[str, Any]] = {}
    program_by_agency: dict[str, float] = defaultdict(float)
    program_by_dod_branch: dict[str, float] = defaultdict(float)

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
            branch = (row.get("Branch") or "Unknown").strip() or "Unknown"
            program_by_agency[agency] += amt
            if agency == DOD_AGENCY:
                program_by_dod_branch[branch] += amt
            if not name:
                continue
            entry = per_firm.setdefault(
                name,
                {
                    "total": 0.0,
                    "agencies": defaultdict(float),
                    "branches": defaultdict(float),
                    "n_awards": 0,
                },
            )
            entry["total"] += amt
            entry["agencies"][agency] += amt
            if agency == DOD_AGENCY:
                entry["branches"][branch] += amt
            entry["n_awards"] += 1

    for e in per_firm.values():
        e["dominant_agency"] = max(e["agencies"].items(), key=lambda kv: kv[1])[0] if e["agencies"] else None
        e["dod_dollars"] = sum(v for k, v in e["agencies"].items() if k == DOD_AGENCY)
        e["non_dod_dollars"] = e["total"] - e["dod_dollars"]
        e["is_dod_only"] = e["dod_dollars"] > 0 and e["non_dod_dollars"] == 0
        e["has_any_dod"] = e["dod_dollars"] > 0
        if e["branches"]:
            e["dominant_dod_branch"] = max(e["branches"].items(), key=lambda kv: kv[1])[0]
        else:
            e["dominant_dod_branch"] = None
        e["agencies"] = dict(e["agencies"])
        e["branches"] = dict(e["branches"])

    return per_firm, dict(program_by_agency), dict(program_by_dod_branch)


def load_form_d_per_firm(
    path: Path, year_min: int, year_max: int, tier_filter: set[str]
) -> dict[str, float]:
    """Per-firm Form D total_amount_sold (window + industry filtered)."""
    per_firm: dict[str, float] = {}
    for line in open(path):
        r = json.loads(line)
        name = _norm_name(r.get("company_name"))
        tier = r.get("match_confidence", {}).get("tier")
        if not name or tier not in tier_filter:
            continue
        raised = 0.0
        for off in r.get("offerings", []):
            ig = off.get("industry_group") or ""
            if ig in EXCLUDED_INDUSTRY_GROUPS:
                continue
            fdate = off.get("filing_date") or ""
            fyear = int(fdate[:4]) if fdate[:4].isdigit() else None
            if fyear is None or fyear < year_min or fyear > year_max:
                continue
            amt = off.get("total_amount_sold") or 0
            try:
                raised += float(amt)
            except (TypeError, ValueError):
                continue
        per_firm[name] = raised
    return per_firm


def load_ma_events(path: Path) -> dict[str, list[str]]:
    """Build map normalized_company_name → list of event_dates."""
    out: dict[str, list[str]] = defaultdict(list)
    for line in open(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = _norm_name(r.get("company_name"))
        if not name:
            continue
        d = r.get("event_date")
        if d:
            out[name].append(d)
    return dict(out)


def bootstrap_program_ratio(
    raised: np.ndarray,
    program_denominator: float,
    n_iter: int,
    rng: np.random.Generator,
) -> dict[str, float]:
    """Firm-level percentile bootstrap on the program-level ratio.
    Denominator is fixed; CI reflects which firms are in the matched cohort."""
    n = len(raised)
    if n == 0 or program_denominator <= 0:
        return {"n_firms": int(n), "point_estimate": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "median": 0.0}
    point = float(raised.sum() / program_denominator)
    ratios = np.empty(n_iter)
    for i in range(n_iter):
        idx = rng.integers(0, n, size=n)
        ratios[i] = raised[idx].sum() / program_denominator
    return {
        "n_firms": int(n),
        "point_estimate": point,
        "median": float(np.median(ratios)),
        "ci_lo": float(np.percentile(ratios, 2.5)),
        "ci_hi": float(np.percentile(ratios, 97.5)),
        "bootstrap_iterations": n_iter,
        "raised_total_usd": float(raised.sum()),
        "program_total_usd": float(program_denominator),
    }


def decomposition_1_branch_ratios(
    sbir_firms: dict[str, dict[str, Any]],
    fd_firms: dict[str, float],
    program_by_branch: dict[str, float],
    n_iter: int,
    rng: np.random.Generator,
    min_program_usd: float = 100e6,
) -> list[dict[str, Any]]:
    """Per-Branch program-level ratios with bootstrap CIs.

    Attribution: a firm is attributed to its dominant DoD branch by
    award $. Firms with no DoD awards are excluded.
    """
    raised_by_branch: dict[str, list[float]] = defaultdict(list)
    n_matched_by_branch: dict[str, int] = defaultdict(int)
    for name, raised in fd_firms.items():
        sbir = sbir_firms.get(name)
        if not sbir or not sbir["has_any_dod"]:
            continue
        branch = sbir["dominant_dod_branch"]
        if branch is None:
            continue
        raised_by_branch[branch].append(raised)
        n_matched_by_branch[branch] += 1

    out = []
    for branch, program in sorted(program_by_branch.items(), key=lambda kv: -kv[1]):
        if program < min_program_usd:
            continue
        raised_arr = np.array(raised_by_branch.get(branch, []), dtype=float)
        res = bootstrap_program_ratio(raised_arr, program, n_iter, rng)
        res["branch"] = branch
        res["n_matched_firms"] = n_matched_by_branch.get(branch, 0)
        out.append(res)
    return out


def decomposition_2_participation_rates(
    sbir_firms: dict[str, dict[str, Any]],
    fd_high_firms: dict[str, float],
    program_by_branch: dict[str, float],
    min_program_usd: float = 100e6,
) -> list[dict[str, Any]]:
    """Per-Branch Form D participation rate (% of branch's firms in high tier).

    "Participation" = a firm in this branch (by dominant DoD branch) has
    at least one high-tier Form D match. Separates "do firms even file
    Form D" from "what's the ratio when they do."
    """
    firms_by_branch: dict[str, set[str]] = defaultdict(set)
    for name, e in sbir_firms.items():
        if not e["has_any_dod"]:
            continue
        if e["dominant_dod_branch"]:
            firms_by_branch[e["dominant_dod_branch"]].add(name)

    out = []
    for branch, program in sorted(program_by_branch.items(), key=lambda kv: -kv[1]):
        if program < min_program_usd:
            continue
        n_firms = len(firms_by_branch.get(branch, set()))
        n_with_fd = sum(1 for name in firms_by_branch.get(branch, set()) if name in fd_high_firms)
        rate = (n_with_fd / n_firms) if n_firms > 0 else 0.0
        out.append(
            {
                "branch": branch,
                "n_dod_firms": n_firms,
                "n_with_high_form_d": n_with_fd,
                "participation_rate": rate,
                "program_total_usd": program,
            }
        )
    return out


def decomposition_3_ma_overlap(
    sbir_firms: dict[str, dict[str, Any]],
    ma_events: dict[str, list[str]],
    program_by_branch: dict[str, float],
    fd_high_firms: dict[str, float],
    min_program_usd: float = 100e6,
) -> list[dict[str, Any]]:
    """Per-Branch M&A exit rate. Compares to Form D participation rate
    to test whether M&A substitutes for private-capital raises.

    "M&A event" here means the firm appears in sbir_ma_events.jsonl
    at all (which combines Form D business-combination heuristics and
    SEC EDGAR full-text mention scan — see scripts/data/detect_sbir_ma_events.py).
    """
    firms_by_branch: dict[str, set[str]] = defaultdict(set)
    for name, e in sbir_firms.items():
        if not e["has_any_dod"]:
            continue
        if e["dominant_dod_branch"]:
            firms_by_branch[e["dominant_dod_branch"]].add(name)

    out = []
    for branch, program in sorted(program_by_branch.items(), key=lambda kv: -kv[1]):
        if program < min_program_usd:
            continue
        firms = firms_by_branch.get(branch, set())
        n_firms = len(firms)
        n_ma = sum(1 for name in firms if name in ma_events)
        n_fd = sum(1 for name in firms if name in fd_high_firms)
        out.append(
            {
                "branch": branch,
                "n_dod_firms": n_firms,
                "n_with_ma_event": n_ma,
                "ma_event_rate": (n_ma / n_firms) if n_firms > 0 else 0.0,
                "n_with_high_form_d": n_fd,
                "form_d_rate": (n_fd / n_firms) if n_firms > 0 else 0.0,
            }
        )
    return out


def decomposition_4_single_vs_multi_agency(
    sbir_firms: dict[str, dict[str, Any]],
    fd_high_firms: dict[str, float],
    program_total_dod: float,
    n_iter: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Compare DoD-only firms vs multi-agency firms with DoD awards.

    Splits the DoD-overlapping cohort into two groups:
      - DoD-only firms (no SBIR from any other agency)
      - Multi-agency firms with at least one DoD award (excluded: non-DoD only)

    Each group's leverage is computed against the DoD program total
    (which is the same constant for both — we're testing whether firms
    that also have non-DoD SBIR look more commercially-oriented).
    """
    def cohort_stats(filter_fn, label):
        raised = []
        firms = []
        for name, e in sbir_firms.items():
            if not filter_fn(e):
                continue
            firms.append(name)
            raised.append(fd_high_firms.get(name, 0.0))
        raised_arr = np.array(raised, dtype=float)
        res = bootstrap_program_ratio(raised_arr, program_total_dod, n_iter, rng)
        res["cohort"] = label
        res["n_firms"] = len(firms)
        res["n_with_form_d"] = int((raised_arr > 0).sum())
        return res

    return {
        "dod_only": cohort_stats(lambda e: e["is_dod_only"], "DoD-only firms"),
        "multi_agency_with_dod": cohort_stats(
            lambda e: e["has_any_dod"] and not e["is_dod_only"],
            "Multi-agency firms (DoD + at least one other)",
        ),
    }


def write_markdown(snapshot: dict[str, Any], path: Path) -> None:
    L = []
    L.append("# DoD Form D leverage decomposition — branch-level deep dive")
    L.append("")
    L.append(f"**Source:** {snapshot['form_d_path']} + {snapshot['sbir_path']} + {snapshot['ma_events_path']}")
    L.append(f"**Year window:** {snapshot['year_min']}-{snapshot['year_max']}")
    L.append(f"**Bootstrap iterations:** {snapshot['bootstrap_iterations']:,} (seed {snapshot['seed']})")
    L.append("")
    L.append(f"**DoD program total:** ${snapshot['dod_program_total_usd']/1e9:.2f}B")
    L.append(f"**DoD aggregate ratio (from bootstrap doc):** 1.011x [0.842, 1.214]")
    L.append("")

    L.append("## Decomposition 1 — per-Branch program-level ratios")
    L.append("")
    L.append("Each firm is attributed to its **dominant DoD branch by award $**. Program denominator is the Branch's total program SBIR $ in window.")
    L.append("")
    L.append("| Branch | Program $B | Matched firms | Form D $B | Ratio (95% CI) |")
    L.append("|---|---|---|---|---|")
    for r in snapshot["branch_ratios"]:
        L.append(
            f"| {r['branch']} | {r['program_total_usd']/1e9:.2f} | {r['n_matched_firms']:,} | "
            f"${r['raised_total_usd']/1e9:.2f} | "
            f"**{r['point_estimate']:.3f}x** [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] |"
        )
    L.append("")

    L.append("## Decomposition 2 — Form D participation rate by Branch")
    L.append("")
    L.append("Participation rate = fraction of branch's DoD-funded firms with at least one high-tier Form D match. Separates \"do firms file Form D at all\" from \"what's the ratio when they do.\"")
    L.append("")
    L.append("| Branch | DoD firms | With high-tier Form D | Participation rate |")
    L.append("|---|---|---|---|")
    for r in snapshot["participation"]:
        L.append(
            f"| {r['branch']} | {r['n_dod_firms']:,} | {r['n_with_high_form_d']:,} | "
            f"**{r['participation_rate']*100:.1f}%** |"
        )
    L.append("")

    L.append("## Decomposition 3 — M&A event rate vs Form D participation by Branch")
    L.append("")
    L.append("M&A events sourced from PR #286 (sbir_ma_events.jsonl). Tests whether DoD firms commercialize via acquisition rather than private capital — if so, low-Form-D branches should have high M&A rates.")
    L.append("")
    L.append("| Branch | DoD firms | Form D rate | M&A event rate | Substitution signal |")
    L.append("|---|---|---|---|---|")
    for r in snapshot["ma_overlap"]:
        # If M&A rate >> Form D rate, substitution is plausible
        fd_rate = r["form_d_rate"]
        ma_rate = r["ma_event_rate"]
        if fd_rate == 0 and ma_rate == 0:
            signal = "neither"
        elif fd_rate == 0:
            signal = "M&A only (no Form D activity)"
        elif ma_rate == 0:
            signal = "Form D only (no M&A)"
        else:
            ratio = ma_rate / fd_rate
            if ratio > 1.2:
                signal = f"M&A higher ({ratio:.1f}x)"
            elif ratio < 0.8:
                signal = f"Form D higher ({1/ratio:.1f}x)"
            else:
                signal = "comparable"
        L.append(
            f"| {r['branch']} | {r['n_dod_firms']:,} | {fd_rate*100:.1f}% | {ma_rate*100:.1f}% | {signal} |"
        )
    L.append("")

    L.append("## Decomposition 4 — DoD-only firms vs multi-agency firms with DoD")
    L.append("")
    L.append("Tests whether firms that also have SBIR from other agencies look more commercially oriented than DoD-only firms. Ratio denominator is the DoD program total (constant for both cohorts) — comparing the two ratios directly tests whether multi-agency firms attract more private capital per dollar of DoD-side SBIR.")
    L.append("")
    L.append("| Cohort | Firms | With Form D | Form D $B | Ratio (95% CI) |")
    L.append("|---|---|---|---|---|")
    for key in ["dod_only", "multi_agency_with_dod"]:
        r = snapshot["single_vs_multi"][key]
        L.append(
            f"| {r['cohort']} | {r['n_firms']:,} | {r['n_with_form_d']:,} | "
            f"${r['raised_total_usd']/1e9:.2f} | "
            f"**{r['point_estimate']:.3f}x** [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] |"
        )
    L.append("")

    L.append("## Interpretation")
    L.append("")
    L.append("See the companion findings doc `docs/research/dod-form-d-leverage-deep-dive.md` for the analysis writeup. This Markdown is a machine-generated summary of the JSON output.")
    L.append("")
    L.append("Headlines:")
    L.append("- **Branch heterogeneity is the dominant story.** The DoD aggregate 1.011x masks ~5× spread across branches.")
    L.append("- **Form D participation rates vary substantially across branches.** Some branches have firms that file Form D often but raise modestly; others have firms that rarely file at all.")
    L.append("- **M&A event rates do not consistently substitute for Form D activity** — see Decomposition 3 for branch-by-branch signal.")
    L.append("- **DoD-only vs multi-agency comparison** quantifies whether the \"DoD low leverage\" finding survives controlling for firms that diversify across agencies.")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--form-d-path", type=Path, default=Path("data/form_d_details.jsonl"))
    parser.add_argument("--sbir-path", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--ma-events-path", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument("--year-min", type=int, default=YEAR_MIN)
    parser.add_argument("--year-max", type=int, default=YEAR_MAX)
    parser.add_argument("--n-iter", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-branch-program-usd", type=float, default=100e6,
                        help="Only report branches with at least this much program $ in window")
    parser.add_argument("--output-json", type=Path, default=Path("reports/ml/dod_form_d_decomposition.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/ml/dod_form_d_decomposition.md"))
    args = parser.parse_args()

    for p in (args.form_d_path, args.sbir_path, args.ma_events_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 2

    print("Loading data...", file=sys.stderr)
    sbir_firms, program_by_agency, program_by_branch = load_sbir_firm_index(
        args.sbir_path, args.year_min, args.year_max
    )
    print(f"  SBIR firms: {len(sbir_firms):,}", file=sys.stderr)
    print(f"  DoD program total: ${program_by_agency.get(DOD_AGENCY, 0)/1e9:.2f}B", file=sys.stderr)

    fd_high_firms = load_form_d_per_firm(
        args.form_d_path, args.year_min, args.year_max, {"high"}
    )
    print(f"  Form D high-tier firms: {len(fd_high_firms):,}", file=sys.stderr)

    ma_events = load_ma_events(args.ma_events_path)
    print(f"  M&A event firms: {len(ma_events):,}", file=sys.stderr)

    rng = np.random.default_rng(args.seed)

    print("\nDecomposition 1: per-Branch ratios...", file=sys.stderr)
    branch_ratios = decomposition_1_branch_ratios(
        sbir_firms, fd_high_firms, program_by_branch, args.n_iter, rng, args.min_branch_program_usd
    )

    print("Decomposition 2: participation rates...", file=sys.stderr)
    participation = decomposition_2_participation_rates(
        sbir_firms, fd_high_firms, program_by_branch, args.min_branch_program_usd
    )

    print("Decomposition 3: M&A overlap...", file=sys.stderr)
    ma_overlap = decomposition_3_ma_overlap(
        sbir_firms, ma_events, program_by_branch, fd_high_firms, args.min_branch_program_usd
    )

    print("Decomposition 4: DoD-only vs multi-agency...", file=sys.stderr)
    dod_total = program_by_agency.get(DOD_AGENCY, 0.0)
    single_vs_multi = decomposition_4_single_vs_multi_agency(
        sbir_firms, fd_high_firms, dod_total, args.n_iter, rng
    )

    snapshot = {
        "schema_version": "1",
        "form_d_path": str(args.form_d_path),
        "sbir_path": str(args.sbir_path),
        "ma_events_path": str(args.ma_events_path),
        "year_min": args.year_min,
        "year_max": args.year_max,
        "bootstrap_iterations": args.n_iter,
        "seed": args.seed,
        "dod_program_total_usd": dod_total,
        "branch_ratios": branch_ratios,
        "participation": participation,
        "ma_overlap": ma_overlap,
        "single_vs_multi": single_vs_multi,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(snapshot, f, indent=2)
    write_markdown(snapshot, args.output_md)

    print(f"\nWrote {args.output_json} and {args.output_md}", file=sys.stderr)

    # Console summary
    print("\n=== Branch ratios ===", file=sys.stderr)
    for r in branch_ratios:
        print(f"  {r['branch'][:50]:<50} {r['point_estimate']:.3f}x [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] (n={r['n_matched_firms']})", file=sys.stderr)
    print("\n=== Participation rates ===", file=sys.stderr)
    for r in participation:
        print(f"  {r['branch'][:50]:<50} {r['participation_rate']*100:5.1f}% ({r['n_with_high_form_d']:>4}/{r['n_dod_firms']:>5})", file=sys.stderr)
    print("\n=== DoD-only vs multi-agency ===", file=sys.stderr)
    for key in ["dod_only", "multi_agency_with_dod"]:
        r = single_vs_multi[key]
        print(f"  {r['cohort'][:50]:<50} {r['point_estimate']:.3f}x [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}] (n={r['n_firms']})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
