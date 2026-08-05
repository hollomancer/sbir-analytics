#!/usr/bin/env python3
"""Capture a point-in-time CET classifier metrics snapshot.

Trains the CET ApplicabilityModel under the current code and configuration,
records test-set precision/recall/F1 (per CET area and macro/micro), and
serializes the result with enough environment metadata that a future run
can be compared against this baseline mechanically rather than from memory.

The motivating use case is the Phase 1 fix-plan checkpoint in
`docs/steering/ml-methodology-review.md`: PRs 1-4 will change how the
classifier is trained and how its metrics are computed. Comparing the
post-fix run against this snapshot quantifies the methodology-honesty
delta — and via the `cet_alignment` cascade, the likely shift in
transition-scoring precision against the CLAUDE.md ≥85% target.

Inputs:
  data/processed/cet_award_training.parquet  (preferred)
  data/processed/cet_award_training.ndjson   (fallback)

  Plus the CET taxonomy + classification config loaded via TaxonomyLoader.

Outputs (default — regenerable, gitignored):
  reports/ml/cet_classifier_baseline.json   — full structured snapshot
  reports/ml/cet_classifier_baseline.md     — human-readable summary

Permanent baseline (with --save-as-baseline):
  docs/ml/baselines/cet_classifier_baseline_<timestamp>.json
  These are committed; treat as immutable historical records.

Usage:
  # Local snapshot (real training data must be present)
  python scripts/ml/snapshot_benchmark.py

  # Test the script with synthetic data (no real training data needed)
  python scripts/ml/snapshot_benchmark.py --synthetic

  # Capture multiple runs to bracket variance (default n=1, recommend 3-5
  # for the pre/post Phase 1 comparison)
  python scripts/ml/snapshot_benchmark.py --n-runs 5

  # Commit the baseline alongside the methodology artifact
  python scripts/ml/snapshot_benchmark.py --save-as-baseline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def _git_branch() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def _capture_env() -> dict[str, Any]:
    import numpy
    import sklearn

    versions = {
        "python": ".".join(str(v) for v in sys.version_info[:3]),
        "numpy": numpy.__version__,
        "sklearn": sklearn.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    try:
        import pandas
        versions["pandas"] = pandas.__version__
    except Exception:
        pass
    try:
        import scipy
        versions["scipy"] = scipy.__version__
    except Exception:
        pass
    try:
        import joblib
        versions["joblib"] = joblib.__version__
    except Exception:
        pass

    return {
        "git_sha": _git_sha(),
        "git_branch": _git_branch(),
        "package_versions": versions,
        "captured_at_utc": datetime.now(UTC).isoformat(),
    }


def _dataset_hash(path: Path) -> str:
    """Hash a dataset file so changes are visible across snapshots."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _resolve_dataset_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.exists() else None
    candidates = [
        Path("data/processed/cet_award_training.parquet"),
        Path("data/processed/cet_award_training.ndjson"),
        Path("data/processed/cet_award_training.jsonl"),
        Path("data/processed/cet_award_training.csv"),
        Path("data/raw/cet_award_training.ndjson"),
        Path("data/raw/cet_award_training.jsonl"),
        Path("data/raw/cet_award_training.csv"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_dataset_from_disk(path: Path, taxonomy_version: str) -> Any:
    """Load a TrainingDataset from a parquet/ndjson/csv file.

    The schema follows `docs/ml/cet-award-training-data.md`: each row has a
    `text` field (or title+abstract+keywords to combine) plus a `labels`
    field that is either a list of CET IDs or a comma-delimited string.
    """
    import pandas as pd

    from sbir_etl.models.cet_models import TrainingDataset, TrainingExample

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix in (".ndjson", ".jsonl"):
        df = pd.read_json(path, lines=True)
    elif suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported dataset suffix: {suffix}")

    examples: list[TrainingExample] = []
    for idx, row in df.iterrows():
        labels_raw = row.get("labels", [])
        if isinstance(labels_raw, str):
            labels = [s.strip() for s in labels_raw.split(",") if s.strip()]
        elif labels_raw is None or (isinstance(labels_raw, float) and pd.isna(labels_raw)):
            labels = []
        else:
            labels = list(labels_raw)

        if not labels:
            continue  # skip unlabeled examples

        text = row.get("text") or " ".join(
            str(row.get(c) or "") for c in ("title", "abstract", "keywords") if row.get(c)
        )
        if not text.strip():
            continue

        examples.append(
            TrainingExample(
                example_id=str(row.get("example_id") or row.get("award_id") or idx),
                text=text,
                title=row.get("title"),
                keywords=row.get("keywords"),
                labels=labels,
                source=str(row.get("source") or "snapshot"),
            )
        )

    return TrainingDataset(
        dataset_id=f"snapshot-{path.stem}",
        examples=examples,
        taxonomy_version=taxonomy_version,
    )


def _build_synthetic_dataset(taxonomy_version: str) -> tuple[Any, list[Any]]:
    """Tiny synthetic dataset for testing the script itself without real data.

    2 CET areas, 12 examples — enough for the trainer to actually do
    train/test split + CV without crashing. The metrics from this run are
    NOT a meaningful baseline; the synthetic mode exists only to validate
    the pipeline end-to-end.
    """
    from sbir_etl.models.cet_models import CETArea, TrainingDataset, TrainingExample

    cet_areas = [
        CETArea(
            cet_id="artificial_intelligence",
            name="Artificial Intelligence",
            definition="ML and AI technologies",
            keywords=["machine learning", "neural network", "deep learning"],
            taxonomy_version=taxonomy_version,
        ),
        CETArea(
            cet_id="quantum_information_science",
            name="Quantum Information Science",
            definition="Quantum computing and algorithms",
            keywords=["quantum", "qubit", "entanglement"],
            taxonomy_version=taxonomy_version,
        ),
    ]

    ai_texts = [
        "machine learning for medical image classification",
        "deep neural network for natural language processing",
        "transformer architectures for sequence modeling",
        "reinforcement learning in robotic control",
        "convolutional neural network for object detection",
        "machine learning anomaly detection in sensor data",
    ]
    qis_texts = [
        "quantum entanglement for secure communication",
        "qubit error correction in superconducting systems",
        "quantum algorithms for combinatorial optimization",
        "trapped ion quantum computing architectures",
        "quantum sensing and metrology applications",
        "variational quantum eigensolvers for chemistry",
    ]

    examples: list[TrainingExample] = []
    for i, t in enumerate(ai_texts):
        examples.append(
            TrainingExample(
                example_id=f"ai_{i}",
                text=t,
                labels=["artificial_intelligence"],
                source="synthetic",
            )
        )
    for i, t in enumerate(qis_texts):
        examples.append(
            TrainingExample(
                example_id=f"qis_{i}",
                text=t,
                labels=["quantum_information_science"],
                source="synthetic",
            )
        )

    dataset = TrainingDataset(
        dataset_id="snapshot-synthetic",
        examples=examples,
        taxonomy_version=taxonomy_version,
    )
    return dataset, cet_areas


def _default_config() -> dict[str, Any]:
    """Minimal config sufficient for ApplicabilityModel.

    Mirrors the synthetic integration test config; in production this would
    be loaded from `config/cet/classification.yaml`. Kept inline to make
    the script runnable in environments where the config file isn't
    present.
    """
    return {
        "model_version": "snapshot-v1",
        "training": {
            "test_size": 0.2,
            "val_size": 0.1,
            "random_state": 42,
            "cv_folds": 3,
        },
        "tfidf": {
            "min_df": 1,
            "max_df": 1.0,
            "ngram_range": [1, 2],
            "keyword_boost_factor": 2.0,
            "sublinear_tf": True,
            "use_idf": True,
            "smooth_idf": True,
            "norm": "l2",
        },
        "logistic_regression": {
            "C": 1.0,
            "max_iter": 200,
            "solver": "lbfgs",
            "random_state": 42,
        },
        "feature_selection": {"enabled": False},
        "calibration": {"method": "sigmoid", "cv": 2},
        "batch": {"size": 16},
        "confidence_thresholds": {"high": 70.0, "medium": 40.0, "low": 0.0},
    }


def _summarize_dataset(dataset: Any) -> dict[str, Any]:
    from collections import Counter

    label_counts: Counter[str] = Counter()
    for ex in dataset.examples:
        for label in ex.labels:
            label_counts[label] += 1
    return {
        "n_examples": len(dataset.examples),
        "n_unique_labels": len(label_counts),
        "label_counts": dict(sorted(label_counts.items())),
        "label_density": (
            sum(len(ex.labels) for ex in dataset.examples) / max(len(dataset.examples), 1)
        ),
    }


def _train_once(
    dataset: Any, cet_areas: list[Any], config: dict[str, Any], seed: int
) -> dict[str, Any]:
    """Train once and return the trainer metrics dict."""
    from sbir_ml.ml.models.trainer import CETModelTrainer

    config = {**config, "training": {**config.get("training", {}), "random_state": seed}}
    config["logistic_regression"]["random_state"] = seed

    trainer = CETModelTrainer(
        cet_areas=cet_areas,
        config=config,
        taxonomy_version=cet_areas[0].taxonomy_version,
    )
    trainer.train(dataset, perform_cv=False, perform_calibration=True)
    return trainer.get_metrics()


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Across-run aggregation of headline test metrics."""
    keys = ("precision_macro", "recall_macro", "f1_macro", "precision_micro", "recall_micro", "f1_micro")
    agg: dict[str, Any] = {}
    for k in keys:
        values = [r["test"].get(k) for r in runs if r.get("test", {}).get(k) is not None]
        if values:
            agg[k] = {
                "mean": mean(values),
                "std": stdev(values) if len(values) > 1 else 0.0,
                "n": len(values),
            }
    return agg


def _write_json(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)


def _write_markdown(snapshot: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# CET classifier baseline snapshot")
    lines.append("")
    lines.append(f"**Snapshot ID:** `{snapshot['snapshot_id']}`  ")
    lines.append(f"**Captured:** {snapshot['env']['captured_at_utc']}  ")
    lines.append(f"**Git SHA:** `{snapshot['env']['git_sha']}` on `{snapshot['env']['git_branch']}`  ")
    versions = snapshot["env"]["package_versions"]
    lines.append(
        f"**Versions:** python={versions['python']}, sklearn={versions['sklearn']}, "
        f"numpy={versions['numpy']}"
    )
    lines.append("")

    lines.append("## Dataset")
    ds = snapshot["dataset"]
    lines.append(f"- Source: `{ds['source_path']}`")
    if ds.get("dataset_hash"):
        lines.append(f"- SHA-256 (16-char): `{ds['dataset_hash']}`")
    lines.append(f"- Examples: {ds['summary']['n_examples']}")
    lines.append(f"- Unique labels: {ds['summary']['n_unique_labels']}")
    lines.append(f"- Label density: {ds['summary']['label_density']:.2f}")
    lines.append("")

    lines.append("## Headline metrics (aggregate over runs)")
    agg = snapshot.get("aggregate") or {}
    if agg:
        lines.append(f"_n_runs: {snapshot['n_runs']}_")
        lines.append("")
        lines.append("| Metric | Mean | Std | n |")
        lines.append("|---|---|---|---|")
        for k, v in agg.items():
            lines.append(f"| {k} | {v['mean']:.4f} | {v['std']:.4f} | {v['n']} |")
    else:
        lines.append("_(no metrics — see runs section)_")
    lines.append("")

    lines.append("## Per-run results")
    for r in snapshot["runs"]:
        lines.append(f"### Run {r['run_id']} (seed={r['seed']})")
        test = r.get("test", {})
        lines.append(
            f"- F1 macro: {test.get('f1_macro', 0):.4f} | "
            f"F1 micro: {test.get('f1_micro', 0):.4f} | "
            f"precision macro: {test.get('precision_macro', 0):.4f} | "
            f"recall macro: {test.get('recall_macro', 0):.4f}"
        )
        lines.append(f"- Training duration: {r.get('training_duration_seconds', 0):.2f}s")
    lines.append("")

    lines.append("## Configuration")
    lines.append("```json")
    lines.append(json.dumps(snapshot["config"], indent=2))
    lines.append("```")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-path", type=Path, default=None, help="Override training data path")
    parser.add_argument("--taxonomy-version", default="NSTC-2025Q1", help="Taxonomy version label")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic 2-CET fixture (script test only)")
    parser.add_argument("--n-runs", type=int, default=1, help="Number of training runs (3-5 recommended for variance)")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed; runs use seed, seed+1, seed+2, ...")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("reports/ml/cet_classifier_baseline.json"),
        help="JSON output path (gitignored by default)",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("reports/ml/cet_classifier_baseline.md"),
        help="Markdown output path (gitignored by default)",
    )
    parser.add_argument(
        "--save-as-baseline",
        action="store_true",
        help="Also write a committed copy to docs/ml/baselines/ with timestamp",
    )
    args = parser.parse_args()

    # Resolve dataset
    if args.synthetic:
        dataset, cet_areas = _build_synthetic_dataset(args.taxonomy_version)
        source_path = "<synthetic>"
        dataset_hash = None
    else:
        path = _resolve_dataset_path(args.data_path)
        if path is None:
            print(
                "ERROR: no CET training data found. Looked under data/processed/ and data/raw/.\n"
                "Either (a) materialize via the Dagster asset cet_award_training_dataset, "
                "(b) pass --data-path, or (c) run with --synthetic to test the script.",
                file=sys.stderr,
            )
            return 2
        dataset = _load_dataset_from_disk(path, args.taxonomy_version)
        from sbir_ml.ml.config.taxonomy_loader import TaxonomyLoader
        cet_areas = TaxonomyLoader().load_cet_areas(args.taxonomy_version)
        source_path = str(path)
        dataset_hash = _dataset_hash(path)

    if not cet_areas:
        print("ERROR: no CET areas loaded — taxonomy resolution failed.", file=sys.stderr)
        return 2

    config = _default_config()
    env = _capture_env()

    # Run training n times with stepped seeds
    runs: list[dict[str, Any]] = []
    for i in range(args.n_runs):
        seed = args.seed + i
        print(f"Run {i + 1}/{args.n_runs} (seed={seed}) ...", file=sys.stderr)
        metrics = _train_once(dataset, cet_areas, config, seed)
        run_record: dict[str, Any] = {
            "run_id": i + 1,
            "seed": seed,
            "training_duration_seconds": metrics.get("training_duration_seconds"),
            "test": metrics.get("test", {}),
        }
        # Drop per_class to keep the snapshot compact; preserve in a side file if needed
        if isinstance(run_record["test"].get("per_class"), dict):
            run_record["test_per_class"] = run_record["test"].pop("per_class")
        runs.append(run_record)

    snapshot_id = f"cet_classifier_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    snapshot: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "schema_version": "1",
        "n_runs": args.n_runs,
        "env": env,
        "dataset": {
            "source_path": source_path,
            "dataset_hash": dataset_hash,
            "taxonomy_version": args.taxonomy_version,
            "summary": _summarize_dataset(dataset),
        },
        "config": config,
        "runs": runs,
        "aggregate": _aggregate(runs),
    }

    _write_json(snapshot, args.output_json)
    _write_markdown(snapshot, args.output_md)
    print(f"Wrote {args.output_json} and {args.output_md}", file=sys.stderr)

    if args.save_as_baseline:
        baseline_path = (
            Path("docs/ml/baselines") / f"{snapshot_id}.json"
        )
        _write_json(snapshot, baseline_path)
        print(f"Saved permanent baseline: {baseline_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
