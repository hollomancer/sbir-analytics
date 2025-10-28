#!/usr/bin/env python3
"""
Transition MVP Gate Script

Purpose:
  Enforce Transition MVP quality gates without Makefile heredocs.

Gates:
  1) contracts_sample coverage gate
     - Default thresholds: action_date ≥ 0.90, any identifier ≥ 0.60
     - Source: reports/validation/transition_mvp.json (preferred, uses "gates.contracts_sample.passed")
       Fallback (when --force-compute or gates missing):
       data/processed/contracts_sample.checks.json -> coverage fields

  2) vendor_resolution rate gate
     - Default threshold: resolution_rate ≥ 0.60
     - Source: reports/validation/transition_mvp.json (preferred, uses "gates.vendor_resolution.passed")
       Fallback (when --force-compute or gates missing):
       data/processed/vendor_resolution.checks.json -> stats.resolution_rate

  3) evidence completeness gate
     - All candidates with score ≥ threshold (default 0.60) must have evidence entries
     - Source: data/processed/transitions_evidence.checks.json -> completeness.complete

Exit codes:
  0 -> All required gates passed
  1 -> Gate(s) failed
  2 -> Missing or unreadable inputs / invalid arguments

Examples:
  poetry run python scripts/transition_mvp_gate.py
  poetry run python scripts/transition_mvp_gate.py --summary reports/validation/transition_mvp.json
  poetry run python scripts/transition_mvp_gate.py --force-compute \
      --contracts-checks data/processed/contracts_sample.checks.json \
      --vendor-checks data/processed/vendor_resolution.checks.json \
      --evidence-checks data/processed/transitions_evidence.checks.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# -----------------------------
# Data structures
# -----------------------------


@dataclass
class GateResult:
    name: str
    passed: bool
    message: str
    metadata: dict[str, Any]


# -----------------------------
# Helpers
# -----------------------------


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(msg)


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _err(f"Failed to read JSON from {path}: {exc}")
        return None


def _get(d: dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safe nested get using dotted path, e.g., "gates.contracts_sample.passed"
    """
    node: Any = d
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


# -----------------------------
# Gate evaluation
# -----------------------------


def eval_contracts_gate_from_summary(summary: dict[str, Any]) -> Optional[GateResult]:
    gates = summary.get("gates") or {}
    cs = gates.get("contracts_sample")
    if not isinstance(cs, dict):
        return None
    passed = bool(cs.get("passed", False))
    msg = "contracts_sample coverage gate " + ("PASSED" if passed else "FAILED")
    return GateResult(
        name="contracts_sample",
        passed=passed,
        message=msg,
        metadata={
            "action_date_coverage": cs.get("action_date_coverage"),
            "any_identifier_coverage": cs.get("any_identifier_coverage"),
            "thresholds": cs.get("thresholds"),
        },
    )


def eval_contracts_gate_from_checks(
    checks: dict[str, Any],
    min_date_cov: float,
    min_id_cov: float,
) -> GateResult:
    cov = checks.get("coverage") or {}
    date_cov = float(cov.get("action_date") or 0.0)
    any_id = float(cov.get("any_identifier") or 0.0)
    passed = (date_cov >= min_date_cov) and (any_id >= min_id_cov)
    msg = (
        f"contracts_sample coverage gate "
        f"{'PASSED' if passed else 'FAILED'} "
        f"(action_date={date_cov:.4f} vs {min_date_cov:.4f}; "
        f"any_identifier={any_id:.4f} vs {min_id_cov:.4f})"
    )
    return GateResult(
        name="contracts_sample",
        passed=passed,
        message=msg,
        metadata={
            "action_date_coverage": date_cov,
            "any_identifier_coverage": any_id,
            "thresholds": {"action_date": min_date_cov, "any_identifier": min_id_cov},
        },
    )


def eval_vendor_gate_from_summary(summary: dict[str, Any]) -> Optional[GateResult]:
    gates = summary.get("gates") or {}
    vr = gates.get("vendor_resolution")
    if not isinstance(vr, dict):
        return None
    passed = bool(vr.get("passed", False))
    msg = "vendor_resolution rate gate " + ("PASSED" if passed else "FAILED")
    return GateResult(
        name="vendor_resolution",
        passed=passed,
        message=msg,
        metadata={
            "resolution_rate": vr.get("resolution_rate"),
            "threshold": vr.get("threshold"),
        },
    )


def eval_vendor_gate_from_checks(checks: dict[str, Any], min_rate: float) -> GateResult:
    stats = checks.get("stats") or {}
    rate = float(stats.get("resolution_rate") or 0.0)
    passed = rate >= min_rate
    msg = (
        f"vendor_resolution rate gate "
        f"{'PASSED' if passed else 'FAILED'} "
        f"(resolution_rate={rate:.4f} vs {min_rate:.4f})"
    )
    return GateResult(
        name="vendor_resolution",
        passed=passed,
        message=msg,
        metadata={"resolution_rate": rate, "threshold": min_rate},
    )


def eval_evidence_gate_from_checks(checks: dict[str, Any]) -> GateResult:
    comp = checks.get("completeness") or {}
    complete = bool(comp.get("complete", False))
    th = comp.get("threshold")
    ca = comp.get("candidates_above_threshold")
    er = comp.get("evidence_rows_for_above_threshold")
    msg = (
        f"evidence completeness gate "
        f"{'PASSED' if complete else 'FAILED'} "
        f"(evidence_rows_for_above_threshold={er}, candidates_above_threshold={ca}, threshold={th})"
    )
    return GateResult(
        name="transition_evidence_v1",
        passed=complete,
        message=msg,
        metadata={
            "threshold": th,
            "candidates_above_threshold": ca,
            "evidence_rows_for_above_threshold": er,
            "complete": complete,
        },
    )


# -----------------------------
# CLI
# -----------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Transition MVP Gate Script")
    p.add_argument(
        "--summary",
        type=str,
        default="reports/validation/transition_mvp.json",
        help="Path to validation summary JSON",
    )
    p.add_argument(
        "--contracts-checks",
        type=str,
        default="data/processed/contracts_sample.checks.json",
        help="Path to contracts_sample checks JSON (fallback or when --force-compute)",
    )
    p.add_argument(
        "--vendor-checks",
        type=str,
        default="data/processed/vendor_resolution.checks.json",
        help="Path to vendor_resolution checks JSON (fallback or when --force-compute)",
    )
    p.add_argument(
        "--evidence-checks",
        type=str,
        default="data/processed/transitions_evidence.checks.json",
        help="Path to transitions_evidence checks JSON (for evidence completeness)",
    )
    p.add_argument(
        "--force-compute",
        action="store_true",
        help="If set, compute contracts/vendor gates from checks JSON even if summary contains gates",
    )
    p.add_argument(
        "--contracts-min-date-coverage",
        type=float,
        default=0.90,
        help="Contracts action_date coverage threshold (used when computing from checks JSON)",
    )
    p.add_argument(
        "--contracts-min-id-coverage",
        type=float,
        default=0.60,
        help="Contracts any-identifier coverage threshold (used when computing from checks JSON)",
    )
    p.add_argument(
        "--vendor-min-resolution-rate",
        type=float,
        default=0.60,
        help="Vendor resolution rate threshold (used when computing from checks JSON)",
    )
    p.add_argument(
        "--no-contracts-gate",
        action="store_true",
        help="Skip contracts_sample coverage gate",
    )
    p.add_argument(
        "--no-vendor-gate",
        action="store_true",
        help="Skip vendor_resolution rate gate",
    )
    p.add_argument(
        "--no-evidence-gate",
        action="store_true",
        help="Skip evidence completeness gate",
    )
    return p.parse_args(argv)


# -----------------------------
# Main
# -----------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    summary_path = Path(args.summary)
    contracts_checks_path = Path(args.contracts_checks)
    vendor_checks_path = Path(args.vendor_checks)
    evidence_checks_path = Path(args.evidence_checks)

    # Load summary if present
    summary: Optional[dict[str, Any]] = None
    if summary_path.exists():
        summary = _load_json(summary_path)
        if summary is None:
            return 2
    else:
        _warn(f"Validation summary not found at {summary_path}; will rely on checks JSON.")

    results: list[GateResult] = []

    # Contracts gate
    if not args.no_contracts_gate:
        cs_result: Optional[GateResult] = None
        if summary is not None and not args.force_compute:
            cs_result = eval_contracts_gate_from_summary(summary)
        if cs_result is None:
            if not contracts_checks_path.exists():
                _err(f"Contracts checks JSON not found at {contracts_checks_path}")
                return 2
            cs_checks = _load_json(contracts_checks_path)
            if cs_checks is None:
                return 2
            cs_result = eval_contracts_gate_from_checks(
                cs_checks,
                min_date_cov=float(args.contracts_min_date_coverage),
                min_id_cov=float(args.contracts_min_id_coverage),
            )
        results.append(cs_result)

    # Vendor gate
    if not args.no_vendor_gate:
        vr_result: Optional[GateResult] = None
        if summary is not None and not args.force_compute:
            vr_result = eval_vendor_gate_from_summary(summary)
        if vr_result is None:
            if not vendor_checks_path.exists():
                _err(f"Vendor checks JSON not found at {vendor_checks_path}")
                return 2
            vr_checks = _load_json(vendor_checks_path)
            if vr_checks is None:
                return 2
            vr_result = eval_vendor_gate_from_checks(
                vr_checks, min_rate=float(args.vendor_min_resolution_rate)
            )
        results.append(vr_result)

    # Evidence gate (always from evidence checks JSON)
    if not args.no_evidence_gate:
        if not evidence_checks_path.exists():
            _err(f"Evidence checks JSON not found at {evidence_checks_path}")
            return 2
        ev_checks = _load_json(evidence_checks_path)
        if ev_checks is None:
            return 2
        ev_result = eval_evidence_gate_from_checks(ev_checks)
        results.append(ev_result)

    # Report and exit
    failed = [r for r in results if not r.passed]
    for r in results:
        _info(f"{r.name}: {r.message}")
        if r.metadata:
            try:
                _info("  " + json.dumps(r.metadata, indent=2))
            except Exception:
                _info(f"  {r.metadata}")

    if failed:
        _err(f"{len(failed)} gate(s) failed.")
        return 1

    _info("All requested gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
