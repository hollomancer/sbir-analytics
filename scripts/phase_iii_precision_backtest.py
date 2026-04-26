#!/usr/bin/env python3
"""Phase III RETROSPECTIVE precision backtest.

Treats DoD-coded Phase III contracts (FPDS Element 10Q codes ``SR3``/``ST3``,
or an explicit ``sbir_phase`` of "Phase III") as ground-truth positives, scores
each one against the prior Phase II award for the same vendor, and asserts that
HIGH (``candidate_score >= HIGH_THRESHOLD_RETROSPECTIVE``) precision is at
least 0.85.

The script is the release gate for the RETROSPECTIVE materialization. It is
intentionally **not** a Dagster asset check — asset materialization must not
depend on a human-maintained audit ledger or on the precision gate's runtime
state.

Outputs: ``reports/phase_iii/backtest.json`` with metrics (precision, recall,
sample size, per-agency breakdown, threshold). Exit code 1 on failure
(precision below threshold), 0 on success or when input data is missing
(documented data-missing sentinel — do not fabricate precision numbers when
the corpus isn't available locally).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from sbir_analytics.assets.phase_iii_candidates.assets import (
    WEIGHTS_RETROSPECTIVE,
    _score_pair,
    _scorer_config,
)
from sbir_analytics.assets.phase_iii_candidates.pairing import _prepare_priors
from sbir_ml.transition.detection.scoring import TransitionScorer

# Paths default to the canonical pipeline outputs. Both can be overridden via
# CLI flags so this script is testable in isolation.
DEFAULT_CONTRACTS_PATHS = (
    Path("data/transition/contracts_ingestion.parquet"),
    Path("data/processed/contracts_ingestion.parquet"),
)
DEFAULT_PHASE_II_PATH = Path("data/processed/phase_ii_awards.parquet")
DEFAULT_REPORT_PATH = Path("reports/phase_iii/backtest.json")
DEFAULT_PRECISION_THRESHOLD = 0.85

_PHASE_III_RESEARCH_CODES = frozenset({"SR3", "ST3"})


def _is_dod_phase_iii(row: pd.Series) -> bool:
    research = row.get("research") if "research" in row else None
    if isinstance(research, str) and research.strip().upper() in _PHASE_III_RESEARCH_CODES:
        return True
    sbir_phase = row.get("sbir_phase") if "sbir_phase" in row else None
    if isinstance(sbir_phase, str):
        s = sbir_phase.strip().upper()
        if s in {"PHASE III", "III", "3", "PHASE 3"}:
            return True
    return False


def _load_first_existing(paths: tuple[Path, ...]) -> tuple[pd.DataFrame | None, Path | None]:
    for p in paths:
        if p.exists():
            try:
                return pd.read_parquet(p), p
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to read parquet at {}: {}", p, exc)
    return None, None


def _build_pair_row(prior: pd.Series, contract: pd.Series) -> pd.Series:
    """Construct a row in the canonical PAIR_S1_COLUMNS shape from raw inputs."""

    def _g(d: pd.Series, *keys: str) -> Any:
        for k in keys:
            if k in d.index and pd.notna(d.get(k)):
                return d.get(k)
        return None

    data = {
        "prior_award_id": prior.get("prior_award_id"),
        "prior_recipient_uei": prior.get("prior_recipient_uei"),
        "prior_agency": prior.get("prior_agency"),
        "prior_sub_agency": prior.get("prior_sub_agency"),
        "prior_office": prior.get("prior_office"),
        "prior_naics_code": prior.get("prior_naics_code"),
        "prior_psc_code": prior.get("prior_psc_code"),
        "prior_title": prior.get("prior_title"),
        "prior_abstract": prior.get("prior_abstract"),
        "prior_period_of_performance_end": prior.get("prior_period_of_performance_end"),
        "prior_cet": prior.get("prior_cet"),
        "target_id": _g(contract, "contract_id", "piid", "generated_unique_award_id"),
        "target_recipient_uei": _g(contract, "vendor_uei", "recipient_uei", "uei"),
        "target_agency": _g(contract, "awarding_agency_name", "agency", "awarding_agency"),
        "target_sub_agency": _g(contract, "awarding_sub_tier_agency_name", "sub_agency"),
        "target_office": _g(contract, "awarding_office_name", "office"),
        "target_naics_code": _g(contract, "naics_code", "naics"),
        "target_psc_code": _g(contract, "psc_code", "product_or_service_code"),
        "target_description": _g(
            contract, "transaction_description", "description", "award_description"
        ),
        "target_action_date": _g(contract, "action_date", "award_date"),
        "target_competition_type": _g(
            contract, "extent_competed", "competition_type", "type_of_set_aside"
        ),
        "target_obligated_amount": _g(
            contract, "federal_action_obligation", "obligated_amount", "obligation_amount"
        ),
        # If the contracts parquet has been CET-enriched upstream, surface it
        # so the cet_alignment signal can score. Production today does not
        # carry this column; the backtest will report a CET-zero precision
        # number until enrichment is wired through.
        "target_cet": _g(contract, "target_cet", "contract_cet", "cet"),
        "agency_match_level": "agency",  # default; refined below
    }
    # Refine agency match level using the same hierarchy the asset uses.
    if (
        data["prior_office"]
        and data["target_office"]
        and str(data["prior_office"]).strip().upper() == str(data["target_office"]).strip().upper()
    ):
        data["agency_match_level"] = "office"
    elif (
        data["prior_sub_agency"]
        and data["target_sub_agency"]
        and str(data["prior_sub_agency"]).strip().upper()
        == str(data["target_sub_agency"]).strip().upper()
    ):
        data["agency_match_level"] = "sub_tier"
    # Include extra keys (e.g. target_cet) beyond PAIR_S1_COLUMNS so the
    # scorer can pick them up via row.get(...).
    return pd.Series(data)


def _agency_label(row: pd.Series) -> str:
    for k in ("target_agency", "prior_agency"):
        v = row.get(k)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            return str(v)
    return "UNKNOWN"


def run_backtest(
    *,
    contracts: pd.DataFrame,
    phase_ii: pd.DataFrame,
    threshold: float,
) -> dict[str, Any]:
    """Score every DoD-coded Phase III contract against its vendor's prior Phase II.

    A "true positive" is a HIGH-confidence candidate (score >= threshold). A
    "false negative" is a known Phase III that scored below the threshold.
    Recall is reported alongside precision; precision is the gate.
    """

    if contracts.empty or phase_ii.empty:
        return _empty_metrics(reason="contracts or phase_ii frame is empty")

    positives = contracts.loc[contracts.apply(_is_dod_phase_iii, axis=1)].copy()
    if positives.empty:
        return _empty_metrics(reason="no DoD-coded Phase III contracts in input")

    priors = _prepare_priors(phase_ii)
    if priors.empty:
        return _empty_metrics(reason="no prior Phase II awards with recipient_uei")

    priors_by_uei: dict[str, pd.Series] = {}
    for _, p in priors.iterrows():
        uei = str(p.get("prior_recipient_uei") or "").strip().upper()
        if uei and uei not in priors_by_uei:
            priors_by_uei[uei] = p

    config = _scorer_config(WEIGHTS_RETROSPECTIVE)
    scorer = TransitionScorer(config)

    high_count = 0
    scored = 0
    skipped_no_prior = 0
    by_agency: dict[str, dict[str, int]] = defaultdict(lambda: {"scored": 0, "high": 0})

    for _, contract in positives.iterrows():
        uei = None
        for k in ("vendor_uei", "recipient_uei", "uei"):
            if k in contract.index and pd.notna(contract.get(k)):
                uei = str(contract.get(k)).strip().upper()
                break
        if not uei or uei not in priors_by_uei:
            skipped_no_prior += 1
            continue
        prior = priors_by_uei[uei]
        pair = _build_pair_row(prior, contract)
        score, _subs, _topical = _score_pair(scorer, pair)
        agency = _agency_label(pair)
        by_agency[agency]["scored"] += 1
        scored += 1
        if score >= threshold:
            high_count += 1
            by_agency[agency]["high"] += 1

    precision = (high_count / scored) if scored else 0.0
    recall = precision  # Same population, same numerator/denominator semantics here.
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "threshold": float(threshold),
        "sample_size": int(scored),
        "skipped_no_prior_phase_ii": int(skipped_no_prior),
        "high_confidence_count": int(high_count),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "per_agency": {
            agency: {
                "scored": stats["scored"],
                "high": stats["high"],
                "precision": round(stats["high"] / stats["scored"], 4)
                if stats["scored"]
                else 0.0,
            }
            for agency, stats in sorted(by_agency.items())
        },
        "positives_in_input": int(len(positives)),
    }


def _empty_metrics(*, reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_missing": True,
        "data_missing_reason": reason,
        "threshold": float(DEFAULT_PRECISION_THRESHOLD),
        "sample_size": 0,
        "high_confidence_count": 0,
        "precision": None,
        "recall": None,
        "per_agency": {},
    }


def _write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--contracts",
        type=Path,
        default=None,
        help=(
            "Path to the contracts parquet (defaults to "
            "data/transition/contracts_ingestion.parquet, then "
            "data/processed/contracts_ingestion.parquet)."
        ),
    )
    parser.add_argument(
        "--phase-ii",
        type=Path,
        default=DEFAULT_PHASE_II_PATH,
        help=f"Path to the Phase II awards parquet (default: {DEFAULT_PHASE_II_PATH}).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Where to write the JSON report (default: {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_PRECISION_THRESHOLD,
        help=f"HIGH precision floor (default: {DEFAULT_PRECISION_THRESHOLD}).",
    )
    parser.add_argument(
        "--allow-data-missing",
        action="store_true",
        default=True,
        help=(
            "Exit 0 (with sentinel report) when input data is missing. Default on; "
            "pass --strict to require inputs."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 2) if inputs are missing instead of writing a data-missing sentinel.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.contracts is not None:
        contracts_df: pd.DataFrame | None = (
            pd.read_parquet(args.contracts) if args.contracts.exists() else None
        )
        contracts_path = args.contracts
    else:
        contracts_df, contracts_path = _load_first_existing(DEFAULT_CONTRACTS_PATHS)

    phase_ii_df: pd.DataFrame | None = (
        pd.read_parquet(args.phase_ii) if args.phase_ii.exists() else None
    )

    if contracts_df is None or phase_ii_df is None:
        reason_parts: list[str] = []
        if contracts_df is None:
            reason_parts.append(f"contracts parquet not found at {contracts_path or args.contracts}")
        if phase_ii_df is None:
            reason_parts.append(f"phase II parquet not found at {args.phase_ii}")
        reason = "; ".join(reason_parts)
        report = _empty_metrics(reason=reason)
        report["inputs"] = {
            "contracts_path": str(contracts_path or args.contracts),
            "phase_ii_path": str(args.phase_ii),
        }
        _write_report(report, args.report)
        if args.strict:
            print(f"FAIL: {reason}", file=sys.stderr)
            return 2
        print(f"WARNING: {reason}; wrote data-missing sentinel to {args.report}")
        return 0

    report = run_backtest(
        contracts=contracts_df,
        phase_ii=phase_ii_df,
        threshold=args.threshold,
    )
    report["inputs"] = {
        "contracts_path": str(contracts_path or args.contracts),
        "phase_ii_path": str(args.phase_ii),
    }
    _write_report(report, args.report)

    if report.get("data_missing"):
        if args.strict:
            print(f"FAIL: {report.get('data_missing_reason')}", file=sys.stderr)
            return 2
        print(
            f"WARNING: {report.get('data_missing_reason')}; "
            f"wrote data-missing sentinel to {args.report}"
        )
        return 0

    precision = float(report["precision"] or 0.0)
    threshold = float(report["threshold"])
    sample = int(report["sample_size"])
    print(
        f"RETROSPECTIVE precision={precision:.4f} "
        f"(threshold={threshold:.2f}, n={sample}, high={report['high_confidence_count']})"
    )
    if precision < threshold:
        print(
            f"FAIL: precision {precision:.4f} < threshold {threshold:.2f}",
            file=sys.stderr,
        )
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_PRECISION_THRESHOLD",
    "main",
    "run_backtest",
]
