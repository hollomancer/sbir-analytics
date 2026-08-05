#!/usr/bin/env python3
"""Export materialized SBIR-DIB network Parquet files for the static graph explorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sbir_etl.supply_chain.web_export import (
    build_web_graph_payload,
)
from sbir_etl.supply_chain.web_release import export_lineage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--network-dir",
        type=Path,
        default=Path("data/processed/sbir_dib_subaward_network"),
    )
    parser.add_argument(
        "--lineage-dir",
        type=Path,
        default=Path("data/processed/nsf_sbir_defense_lineage"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/sbir-dib-network-explorer/data/network.json"),
    )
    parser.add_argument(
        "--legacy-subaward-only",
        action="store_true",
        help="Export the original supplier-to-prime-family graph instead of NSF lineage.",
    )
    parser.add_argument("--allow-failed-quality", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.legacy_subaward_only:
        payload = export_lineage(
            args.lineage_dir,
            args.output,
            allow_failed_quality=args.allow_failed_quality,
        )
        scope = payload["scope"]
        print(
            f"Wrote {args.output}: {scope['node_count']:,} nodes, "
            f"{scope['edge_count']:,} relationships, "
            f"{scope['verified_funding_edge_count']:,} verified funding edges"
        )
        return 0

    edges_path = args.network_dir / "sbir_dib_supplier_prime_edges.parquet"
    exposure_path = args.network_dir / "sbir_supplier_customer_exposure.parquet"
    metadata_path = args.network_dir / "sbir_dib_subaward_network.metadata.json"

    missing = [path for path in (edges_path, exposure_path) if not path.exists()]
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"materialized network artifacts not found: {rendered}")

    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    payload = build_web_graph_payload(
        pd.read_parquet(edges_path),
        pd.read_parquet(exposure_path),
        metadata=metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    scope = payload["scope"]
    print(
        f"Wrote {args.output}: {scope['supplier_count']:,} suppliers, "
        f"{scope['prime_family_count']:,} prime families, "
        f"{scope['display_prime_family_edge_count']:,} displayed relationships"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
