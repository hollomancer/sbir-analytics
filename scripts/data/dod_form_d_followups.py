#!/usr/bin/env python3
"""DoD Form D leverage — follow-ups from PR #342 deferred items.

The Branch decomposition in
``docs/research/dod-form-d-leverage-deep-dive.md`` flagged four
follow-up items. The FPDS substitution test (item 1) requires fresh
USAspending pulls and is left as separate-PR work. This script
implements the three computational items:

**Item 2 — Per-firm leverage decomposition.** The DoD decomposition
attributed each firm to its dominant Branch but used the Branch's
program total as the denominator. That produced a methodology caveat
in Decomposition 4 about multi-agency firms being artificially deflated
against the DoD denominator. This script resolves it by computing per-
firm leverage (Form D $ / firm's own DoD SBIR $) and aggregating by
Branch with median/mean across firms. This is comparable across firms
and removes the multi-agency denominator artifact.

**Item 3 — Time-series Branch decomposition.** Was Air Force's high
2.12x leverage always there, or is it a recent post-AFWERX phenomenon?
This script computes per-(Branch, Year) program-level ratios from
2009 to 2024 and surfaces whether leverage trends are stable or
emerging.

**Item 4 — Navy acquirer-type analysis.** PR #342 found that Navy is
the only DoD branch where M&A rate exceeds Form D rate, suggesting
acquisition substitutes for private capital. If Navy firms are
predominantly acquired by *defense primes* (Lockheed, Northrop,
L3Harris, Leidos, CACI, Kratos, Mercury, Teledyne), that's the
"Navy commercializes via FPDS-adjacent acquisition" pattern. If
they're acquired by commercial buyers, it's a different story. This
script classifies Navy SBIR firm acquirers by type and compares
against Air Force as a control.

Inputs:
  data/form_d_details.jsonl
  data/raw/sbir/award_data.csv
  data/sbir_ma_events.jsonl

Outputs (default — gitignored):
  reports/ml/dod_form_d_followups.json
  reports/ml/dod_form_d_followups.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
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


# Acquirer-type lexicon for Item 4. Patterns drawn from the observed
# Navy + Air Force acquirer lists in sbir_ma_events.jsonl plus the
# canonical DoD-prime / financial-sponsor name catalogs.
#
# Defense primes split into two groups:
# - PREFIX patterns: matched against the start of the acquirer name OR
#   immediately after a non-alpha character (handles "KBR," "KBR-Wyle"
#   etc. without false-positive matches against "Sebkbright" or similar)
# - SUBSTRING patterns: matched anywhere (multi-word brand names that
#   don't have substring collisions)
import re

_DEFENSE_PRIME_PREFIXES = frozenset(
    {"KBR", "HII", "SAIC", "BAE", "L3", "L-3", "CACI"}
)
_DEFENSE_PRIME_SUBSTRINGS = frozenset(
    {
        "LOCKHEED MARTIN", "NORTHROP GRUMMAN", "RAYTHEON", "BOEING",
        "GENERAL DYNAMICS", "BAE SYSTEMS", "L3HARRIS",
        "L3 TECHNOLOGIES", "LEIDOS", "KRATOS", "MERCURY SYSTEMS",
        "TELEDYNE", "BOOZ ALLEN", "PARSONS CORP",
        "MAXAR", "ENGILITY", "PERSPECTA", "SCIENCE APPLICATIONS",
        "ELBIT", "RAFAEL ", "TEXTRON", "HUNTINGTON INGALLS",
        "CURTISS-WRIGHT", "MANTECH", "AECOM", "AMENTUM", "DXC TECHNOLOGY",
        "PEROT SYSTEMS", "MOOG INC", "TRANSDIGM", "HONEYWELL",
    }
)
# Compiled once for speed: word-boundary match for the prefix-style names.
_DEFENSE_PRIME_PREFIX_RE = re.compile(
    r"(?:^|[^A-Z])(" + "|".join(re.escape(p) for p in _DEFENSE_PRIME_PREFIXES) + r")(?:[^A-Z]|$)"
)

# Financial-sponsor patterns. Avoid "HOLDINGS" alone because many real
# operating companies use it ("Ortho Clinical Diagnostics Holdings",
# "Alarm.com Holdings"). Keep narrow markers that genuinely indicate
# investment vehicles or SPACs.
FINANCIAL_SPONSOR_PATTERNS = frozenset(
    {
        " CAPITAL ", " CAPITAL,", " PARTNERS", "BDC",
        "PRIVATE EQUITY", "VENTURES",
        "MERGER SUB", "ACQUISITION CORP", "SPAC ", "FINANCE CORP",
        "HORIZON TECHNOLOGY FINANCE", "HERCULES CAPITAL",
        "GOLUB CAPITAL", "CHURCHILL CAPITAL",
    }
)


def classify_acquirer(name: str | None) -> str:
    """Classify an acquirer string into one of:
    'defense_prime' | 'financial_sponsor' | 'commercial' | 'unknown'.
    """
    if not name:
        return "unknown"
    n = name.upper()
    # Defense primes take priority (most informative)
    if any(p in n for p in _DEFENSE_PRIME_SUBSTRINGS):
        return "defense_prime"
    if _DEFENSE_PRIME_PREFIX_RE.search(n):
        return "defense_prime"
    # Financial sponsor markers
    if any(p in n for p in FINANCIAL_SPONSOR_PATTERNS):
        return "financial_sponsor"
    return "commercial"


def _norm_name(s: str | None) -> str:
    return (s or "").strip().upper()


def _parse_amount(s: str | None) -> float | None:
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
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int], float]]:
    """Per-firm SBIR aggregates (DoD only) + per-(branch, year) totals.

    Returns:
      per_firm: name → {total, dod_dollars, dod_dollars_by_year, branches,
                        dominant_dod_branch, dominant_branch_dollars}
      program_by_branch_year: (branch, year) → $ total
    """
    per_firm: dict[str, dict[str, Any]] = {}
    program_by_branch_year: dict[tuple[str, int], float] = defaultdict(float)

    with open(path) as f:
        for row in csv.DictReader(f):
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
            name = _norm_name(row.get("Company"))
            if agency == DOD_AGENCY:
                program_by_branch_year[(branch, year)] += amt
            if not name:
                continue
            entry = per_firm.setdefault(
                name,
                {
                    "total": 0.0,
                    "dod_dollars": 0.0,
                    "dod_dollars_by_year": defaultdict(float),
                    "branches": defaultdict(float),
                    "branches_by_year": defaultdict(lambda: defaultdict(float)),
                },
            )
            entry["total"] += amt
            if agency == DOD_AGENCY:
                entry["dod_dollars"] += amt
                entry["dod_dollars_by_year"][year] += amt
                entry["branches"][branch] += amt
                entry["branches_by_year"][branch][year] += amt

    for e in per_firm.values():
        if e["branches"]:
            e["dominant_dod_branch"] = max(e["branches"].items(), key=lambda kv: kv[1])[0]
            e["dominant_branch_dollars"] = e["branches"][e["dominant_dod_branch"]]
        else:
            e["dominant_dod_branch"] = None
            e["dominant_branch_dollars"] = 0.0
        # Convert defaultdicts so the snapshot serializes cleanly
        e["branches"] = dict(e["branches"])
        e["dod_dollars_by_year"] = dict(e["dod_dollars_by_year"])
        e["branches_by_year"] = {b: dict(yy) for b, yy in e["branches_by_year"].items()}

    return per_firm, dict(program_by_branch_year)


def load_form_d_per_firm(
    path: Path, year_min: int, year_max: int
) -> tuple[dict[str, float], dict[str, dict[int, float]]]:
    """Per-firm Form D total + per-firm-per-year breakdown (high tier only).

    Defensive: skips malformed JSON lines and records missing
    company_name / match_confidence.tier, matching the convention in
    bootstrap_form_d_leverage_ci.py.
    """
    per_firm: dict[str, float] = {}
    per_firm_year: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for line in open(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = _norm_name(r.get("company_name"))
        tier = (r.get("match_confidence") or {}).get("tier")
        if not name or tier != "high":
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
                amt_f = float(amt)
                raised += amt_f
                per_firm_year[name][fyear] += amt_f
            except (TypeError, ValueError):
                continue
        per_firm[name] = raised
    return per_firm, {k: dict(v) for k, v in per_firm_year.items()}


def item_2_per_firm_leverage_by_branch(
    sbir_firms: dict[str, dict[str, Any]],
    fd_firms: dict[str, float],
    min_n_firms: int = 10,
) -> list[dict[str, Any]]:
    """Per-firm leverage (Form D $ / firm DoD SBIR $) aggregated by Branch.

    For each firm matched in Form D with at least some DoD SBIR in
    window, compute the firm's per-firm leverage ratio using its OWN
    DoD-side SBIR $ as denominator. Aggregate by dominant Branch with
    count, mean, median, and 25th/75th percentiles.
    """
    firm_ratios_by_branch: dict[str, list[float]] = defaultdict(list)
    firm_count_with_fd_by_branch: dict[str, int] = defaultdict(int)

    for name, raised in fd_firms.items():
        sbir = sbir_firms.get(name)
        if not sbir or sbir["dod_dollars"] <= 0:
            continue
        branch = sbir["dominant_dod_branch"]
        if branch is None:
            continue
        # Per-firm leverage uses the firm's TOTAL DoD SBIR (across branches),
        # since the Form D total isn't branch-attributed.
        ratio = raised / sbir["dod_dollars"]
        firm_ratios_by_branch[branch].append(ratio)
        if raised > 0:
            firm_count_with_fd_by_branch[branch] += 1

    out = []
    for branch, ratios in firm_ratios_by_branch.items():
        if len(ratios) < min_n_firms:
            continue
        arr = np.array(ratios)
        out.append(
            {
                "branch": branch,
                "n_firms": len(ratios),
                "n_with_form_d_raise": firm_count_with_fd_by_branch[branch],
                "mean_per_firm_leverage": float(arr.mean()),
                "median_per_firm_leverage": float(np.median(arr)),
                "p25_per_firm_leverage": float(np.percentile(arr, 25)),
                "p75_per_firm_leverage": float(np.percentile(arr, 75)),
            }
        )
    out.sort(key=lambda r: -r["n_firms"])
    return out


def item_3_time_series_branch_ratios(
    sbir_firms: dict[str, dict[str, Any]],
    fd_per_firm_year: dict[str, dict[int, float]],
    program_by_branch_year: dict[tuple[str, int], float],
    year_min: int,
    year_max: int,
    min_program_usd: float = 100e6,
) -> dict[str, list[dict[str, Any]]]:
    """Per-(Branch, Year) program-level ratios for major branches.

    Numerator: sum across firms whose dominant DoD Branch is X, of their
    Form D raises in year Y.
    Denominator: total DoD SBIR program $ in Branch X in year Y.
    """
    # Total program $ per branch across all years — for filtering
    branch_totals: dict[str, float] = defaultdict(float)
    for (b, y), v in program_by_branch_year.items():
        branch_totals[b] += v
    major_branches = {b for b, t in branch_totals.items() if t >= min_program_usd}

    # Build per-(branch, year) numerator from Form D
    fd_by_branch_year: dict[tuple[str, int], float] = defaultdict(float)
    for name, year_dict in fd_per_firm_year.items():
        sbir = sbir_firms.get(name)
        if not sbir or sbir["dominant_dod_branch"] not in major_branches:
            continue
        branch = sbir["dominant_dod_branch"]
        for year, amt in year_dict.items():
            fd_by_branch_year[(branch, year)] += amt

    out: dict[str, list[dict[str, Any]]] = {}
    for branch in sorted(major_branches, key=lambda b: -branch_totals[b]):
        rows = []
        for year in range(year_min, year_max + 1):
            program = program_by_branch_year.get((branch, year), 0.0)
            fd = fd_by_branch_year.get((branch, year), 0.0)
            ratio = (fd / program) if program > 0 else 0.0
            rows.append(
                {
                    "year": year,
                    "program_usd": program,
                    "form_d_usd": fd,
                    "ratio": ratio,
                }
            )
        out[branch] = rows
    return out


def item_4_navy_acquirer_analysis(
    sbir_firms: dict[str, dict[str, Any]],
    ma_events_path: Path,
    target_branches: list[str] | None = None,
) -> dict[str, Any]:
    """Classify acquirers of SBIR firms with the given dominant DoD Branch.

    Default: ['Navy', 'Air Force'] for Navy-vs-Air-Force comparison
    (Air Force as a control, since it has very different Form D /
    leverage characteristics).
    """
    if target_branches is None:
        target_branches = ["Navy", "Air Force"]
    firms_by_branch: dict[str, set[str]] = {
        b: {name for name, e in sbir_firms.items() if e.get("dominant_dod_branch") == b}
        for b in target_branches
    }

    results: dict[str, Any] = {}
    for branch in target_branches:
        branch_firms = firms_by_branch[branch]
        type_counts: Counter[str] = Counter()
        type_acquirers: dict[str, list[str]] = defaultdict(list)
        n_events = 0
        n_unique_firms_with_acquirer = set()

        for line in open(ma_events_path):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = _norm_name(r.get("company_name"))
            if name not in branch_firms:
                continue
            n_events += 1
            acq = r.get("acquirer")
            if not acq:
                continue
            n_unique_firms_with_acquirer.add(name)
            kind = classify_acquirer(acq)
            type_counts[kind] += 1
            type_acquirers[kind].append(acq)

        # Most common acquirers per type (for spot-checking the classification)
        top_acquirers = {
            kind: Counter(acqs).most_common(5) for kind, acqs in type_acquirers.items()
        }

        total_classified = sum(type_counts.values())
        results[branch] = {
            "n_branch_firms": len(branch_firms),
            "n_ma_events": n_events,
            "n_unique_firms_with_named_acquirer": len(n_unique_firms_with_acquirer),
            "type_counts": dict(type_counts),
            "type_pct": {
                k: (v / total_classified * 100) if total_classified > 0 else 0.0
                for k, v in type_counts.items()
            },
            "top_acquirers_by_type": {
                k: [{"acquirer": a, "n": n} for a, n in v]
                for k, v in top_acquirers.items()
            },
        }
    return results


def write_markdown(snapshot: dict[str, Any], path: Path) -> None:
    L = []
    L.append("# DoD Form D leverage — deferred follow-ups from PR #342")
    L.append("")
    L.append(f"Year window: {snapshot['year_min']}-{snapshot['year_max']}")
    L.append("")

    L.append("## Item 2 — Per-firm leverage by Branch")
    L.append("")
    L.append("Per-firm leverage = each high-tier matched firm's Form D $ divided by its OWN DoD SBIR $. Aggregates by dominant Branch. Resolves the multi-agency methodology caveat in Decomposition 4 of PR #342.")
    L.append("")
    L.append("| Branch | Firms | With Form D | Mean | Median | P25 | P75 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in snapshot["item_2_per_firm_leverage"]:
        L.append(
            f"| {r['branch']} | {r['n_firms']} | {r['n_with_form_d_raise']} | "
            f"{r['mean_per_firm_leverage']:.2f}x | {r['median_per_firm_leverage']:.2f}x | "
            f"{r['p25_per_firm_leverage']:.2f}x | {r['p75_per_firm_leverage']:.2f}x |"
        )
    L.append("")
    L.append("**Note on median vs mean.** Per-firm leverage distributions are heavily right-skewed (a handful of large-raise outliers per Branch). Median is the more representative central tendency; mean is sensitive to the top few firms.")
    L.append("")

    L.append("## Item 3 — Time-series Branch ratios")
    L.append("")
    L.append("Per-(Branch, Year) program-level ratio = sum of Form D $ from firms whose dominant Branch is X in year Y, divided by total DoD SBIR program $ in Branch X in year Y. Tests whether Branch-level leverage trends are stable or emerging.")
    L.append("")
    for branch in snapshot["item_3_time_series"]:
        L.append(f"### {branch}")
        L.append("")
        L.append("| Year | Program $M | Form D $M | Ratio |")
        L.append("|---|---|---|---|")
        rows = snapshot["item_3_time_series"][branch]
        for r in rows:
            if r["program_usd"] > 0:
                L.append(
                    f"| {r['year']} | {r['program_usd']/1e6:.0f} | {r['form_d_usd']/1e6:.0f} | "
                    f"{r['ratio']:.3f}x |"
                )
        # Compute trend
        ratios = [r["ratio"] for r in rows if r["program_usd"] > 0]
        if len(ratios) >= 5:
            early = sum(ratios[:5]) / 5
            late = sum(ratios[-5:]) / 5
            if late > early * 1.5:
                trend = f"**Increasing**: 5-yr early avg {early:.2f}x → 5-yr late avg {late:.2f}x"
            elif late < early * 0.67:
                trend = f"**Decreasing**: 5-yr early avg {early:.2f}x → 5-yr late avg {late:.2f}x"
            else:
                trend = f"Stable: 5-yr early avg {early:.2f}x, 5-yr late avg {late:.2f}x"
            L.append("")
            L.append(trend)
        L.append("")

    L.append("## Item 4 — Navy acquirer-type analysis (Air Force as control)")
    L.append("")
    L.append("Classifies acquirers of M&A-event SBIR firms into three types using substring matching against canonical name patterns: **defense_prime** (Lockheed, Northrop, L3Harris, Leidos, CACI, Kratos, KBR, BAE, etc. — short acronyms use word-boundary regex), **financial_sponsor** (narrow markers only: Capital, Partners, BDC, Acquisition Corp, plus specific named investment vehicles like Hercules Capital, Golub Capital, Churchill Capital — \"Holdings\" alone is NOT matched because too many real operating companies use it), and **commercial** (everything else). Tests whether Navy's higher M&A-than-Form-D pattern is driven by defense-prime acquisition specifically.")
    L.append("")
    for branch, r in snapshot["item_4_navy_acquirers"].items():
        L.append(f"### {branch}")
        L.append(f"- Branch firms (dominant {branch}): {r['n_branch_firms']:,}")
        L.append(f"- M&A events for these firms: {r['n_ma_events']:,}")
        L.append(f"- Events with named acquirer: {r['n_unique_firms_with_named_acquirer']:,}")
        L.append("")
        L.append("| Acquirer type | Count | Share |")
        L.append("|---|---|---|")
        for kind in ("defense_prime", "commercial", "financial_sponsor", "unknown"):
            n = r["type_counts"].get(kind, 0)
            pct = r["type_pct"].get(kind, 0.0)
            L.append(f"| {kind} | {n} | {pct:.1f}% |")
        L.append("")
        for kind in ("defense_prime", "commercial", "financial_sponsor"):
            top = r["top_acquirers_by_type"].get(kind, [])
            if top:
                L.append(f"**Top {kind} acquirers:**")
                for entry in top:
                    L.append(f"- {entry['n']} × {entry['acquirer']}")
                L.append("")

    # Interpretation
    L.append("## Interpretation")
    L.append("")
    L.append("See companion findings doc `docs/research/dod-form-d-followup-findings.md` for the narrative analysis tying these three items back to PR #342's deferred items.")
    L.append("")

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
    parser.add_argument("--output-json", type=Path, default=Path("reports/ml/dod_form_d_followups.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/ml/dod_form_d_followups.md"))
    args = parser.parse_args()

    for p in (args.form_d_path, args.sbir_path, args.ma_events_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 2

    print("Loading data...", file=sys.stderr)
    sbir_firms, program_by_branch_year = load_sbir_firm_index(
        args.sbir_path, args.year_min, args.year_max
    )
    fd_per_firm, fd_per_firm_year = load_form_d_per_firm(
        args.form_d_path, args.year_min, args.year_max
    )

    print("Item 2: per-firm leverage by Branch...", file=sys.stderr)
    item_2 = item_2_per_firm_leverage_by_branch(sbir_firms, fd_per_firm)

    print("Item 3: time-series Branch ratios...", file=sys.stderr)
    item_3 = item_3_time_series_branch_ratios(
        sbir_firms, fd_per_firm_year, program_by_branch_year, args.year_min, args.year_max
    )

    print("Item 4: Navy acquirer analysis...", file=sys.stderr)
    item_4 = item_4_navy_acquirer_analysis(sbir_firms, args.ma_events_path)

    snapshot = {
        "schema_version": "1",
        "year_min": args.year_min,
        "year_max": args.year_max,
        "item_2_per_firm_leverage": item_2,
        "item_3_time_series": item_3,
        "item_4_navy_acquirers": item_4,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(snapshot, f, indent=2)
    write_markdown(snapshot, args.output_md)

    # Console summary
    print("\n=== Item 2: Per-firm leverage by Branch (median) ===", file=sys.stderr)
    for r in item_2:
        print(f"  {r['branch'][:40]:<40} n={r['n_firms']:>4} median={r['median_per_firm_leverage']:6.2f}x  mean={r['mean_per_firm_leverage']:6.2f}x  P25-P75=[{r['p25_per_firm_leverage']:.2f}, {r['p75_per_firm_leverage']:.2f}]", file=sys.stderr)

    print("\n=== Item 4: Navy vs Air Force acquirer mix ===", file=sys.stderr)
    for b, r in item_4.items():
        print(f"  {b}: defense_prime={r['type_pct'].get('defense_prime', 0):.1f}%  commercial={r['type_pct'].get('commercial', 0):.1f}%  financial={r['type_pct'].get('financial_sponsor', 0):.1f}%", file=sys.stderr)

    print(f"\nWrote {args.output_json} and {args.output_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
