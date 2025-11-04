#!/usr/bin/env python3
"""
run_cet_drift.py

Standalone script to compute distributional drift for CET award classifications.

This script:
- Reads award-level CET classifications from a parquet file or NDJSON fallback.
- Computes:
    - primary CET label PMF (categorical)
    - primary score histogram PMF (binned numeric)
- Loads a baseline distributions file (expected JSON with `label_pmf` and `score_pmf`)
  from reports/benchmarks/cet_baseline_distributions.json if present.
- If baseline is absent, writes a candidate baseline file (reports/benchmarks/cet_baseline_distributions_current.json)
  and exits with a descriptive report (no alerts).
- If baseline exists, computes Jensen-Shannon divergence (JS) between baseline and current
  distributions for both label and score PMFs, writes a drift report and alerts JSON.
- Does NOT import Dagster; runnable as a plain Python script.

Usage:
    python scripts/run_cet_drift.py \
      --awards data/processed/cet_award_classifications.parquet \
      --baseline reports/benchmarks/cet_baseline_distributions.json \
      --out-report reports/benchmarks/cet_drift_report.json \
      --out-alerts reports/alerts/cet_drift_alerts.json

Defaults are chosen to match repository conventions.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any


# Optional imports
try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore


def read_json_records(path: Path) -> list[dict[str, Any]]:
    """Read JSON array or NDJSON file and return list of dicts."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    # Try full JSON array first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        pass
    # Fallback NDJSON
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    return out


def load_awards_dataframe(parquet_path: Path, json_path: Path):
    """Return a pandas.DataFrame if possible, else None. Prefer parquet then NDJSON."""
    if pd is not None and parquet_path.exists():
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass
    # Try NDJSON fallback
    if json_path.exists():
        rows = read_json_records(json_path)
        if pd is not None:
            try:
                return pd.DataFrame(rows)
            except Exception:
                return None
        # If pandas not available, return None (we will handle raw JSON approach)
    return None


def read_awards_records(parquet_path: Path, json_path: Path) -> list[dict[str, Any]]:
    """Return a list of award dicts from parquet (via pandas) or NDJSON."""
    df = load_awards_dataframe(parquet_path, json_path)
    if df is not None:
        # Convert DataFrame rows to dicts; ensure standard Python types
        return [
            json.loads(row.to_json()) if hasattr(row, "to_json") else dict(row)
            for _, row in df.iterrows()
        ]
    # Fallback: read NDJSON directly
    return read_json_records(json_path)


def pmf_from_counts(counts: dict[Any, int]) -> dict[str, float]:
    """Normalize counts dict into a PMF mapping str(key) -> probability."""
    total = sum(int(v) for v in counts.values()) if counts else 0
    if total <= 0:
        return {}
    pmf: dict[str, float] = {}
    for k, v in counts.items():
        try:
            pmf[str(k)] = float(v) / float(total)
        except Exception:
            pmf[str(k)] = 0.0
    return pmf


def score_hist_pmf(scores: Iterable[float], bins: list[float]) -> dict[str, float]:
    """Compute histogram PMF for scores clipped to [min(bins), max(bins)]."""
    if np is not None:
        try:
            arr = np.array(
                [
                    float(s)
                    for s in scores
                    if s is not None and not (isinstance(s, float) and math.isnan(s))
                ],
                dtype=float,
            )
            if arr.size == 0:
                return {}
            # Clip values to min..max
            arr = np.clip(arr, bins[0], bins[-1])
            hist, edges = np.histogram(arr, bins=bins)
            total = int(hist.sum())
            if total == 0:
                return {}
            pmf: dict[str, float] = {}
            for i in range(len(hist)):
                label = f"{int(edges[i])}-{int(edges[i+1])}"
                pmf[label] = float(hist[i]) / float(total)
            return pmf
        except Exception:
            # fall through to python fallback
            pass
    # Pure python fallback
    b = bins
    # Build bins as tuples (lo, hi)
    ranges = [(b[i], b[i + 1]) for i in range(len(b) - 1)]
    counts = [0] * len(ranges)
    total = 0
    for s in scores:
        try:
            val = float(s)
        except Exception:
            continue
        # clip
        if val < ranges[0][0]:
            val = ranges[0][0]
        if val > ranges[-1][1]:
            val = ranges[-1][1]
        for i, (lo, hi) in enumerate(ranges):
            # include left, exclude right except last bin
            if i < len(ranges) - 1:
                if lo <= val < hi:
                    counts[i] += 1
                    total += 1
                    break
            else:
                if lo <= val <= hi:
                    counts[i] += 1
                    total += 1
                    break
    if total == 0:
        return {}
    pmf: dict[str, float] = {}
    for i, (lo, hi) in enumerate(ranges):
        pmf[f"{int(lo)}-{int(hi)}"] = float(counts[i]) / float(total)
    return pmf


def align_pmfs_dicts(
    a: dict[str, float], b: dict[str, float]
) -> tuple[list[float], list[float], list[str]]:
    """Align two PMF dicts onto the union of keys, returning arrays (p_arr, q_arr, keys_sorted)."""
    keys = sorted(set(a.keys()) | set(b.keys()))
    p_arr = [float(a.get(k, 0.0)) for k in keys]
    q_arr = [float(b.get(k, 0.0)) for k in keys]
    return p_arr, q_arr, keys


def js_divergence(p_arr: list[float], q_arr: list[float]) -> float:
    """Compute Jensen-Shannon divergence between two probability arrays. Uses log base 2."""
    # Convert to numpy if available
    if np is not None:
        p = np.array(p_arr, dtype=float)
        q = np.array(q_arr, dtype=float)
        # normalize defensively
        if p.sum() > 0:
            p = p / p.sum()
        if q.sum() > 0:
            q = q / q.sum()
        m = 0.5 * (p + q)

        # KL divergence function with handling of zeros
        def _kl(a, b):
            mask = (a > 0) & (b > 0)
            if not mask.any():
                return 0.0
            return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

        return float(0.5 * (_kl(p, m) + _kl(q, m)))
    # Pure python fallback
    # Normalize
    p = list(map(float, p_arr))
    q = list(map(float, q_arr))
    p_sum = sum(p)
    q_sum = sum(q)
    if p_sum > 0:
        p = [x / p_sum for x in p]
    if q_sum > 0:
        q = [x / q_sum for x in q]
    m = [0.5 * (pp + qq) for pp, qq in zip(p, q, strict=False)]

    def _safe_log2(x):
        return math.log(x, 2) if x > 0 else 0.0

    def _kl(a, b):
        s = 0.0
        for ai, bi in zip(a, b, strict=False):
            if ai > 0 and bi > 0:
                s += ai * _safe_log2(ai / bi)
        return s

    return 0.5 * (_kl(p, m) + _kl(q, m))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, default=str)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run CET drift detection standalone (no Dagster).")
    parser.add_argument(
        "--awards",
        type=str,
        default="data/processed/cet_award_classifications.parquet",
        help="Path to awards parquet (preferred) or NDJSON fallback.",
    )
    parser.add_argument(
        "--awards-json",
        type=str,
        default="data/processed/cet_award_classifications.json",
        help="NDJSON fallback path for awards.",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="reports/benchmarks/cet_baseline_distributions.json",
        help="Canonical baseline distributions JSON path.",
    )
    parser.add_argument(
        "--candidate-out",
        type=str,
        default="reports/benchmarks/cet_baseline_distributions_current.json",
        help="Where to write candidate baseline if canonical baseline missing.",
    )
    parser.add_argument(
        "--out-report",
        type=str,
        default="reports/benchmarks/cet_drift_report.json",
        help="Output drift report JSON path.",
    )
    parser.add_argument(
        "--out-alerts",
        type=str,
        default="reports/alerts/cet_drift_alerts.json",
        help="Output alerts JSON path.",
    )
    parser.add_argument(
        "--score-bins",
        type=str,
        default="0,10,20,30,40,50,60,70,80,90,100",
        help="Comma-separated score bin edges (inclusive last).",
    )
    parser.add_argument(
        "--label-threshold",
        type=float,
        default=0.10,
        help="JS divergence threshold for label distribution drift.",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.15,
        help="JS divergence threshold for score distribution drift.",
    )
    args = parser.parse_args(argv)

    awards_parquet = Path(args.awards)
    awards_json = Path(args.awards_json)
    baseline_path = Path(args.baseline)
    candidate_out = Path(args.candidate_out)
    out_report = Path(args.out_report)
    out_alerts = Path(args.out_alerts)

    # Read awards
    records = []
    try:
        df = load_awards_dataframe(awards_parquet, awards_json)
        if df is not None:
            # Convert DataFrame to list of dicts with native types
            records = []
            for _, row in df.iterrows():
                # row may be Series; convert to dict safely using .to_dict
                try:
                    records.append(dict(row.dropna().to_dict()))
                except Exception:
                    # fallback
                    records.append(dict(row.to_dict()))
        else:
            # fallback NDJSON
            records = read_json_records(awards_json)
    except Exception:
        records = read_json_records(awards_json)

    if not records:
        print("No award classification records found (parquet/ndjson). Exiting with no-op.")
        # write minimal report
        payload = {
            "ok": True,
            "reason": "no_input",
            "generated_at": datetime.utcnow().isoformat(),
            "label_js_divergence": None,
            "score_js_divergence": None,
        }
        try:
            write_json(out_report, payload)
        except Exception:
            pass
        return 0

    # Build label counts and score list
    label_counts: Counter = Counter()
    scores_list: list[float] = []
    for r in records:
        # primary_cet may be nested or directly present
        pc = r.get("primary_cet")
        if pc is None:
            pc = "__none__"
        label_counts[str(pc)] += 1
        # primary_score may be present
        ps = r.get("primary_score")
        if ps is None:
            # try alternate keys
            ps = r.get("score") or r.get("primary_score")
        if ps is not None:
            try:
                val = float(ps)
                # clamp to sensible range for PMF
                if math.isfinite(val):
                    scores_list.append(val)
            except Exception:
                continue

    current_label_pmf = pmf_from_counts(dict(label_counts))

    # Parse bins
    try:
        bins = [float(x) for x in args.score_bins.split(",")]
        if len(bins) < 2:
            bins = list(range(0, 101, 10))
    except Exception:
        bins = list(range(0, 101, 10))

    current_score_pmf = score_hist_pmf(scores_list, bins)

    # Load baseline if present
    baseline = None
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception:
            baseline = None

    if baseline is None:
        # Write candidate baseline and exit
        candidate = {
            "generated_at": datetime.utcnow().isoformat(),
            "label_pmf": current_label_pmf,
            "score_pmf": current_score_pmf,
            "notes": "Candidate baseline generated. Promote to canonical baseline file to enable drift detection.",
        }
        try:
            write_json(candidate_out, candidate)
            print(f"Baseline not found; wrote candidate baseline to: {candidate_out}")
        except Exception as exc:
            print(f"Failed to write candidate baseline: {exc}", file=sys.stderr)
            return 2
        # Also write a minimal report
        report_payload = {
            "ok": True,
            "reason": "baseline_missing",
            "candidate_path": str(candidate_out),
            "generated_at": datetime.utcnow().isoformat(),
        }
        try:
            write_json(out_report, report_payload)
        except Exception:
            pass
        return 0

    # Extract PMFs from baseline with permissive keys
    baseline_label_pmf = baseline.get("label_pmf") or baseline.get("label_distribution") or {}
    baseline_score_pmf = baseline.get("score_pmf") or baseline.get("score_distribution") or {}

    # Align pmfs and compute JS divergence
    p_label, q_label, label_keys = align_pmfs_dicts(baseline_label_pmf, current_label_pmf)
    p_score, q_score, score_keys = align_pmfs_dicts(baseline_score_pmf, current_score_pmf)

    label_js = js_divergence(p_label, q_label) if label_keys else None
    score_js = js_divergence(p_score, q_score) if score_keys else None

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "label_js_divergence": label_js,
        "score_js_divergence": score_js,
        "label_threshold": args.label_threshold,
        "score_threshold": args.score_threshold,
        "label_keys": label_keys,
        "score_keys": score_keys,
        "counts": {"total_awards": len(records), "label_count": sum(label_counts.values())},
    }

    alerts: dict[str, Any] = {"alerts": [], "generated_at": datetime.utcnow().isoformat()}

    # Evaluate thresholds
    if label_js is not None:
        if label_js > args.label_threshold:
            severity = "WARNING" if label_js <= 2 * args.label_threshold else "FAILURE"
            alerts["alerts"].append(
                {
                    "type": "label_distribution_drift",
                    "message": f"Label JS divergence {label_js:.4f} > threshold {args.label_threshold:.4f}",
                    "value": label_js,
                    "severity": severity,
                }
            )
    if score_js is not None:
        if score_js > args.score_threshold:
            severity = "WARNING" if score_js <= 2 * args.score_threshold else "FAILURE"
            alerts["alerts"].append(
                {
                    "type": "score_distribution_drift",
                    "message": f"Score JS divergence {score_js:.4f} > threshold {args.score_threshold:.4f}",
                    "value": score_js,
                    "severity": severity,
                }
            )

    # Write outputs
    try:
        write_json(out_report, report)
    except Exception:
        pass
    try:
        write_json(out_alerts, alerts)
    except Exception:
        pass

    # Print summary to stdout
    print("CET drift detection report written to:", out_report)
    if alerts["alerts"]:
        print("Alerts written to:", out_alerts)
        for a in alerts["alerts"]:
            print(f"- [{a['severity']}] {a['type']}: {a['message']}")
        # Return non-zero if any FAILURE alerts
        if any(a.get("severity") == "FAILURE" for a in alerts["alerts"]):
            return 3
        return 0
    else:
        print("No drift detected (divergences within thresholds).")
        return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv[1:])
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
        rc = 130
    sys.exit(rc)
