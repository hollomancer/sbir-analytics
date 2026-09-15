#!/usr/bin/env python3
"""Audit Pooled Investment Fund cross-links into the counted operating-co cohort.

The retired v1 study found cross-links between Pooled Investment Fund (PIF)
entities and operating-company SBIR matches through shared related persons or
CIKs. PIF offerings are excluded from cohort totals, but those links remain an
identity-review signal.

This script answers that question quantitatively. For each PIF-tagged
record, it finds operating-co records that share a related_person name
or CIK, classifies the resulting cross-links by the op-side tier, and
quantifies the dollar exposure as a share of the published high-only
and high+medium headlines.

It classifies each v2 high-tier cross-linked operating-company record by
the signals recorded at company-aggregate scope:

- person + ZIP;
- ZIP without a person hit;
- person + state without ZIP (valid under ``corroborated-person-v2``);
- inconsistent high rows that do not satisfy v2.

These are review profiles, not trust verdicts. Legacy confidence signals were
pooled across all filings attached to a company record and may span CIKs, so
this audit cannot prove that corroboration occurred in one filing or issuer.

Outputs (default — gitignored):
  reports/ml/form_d_pif_cross_links.json   (full audit results)
  reports/ml/form_d_pif_cross_links.md     (human-readable summary)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_VERSION,
    require_form_d_tier_rule,
)


YEAR_MIN = 2009
YEAR_MAX = 2024

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

PIF_INDUSTRY = "Pooled Investment Fund"


def _norm_name(s: str | None) -> str:
    return (s or "").strip().upper()


def load_records(
    path: Path,
    year_min: int,
    year_max: int,
    *,
    expected_rule_version: str = FORM_D_TIER_RULE_VERSION,
) -> list[dict[str, Any]]:
    """Load Form D records and pre-compute the fields we need for the audit.

    Defensive: skips malformed JSON lines and records missing company_name
    or match_confidence.tier, matching the convention in
    ``bootstrap_form_d_leverage_ci.py``.
    """
    out: list[dict[str, Any]] = []
    for line in open(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = r.get("company_name")
        mc = require_form_d_tier_rule(
            r.get("match_confidence"),
            expected_rule_version=expected_rule_version,
            context=f"Form D record {name or '<unnamed>'!r}",
        )
        tier = mc.get("tier")
        if not name or not tier:
            continue
        rule_version = mc["rule_version"]
        has_pif = any(o.get("industry_group") == PIF_INDUSTRY for o in r.get("offerings", []))
        has_non_pif = any(o.get("industry_group") != PIF_INDUSTRY for o in r.get("offerings", []))

        persons: set[str] = set()
        ciks: set[str] = set()
        for off in r.get("offerings", []):
            cik = off.get("cik") or ""
            if cik:
                ciks.add(cik)
            for p in off.get("related_persons", []):
                p_name = _norm_name(p.get("name"))
                if p_name:
                    persons.add(p_name)

        # Compute the cohort-counted raised total (after year + industry filter)
        raised_counted = 0.0
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
                raised_counted += float(amt)
            except (TypeError, ValueError):
                continue

        out.append(
            {
                "company_name": name,
                "tier": tier,
                "rule_version": rule_version,
                "has_pif": has_pif,
                "has_non_pif": has_non_pif,
                "persons": persons,
                "ciks": ciks,
                "raised_counted": raised_counted,
                "person_score": mc.get("person_score"),
                "address_score": mc.get("address_score"),
                "state_score": mc.get("state_score"),
                "signals_may_span_filings": bool(
                    (r.get("match_confidence_scope") or {}).get("signals_may_span_filings")
                ),
                "signals_may_span_ciks": bool(
                    (r.get("match_confidence_scope") or {}).get("signals_may_span_ciks")
                ),
            }
        )
    return out


def find_cross_links(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one row per PIF/operating-company pair sharing a person or CIK.

    Only pure-PIF records (no non-PIF offerings) are considered on the PIF
    side. Mixed records (have both PIF and non-PIF offerings) are treated
    as operating cos for cross-link target purposes — they're already in
    the counted cohort via their non-PIF offerings. When a pair shares both
    signal types, both are retained instead of whichever happens to be seen
    first.
    """
    pif_only = [r for r in records if r["has_pif"] and not r["has_non_pif"]]
    operating = [r for r in records if r["has_non_pif"]]

    person_to_ops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cik_to_ops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in operating:
        for p in r["persons"]:
            person_to_ops[p].append(r)
        for c in r["ciks"]:
            cik_to_ops[c].append(r)

    links_by_pair: dict[tuple[str, str], dict[str, Any]] = {}

    def link_for(pif: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
        pair = (pif["company_name"], op["company_name"])
        if pair not in links_by_pair:
            links_by_pair[pair] = {
                "pif_company": pif["company_name"],
                "op_company": op["company_name"],
                "link_types": set(),
                "shared_persons": set(),
                "shared_ciks": set(),
                "op_tier": op["tier"],
                "op_rule_version": op.get("rule_version"),
                "op_raised_counted": op["raised_counted"],
                "op_person_score": op["person_score"],
                "op_address_score": op["address_score"],
                "op_state_score": op["state_score"],
                "op_signals_may_span_filings": op.get("signals_may_span_filings", False),
                "op_signals_may_span_ciks": op.get("signals_may_span_ciks", False),
            }
        return links_by_pair[pair]

    for pif in pif_only:
        for p in pif["persons"]:
            for op in person_to_ops.get(p, []):
                link = link_for(pif, op)
                link["link_types"].add("person")
                link["shared_persons"].add(p)
        for c in pif["ciks"]:
            for op in cik_to_ops.get(c, []):
                link = link_for(pif, op)
                link["link_types"].add("cik")
                link["shared_ciks"].add(c)

    cross_links: list[dict[str, Any]] = []
    for pair in sorted(links_by_pair):
        link = links_by_pair[pair]
        link["link_types"] = sorted(link["link_types"])
        link["shared_persons"] = sorted(link["shared_persons"])
        link["shared_ciks"] = sorted(link["shared_ciks"])
        cross_links.append(link)
    return cross_links


def classify_high_tier_robustness(
    cross_links: list[dict[str, Any]], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Classify distinct cross-linked high records by their v2 signal profile.

    The historical function name is retained for callers, but the result no
    longer labels any group "safe". Company-level scores may pool evidence
    across filings, and a shared CIK is itself an entity-resolution review flag.
    """

    del records  # Cross-link rows carry the operating-side fields needed here.
    high_xl = [x for x in cross_links if x["op_tier"] == "high"]
    distinct_ops: dict[str, dict[str, Any]] = {}
    for x in high_xl:
        op_name = x["op_company"]
        if op_name not in distinct_ops:
            distinct_ops[op_name] = {
                "op_company": op_name,
                "raised_counted": x["op_raised_counted"],
                "person_score": x["op_person_score"],
                "address_score": x["op_address_score"],
                "state_score": x["op_state_score"],
                "link_types": set(x["link_types"]),
                "signals_may_span_filings": x.get("op_signals_may_span_filings", False),
                "signals_may_span_ciks": x.get("op_signals_may_span_ciks", False),
            }
        else:
            distinct_ops[op_name]["link_types"].update(x["link_types"])

    profile: dict[str, list[dict[str, Any]]] = {
        "person_and_zip": [],
        "zip_without_person": [],
        "person_and_state_no_zip": [],
        "invalid_under_v2": [],
    }
    for _op_name, op in distinct_ops.items():
        person = op["person_score"] or 0.0
        addr = op["address_score"] or 0.0
        state = op["state_score"] or 0.0
        person_ok = person >= 0.7
        zip_ok = addr >= 1.0
        state_ok = state >= 1.0
        op["link_types"] = sorted(op["link_types"])
        if person_ok and zip_ok:
            profile["person_and_zip"].append(op)
        elif zip_ok and not person_ok:
            profile["zip_without_person"].append(op)
        elif person_ok and state_ok and not zip_ok:
            profile["person_and_state_no_zip"].append(op)
        else:
            profile["invalid_under_v2"].append(op)
    return profile


def summarize(
    cross_links: list[dict[str, Any]],
    records: list[dict[str, Any]],
    high_headline_usd: float | None,
    hm_headline_usd: float | None,
) -> dict[str, Any]:
    """Build the audit summary structure."""
    # Tier distribution
    tier_counts = Counter(x["op_tier"] for x in cross_links)

    # Distinct ops per tier
    high_xl = [x for x in cross_links if x["op_tier"] == "high"]
    medium_xl = [x for x in cross_links if x["op_tier"] == "medium"]
    distinct_high_ops = {x["op_company"]: x["op_raised_counted"] for x in high_xl}
    distinct_med_ops = {x["op_company"]: x["op_raised_counted"] for x in medium_xl}
    high_dollars = sum(distinct_high_ops.values())
    med_dollars = sum(distinct_med_ops.values())

    # Most-shared person names (to spot common-name false positives)
    person_link_counts = Counter(person for x in cross_links for person in x["shared_persons"])

    # V2 signal-profile classification. These are not trust verdicts.
    robustness = classify_high_tier_robustness(cross_links, records)
    person_state_ops = robustness["person_and_state_no_zip"]
    person_state_dollars = sum(o["raised_counted"] for o in person_state_ops)
    cik_review_ops = {
        x["op_company"]: x["op_raised_counted"] for x in high_xl if "cik" in x["link_types"]
    }
    aggregate_scope_ops = {
        x["op_company"]: x["op_raised_counted"]
        for x in high_xl
        if x.get("op_signals_may_span_filings") or x.get("op_signals_may_span_ciks")
    }
    person_state_review = sorted(
        [
            {
                "op_company": op["op_company"],
                "raised_counted": op["raised_counted"],
                "link_types": op["link_types"],
            }
            for op in person_state_ops
        ],
        key=lambda o: -o["raised_counted"],
    )

    pif_only_count = sum(1 for r in records if r["has_pif"] and not r["has_non_pif"])
    mixed_count = sum(1 for r in records if r["has_pif"] and r["has_non_pif"])

    def pct(numerator: float, denominator: float | None) -> float | None:
        if denominator is None or denominator <= 0:
            return None
        return numerator / denominator * 100

    return {
        "schema_version": "2",
        "tier_rule_version": FORM_D_TIER_RULE_VERSION,
        "n_records_total": len(records),
        "n_pif_only_records": pif_only_count,
        "n_mixed_records": mixed_count,
        "n_cross_link_pairs": len(cross_links),
        "tier_distribution": dict(tier_counts),
        "distinct_high_tier_ops_with_cross_link": len(distinct_high_ops),
        "distinct_medium_tier_ops_with_cross_link": len(distinct_med_ops),
        "high_only_headline_usd": high_headline_usd,
        "hm_headline_usd": hm_headline_usd,
        "high_tier_counted_dollars_at_cross_link_op_side": high_dollars,
        "high_tier_pct_of_headline": pct(high_dollars, high_headline_usd),
        "hm_tier_counted_dollars_at_cross_link_op_side": high_dollars + med_dollars,
        "hm_pct_of_headline": pct(high_dollars + med_dollars, hm_headline_usd),
        "signal_profile": {
            "person_and_zip": len(robustness["person_and_zip"]),
            "zip_without_person": len(robustness["zip_without_person"]),
            "person_and_state_no_zip": len(robustness["person_and_state_no_zip"]),
            "invalid_under_v2": len(robustness["invalid_under_v2"]),
        },
        "person_and_state_no_zip_dollars_usd": person_state_dollars,
        "person_and_state_no_zip_pct_of_high_headline": pct(
            person_state_dollars, high_headline_usd
        ),
        "person_and_state_no_zip_ops": person_state_review,
        "distinct_high_tier_ops_with_cik_link": len(cik_review_ops),
        "high_tier_cik_link_dollars_usd": sum(cik_review_ops.values()),
        "distinct_high_tier_ops_with_aggregate_signal_scope": len(aggregate_scope_ops),
        "high_tier_aggregate_scope_dollars_usd": sum(aggregate_scope_ops.values()),
        "top_shared_person_names": [
            {"name": n, "n_cross_links": c} for n, c in person_link_counts.most_common(10)
        ],
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Form D — Pooled Investment Fund cross-link audit",
        "",
        f"**Tier rule:** `{summary['tier_rule_version']}`  ",
        f"**Cross-link pairs:** {summary['n_cross_link_pairs']:,}  ",
        f"**Tier distribution:** {summary['tier_distribution']}  ",
        (
            "**Distinct high-tier operating-company records cross-linked:** "
            f"{summary['distinct_high_tier_ops_with_cross_link']}"
        ),
        "",
        "> This is an identity-review diagnostic, not a validation result. Record-level confidence ",
        "> signals can pool evidence across filings and CIKs. No profile below proves that a match ",
        "> is trustworthy or that corroboration occurred in one filing.",
        "",
        "## Counted-dollar footprint",
        "",
        "| Cohort | Counted dollars at cross-linked operating records | Headline share |",
        "|---|---:|---:|",
    ]

    def pct_text(value: float | None) -> str:
        return "not computed" if value is None else f"{value:.2f}%"

    lines.extend(
        [
            (
                "| High only | "
                f"${summary['high_tier_counted_dollars_at_cross_link_op_side'] / 1e9:.3f}B | "
                f"{pct_text(summary['high_tier_pct_of_headline'])} |"
            ),
            (
                "| High + medium | "
                f"${summary['hm_tier_counted_dollars_at_cross_link_op_side'] / 1e9:.3f}B | "
                f"{pct_text(summary['hm_pct_of_headline'])} |"
            ),
            "",
        ]
    )
    if summary["high_only_headline_usd"] is None or summary["hm_headline_usd"] is None:
        lines.extend(
            [
                "Headline denominators were not supplied. Shares are suppressed so this audit cannot ",
                "silently reuse retired v1 fundraising totals.",
                "",
            ]
        )

    profile = summary["signal_profile"]
    lines.extend(
        [
            "## High-tier signal profiles",
            "",
            "| Stored aggregate profile | Distinct records | Review meaning |",
            "|---|---:|---|",
            (
                f"| Person + ZIP | {profile['person_and_zip']} | Satisfies v2; same-filing "
                "scope is not established |"
            ),
            (
                f"| ZIP without person | {profile['zip_without_person']} | Satisfies v2; issuer and "
                "cross-filing identity still require review |"
            ),
            (
                f"| Person + state, no ZIP | {profile['person_and_state_no_zip']} | Satisfies v2, "
                "but remains sensitive to a shared-person collision |"
            ),
            (
                f"| Invalid under v2 | {profile['invalid_under_v2']} | Stale or inconsistent tier; "
                "exclude and investigate |"
            ),
            "",
            (
                "Person + state/no-ZIP records account for "
                f"${summary['person_and_state_no_zip_dollars_usd'] / 1e6:.1f}M in this diagnostic. "
                "They are not person-only under v2, but state is not a unique identity key and the "
                "legacy record does not prove both signals came from one filing."
            ),
            "",
            "## Aggregation review flags",
            "",
            (
                f"- {summary['distinct_high_tier_ops_with_cik_link']} distinct high-tier records "
                "share a CIK with a PIF-side record. Shared CIK is an entity-resolution flag, not "
                "automatic corroboration."
            ),
            (
                "- "
                f"{summary['distinct_high_tier_ops_with_aggregate_signal_scope']} distinct high-tier "
                "records report signal scope that may span filings or CIKs."
            ),
            "",
            "## Person + state/no-ZIP review queue",
            "",
        ]
    )
    if summary["person_and_state_no_zip_ops"]:
        lines.extend(["| Operating company | Counted dollars | Link types |", "|---|---:|---|"])
        for op in summary["person_and_state_no_zip_ops"]:
            lines.append(
                f"| {op['op_company']} | ${op['raised_counted'] / 1e6:.1f}M | "
                f"{', '.join(op['link_types'])} |"
            )
    else:
        lines.append("_(none)_")

    lines.extend(
        ["", "## Top shared person names", "", "| Name | Cross-link pairs |", "|---|---:|"]
    )
    for entry in summary["top_shared_person_names"]:
        lines.append(f"| {entry['name']} | {entry['n_cross_links']} |")
    lines.extend(
        [
            "",
            "## Interpretation limit",
            "",
            "The audit identifies records for review. It cannot estimate matching error, establish an ",
            "investor-to-portfolio relationship, or show that the remaining high tier is valid. A ",
            "same-filing or issuer-scoped rebuild plus human identity review is required before using ",
            "these results to reopen the retired fundraising study.",
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
    parser.add_argument("--year-min", type=int, default=YEAR_MIN)
    parser.add_argument("--year-max", type=int, default=YEAR_MAX)
    parser.add_argument("--expected-rule-version", default=FORM_D_TIER_RULE_VERSION)
    parser.add_argument(
        "--high-headline-usd",
        type=float,
        help="Optional same-materialization denominator; no retired value is assumed.",
    )
    parser.add_argument(
        "--hm-headline-usd",
        type=float,
        help="Optional same-materialization denominator; no retired value is assumed.",
    )
    parser.add_argument(
        "--output-json", type=Path, default=Path("reports/ml/form_d_pif_cross_links.json")
    )
    parser.add_argument(
        "--output-md", type=Path, default=Path("reports/ml/form_d_pif_cross_links.md")
    )
    args = parser.parse_args()

    if not args.form_d_path.exists():
        print(f"ERROR: {args.form_d_path} not found", file=sys.stderr)
        return 2

    print(f"Loading {args.form_d_path}...", file=sys.stderr)
    records = load_records(
        args.form_d_path,
        args.year_min,
        args.year_max,
        expected_rule_version=args.expected_rule_version,
    )
    print(f"  Loaded {len(records):,} records", file=sys.stderr)

    cross_links = find_cross_links(records)
    print(f"  Cross-links found: {len(cross_links):,}", file=sys.stderr)

    summary = summarize(cross_links, records, args.high_headline_usd, args.hm_headline_usd)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w") as f:
        json.dump(summary, f, indent=2)
    write_markdown(summary, args.output_md)

    # Console headlines
    print(
        "\n  High-tier cross-link footprint: "
        f"${summary['high_tier_counted_dollars_at_cross_link_op_side'] / 1e9:.3f}B",
        file=sys.stderr,
    )
    print(
        "  Person + state/no-ZIP footprint: "
        f"${summary['person_and_state_no_zip_dollars_usd'] / 1e6:.0f}M",
        file=sys.stderr,
    )
    print(f"\nWrote {args.output_json} and {args.output_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
