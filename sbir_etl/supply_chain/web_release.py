"""Publish validated NSF-to-defense lineage tables for the static graph explorer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sbir_etl.supply_chain.web_export import build_nsf_defense_lineage_payload


def export_lineage(
    lineage_dir: Path,
    output: Path,
    *,
    allow_failed_quality: bool = False,
) -> dict:
    """Export the materialized NSF lineage graph and downloadable evidence tables."""

    required = {
        "direct_awards": lineage_dir / "nsf_sbir_awards_direct.parquet",
        "awardees": lineage_dir / "nsf_sbir_awardee_status.parquet",
        "prime_transactions": lineage_dir / "nsf_awardee_dod_prime_transactions.parquet",
        "subaward_transactions": (lineage_dir / "nsf_awardee_dod_subaward_transactions.parquet"),
        "funding_summary": lineage_dir / "nsf_awardee_defense_funding_summary.parquet",
        "award_screen": lineage_dir / "nsf_sbir_critical_supply_chain_screen.parquet",
        "evidence": lineage_dir / "nsf_award_defense_evidence.parquet",
    }
    if missing := [path for path in required.values() if not path.is_file()]:
        rendered = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"materialized NSF lineage artifacts not found: {rendered}")
    quality_path = lineage_dir / "nsf_defense_lineage_quality.json"
    quality = json.loads(quality_path.read_text()) if quality_path.is_file() else {}
    if quality.get("quality_gates_passed") is False and not allow_failed_quality:
        raise ValueError("NSF lineage quality gates failed; refusing graph export")
    manifest_path = lineage_dir / "nsf_defense_lineage_manifest.json"
    metadata = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    metadata["quality_gates_passed"] = quality.get("quality_gates_passed")
    frames = {name: pd.read_parquet(path) for name, path in required.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    download_files = {
        "Direct NSF awards": ("nsf_sbir_awards_direct.csv", frames["direct_awards"]),
        "DoD prime transactions": (
            "nsf_awardee_dod_prime_transactions.csv",
            frames["prime_transactions"],
        ),
        "DoD reported subawards": (
            "nsf_awardee_dod_subaward_transactions.csv",
            frames["subaward_transactions"],
        ),
        "Awardee funding summary": (
            "nsf_awardee_defense_funding_summary.csv",
            frames["funding_summary"],
        ),
        "NSF–DoD evidence": ("nsf_award_defense_evidence.csv", frames["evidence"]),
        "Critical supply-chain screen": (
            "nsf_sbir_critical_supply_chain_screen.csv",
            frames["award_screen"],
        ),
    }
    downloads: dict[str, str] = {}
    for label, (file_name, frame) in download_files.items():
        frame.to_csv(output.parent / file_name, index=False)
        downloads[label] = f"data/{file_name}"
    payload = build_nsf_defense_lineage_payload(
        frames["direct_awards"],
        frames["awardees"],
        frames["prime_transactions"],
        frames["subaward_transactions"],
        frames["award_screen"],
        frames["evidence"],
        metadata=metadata,
        downloads=downloads,
    )
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return payload


__all__ = ["export_lineage"]
