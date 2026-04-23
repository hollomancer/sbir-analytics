#!/usr/bin/env python3
"""Analyze Form D confidence score distribution and identify natural clusters.

Reads form_d_details.jsonl and produces:
1. Composite score histogram with density estimate
2. Person score distribution (bimodal test)
3. Person score vs state score scatter
4. Signal correlation matrix
5. Sample companies from each natural cluster for manual validation
6. Suggested tier thresholds based on score gaps

Usage:
    python scripts/data/analyze_form_d_tiers.py
    python scripts/data/analyze_form_d_tiers.py --input data/form_d_details.jsonl
    python scripts/data/analyze_form_d_tiers.py --output-dir data/analysis
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def load_records(path: str) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def analyze(records: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract signals
    composites = []
    person_scores = []
    state_scores = []
    temporal_scores = []
    yoi_scores = []
    name_scores = []

    for r in records:
        c = r["match_confidence"]
        composites.append(c["score"])
        name_scores.append(c["name_score"])
        if c.get("person_score") is not None:
            person_scores.append(c["person_score"])
        if c.get("state_score") is not None:
            state_scores.append(c["state_score"])
        if c.get("temporal_score") is not None:
            temporal_scores.append(c["temporal_score"])
        if c.get("year_of_inc_score") is not None:
            yoi_scores.append(c["year_of_inc_score"])

    print(f"Total records: {len(records):,}")
    print(f"  With person_score: {len(person_scores):,} ({len(person_scores)/len(records)*100:.1f}%)")
    print(f"  With state_score: {len(state_scores):,} ({len(state_scores)/len(records)*100:.1f}%)")
    print(f"  With temporal_score: {len(temporal_scores):,} ({len(temporal_scores)/len(records)*100:.1f}%)")
    print(f"  With year_of_inc_score: {len(yoi_scores):,} ({len(yoi_scores)/len(records)*100:.1f}%)")

    # --- 1. Composite score distribution ---
    print(f"\n{'='*60}")
    print("COMPOSITE SCORE DISTRIBUTION")
    print(f"{'='*60}")
    buckets = Counter()
    for s in composites:
        bucket = round(s * 20) / 20  # 0.05 buckets
        buckets[bucket] += 1

    for bucket in sorted(buckets.keys()):
        count = buckets[bucket]
        bar = "#" * (count // max(1, len(records) // 200))
        print(f"  {bucket:.2f}: {count:>5,} {bar}")

    # Percentiles
    sorted_comp = sorted(composites)
    for pct in [10, 25, 50, 75, 90]:
        idx = int(len(sorted_comp) * pct / 100)
        print(f"  P{pct}: {sorted_comp[idx]:.3f}")

    # --- 2. Person score distribution ---
    print(f"\n{'='*60}")
    print("PERSON SCORE DISTRIBUTION")
    print(f"{'='*60}")
    if person_scores:
        p_buckets = Counter()
        for s in person_scores:
            bucket = round(s * 10) / 10  # 0.1 buckets
            p_buckets[bucket] += 1

        for bucket in sorted(p_buckets.keys()):
            count = p_buckets[bucket]
            bar = "#" * (count // max(1, len(person_scores) // 100))
            print(f"  {bucket:.1f}: {count:>5,} {bar}")

        # Bimodality check
        low = sum(1 for s in person_scores if s < 0.4)
        mid = sum(1 for s in person_scores if 0.4 <= s < 0.7)
        high = sum(1 for s in person_scores if s >= 0.7)
        print(f"\n  Low (<0.4): {low:,}  Mid (0.4-0.7): {mid:,}  High (≥0.7): {high:,}")
        if low > len(person_scores) * 0.3 and high > len(person_scores) * 0.1:
            print("  → Appears bimodal (distinct low and high clusters)")
        else:
            print("  → Not clearly bimodal")
    else:
        print("  No person scores available")

    # --- 3. Person vs State cross-tabulation ---
    print(f"\n{'='*60}")
    print("PERSON SCORE vs STATE SCORE")
    print(f"{'='*60}")
    quadrants = {"match_match": 0, "match_nomatch": 0, "nomatch_match": 0, "nomatch_nomatch": 0, "missing": 0}
    for r in records:
        c = r["match_confidence"]
        ps = c.get("person_score")
        ss = c.get("state_score")
        if ps is None or ss is None:
            quadrants["missing"] += 1
        elif ps >= 0.7 and ss >= 0.5:
            quadrants["match_match"] += 1
        elif ps >= 0.7 and ss < 0.5:
            quadrants["match_nomatch"] += 1
        elif ps < 0.7 and ss >= 0.5:
            quadrants["nomatch_match"] += 1
        else:
            quadrants["nomatch_nomatch"] += 1

    print(f"  Person HIGH + State MATCH:     {quadrants['match_match']:>5,}  (strongest confirmation)")
    print(f"  Person HIGH + State MISMATCH:  {quadrants['match_nomatch']:>5,}  (relocation candidates)")
    print(f"  Person LOW  + State MATCH:     {quadrants['nomatch_match']:>5,}  (state-only evidence)")
    print(f"  Person LOW  + State MISMATCH:  {quadrants['nomatch_nomatch']:>5,}  (likely false positive)")
    print(f"  Missing signal(s):             {quadrants['missing']:>5,}")

    # --- 4. Natural gap detection ---
    print(f"\n{'='*60}")
    print("NATURAL THRESHOLD DETECTION")
    print(f"{'='*60}")
    # Find the largest gaps in the sorted composite distribution
    sorted_comp = sorted(composites)
    gaps = []
    window = max(1, len(sorted_comp) // 100)  # 1% window
    for i in range(window, len(sorted_comp) - window):
        gap = sorted_comp[i + 1] - sorted_comp[i]
        if gap > 0.01:
            density_before = window / (sorted_comp[i] - sorted_comp[max(0, i - window)] + 0.001)
            density_after = window / (sorted_comp[min(len(sorted_comp) - 1, i + window)] - sorted_comp[i] + 0.001)
            gaps.append((sorted_comp[i], gap, density_before, density_after))

    # Top gaps by size
    gaps.sort(key=lambda x: -x[1])
    print("  Largest score gaps (potential natural thresholds):")
    for score, gap, db, da in gaps[:10]:
        pct_below = sum(1 for s in composites if s <= score) / len(composites) * 100
        print(f"    score={score:.3f}  gap={gap:.4f}  {pct_below:.1f}% below")

    # --- 5. Current tier distribution ---
    print(f"\n{'='*60}")
    print("CURRENT TIER DISTRIBUTION")
    print(f"{'='*60}")
    tiers = Counter(r["match_confidence"]["tier"] for r in records)
    for tier in ["high", "medium", "low"]:
        count = tiers.get(tier, 0)
        pct = count / len(records) * 100
        print(f"  {tier:>6s}: {count:>5,} ({pct:.1f}%)")

    # --- 6. Sample companies for validation ---
    print(f"\n{'='*60}")
    print("SAMPLE COMPANIES FOR MANUAL VALIDATION")
    print(f"{'='*60}")

    # Sort by composite score, sample from different ranges
    by_score = sorted(records, key=lambda r: r["match_confidence"]["score"])

    ranges = [
        ("High (≥0.75)", [r for r in by_score if r["match_confidence"]["score"] >= 0.75]),
        ("Upper-mid (0.60-0.74)", [r for r in by_score if 0.60 <= r["match_confidence"]["score"] < 0.75]),
        ("Lower-mid (0.50-0.59)", [r for r in by_score if 0.50 <= r["match_confidence"]["score"] < 0.60]),
        ("Low (0.35-0.49)", [r for r in by_score if 0.35 <= r["match_confidence"]["score"] < 0.50]),
        ("Very low (<0.35)", [r for r in by_score if r["match_confidence"]["score"] < 0.35]),
    ]

    for label, group in ranges:
        print(f"\n  {label} ({len(group):,} companies):")
        # Pick 5 evenly spaced
        if not group:
            print("    (none)")
            continue
        step = max(1, len(group) // 5)
        samples = group[::step][:5]
        for r in samples:
            c = r["match_confidence"]
            ps = c.get("person_score")
            ps_str = f"{ps:.2f}" if ps is not None else "n/a"
            detail = c.get("person_match_detail", "")
            raised = r.get("total_raised")
            raised_str = f"${raised/1e6:.1f}M" if raised else "n/a"
            print(
                f"    {r['company_name']:40s} score={c['score']:.2f} "
                f"person={ps_str:>5s} state={c.get('state_score', 'n/a')!s:>4s} "
                f"raised={raised_str:>8s}  {(detail or '')[:50]}"
            )

    # --- 7. Write raw data for external plotting ---
    scores_path = output_dir / "form_d_scores.jsonl"
    with open(scores_path, "w") as f:
        for r in records:
            c = r["match_confidence"]
            row = {
                "company_name": r["company_name"],
                "composite": c["score"],
                "name_score": c["name_score"],
                "person_score": c.get("person_score"),
                "state_score": c.get("state_score"),
                "temporal_score": c.get("temporal_score"),
                "year_of_inc_score": c.get("year_of_inc_score"),
                "tier": c["tier"],
                "offering_count": r["offering_count"],
                "total_raised": r.get("total_raised"),
            }
            f.write(json.dumps(row) + "\n")
    print(f"\nRaw scores written to {scores_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Form D confidence tiers")
    parser.add_argument("--input", default="data/form_d_details.jsonl")
    parser.add_argument("--output-dir", default="data/analysis")
    args = parser.parse_args()

    records = load_records(args.input)
    if not records:
        print(f"No records in {args.input}")
        sys.exit(1)

    analyze(records, Path(args.output_dir))


if __name__ == "__main__":
    main()
