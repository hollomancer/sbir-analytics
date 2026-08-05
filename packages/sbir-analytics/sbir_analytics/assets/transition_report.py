"""Dagster assets for the tech-area transition-report cohorts (spec T9).

Thin orchestration wrapper around ``scripts/data/build_tech_area_cohort.py``.
That CLI is the single, bit-exact-verified source of truth for how a Phase II
tech-area cohort is built (Method A keyword + Method B taxonomy, deficiency-class
enrichment, external-reference reconciliation). Rather than duplicate or refactor
that 800-line builder — and risk perturbing the parity the nanotech cutover
verified — each asset here shells out to it (``sys.executable`` on the same repo)
and then reads back the emitted ``overlap_summary.json`` + ``composition.json`` to
surface cohort metrics as Dagster metadata.

One asset + one non-empty asset-check per area, grouped under
``transition_reports``. Areas are the three defined in
``config/transition_reports/`` — add a factory call below to wire a new one.

Materialization is by side effect: the builder writes CSV/JSON artifacts under
``data/reports/<area_id>/`` (the same convention the rest of the pipeline reads),
matching how the fiscal/cet assets in this package materialize to ``data/`` and
emit metadata + checks rather than returning IO-managed frames.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dagster import shim (mirrors assets/cet/utils.py): keep the module importable
# for unit tests in environments without Dagster installed.
# ---------------------------------------------------------------------------
try:
    from dagster import (
        AssetCheckResult,
        AssetCheckSeverity,
        Output,
        asset,
        asset_check,
    )
except Exception:  # pragma: no cover - exercised only without Dagster

    def asset(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def _wrap(fn: Any) -> Any:
            return fn

        return _wrap

    def asset_check(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def _wrap(fn: Any) -> Any:
            return fn

        return _wrap

    class Output:  # type: ignore[no-redef]
        def __init__(self, value: Any, metadata: dict | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class AssetCheckSeverity:  # type: ignore[no-redef]
        WARN = "WARN"
        ERROR = "ERROR"

    class AssetCheckResult:  # type: ignore[no-redef]
        def __init__(
            self,
            passed: bool,
            severity: Any = None,
            description: str | None = None,
            metadata: dict | None = None,
        ) -> None:
            self.passed = passed
            self.severity = severity
            self.description = description
            self.metadata = metadata or {}


# Areas defined under config/transition_reports/. Add a factory call at the
# bottom of this module to wire a new one.
TECH_AREAS = (
    "nanotechnology",
    "quantum_information_science",
    "hypersonics",
)


def _repo_root() -> Path:
    """Locate the repo root by walking up to the cohort builder script."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "data" / "build_tech_area_cohort.py").exists():
            return parent
    raise RuntimeError("could not locate repo root (build_tech_area_cohort.py not found)")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cohort_metrics(summary: dict, composition: dict) -> dict[str, Any]:
    """Flatten overlap_summary.json + composition.json into scalar metrics.

    Pure function (no Dagster, no I/O) so it is unit-testable against fixtures.
    """
    overlap = summary.get("overlap") or {}
    totals = composition.get("totals") or {}
    return {
        "area_id": summary.get("area_id"),
        "phase2_universe": summary.get("phase2_universe"),
        "method_a_awards": composition.get("n_unique_awards"),
        "method_b_awards": overlap.get("method_b_n"),
        "method_a_source": summary.get("method_a_source"),
        "method_b_source": summary.get("method_b_source"),
        "intersection": overlap.get("intersection_n"),
        "jaccard": overlap.get("jaccard"),
        "phase2_dollars_m": totals.get("phase2_dollars_m"),
        "unique_firms": totals.get("unique_firms"),
        "agencies": len(composition.get("by_agency") or {}),
        "signals_absent": len(summary.get("signals_absent") or []),
        "has_deficiency_class": bool(summary.get("has_deficiency_class")),
    }


def _run_cohort_build(area_id: str, log: Any) -> Path:
    """Run build_tech_area_cohort.py for one area; return its report dir."""
    repo = _repo_root()
    script = repo / "scripts" / "data" / "build_tech_area_cohort.py"
    cmd = [sys.executable, str(script), "--area", area_id]
    log.info(f"[tech_area_cohort] {shlex.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
    if proc.stdout:
        log.info(f"[tech_area_cohort:{area_id}] stdout tail:\n{proc.stdout[-4000:]}")
    if proc.stderr:
        log.info(f"[tech_area_cohort:{area_id}] stderr tail:\n{proc.stderr[-4000:]}")
    if proc.returncode != 0:
        raise RuntimeError(
            f"build_tech_area_cohort.py failed for area={area_id} (exit {proc.returncode}).\n"
            f"stdout tail:\n{proc.stdout[-2000:]}\n"
            f"stderr tail:\n{proc.stderr[-2000:]}"
        )
    return repo / "data" / "reports" / area_id


def _make_cohort_asset(area_id: str) -> Any:
    @asset(
        name=f"tech_area_cohort_{area_id}",
        group_name="transition_reports",
        compute_kind="python",
        description=(
            f"Phase II tech-area cohort for {area_id}: runs "
            "build_tech_area_cohort.py and writes cohort/composition/overlap "
            "artifacts under data/reports/<area>/."
        ),
    )
    # NOTE: `context` is intentionally left unannotated — Dagster rejects an
    # explicit `Any` annotation on the context parameter.
    def _cohort(context) -> Output:
        report_dir = _run_cohort_build(area_id, context.log)
        summary = _read_json(report_dir / "overlap_summary.json")
        composition = _read_json(report_dir / "composition.json")
        metrics = _cohort_metrics(summary, composition)
        n = metrics["method_a_awards"]
        if not n:
            raise RuntimeError(
                f"tech_area_cohort_{area_id}: builder produced an empty/invalid cohort "
                f"(method_a_awards={n!r})"
            )
        metadata = {k: v for k, v in metrics.items() if v is not None}
        metadata["report_dir"] = str(report_dir)
        return Output(metrics, metadata=metadata)

    return _cohort


def _make_cohort_check(area_id: str) -> Any:
    @asset_check(
        asset=f"tech_area_cohort_{area_id}",
        description="Cohort is non-empty and carries a deficiency_class column.",
    )
    def _check(context) -> AssetCheckResult:
        report_dir = _repo_root() / "data" / "reports" / area_id
        summ_path = report_dir / "overlap_summary.json"
        comp_path = report_dir / "composition.json"
        if not summ_path.exists() or not comp_path.exists():
            return AssetCheckResult(
                passed=False,
                severity=AssetCheckSeverity.ERROR,
                description=f"missing cohort outputs under {report_dir}",
            )
        metrics = _cohort_metrics(_read_json(summ_path), _read_json(comp_path))
        n = metrics["method_a_awards"] or 0
        passed = n > 0 and metrics["has_deficiency_class"]
        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.WARN,
            description=(
                f"method_a_awards={n}, has_deficiency_class={metrics['has_deficiency_class']}"
            ),
            metadata={
                "method_a_awards": n,
                "has_deficiency_class": metrics["has_deficiency_class"],
            },
        )

    return _check


# One asset + one non-empty check per area, generated from TECH_AREAS (single
# source of truth). Bound to module globals so Dagster's load_assets_from_modules
# / load_asset_checks_from_modules discover them.
for _area in TECH_AREAS:
    globals()[f"tech_area_cohort_{_area}"] = _make_cohort_asset(_area)
    globals()[f"tech_area_cohort_{_area}_nonempty"] = _make_cohort_check(_area)
del _area
