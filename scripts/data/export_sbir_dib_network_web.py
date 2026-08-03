#!/usr/bin/env python3
"""Export materialized SBIR-DIB network Parquet files for the static graph explorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sbir_etl.supply_chain.web_export import build_web_graph_payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--network-dir",
        type=Path,
        default=Path("data/processed/sbir_dib_subaward_network"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/sbir-dib-network-explorer/data/network.json"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
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
