"""CET validation assets.

This module contains:
- raw_cet_human_sampling: Generate human-annotation sample from classifications
- validated_cet_iaa_report: Compute inter-annotator agreement for CET labels
- validated_cet_drift_detection: Detect distributional drift in classifications
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from .utils import (
    Output,
    asset,
)


@asset(
    name="raw_cet_human_sampling",
    key_prefix=["ml"],
    description="Generate a human-annotation sample from award classifications (balanced by CET where possible).",
)
def raw_cet_human_sampling() -> Output:
    """
    Produce a small, human-readable sample for annotation.

    - Reads `data/processed/cet_award_classifications.parquet` (preferred) or `.json` NDJSON.
    - Writes NDJSON sample to `data/processed/cet_human_sample.ndjson`.
    - Writes a checks JSON to `data/processed/cet_human_sample.checks.json`.

    Sampling is best-effort:
    - If primary_cet exists, attempt to sample roughly uniformly across CETs.
    - Otherwise, uniform random sample across all rows.
    - Configurable via environment variables:
        - SBIR_ETL__CET__SAMPLE_SIZE (default: 50)
        - SBIR_ETL__CET__SAMPLE_SEED (default: 42)
    """
    import json
    import os
    from pathlib import Path
    from random import Random

    try:
        import pandas as pd
    except Exception:
        pd = None  # type: ignore

    processed_dir = Path("data/processed")
    input_parquet = processed_dir / "cet_award_classifications.parquet"
    input_json = processed_dir / "cet_award_classifications.json"

    output_ndjson = processed_dir / "cet_human_sample.ndjson"
    checks_path = processed_dir / "cet_human_sample.checks.json"

    # Config
    sample_size = int(os.environ.get("SBIR_ETL__CET__SAMPLE_SIZE", "50"))
    seed = int(os.environ.get("SBIR_ETL__CET__SAMPLE_SEED", "42"))
    Random(seed)

    def _read_awards():
        if pd is not None and input_parquet.exists():
            try:
                return pd.read_parquet(input_parquet)
            except Exception:
                pass
        if input_json.exists():
            rows = []
            with input_json.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
            if rows:
                try:
                    return pd.DataFrame(rows)
                except Exception:
                    return None
        return None

    df = _read_awards()
    total_rows = 0
    sampled_rows = 0

    if df is None or df.empty:
        # Write empty sample and checks
        output_ndjson.write_text("", encoding="utf-8")
        with checks_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "ok": True,
                    "reason": "no_input",
                    "total_rows": 0,
                    "sampled_rows": 0,
                    "source": str(input_parquet if input_parquet.exists() else input_json),
                },
                fh,
                indent=2,
            )
        return Output(
            value=str(output_ndjson),
            metadata={"path": str(output_ndjson), "rows": 0, "checks_path": str(checks_path)},
        )

    # Normalize fields for annotation convenience
    total_rows = len(df)
    keep_cols = [
        "award_id",
        "primary_cet",
        "primary_score",
        "supporting_cets",
        "classified_at",
        "taxonomy_version",
        "title",
        "abstract",
        "keywords",
    ]
    existing_cols = [c for c in keep_cols if c in df.columns]
    df = df[existing_cols].copy()

    # Sampling strategy: balanced by primary_cet if present, else uniform random
    if "primary_cet" in df.columns and df["primary_cet"].notna().any():
        groups = []
        per_cet = max(1, sample_size // max(1, df["primary_cet"].nunique()))
        for _cet, sub in df.groupby("primary_cet"):
            rows = (
                sub.sample(n=min(per_cet, len(sub)), random_state=seed)
                if hasattr(sub, "sample")
                else sub.iloc[:per_cet]
            )
            groups.append(rows)
        df_sample = (
            pd.concat(groups).drop_duplicates("award_id")
            if pd is not None
            else df.iloc[:sample_size]
        )
        # If under-filled due to small groups, top-up uniformly
        if len(df_sample) < sample_size:
            remaining = df[~df["award_id"].isin(df_sample["award_id"])]
            top_up = remaining.sample(
                n=min(sample_size - len(df_sample), len(remaining)), random_state=seed
            )
            df_sample = pd.concat([df_sample, top_up]).drop_duplicates("award_id")
        df_sample = df_sample.head(sample_size)
    else:
        # Uniform random
        if hasattr(df, "sample"):
            df_sample = df.sample(n=min(sample_size, len(df)), random_state=seed)
        else:
            # Fallback deterministic slice
            df_sample = df.head(sample_size)

    sampled_rows = len(df_sample)

    # Write NDJSON
    with output_ndjson.open("w", encoding="utf-8") as fh:
        for _, row in df_sample.iterrows():
            # Keep only JSON-serializable structures
            rec = {k: row.get(k) for k in existing_cols}
            # Ensure keywords and supporting_cets are basic types
            if isinstance(rec.get("keywords"), list | tuple):
                rec["keywords"] = list(rec["keywords"])
            if isinstance(rec.get("supporting_cets"), list | tuple):
                rec["supporting_cets"] = list(rec["supporting_cets"])
            fh.write(json.dumps(rec) + "\n")

    # Checks
    checks = {
        "ok": True,
        "total_rows": int(total_rows),
        "sampled_rows": int(sampled_rows),
        "balanced_by_primary": "primary_cet" in existing_cols,
        "seed": seed,
        "source": str(input_parquet if input_parquet.exists() else input_json),
    }
    with checks_path.open("w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    return Output(
        value=str(output_ndjson),
        metadata={
            "path": str(output_ndjson),
            "rows": int(sampled_rows),
            "checks_path": str(checks_path),
        },
    )




@asset(
    name="validated_cet_iaa_report",
    key_prefix=["ml"],
    description="Compute inter-annotator agreement (IAA) for CET labels from human annotations.",
)
def validated_cet_iaa_report() -> Output:
    """
    Compute inter-annotator agreement (Cohen's kappa and percent agreement) for CET labels.

    Expected input:
    - Annotation files under `data/processed/annotations/` with extension `.jsonl` or `.ndjson`.
    - Each line contains at least:
        { "award_id": "...", "annotator": "userA", "labels": ["cet_id1", "cet_id2", ...] }

    Behavior:
    - Aligns on award_id across annotators
    - Converts multi-label sets to a canonical single-label for kappa via:
        - primary chosen label (first in list) or None
      and computes:
        - Cohen's kappa for each annotator pair on the canonical label
        - Percent agreement on exact set equality across annotators
    - Writes `reports/analytics/cet_iaa_report.json` and returns a summary.
    """
    import json
    from itertools import combinations
    from pathlib import Path

    try:
        import pandas as pd
    except Exception:
        pd = None  # type: ignore

    annotations_dir = Path("data/processed/annotations")
    reports_dir = Path("reports/analytics")
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "cet_iaa_report.json"

    # Collect rows from all .jsonl/.ndjson files
    rows = []
    if annotations_dir.exists():
        for p in annotations_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".jsonl", ".ndjson"):
                continue
            try:
                with p.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        obj = json.loads(line)
                        rows.append(
                            {
                                "award_id": obj.get("award_id"),
                                "annotator": obj.get("annotator"),
                                "labels": obj.get("labels") or [],
                            }
                        )
            except Exception:
                continue

    if not rows or pd is None:
        payload: Any = {
            "ok": True,
            "reason": "no_annotations" if not rows else "pandas_unavailable",
            "pairs": 0,
            "kappa": {},
            "percent_agreement": None,
            "path": str(out_path),
        }
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        return Output(value=str(out_path), metadata=payload)

    df = pd.DataFrame(rows)

    # Canonical per-annotator primary label (first label or None)
    def _primary(labels):
        try:
            return (labels or [None])[0]
        except Exception:
            return None

    df["primary"] = df["labels"].apply(_primary)

    # Build pivot award_id x annotator -> primary label
    pivot = df.pivot_table(index="award_id", columns="annotator", values="primary", aggfunc="first")

    # Kappa per annotator pair (only on overlapping awards)
    def _cohen_kappa(series_a, series_b):
        # Compute Cohen's kappa manually for two categorical series
        import math

        # Drop pairs with missing values
        paired = [
            (a, b) for a, b in zip(series_a, series_b, strict=False) if pd.notna(a) and pd.notna(b)
        ]
        if not paired:
            return None
        labels = list({x for ab in paired for x in ab})
        label_to_idx = {label: i for i, label in enumerate(labels)}
        n = len(paired)
        # Confusion counts
        counts = [[0] * len(labels) for _ in labels]
        for a, b in paired:
            counts[label_to_idx[a]][label_to_idx[b]] += 1
        # Observed agreement
        po = sum(counts[i][i] for i in range(len(labels))) / n
        # Expected agreement
        row_marginals = [
            sum(counts[i][j] for j in range(len(labels))) / n for i in range(len(labels))
        ]
        col_marginals = [
            sum(counts[i][j] for i in range(len(labels))) / n for j in range(len(labels))
        ]
        pe = sum(row_marginals[i] * col_marginals[i] for i in range(len(labels)))
        if math.isclose(1.0 - pe, 0.0):
            return None
        return (po - pe) / (1.0 - pe)

    kappa_results = {}
    annotators = [c for c in pivot.columns if str(c) != "nan"]
    for a, b in combinations(annotators, 2):
        s1 = pivot[a].tolist()
        s2 = pivot[b].tolist()
        kappa_results[f"{a}__vs__{b}"] = _cohen_kappa(s1, s2)

    # Percent agreement on exact label sets across annotators (only awards with >=2 annotations)
    set_pivot = df.pivot_table(
        index="award_id", columns="annotator", values="labels", aggfunc="first"
    )
    agree_count = 0
    denom = 0
    for _, row in set_pivot.iterrows():
        non_null = [v for v in row.tolist() if isinstance(v, list)]
        if len(non_null) < 2:
            continue
        denom += 1
        # Compare all sets for equality
        eq = True
        for i in range(1, len(non_null)):
            if set(non_null[i]) != set(non_null[0]):
                eq = False
                break
        if eq:
            agree_count += 1
    percent_agreement = (agree_count / denom) if denom > 0 else None

    payload = {
        "ok": True,
        "pairs": int(len(kappa_results)),
        "kappa": kappa_results,
        "percent_agreement": percent_agreement,
        "path": str(out_path),
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    return Output(value=str(out_path), metadata=payload)




@asset(
    name="validated_cet_drift_detection",
    key_prefix=["ml"],
    description=(
        "Detect distributional drift for CET classifications and model scores by "
        "comparing current distributions to a stored baseline. Emits alerts and "
        "writes a small report to `reports/alerts` and `reports/benchmarks`."
    ),
)
def validated_cet_drift_detection() -> Output:
    """
    Model drift detection asset for CET classification outputs.

    Behavior (best-effort / import-safe):
    - Loads award-level CET classifications from `data/processed/cet_award_classifications.parquet`
      or NDJSON fallback.
    - Computes two simple distributions:
        * primary_score histogram (continuous scores)
        * primary_cet frequency distribution (categorical)
    - Attempts to load a baseline distributions file at `reports/benchmarks/cet_baseline_distributions.json`.
      If baseline is missing, the asset writes current distributions as a baseline candidate
      to `reports/benchmarks/cet_baseline_distributions_current.json` and returns with no alert.
    - If baseline exists, computes Jensen-Shannon divergence (symmetric) between baseline and current
      distributions for both score and label distributions. If divergence exceeds thresholds (configurable
      via env vars), writes an alerts JSON and emits a non-fatal report.
    - Writes:
        - reports/benchmarks/cet_drift_report.json  (summary & divergence values)
        - reports/alerts/cet_drift_alerts.json       (alerts if any)
    """
    import json
    import os
    from datetime import datetime
    from pathlib import Path

    try:
        import numpy as np
        import pandas as pd
    except Exception:
        pd = None  # type: ignore
        np = None  # type: ignore

    # Lazy import for AlertCollector (best-effort)
    try:
        from src.utils.performance_alerts import (
            Alert,
            AlertCollector,
            AlertSeverity,
        )
    except Exception:
        AlertCollector = None  # type: ignore
        Alert = None  # type: ignore
        AlertSeverity = None  # type: ignore

    processed_dir = Path("data/processed")
    awards_parquet = processed_dir / "cet_award_classifications.parquet"
    awards_json = processed_dir / "cet_award_classifications.json"

    benchmarks_dir = Path("reports/benchmarks")
    benchmarks_dir.mkdir(parents=True, exist_ok=True)
    alerts_dir = Path("reports/alerts")
    alerts_dir.mkdir(parents=True, exist_ok=True)

    baseline_path = benchmarks_dir / "cet_baseline_distributions.json"
    baseline_candidate_path = benchmarks_dir / "cet_baseline_distributions_current.json"
    drift_report = benchmarks_dir / "cet_drift_report.json"
    alerts_out = alerts_dir / "cet_drift_alerts.json"

    # Configurable thresholds (env vars, fallback defaults)
    SCORE_JS_THRESHOLD = float(os.environ.get("SBIR_ETL__CET__DRIFT__SCORE_JS_THRESHOLD", "0.15"))
    LABEL_JS_THRESHOLD = float(os.environ.get("SBIR_ETL__CET__DRIFT__LABEL_JS_THRESHOLD", "0.10"))

    # Helper: safe JSON read
    def _read_json(path: Path):
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            return None
        return None

    # Read awards
    def _read_awards():
        if pd is None:
            return None  # type: ignore[unreachable]
        if awards_parquet.exists():
            try:
                return pd.read_parquet(awards_parquet)
            except Exception:
                pass
        if awards_json.exists():
            try:
                rows = []
                with awards_json.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        rows.append(json.loads(line))
                return pd.DataFrame(rows)
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()

    df = _read_awards()
    if df is None or df.empty:
        # Nothing to do; write an empty report and return
        payload = {
            "ok": True,
            "reason": "no_input",
            "generated_at": datetime.utcnow().isoformat(),
            "score_js_divergence": None,
            "label_js_divergence": None,
            "score_threshold": SCORE_JS_THRESHOLD,
            "label_threshold": LABEL_JS_THRESHOLD,
        }
        try:
            with drift_report.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except Exception:
            pass
        return Output(value=payload, metadata=payload)

    # Prepare current distributions
    # Primary scores (coerce to floats, dropna)
    scores = None
    if "primary_score" in df.columns:
        try:
            scores = pd.to_numeric(df["primary_score"], errors="coerce").dropna().astype(float)
        except Exception:
            scores = None

    # Primary CET frequency
    label_counts = {}
    if "primary_cet" in df.columns:
        try:
            label_counts = df["primary_cet"].fillna("__none__").value_counts().to_dict()
        except Exception:
            label_counts = {}

    # Convert counts to probability mass function (PMF) for labels
    def _pmf_from_counts(counts: dict):
        total = sum(v for v in counts.values() if v is not None)
        if total <= 0:
            return {}
        return {k: float(v) / total for k, v in counts.items()}

    current_label_pmf = _pmf_from_counts(label_counts)

    # For score histogram, create fixed bins (0..100 by 10)
    def _score_hist_pmf(series, bins=None):
        if series is None or len(series) == 0 or np is None:
            return {}
        if bins is None:
            bins = list(range(0, 101, 10))  # 0-10,10-20,...,90-100
        try:
            hist, bin_edges = np.histogram(series.clip(0, 100), bins=bins)
            total = int(hist.sum())
            if total == 0:
                return {}
            pmf = {}
            for i in range(len(hist)):
                label = f"{int(bin_edges[i])}-{int(bin_edges[i+1])}"
                pmf[label] = float(hist[i]) / total
            return pmf
        except Exception:
            return {}

    current_score_pmf = _score_hist_pmf(scores)

    # If no baseline exists, write candidate and exit (operator can promote to baseline manually)
    baseline = _read_json(baseline_path)
    if baseline is None:
        # Write current distributions as candidate baseline
        candidate = {
            "generated_at": datetime.utcnow().isoformat(),
            "label_pmf": current_label_pmf,
            "score_pmf": current_score_pmf,
        }
        try:
            with baseline_candidate_path.open("w", encoding="utf-8") as fh:
                json.dump(candidate, fh, indent=2)
        except Exception:
            pass
        payload = {
            "ok": True,
            "reason": "baseline_missing",
            "message": "Baseline distributions not found; wrote current distributions as candidate",
            "candidate_path": str(baseline_candidate_path),
            "generated_at": datetime.utcnow().isoformat(),
        }
        try:
            with drift_report.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        except Exception:
            pass
        return Output(value=payload, metadata=payload)

    # Baseline exists: extract baseline pmfs (expected keys: label_pmf, score_pmf)
    baseline_label_pmf = baseline.get("label_pmf", {}) if isinstance(baseline, dict) else {}
    baseline_score_pmf = baseline.get("score_pmf", {}) if isinstance(baseline, dict) else {}

    # Ensure support alignment for label pmfs (add zeros for missing labels)
    def _align_pmfs(p, q):
        keys = set(p.keys()) | set(q.keys())
        p_arr = [p.get(k, 0.0) for k in sorted(keys)]
        q_arr = [q.get(k, 0.0) for k in sorted(keys)]
        labels = sorted(keys)
        return p_arr, q_arr, labels

    # Jensen-Shannon divergence (symmetric, bounded 0..1)
    def _js_divergence(p_arr, q_arr):
        try:
            import math
        except Exception:
            # Fallback simple impl using pure math
            pass
        # Convert to numpy arrays if available for numeric stability
        if np is not None:
            p = np.array(p_arr, dtype=float)
            q = np.array(q_arr, dtype=float)
            # normalize
            p_sum = p.sum()
            q_sum = q.sum()
            if p_sum > 0:
                p = p / p_sum
            if q_sum > 0:
                q = q / q_sum
            m = 0.5 * (p + q)

            # Use KL divergence helper with safe handling
            def _kl(a, b):
                # kl divergence sum a * log2(a/b) where 0*log(0)=0
                mask = (a > 0) & (b > 0)
                if mask.sum() == 0:
                    return 0.0
                return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

            kl_pm = _kl(p, m)
            kl_qm = _kl(q, m)
            js = 0.5 * (kl_pm + kl_qm)
            # Convert to 0..1 by dividing by log2(len) if len>1 (optional). Keep raw JS for thresholding.
            return float(js)
        else:
            # Pure python fallback
            import math  # type: ignore[unreachable]

            def safe_log2(x):
                return math.log(x, 2) if x > 0 else 0.0

            p = list(map(float, p_arr))
            q = list(map(float, q_arr))
            p_sum = sum(p)
            q_sum = sum(q)
            if p_sum > 0:
                p = [x / p_sum for x in p]
            if q_sum > 0:
                q = [x / q_sum for x in q]
            m = [0.5 * (pp + qq) for pp, qq in zip(p, q, strict=False)]

            def kl(a, b):
                s = 0.0
                for ai, bi in zip(a, b, strict=False):
                    if ai > 0 and bi > 0:
                        s += ai * safe_log2(ai / bi)
                return s

            return 0.5 * (kl(p, m) + kl(q, m))

    # Align and compute divergences
    p_label, q_label, label_keys = _align_pmfs(baseline_label_pmf, current_label_pmf)
    label_js = _js_divergence(p_label, q_label) if label_keys else None

    p_score, q_score, score_keys = _align_pmfs(baseline_score_pmf, current_score_pmf)
    score_js = _js_divergence(p_score, q_score) if score_keys else None

    # Compose report
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "label_js_divergence": label_js,
        "score_js_divergence": score_js,
        "label_keys": label_keys,
        "score_keys": score_keys,
        "score_threshold": SCORE_JS_THRESHOLD,
        "label_threshold": LABEL_JS_THRESHOLD,
    }

    # Build alerts based on thresholds
    alerts_payload = {"alerts": [], "generated_at": datetime.utcnow().isoformat()}
    if label_js is not None and label_js > LABEL_JS_THRESHOLD:
        alerts_payload["alerts"].append(
            {
                "severity": "WARNING" if label_js <= 2 * LABEL_JS_THRESHOLD else "FAILURE",
                "type": "label_distribution_drift",
                "message": f"Label distribution JS divergence {label_js:.4f} exceeds threshold {LABEL_JS_THRESHOLD:.4f}",
                "value": label_js,
            }
        )
    if score_js is not None and score_js > SCORE_JS_THRESHOLD:
        alerts_payload["alerts"].append(
            {
                "severity": "WARNING" if score_js <= 2 * SCORE_JS_THRESHOLD else "FAILURE",
                "type": "score_distribution_drift",
                "message": f"Score distribution JS divergence {score_js:.4f} exceeds threshold {SCORE_JS_THRESHOLD:.4f}",
                "value": score_js,
            }
        )

    # Persist report and alerts
    try:
        with drift_report.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    except Exception:
        pass

    try:
        with alerts_out.open("w", encoding="utf-8") as fh:
            json.dump(alerts_payload, fh, indent=2)
    except Exception:
        pass

    # Optionally log alerts via AlertCollector if available (best-effort)
    if AlertCollector is not None and Alert is not None and AlertSeverity is not None:
        try:
            collector = AlertCollector(asset_name="validated_cet_drift_detection")
            for a in alerts_payload.get("alerts", []):
                sev = AlertSeverity.WARNING if a["severity"] == "WARNING" else AlertSeverity.FAILURE
                alert = Alert(
                    timestamp=datetime.utcnow(),
                    severity=sev,
                    alert_type=a["type"],
                    message=a["message"],
                    threshold_value=LABEL_JS_THRESHOLD
                    if "label" in a["type"]
                    else SCORE_JS_THRESHOLD,
                    actual_value=a["value"],
                    metric_name=a["type"],
                )
                collector.alerts.append(alert)
            # Save structured alerts JSON via collector
            try:
                collector.save_to_file(alerts_out)
            except Exception:
                pass
        except Exception:
            pass

    # Return the report as asset output
    metadata = {"drift_report": str(drift_report), "alerts": str(alerts_out)}
    return Output(value=report, metadata=metadata)


