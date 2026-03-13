"""
Extract federal procurement contracts from FPDS-NG via USAspending dumps.

Wraps the existing ContractExtractor to pull federal procurement contracts:
amounts, agencies, vendors, NAICS, competition type.

FPDS contracts are the strongest public commercialization signal. They unlock
"did this SBIR company win real federal contracts?" — the core question for
Mission B benchmarks and Mission C fiscal returns.

Data source: FPDS-NG via USAspending.gov bulk downloads
Access method: PostgreSQL dump streaming (.dat.gz)
Refresh cadence: Daily (FPDS), Monthly (USAspending bulk)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class ExtractFPDSContractsTool(BaseTool):
    """Extract federal procurement contracts from USAspending/FPDS dump files.

    Supports two modes:
    1. Full extraction from .dat.gz dump files (streaming, memory-efficient)
    2. Loading from pre-extracted Parquet files (fast, for re-runs)

    Vendor filtering ensures only SBIR-relevant companies are extracted,
    keeping output manageable for downstream entity resolution.
    """

    name = "extract_fpds_contracts"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        dump_dir: str | Path | None = None,
        parquet_path: str | Path | None = None,
        vendor_filter_file: str | Path | None = None,
        output_path: str | Path | None = None,
        batch_size: int = 10000,
        **kwargs: Any,
    ) -> ToolResult:
        """Extract FPDS contracts from dump files or load from Parquet.

        Args:
            metadata: Pre-initialized metadata to populate
            dump_dir: Path to USAspending PostgreSQL dump directory
            parquet_path: Path to pre-extracted Parquet (skip extraction if provided)
            vendor_filter_file: JSON file with UEI/DUNS/name filters for SBIR vendors
            output_path: Where to save extracted Parquet (only for dump extraction)
            batch_size: Records per batch during streaming extraction

        Returns:
            ToolResult with DataFrame of federal contract records
        """
        if parquet_path and Path(parquet_path).exists():
            # Fast path: load pre-extracted data
            df = pd.read_parquet(parquet_path)
            logger.info(f"Loaded {len(df):,} contracts from {parquet_path}")
            access_method = "parquet_preextracted"
        elif dump_dir:
            # Full extraction from dump files
            from src.extractors.contract_extractor import ContractExtractor

            extractor = ContractExtractor(
                vendor_filter_file=Path(vendor_filter_file) if vendor_filter_file else None,
                batch_size=batch_size,
            )

            dump_path = Path(dump_dir)
            out_path = Path(output_path) if output_path else dump_path / "extracted_contracts.parquet"

            count = extractor.extract_from_dump(
                dump_dir=dump_path,
                output_file=out_path,
            )

            if count > 0 and out_path.exists():
                df = pd.read_parquet(out_path)
            else:
                df = pd.DataFrame()
                metadata.warnings.append("No contracts extracted from dump files")

            access_method = "usaspending_dump_streaming"
        else:
            raise ValueError(
                "Must provide either parquet_path (pre-extracted) or dump_dir (raw extraction)"
            )

        # Populate metadata
        metadata.data_sources.append(
            DataSourceRef(
                name="FPDS-NG (via USAspending.gov)",
                url="https://usaspending.gov/download_center",
                version=datetime.utcnow().strftime("%Y-%m-%d"),
                record_count=len(df),
                access_method=access_method,
            )
        )
        metadata.record_count = len(df)

        return ToolResult(data=df, metadata=metadata)
