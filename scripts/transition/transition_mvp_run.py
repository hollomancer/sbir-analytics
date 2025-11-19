#!/usr/bin/env python3
"""
Transition MVP Runner (shim, no Dagster required)

This script materializes the Transition MVP pipeline locally using the import-safe
assets in src.assets.transition:

    1) contracts_sample
    2) vendor_resolution
    3) transition_scores_v1
    4) transition_evidence_v1

It will optionally seed a small contracts sample if none exists. Outputs are
written under data/processed/, and a validation summary is written to:
    reports/validation/transition_mvp.json

Usage:
    poetry run python scripts/transition_mvp_run.py
    poetry run python scripts/transition_mvp_run.py --contracts-path data/processed/contracts_sample.parquet
    poetry run python scripts/transition_mvp_run.py --no-seed
    poetry run python scripts/transition_mvp_run.py --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _to_parquet_or_csv(df: pd.DataFrame, path: Path) -> Path:
    """
    Persist DataFrame to parquet when possible; fall back to CSV if parquet engine unavailable.
    Returns the path written (parquet or CSV).
    """
    _ensure_parent(path)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception:
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def _unwrap_output(result: Any) -> tuple[Any, dict | None]:
    """
    Helper to unwrap Dagster Output-like objects or pass through the bare value.
    The transition assets return Output(value=..., metadata=...).
    """
    if hasattr(result, "value"):
        return result.value, getattr(result, "metadata", None)
    return result, None


def _seed_contracts_if_missing(contracts_path: Path, verbose: bool) -> Path | None:
    """
    Seed a tiny contracts sample if the parquet (or CSV fallback) is missing.
    Returns the path written or None if no seed was required.
    """
    parquet = contracts_path
    csv = contracts_path.with_suffix(".csv")
    if parquet.exists() or csv.exists():
        if verbose:
            print(f"[seed] Skipping; found {parquet if parquet.exists() else csv}")
        return None

    if verbose:
        print(
            f"[seed] Seeding sample contracts to {parquet} (CSV fallback if parquet engine missing)"
        )

    df_contracts_seed = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": "UEI123",
                "vendor_duns": None,
                "vendor_name": "UEI Vendor Inc",
                "action_date": "2023-01-01",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
        ]
    )
    written = _to_parquet_or_csv(df_contracts_seed, parquet)
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Transition MVP (shimmed)")
    p.add_argument(
        "--contracts-path",
        type=str,
        default="data/processed/contracts_sample.parquet",
        help="Path for contracts sample parquet (CSV fallback used if parquet engine unavailable)",
    )
    p.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not seed sample contracts if not present",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    verbose = bool(args.verbose)

    contracts_path = Path(args.contracts_path).resolve()
    # Ensure common directories exist
    _ensure_parent(contracts_path)
    _ensure_parent(Path("reports/validation/transition_mvp.json"))

    if not args.no_seed:
        _seed_contracts_if_missing(contracts_path, verbose=verbose)

    # Import assets (import-safe; works without Dagster installed)
    try:
        from src.assets.transition import AssetExecutionContext  # type: ignore
        from src.assets.transition import enriched_vendor_resolution as a_vendor_resolution
        from src.assets.transition import (
            transformed_transition_evidence as a_transition_evidence_v1,
        )
        from src.assets.transition import (
            transformed_transition_scores as a_transition_scores_v1,
        )
        from src.assets.transition import validated_contracts_sample as a_contracts_sample
    except Exception as exc:
        print(f"[error] Failed to import transition assets: {exc}", file=sys.stderr)
        return 2

    if verbose:
        print("[run] Initializing context")

    # Create context - handle both shim (no args) and real Dagster (requires op_execution_context)
    try:
        ctx = AssetExecutionContext()
    except TypeError as e:
        if "op_execution_context" in str(e):
            # Real Dagster AssetExecutionContext requires op_execution_context
            # Create minimal mock that satisfies Dagster's requirements
            mock_run = SimpleNamespace()
            mock_run.run_id = "mock-run-id"

            mock_op_ctx = SimpleNamespace()
            # Add minimal attributes that Dagster might expect
            mock_op_ctx.log = type(
                "Log",
                (),
                {
                    "info": lambda self, *args, **kwargs: None,
                    "warning": lambda self, *args, **kwargs: None,
                    "error": lambda self, *args, **kwargs: None,
                    "exception": lambda self, *args, **kwargs: None,
                },
            )()
            mock_op_ctx.instance = None
            mock_op_ctx.resources = SimpleNamespace()
            mock_op_ctx.run = mock_run
            mock_op_ctx.run_id = "mock-run-id"
            ctx = AssetExecutionContext(mock_op_ctx)
        else:
            raise

    # 1) contracts_sample (reads the configured path internally)
    if verbose:
        print("[run] Materializing contracts_sample")
    try:
        contracts_out = a_contracts_sample(ctx)
    except Exception as exc:
        print(f"[error] contracts_sample failed: {exc}", file=sys.stderr)
        return 2
    contracts_df, contracts_meta = _unwrap_output(contracts_out)

    # 2) Build a tiny awards fixture in-memory (sufficient for MVP chain)
    #    Includes fields for agency alignment and date overlap.
    if verbose:
        print("[run] Building awards fixture")
    awards_df = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "Company": "UEI Vendor Inc",
                "UEI": "UEI123",
                "Duns": None,
                "Agency": "DEPT OF DEFENSE",
                "award_date": "2022-06-15",
            },
            {
                "award_id": "A2",
                "Company": "Acme Corp",
                "UEI": None,
                "Duns": None,
                "Agency": "DEPT OF DEFENSE",
                "award_date": "2022-09-10",
            },
        ]
    )

    # 3) vendor_resolution
    if verbose:
        print("[run] Materializing vendor_resolution")
    try:
        vendor_res_out = a_vendor_resolution(ctx, contracts_df, awards_df)
    except Exception as exc:
        print(f"[error] vendor_resolution failed: {exc}", file=sys.stderr)
        return 2
    vendor_df, vendor_meta = _unwrap_output(vendor_res_out)

    # 4) transition_scores_v1
    if verbose:
        print("[run] Materializing transition_scores_v1")
    try:
        scores_out = a_transition_scores_v1(ctx, vendor_df, contracts_df, awards_df)
    except Exception as exc:
        print(f"[error] transition_scores_v1 failed: {exc}", file=sys.stderr)
        return 2
    scores_df, scores_meta = _unwrap_output(scores_out)

    # 5) transition_evidence_v1
    if verbose:
        print("[run] Materializing transition_evidence_v1")
    try:
        evidence_out = a_transition_evidence_v1(ctx, scores_df, contracts_df)
    except Exception as exc:
        print(f"[error] transition_evidence_v1 failed: {exc}", file=sys.stderr)
        return 2
    evidence_path, evidence_meta = _unwrap_output(evidence_out)

    # 6) transition_analytics
    if verbose:
        print("[run] Materializing transition_analytics")
    try:
        from src.assets.transition import (  # type: ignore
            transformed_transition_analytics as a_transition_analytics,
        )

        analytics_out = a_transition_analytics(ctx, awards_df, scores_df, contracts_df)
    except Exception as exc:
        print(f"[error] transition_analytics failed: {exc}", file=sys.stderr)
        return 2
    analytics_path, analytics_meta = _unwrap_output(analytics_out)

    # Summary
    validation_path = Path("reports/validation/transition_mvp.json")
    print("✓ Transition MVP completed")
    print(
        f"  - contracts_sample rows: {len(contracts_df)} (source: {contracts_meta.get('source') if contracts_meta else 'n/a'})"
    )
    print(f"  - vendor_resolution rows: {len(vendor_df)}")
    print(f"  - transitions rows: {len(scores_df)}")
    print(f"  - evidence path: {evidence_path}")
    print(f"  - validation summary: {validation_path}")
    print(f"  - analytics summary: {analytics_path}")
    if analytics_meta and analytics_meta.get("checks_path"):
        print(f"  - analytics checks: {analytics_meta.get('checks_path')}")

    # Optional note on gates
    if validation_path.exists():
        try:
            import json

            gates = {}
            data = json.loads(validation_path.read_text(encoding="utf-8"))
            gates = data.get("gates", {}) or {}
            cs = gates.get("contracts_sample", {})
            vr = gates.get("vendor_resolution", {})
            print("  - gates:")
            print(
                f"      contracts_sample: {'PASS' if cs.get('passed') else 'FAIL'} "
                f"(date_cov={cs.get('action_date_coverage')}, any_id_cov={cs.get('any_identifier_coverage')})"
            )
            print(
                f"      vendor_resolution: {'PASS' if vr.get('passed') else 'FAIL'} "
                f"(resolution_rate={vr.get('resolution_rate')})"
            )
        except Exception:
            # Non-fatal if summary cannot be parsed
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
