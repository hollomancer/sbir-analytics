#!/usr/bin/env python3
"""
Transition Precision Audit Sampler for vendor_resolution

Purpose:
  - Sample N vendor_resolution rows (excluding unresolved) for manual precision audit
  - Support three workflows:
      1) Interactive labeling in the terminal
      2) Export a CSV for offline labeling
      3) Import a labeled CSV and compute precision metrics

Inputs:
  - vendor_resolution table (default: data/processed/vendor_resolution.parquet)
  - optional contracts_sample table to enrich audit rows (default: data/processed/contracts_sample.parquet)

Outputs:
  - Labeled CSV (optional) for records under audit
  - JSON report (default: reports/validation/transition_precision_audit.json) with precision metrics

Usage examples:
  - Interactive audit (50 random):
      python scripts/transition_precision_audit.py --interactive

  - Export a CSV for offline labeling:
      python scripts/transition_precision_audit.py --export-csv reports/validation/vendor_resolution_audit_sample.csv

  - Import labeled CSV and compute metrics (precision at confidence >= 0.8):
      python scripts/transition_precision_audit.py --import-csv reports/validation/vendor_resolution_audit_sample.csv --threshold 0.8

Notes:
  - Labeled CSV should include a 'label' column with values like: y/yes/1/true (positive) or n/no/0/false (negative).
  - For interactive labeling, you can enter: y (yes), n (no), u (unsure), q (quit).
  - Precision is computed as (#positive / #labeled) for the chosen cohort (above threshold or overall).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# -----------------------------
# IO helpers
# -----------------------------


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_table(path: Path) -> pd.DataFrame:
    """
    Load a table from path, supporting parquet, ndjson/jsonl, or csv.

    Raises FileNotFoundError if path doesn't exist and no fallback exists.
    """
    if path.exists():
        return _read_any(path)

    # Fallbacks for common extensions
    fallbacks = []
    if path.suffix == ".parquet":
        fallbacks = [
            path.with_suffix(".ndjson"),
            path.with_suffix(".jsonl"),
            path.with_suffix(".csv"),
        ]
    elif path.suffix in {".ndjson", ".jsonl"}:
        fallbacks = [path.with_suffix(".parquet"), path.with_suffix(".csv")]
    elif path.suffix == ".csv":
        fallbacks = [
            path.with_suffix(".parquet"),
            path.with_suffix(".ndjson"),
            path.with_suffix(".jsonl"),
        ]

    for fb in fallbacks:
        if fb.exists():
            return _read_any(fb)

    raise FileNotFoundError(
        f"Could not find {path} or any fallback: {', '.join(map(str, fallbacks))}"
    )


def _read_any(path: Path) -> pd.DataFrame:
    p = str(path)
    if p.endswith(".parquet"):
        try:
            return pd.read_parquet(p)
        except Exception as exc:
            raise RuntimeError(f"Failed to read parquet: {path} ({exc})") from exc
    if p.endswith(".ndjson") or p.endswith(".jsonl"):
        # Read streaming NDJSON
        rows: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return pd.DataFrame(rows)
    if p.endswith(".csv"):
        return pd.read_csv(p)
    if p.endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        # Accept list[dict] or dict with "data" key
        if isinstance(data, list):
            return pd.DataFrame(data)
        if isinstance(data, dict) and "data" in data:
            return pd.DataFrame(data["data"])
        raise ValueError(f"Unsupported JSON shape in {path}")
    # Fallback: try pandas
    return pd.read_table(p)


# -----------------------------
# Label parsing and metrics
# -----------------------------


def _parse_bool_label(v: Any) -> int | None:
    """
    Map various truthy/falsey labels to 1/0.

    Returns:
      1 for positive, 0 for negative, None for unsure/unlabeled.
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"y", "yes", "1", "true", "t"}:
        return 1
    if s in {"n", "no", "0", "false", "f"}:
        return 0
    # treat 'u'/'unsure'/'skip' as None
    if s in {"u", "unsure", "skip", ""}:
        return None
    # unrecognized -> None
    return None


@dataclass
class PrecisionMetrics:
    n_total: int
    n_labeled: int
    n_positive: int
    precision: float | None  # positive / labeled (None if n_labeled == 0)


def _compute_precision(
    df: pd.DataFrame, threshold: float | None = None
) -> dict[str, PrecisionMetrics]:
    """
    Compute precision metrics overall and for cohort above threshold (if threshold provided).

    Expects df to have columns: 'confidence' (float), 'label' (0/1/None).
    """

    def _metrics(sub: pd.DataFrame) -> PrecisionMetrics:
        labeled = sub["label"].apply(lambda x: x in (0, 1))
        n_labeled = int(labeled.sum())
        n_positive = int(sub.loc[labeled, "label"].sum()) if n_labeled > 0 else 0
        prec = (n_positive / n_labeled) if n_labeled > 0 else None
        return PrecisionMetrics(
            n_total=len(sub), n_labeled=n_labeled, n_positive=n_positive, precision=prec
        )

    out: dict[str, PrecisionMetrics] = {}
    out["overall"] = _metrics(df)

    if threshold is not None:
        above = df[pd.to_numeric(df["confidence"], errors="coerce").fillna(0.0) >= float(threshold)]
        out["above_threshold"] = _metrics(above)
    return out


# -----------------------------
# Sampling and enrichment
# -----------------------------


def _sample_vendor_resolution(df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    matched = df[df["match_method"].fillna("unresolved") != "unresolved"].copy()
    if len(matched) == 0:
        return matched
    n = min(sample_size, len(matched))
    # stable random sample with seed (use Python's random for consistency)
    idx = list(matched.index)
    rng = random.Random(seed)
    rng.shuffle(idx)
    chosen = idx[:n]
    return matched.loc[chosen].reset_index(drop=True)


def _enrich_with_contracts(sample: pd.DataFrame, contracts_path: Path | None) -> pd.DataFrame:
    """
    Attach selected fields from contracts_sample if available.
    """
    if not contracts_path:
        return sample
    try:
        dfc = _load_table(contracts_path)
    except Exception:
        return sample

    # select informative fields
    cols = [
        "contract_id",
        "piid",
        "fain",
        "vendor_uei",
        "vendor_duns",
        "vendor_name",
        "action_date",
        "obligated_amount",
        "awarding_agency_code",
        "awarding_agency_name",
    ]
    for c in cols:
        if c not in dfc.columns:
            dfc[c] = None

    # left-join on contract_id (fallback to piid when contract_id missing in vendor_resolution)
    sample = sample.copy()
    if "contract_id" not in sample.columns:
        sample["contract_id"] = ""
    # fallback normalize contract_id
    sample["contract_id_norm"] = sample["contract_id"].astype(str)
    dfc = dfc.copy()
    dfc["contract_id_norm"] = dfc["contract_id"].astype(str)

    merged = sample.merge(
        dfc[cols + ["contract_id_norm"]],
        on="contract_id_norm",
        how="left",
        suffixes=("", "_contract"),
    )
    merged.drop(columns=["contract_id_norm"], inplace=True)
    return merged


# -----------------------------
# Export / Import
# -----------------------------


def _export_csv(df: pd.DataFrame, path: Path) -> None:
    _ensure_parent(path)
    df_out = df.copy()
    # Provide label and notes columns for auditors
    if "label" not in df_out.columns:
        df_out["label"] = None
    if "notes" not in df_out.columns:
        df_out["notes"] = None
    df_out.to_csv(path, index=False)
    print(f"[audit] Wrote unlabeled sample to {path}")
    print("        Fill 'label' with y/yes/1/true (positive) or n/no/0/false (negative).")
    print("        Optionally add notes; then re-run with --import-csv to compute precision.")


def _import_labeled_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # normalize label to 0/1/None
    df["label"] = df.get("label").apply(_parse_bool_label)
    # ensure confidence present
    if "confidence" not in df.columns:
        raise ValueError("Labeled CSV must contain a 'confidence' column.")
    return df


# -----------------------------
# Interactive labeling
# -----------------------------


def _prompt_label(row: pd.Series) -> int | None:
    """
    Prompt: y (yes), n (no), u (unsure), q (quit).
    Returns 1/0/None or raises KeyboardInterrupt on 'q'.
    """
    print("-" * 72)
    print(f"contract_id: {row.get('contract_id')}")
    print(f"match_method: {row.get('match_method')}  confidence: {row.get('confidence')}")
    print(f"matched_vendor_id: {row.get('matched_vendor_id')}")
    # Helpful context (when contracts attached)
    if pd.notna(row.get("vendor_name")):
        print(f"vendor_name: {row.get('vendor_name')}")
    if pd.notna(row.get("piid")) or pd.notna(row.get("fain")):
        print(f"PIID/FAIN: {row.get('piid')} / {row.get('fain')}")
    if pd.notna(row.get("action_date")):
        print(f"action_date: {row.get('action_date')}")
    if pd.notna(row.get("obligated_amount")):
        print(f"obligated_amount: {row.get('obligated_amount')}")
    if pd.notna(row.get("awarding_agency_code")) or pd.notna(row.get("awarding_agency_name")):
        print(f"agency: {row.get('awarding_agency_code')}  {row.get('awarding_agency_name')}")
    print("Label? (y=yes, n=no, u=unsure, q=quit): ", end="", flush=True)
    while True:
        ans = sys.stdin.readline()
        if not ans:
            return None
        s = ans.strip().lower()
        if s in {"y", "yes"}:
            return 1
        if s in {"n", "no"}:
            return 0
        if s in {"u", "unsure", ""}:
            return None
        if s in {"q", "quit"}:
            raise KeyboardInterrupt()
        print("Please enter y / n / u / q: ", end="", flush=True)


def _interactive_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    labels: list[int | None] = []
    try:
        for _, row in df.iterrows():
            label = _prompt_label(row)
            labels.append(label)
    except KeyboardInterrupt:
        # If auditor quits early, pad None for remaining rows
        remaining = len(df) - len(labels)
        if remaining > 0:
            labels.extend([None] * remaining)
        print("\n[audit] Quit requested. Computing metrics on labeled subset...")
    df["label"] = labels
    return df


# -----------------------------
# Reporting
# -----------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _write_report(
    out_path: Path,
    input_path: Path,
    contracts_path: Path | None,
    sample_size: int,
    threshold: float,
    df_labeled: pd.DataFrame,
    metrics: dict[str, PrecisionMetrics],
) -> None:
    _ensure_parent(out_path)

    def _metrics_to_dict(pm: PrecisionMetrics) -> dict[str, Any]:
        return {
            "n_total": pm.n_total,
            "n_labeled": pm.n_labeled,
            "n_positive": pm.n_positive,
            "precision": (None if pm.precision is None else round(pm.precision, 4)),
        }

    by_method = {}
    if len(df_labeled):
        counts = df_labeled["match_method"].value_counts(dropna=False)
        by_method = {str(k): int(v) for k, v in counts.items()}

    report = {
        "generated_at": _now_iso(),
        "input": str(input_path),
        "contracts": str(contracts_path) if contracts_path else None,
        "sample_size_requested": sample_size,
        "sample_size_actual": int(len(df_labeled)),
        "threshold": float(threshold),
        "metrics": {k: _metrics_to_dict(v) for k, v in metrics.items()},
        "by_method": by_method,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"[audit] Wrote precision report to {out_path}")


# -----------------------------
# CLI
# -----------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Transition MVP - Vendor Resolution Precision Audit")
    p.add_argument(
        "--input",
        type=str,
        default="data/processed/vendor_resolution.parquet",
        help="Path to vendor_resolution table (parquet/ndjson/csv)",
    )
    p.add_argument(
        "--contracts",
        type=str,
        default="data/processed/contracts_sample.parquet",
        help="Optional contracts table to enrich audit sample (parquet/ndjson/csv)",
    )
    p.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of records to sample for audit (matched only)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.80,
        help="Confidence threshold for precision metric (≥ threshold)",
    )
    p.add_argument(
        "--out",
        type=str,
        default="reports/validation/transition_precision_audit.json",
        help="Path to write JSON precision report",
    )
    p.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="If set, export unlabeled sample to CSV for offline labeling",
    )
    p.add_argument(
        "--import-csv",
        type=str,
        default=None,
        help="If set, import labeled CSV and compute precision metrics",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive labeling in terminal (y/n/u/q) then compute precision",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    input_path = Path(args.input)
    contracts_path = Path(args.contracts) if args.contracts else None
    out_path = Path(args.out)
    threshold = float(args.threshold)
    sample_size = int(args.sample_size)
    seed = int(args.seed)

    # Import labeled CSV path overrides reading the input table
    if args.import_csv:
        labeled_csv_path = Path(args.import_csv)
        if not labeled_csv_path.exists():
            print(f"[audit] Labeled CSV not found: {labeled_csv_path}", file=sys.stderr)
            return 2
        df_labeled = _import_labeled_csv(labeled_csv_path)
        metrics = _compute_precision(df_labeled, threshold=threshold)
        _write_report(
            out_path, input_path, contracts_path, sample_size, threshold, df_labeled, metrics
        )
        return 0

    # Load vendor_resolution table and sample
    try:
        df = _load_table(input_path)
    except Exception as exc:
        print(f"[audit] Failed to load input table: {exc}", file=sys.stderr)
        return 2

    required = ["contract_id", "matched_vendor_id", "match_method", "confidence"]
    for c in required:
        if c not in df.columns:
            df[c] = None

    sample = _sample_vendor_resolution(df, sample_size=sample_size, seed=seed)
    if len(sample) == 0:
        print(
            "[audit] No matched rows found in vendor_resolution (nothing to audit).",
            file=sys.stderr,
        )
        return 0

    sample = _enrich_with_contracts(sample, contracts_path)

    # Export-only mode
    if args.export_csv and not args.interactive:
        _export_csv(sample, Path(args.export_csv))
        return 0

    # Interactive mode (default to interactive if no export/import flags set)
    if args.interactive or (not args.export_csv and not args.import_csv):
        print(f"[audit] Starting interactive audit for {len(sample)} records")
        print("        Enter y (yes), n (no), u (unsure), q (quit)")
        df_labeled = _interactive_label(sample)
        # Optionally write a labeled CSV next to the report for records
        labeled_csv_default = out_path.with_suffix(".labeled.csv")
        _ensure_parent(labeled_csv_default)
        df_labeled.to_csv(labeled_csv_default, index=False)
        print(f"[audit] Wrote labeled CSV to {labeled_csv_default}")
        metrics = _compute_precision(df_labeled, threshold=threshold)
        _write_report(
            out_path, input_path, contracts_path, sample_size, threshold, df_labeled, metrics
        )
        return 0

    # Fallback (shouldn't reach here)
    print(
        "[audit] No action performed (use --interactive, --export-csv, or --import-csv).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
