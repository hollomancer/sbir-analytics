#!/usr/bin/env python3
"""
CET performance profiling script

Profiles the CET award classification inference step and produces a small
performance report (JSON + Markdown). The script is intended for local
profiling and CI benchmark runs.

Behavior:
- Loads a sample of enriched award records:
  - Prefers `data/processed/enriched_sbir_awards.parquet`
  - Falls back to `data/processed/enriched_sbir_awards.ndjson`
  - If neither exists, uses a tiny synthetic sample.
- Runs a lightweight classification routine in batches (configurable).
  - If a real trained model artifact exists at `artifacts/models/cet_classifier_v1.pkl`
    this script will attempt to load it (best-effort). If loading fails, a
    deterministic keyword-based fallback classifier is used for profiling.
- Uses the performance monitoring utilities (`src.utils.performance_monitor`)
  to capture timing/memory metrics where available.
- Writes outputs:
  - JSON summary: --output-json (default: /tmp/cet_performance.json)
  - Markdown summary: --output-md (default: /tmp/cet_performance.md)
  - Optionally saves as baseline in reports/benchmarks/baseline.json with --save-as-baseline

Exit code:
- 0 on success
- non-zero on unexpected failures
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

# Defensive optional imports
try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore

# Performance monitor/reporting utilities (import-safe)
try:
    from src.utils.performance_monitor import performance_monitor  # type: ignore
except Exception:
    performance_monitor = None  # type: ignore

try:
    from src.utils.performance_reporting import PerformanceReporter  # type: ignore
except Exception:
    PerformanceReporter = None  # type: ignore


DEFAULT_MODEL_PATH = Path("artifacts/models/cet_classifier_v1.pkl")
DEFAULT_SAMPLE_PARQUET = Path("data/processed/enriched_sbir_awards.parquet")
DEFAULT_SAMPLE_NDJSON = Path("data/processed/enriched_sbir_awards.ndjson")
DEFAULT_BASELINE_OUT = Path("reports/benchmarks/baseline.json")


def load_sample_texts(sample_size: int) -> List[str]:
    """
    Load award texts for profiling. Returns a list of concatenated text documents
    (title + abstract + keywords) to be classified.
    """
    texts: List[str] = []

    # Try parquet first
    if pd is not None and DEFAULT_SAMPLE_PARQUET.exists():
        try:
            df = pd.read_parquet(DEFAULT_SAMPLE_PARQUET)
            logger.info("Loaded %d rows from %s", len(df), DEFAULT_SAMPLE_PARQUET)

            # Build lightweight text field
            def _row_to_text(r):
                parts = []
                for col in ("title", "abstract", "keywords"):
                    v = (
                        r.get(col)
                        if isinstance(r, dict)
                        else r.get(col)
                        if hasattr(r, "get")
                        else None
                    )
                    if v is None:
                        continue
                    if isinstance(v, (list, tuple)):
                        parts.append(" ".join(map(str, v)))
                    else:
                        parts.append(str(v))
                return " ".join(parts)

            for _, r in df.head(sample_size).iterrows():
                texts.append(_row_to_text(r))
            if texts:
                return texts
        except Exception as exc:
            logger.warning("Failed to read parquet sample: %s", exc)

    # Fallback to NDJSON
    if DEFAULT_SAMPLE_NDJSON.exists():
        try:
            with DEFAULT_SAMPLE_NDJSON.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        title = obj.get("title", "")
                        abstract = obj.get("abstract", "")
                        keywords = obj.get("keywords", "")
                        if isinstance(keywords, (list, tuple)):
                            keywords = " ".join(map(str, keywords))
                        texts.append(" ".join([str(title), str(abstract), str(keywords)]).strip())
                        if len(texts) >= sample_size:
                            break
                    except Exception:
                        continue
            if texts:
                logger.info("Loaded %d rows from %s", len(texts), DEFAULT_SAMPLE_NDJSON)
                return texts
        except Exception as exc:
            logger.warning("Failed to read NDJSON sample: %s", exc)

    # Synthetic fallback
    logger.warning("No processed sample found; using synthetic sample for profiling")
    sample_texts = [
        "machine learning and neural networks for image analysis",
        "quantum computing research on qubit coherence and entanglement",
        "natural language processing with transformer models for text classification",
        "biomedical imaging and signal processing using convolutional networks",
        "statistical models for optimization and operations research",
    ]
    # Repeat to reach sample_size
    while len(texts) < sample_size:
        texts.extend(sample_texts)
    return texts[:sample_size]


class FallbackClassifier:
    """
    Very small, deterministic classifier used when a real model artifact is missing.
    It maps a small set of keywords to CET IDs for the purpose of profiling.
    """

    def __init__(self, taxonomy: Optional[Dict[str, List[str]]] = None):
        # Default minimal keyword map
        self.keyword_map = taxonomy or {
            "artificial_intelligence": ["machine", "learning", "neural", "network", "deep"],
            "quantum_information_science": ["quantum", "qubit", "entanglement"],
            "biotech": ["biomedical", "bio", "protein", "genome"],
        }

    def classify_batch(
        self, texts: Iterable[str], batch_size: int = 128
    ) -> List[List[Dict[str, Any]]]:
        """
        Returns a list of lists (predictions per text). Each prediction is a dict:
            {"cet_id": str, "score": float}
        The primary prediction is first in the list.
        """
        out: List[List[Dict[str, Any]]] = []
        for t in texts:
            txt = (t or "").lower()
            scores: Dict[str, int] = {}
            for cet_id, keys in self.keyword_map.items():
                score = 0
                for k in keys:
                    if k in txt:
                        score += 1
                if score > 0:
                    scores[cet_id] = score
            # Convert to sorted list
            preds = sorted(
                [{"cet_id": k, "score": float(v)} for k, v in scores.items()],
                key=lambda x: -x["score"],
            )
            out.append(preds)
        return out


def try_load_model(path: Path):
    """
    Best-effort attempt to load a pickled ApplicabilityModel or similar artifact.
    If loading fails or the artifact is absent, return None.
    """
    if not path.exists():
        logger.info("Model artifact not found at %s", path)
        return None

    try:
        with path.open("rb") as fh:
            obj = pickle.load(fh)
        # The artifact may be a dict with 'pipelines' or a wrapped model object.
        # We try to detect a callable classify_batch method; otherwise return the raw object.
        if hasattr(obj, "classify_batch"):
            logger.info("Loaded model object with classify_batch()")
            return obj
        if isinstance(obj, dict) and "pipelines" in obj:
            # Some saved artifacts are dicts; wrap a simple adaptor that calls pipeline.predict_proba
            pipelines = obj.get("pipelines", {})

            class Adaptor:
                def __init__(self, pipelines):
                    self.pipelines = pipelines

                def classify_batch(self, texts: Iterable[str], batch_size: int = 128):
                    # Simple deterministic scoring using pipeline.predict_proba if available
                    results = []
                    for t in texts:
                        row_preds = []
                        for cet_id, pipe in self.pipelines.items():
                            try:
                                # Some DummyPipeline implementations expose predict_proba
                                if hasattr(pipe, "predict_proba"):
                                    prob = pipe.predict_proba([t])[0]
                                    # If predict_proba returns 2-class array, take positive class
                                    if isinstance(prob, (list, tuple)) and len(prob) >= 1:
                                        score = float(prob[-1] if len(prob) > 1 else prob[0])
                                    else:
                                        score = float(prob)
                                else:
                                    # fallback: keyword boosting
                                    score = 0.0
                            except Exception:
                                score = 0.0
                            if score > 0.0:
                                row_preds.append({"cet_id": cet_id, "score": float(score)})
                        row_preds = sorted(row_preds, key=lambda x: -x["score"])
                        results.append(row_preds)
                    return results

            logger.info("Wrapped pipelines dict into an adaptor for classify_batch()")
            return Adaptor(pipelines)
        # Unknown artifact shape; try to use as-is
        logger.info("Loaded artifact but could not detect classify_batch; returning raw object")
        return obj
    except Exception as exc:
        logger.exception("Failed to load model artifact: %s", exc)
        return None


def profile_inference(
    texts: List[str],
    classifier,
    batch_size: int = 128,
) -> Dict[str, Any]:
    """
    Run classification in batches and capture performance metrics using performance_monitor if available.
    Returns a summary dict with timing and throughput metrics.
    """
    total = len(texts)
    logger.info("Profiling inference on %d texts (batch_size=%d)", total, batch_size)

    # Reset and prime performance monitor if available
    if performance_monitor is not None:
        try:
            performance_monitor.reset_metrics()
        except Exception:
            # best-effort
            pass

    t0 = time.perf_counter()
    peak_memory_mb_before = (
        psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else None
    )

    # Run batches
    processed = 0
    try:
        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            # time a single batch via performance monitor if available
            if performance_monitor is not None:
                try:
                    with performance_monitor.monitor_block("cet_inference_batch"):
                        _ = classifier.classify_batch(batch, batch_size=batch_size)
                except Exception:
                    # Fallback to direct call
                    _ = classifier.classify_batch(batch, batch_size=batch_size)
            else:
                _ = classifier.classify_batch(batch, batch_size=batch_size)
            processed += len(batch)
    except Exception as exc:
        logger.exception("Error during inference profiling: %s", exc)
        raise

    t1 = time.perf_counter()
    peak_memory_mb_after = (
        psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024) if psutil else None
    )

    duration = t1 - t0
    records_per_sec = float(processed) / duration if duration > 0 else None
    memory_delta_mb = None
    if peak_memory_mb_before is not None and peak_memory_mb_after is not None:
        memory_delta_mb = peak_memory_mb_after - peak_memory_mb_before

    # Optionally fetch monitor summary
    monitor_summary = None
    if performance_monitor is not None:
        try:
            monitor_summary = performance_monitor.get_metrics_summary()
        except Exception:
            monitor_summary = None

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "sample_count": processed,
        "duration_seconds": duration,
        "records_per_second": records_per_sec,
        "memory_delta_mb": memory_delta_mb,
        "monitor_summary": monitor_summary,
    }
    logger.info(
        "Inference profiling complete: duration=%.3fs, r/s=%.1f",
        duration,
        records_per_sec or 0.0,
    )
    return summary


def save_reports(summary: Dict[str, Any], output_json: Path, output_md: Path) -> None:
    """
    Save JSON and Markdown reports summarizing the profiling results.
    """
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    # Build Markdown
    lines = []
    lines.append("# CET Inference Performance Profile")
    lines.append("")
    lines.append(f"- Timestamp: {summary.get('timestamp')}")
    lines.append(f"- Sample count: {summary.get('sample_count')}")
    lines.append(f"- Duration (s): {summary.get('duration_seconds'):.3f}")
    rps = summary.get("records_per_second")
    lines.append(f"- Records / second: {rps:.2f}" if rps else "- Records / second: n/a")
    md = "\n".join(lines)
    with output_md.open("w", encoding="utf-8") as fh:
        fh.write(md)


def maybe_publish_baseline(
    summary: Dict[str, Any], baseline_path: Path, force: bool = False
) -> None:
    """
    Optionally write the summary into the baseline file for future regression comparisons.
    """
    try:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.utcnow().isoformat(),
            "cet_inference": {
                "sample_count": summary.get("sample_count"),
                "duration_seconds": summary.get("duration_seconds"),
                "records_per_second": summary.get("records_per_second"),
            },
        }
        if baseline_path.exists() and not force:
            logger.info("Baseline already exists at %s (use --force to overwrite)", baseline_path)
            return
        baseline_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Baseline written to %s", baseline_path)
    except Exception as exc:
        logger.exception("Failed to write baseline: %s", exc)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile CET inference performance")
    parser.add_argument(
        "--sample-size", type=int, default=1000, help="Number of award texts to profile"
    )
    parser.add_argument("--batch-size", type=int, default=128, help="Batch size for inference")
    parser.add_argument(
        "--model-path",
        type=str,
        default=str(DEFAULT_MODEL_PATH),
        help="Path to model artifact (pickle)",
    )
    parser.add_argument(
        "--output-json", type=str, default="/tmp/cet_performance.json", help="JSON output path"
    )
    parser.add_argument(
        "--output-md", type=str, default="/tmp/cet_performance.md", help="Markdown output path"
    )
    parser.add_argument(
        "--save-as-baseline",
        action="store_true",
        help="Save profile as baseline to reports/benchmarks",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite baseline if present")
    args = parser.parse_args(argv)

    # Load sample texts
    try:
        texts = load_sample_texts(args.sample_size)
    except Exception as exc:
        logger.exception("Failed to load sample texts: %s", exc)
        return 2

    # Attempt to load a model artifact; else fallback
    classifier = None
    try:
        classifier = try_load_model(Path(args.model_path))
    except Exception:
        classifier = None

    if classifier is None:
        logger.warning("No usable model found; using fallback classifier for profiling")
        classifier = FallbackClassifier()

    # Run profiling
    try:
        summary = profile_inference(texts, classifier, batch_size=args.batch_size)
    except Exception as exc:
        logger.exception("Profiling failed: %s", exc)
        return 3

    # Save reports
    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    try:
        save_reports(summary, out_json, out_md)
    except Exception as exc:
        logger.exception("Failed to save reports: %s", exc)

    # Optionally save baseline
    if args.save_as_baseline:
        try:
            maybe_publish_baseline(summary, DEFAULT_BASELINE_OUT, force=args.force)
        except Exception:
            logger.exception("Failed to publish baseline")

    # Optionally publish via PerformanceReporter if available
    if PerformanceReporter is not None:
        try:
            reporter = PerformanceReporter()
            # Best-effort; many reporter implementations vary - attempt common call patterns
            if hasattr(reporter, "save"):
                reporter.save(summary, out_json)
            elif hasattr(reporter, "publish"):
                reporter.publish(summary, out_json)
            elif hasattr(reporter, "record"):
                reporter.record("cet_inference", summary)
            else:
                logger.debug(
                    "PerformanceReporter available but has no known API to publish summary"
                )
        except Exception:
            logger.debug("PerformanceReporter publish attempt failed (continuing)")

    logger.info("Profile complete. JSON -> %s, MD -> %s", out_json, out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
