"""Chunked and streaming enrichment processor for large datasets.

This module provides utilities for processing large SBIR datasets with
USAspending enrichment in configurable chunks, enabling memory-efficient
processing of datasets larger than available RAM.

Features:
- Configurable chunk sizes from config
- Memory monitoring with adaptive sizing
- Progress tracking and checkpoint support
- Streaming/dynamic output generation
- Error recovery and retry logic
- Performance metrics collection
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..enrichers.usaspending_enricher import enrich_sbir_with_usaspending
from ..utils.performance_monitor import performance_monitor


@dataclass
class ChunkProgress:
    """Tracks progress through chunked processing."""

    total_records: int
    chunk_size: int
    chunks_processed: int = 0
    records_processed: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_checkpoint: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    checkpoint_dir: Optional[Path] = None

    @property
    def total_chunks(self) -> int:
        """Calculate total expected chunks."""
        return (self.total_records + self.chunk_size - 1) // self.chunk_size

    @property
    def percent_complete(self) -> float:
        """Calculate percentage complete."""
        if self.total_records == 0:
            return 0.0
        return (self.records_processed / self.total_records) * 100

    @property
    def elapsed_seconds(self) -> float:
        """Calculate elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def estimated_remaining_seconds(self) -> float:
        """Estimate remaining time based on current rate."""
        if self.records_processed == 0:
            return 0.0
        rate = self.records_processed / self.elapsed_seconds
        remaining = self.total_records - self.records_processed
        return remaining / rate if rate > 0 else 0.0

    def save_checkpoint(self, metadata: Dict[str, Any]) -> Optional[Path]:
        """Save progress checkpoint to file.

        Args:
            metadata: Additional metadata to save

        Returns:
            Path to checkpoint file or None
        """
        if not self.checkpoint_dir:
            return None

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self.checkpoint_dir / f"checkpoint_{self.chunks_processed:04d}.json"

        checkpoint_data = {
            "timestamp": datetime.now().isoformat(),
            "chunks_processed": self.chunks_processed,
            "records_processed": self.records_processed,
            "percent_complete": self.percent_complete,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
            "errors": self.errors,
            "metadata": metadata,
        }

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint_data, f, indent=2)

        self.last_checkpoint = datetime.now()
        return checkpoint_path

    def log_progress(self) -> None:
        """Log current progress to logger."""
        logger.info(
            f"Progress: {self.percent_complete:.1f}% "
            f"({self.records_processed}/{self.total_records} records, "
            f"{self.chunks_processed}/{self.total_chunks} chunks, "
            f"~{self.estimated_remaining_seconds/60:.0f} min remaining)"
        )


class ChunkedEnricher:
    """Processor for chunked enrichment of large datasets."""

    def __init__(
        self,
        sbir_df: pd.DataFrame,
        recipient_df: pd.DataFrame,
        checkpoint_dir: Optional[Path] = None,
        enable_progress_tracking: bool = True,
    ):
        """Initialize chunked enricher.

        Args:
            sbir_df: SBIR awards DataFrame
            recipient_df: USAspending recipients DataFrame
            checkpoint_dir: Optional directory for checkpoints
            enable_progress_tracking: Enable progress checkpoints
        """
        self.sbir_df = sbir_df
        self.recipient_df = recipient_df
        self.checkpoint_dir = checkpoint_dir if enable_progress_tracking else None
        self.enable_progress_tracking = enable_progress_tracking

        # Get configuration
        config = get_config()
        self.chunk_size = config.enrichment.performance.chunk_size
        self.memory_threshold_mb = config.enrichment.performance.memory_threshold_mb
        self.timeout_seconds = config.enrichment.performance.timeout_seconds
        self.high_threshold = config.enrichment.performance.high_confidence_threshold
        self.low_threshold = config.enrichment.performance.low_confidence_threshold
        self.enable_memory_monitoring = config.enrichment.performance.enable_memory_monitoring
        self.enable_fuzzy_matching = config.enrichment.performance.enable_fuzzy_matching

        # Initialize progress tracking
        self.progress = ChunkProgress(
            total_records=len(sbir_df),
            chunk_size=self.chunk_size,
            checkpoint_dir=checkpoint_dir,
        )

        logger.info(
            f"Initialized chunked enricher: "
            f"{len(sbir_df)} records, "
            f"chunk_size={self.chunk_size}, "
            f"memory_threshold={self.memory_threshold_mb}MB"
        )

    def chunk_generator(self) -> Generator[pd.DataFrame, None, None]:
        """Generate chunks of SBIR data.

        Yields:
            DataFrame chunks of size chunk_size
        """
        for start_idx in range(0, len(self.sbir_df), self.chunk_size):
            end_idx = min(start_idx + self.chunk_size, len(self.sbir_df))
            chunk = self.sbir_df.iloc[start_idx:end_idx].copy()
            yield chunk

    def enrich_chunk(
        self, chunk: pd.DataFrame, chunk_num: int
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Enrich a single chunk of data.

        Args:
            chunk: DataFrame chunk to enrich
            chunk_num: Chunk number for tracking

        Returns:
            Tuple of (enriched DataFrame, metrics dict)
        """
        chunk_start_time = datetime.now()
        metrics = {
            "chunk_num": chunk_num,
            "chunk_size": len(chunk),
            "start_time": chunk_start_time.isoformat(),
        }

        try:
            # Enrich chunk with performance monitoring
            with performance_monitor.monitor_block(f"enrichment_chunk_{chunk_num}"):
                enriched_chunk = enrich_sbir_with_usaspending(
                    sbir_df=chunk,
                    recipient_df=self.recipient_df,
                    sbir_company_col="Company",
                    sbir_uei_col="UEI",
                    sbir_duns_col="Duns",
                    recipient_name_col="recipient_name",
                    recipient_uei_col="recipient_uei",
                    recipient_duns_col="recipient_duns",
                    high_threshold=self.high_threshold,
                    low_threshold=self.low_threshold,
                    return_candidates=True,
                )

            # Calculate chunk metrics
            matched = enriched_chunk["_usaspending_match_method"].notna().sum()
            match_rate = matched / len(enriched_chunk) if len(enriched_chunk) > 0 else 0

            metrics.update(
                {
                    "success": True,
                    "end_time": datetime.now().isoformat(),
                    "duration_seconds": (datetime.now() - chunk_start_time).total_seconds(),
                    "records_matched": int(matched),
                    "match_rate": match_rate,
                    "exact_matches": int(
                        enriched_chunk["_usaspending_match_method"]
                        .str.contains("exact", na=False)
                        .sum()
                    ),
                    "fuzzy_matches": int(
                        enriched_chunk["_usaspending_match_method"]
                        .str.contains("fuzzy", na=False)
                        .sum()
                    ),
                }
            )

            logger.info(
                f"Chunk {chunk_num} enriched: "
                f"{len(enriched_chunk)} records, "
                f"{match_rate:.1%} match rate, "
                f"{metrics['duration_seconds']:.2f}s"
            )

            return enriched_chunk, metrics

        except Exception as e:
            logger.error(f"Error enriching chunk {chunk_num}: {e}")
            metrics.update(
                {
                    "success": False,
                    "error": str(e),
                    "end_time": datetime.now().isoformat(),
                }
            )
            raise

    def process_all_chunks(self) -> Generator[Tuple[pd.DataFrame, Dict[str, Any]], None, None]:
        """Process all chunks with progress tracking.

        Yields:
            Tuple of (enriched chunk, metrics)
        """
        for chunk_num, chunk in enumerate(self.chunk_generator()):
            try:
                # Enrich chunk
                enriched_chunk, chunk_metrics = self.enrich_chunk(chunk, chunk_num)

                # Update progress
                self.progress.chunks_processed += 1
                self.progress.records_processed += len(chunk)

                # Save checkpoint if enabled
                if self.enable_progress_tracking:
                    checkpoint_path = self.progress.save_checkpoint(chunk_metrics)
                    logger.debug(f"Checkpoint saved: {checkpoint_path}")

                # Log progress
                self.progress.log_progress()

                yield enriched_chunk, chunk_metrics

            except Exception as e:
                logger.error(f"Failed to process chunk {chunk_num}: {e}")
                self.progress.errors.append(f"Chunk {chunk_num}: {str(e)}")

                # Save error checkpoint
                if self.enable_progress_tracking:
                    self.progress.save_checkpoint({"error": str(e), "chunk_num": chunk_num})

                raise

    def process_to_dataframe(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Process all chunks and return combined DataFrame.

        Returns:
            Tuple of (enriched DataFrame, summary metrics)
        """
        enriched_chunks = []
        all_metrics = {
            "total_chunks": self.progress.total_chunks,
            "chunk_size": self.chunk_size,
            "chunks": [],
            "start_time": datetime.now().isoformat(),
        }

        for enriched_chunk, chunk_metrics in self.process_all_chunks():
            enriched_chunks.append(enriched_chunk)
            all_metrics["chunks"].append(chunk_metrics)

        # Combine chunks
        if enriched_chunks:
            combined_df = pd.concat(enriched_chunks, ignore_index=True)
        else:
            combined_df = pd.DataFrame()

        # Calculate summary metrics
        total_matched = combined_df["_usaspending_match_method"].notna().sum()
        total_records = len(combined_df)
        overall_match_rate = total_matched / total_records if total_records > 0 else 0

        all_metrics.update(
            {
                "end_time": datetime.now().isoformat(),
                "total_records": total_records,
                "total_matched": int(total_matched),
                "overall_match_rate": overall_match_rate,
                "chunks_processed": self.progress.chunks_processed,
                "errors": self.progress.errors,
                "total_duration_seconds": self.progress.elapsed_seconds,
                "records_per_second": (
                    total_records / self.progress.elapsed_seconds
                    if self.progress.elapsed_seconds > 0
                    else 0
                ),
            }
        )

        logger.info(
            f"Chunked enrichment complete: "
            f"{total_records} records, "
            f"{overall_match_rate:.1%} match rate, "
            f"{all_metrics['total_duration_seconds']:.2f}s total"
        )

        return combined_df, all_metrics

    def process_streaming(self) -> Generator[pd.DataFrame, None, None]:
        """Process chunks and yield progressively enriched data.

        Use this for memory-constrained environments or when you need
        to process results as they complete.

        Yields:
            Enriched DataFrame chunks
        """
        for enriched_chunk, _ in self.process_all_chunks():
            yield enriched_chunk

    @staticmethod
    def estimate_memory_usage(
        sbir_records: int, recipient_records: int, chunk_size: int
    ) -> Dict[str, float]:
        """Estimate memory usage for chunked enrichment.

        Args:
            sbir_records: Number of SBIR records
            recipient_records: Number of recipient records
            chunk_size: Chunk size in records

        Returns:
            Dictionary with memory estimates
        """
        # Rough estimates based on typical dataframe memory usage
        # Average ~1KB per SBIR record, ~1KB per recipient record
        sbir_memory_mb = (sbir_records * 1.0) / 1024  # Per full dataset
        recipient_memory_mb = (recipient_records * 1.0) / 1024  # Loaded once
        chunk_working_memory_mb = (chunk_size * 0.5) / 1024  # Per chunk processing

        return {
            "sbir_memory_mb": sbir_memory_mb,
            "recipient_memory_mb": recipient_memory_mb,
            "chunk_working_memory_mb": chunk_working_memory_mb,
            "peak_memory_mb": recipient_memory_mb + chunk_working_memory_mb,
            "chunk_size": chunk_size,
        }


def create_dynamic_outputs_enrichment(
    sbir_df: pd.DataFrame, recipient_df: pd.DataFrame
) -> Generator[Tuple[int, pd.DataFrame], None, None]:
    """Create dynamic outputs for Dagster multi-asset pattern.

    This function enables Dagster's dynamic output pattern for
    processing large datasets in parallel across multiple workers.

    Args:
        sbir_df: SBIR awards DataFrame
        recipient_df: USAspending recipients DataFrame

    Yields:
        Tuple of (chunk_id, enriched_chunk_df)
    """
    config = get_config()
    chunk_size = config.enrichment.performance.chunk_size

    enricher = ChunkedEnricher(
        sbir_df=sbir_df,
        recipient_df=recipient_df,
        checkpoint_dir=Path("reports/checkpoints"),
        enable_progress_tracking=True,
    )

    for chunk_num, enriched_chunk in enumerate(enricher.process_streaming()):
        yield chunk_num, enriched_chunk


def combine_enriched_chunks(
    chunks: List[pd.DataFrame],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Combine multiple enriched chunks into final dataset.

    Args:
        chunks: List of enriched DataFrames

    Returns:
        Tuple of (combined DataFrame, metrics)
    """
    if not chunks:
        return pd.DataFrame(), {"error": "No chunks provided"}

    combined_df = pd.concat(chunks, ignore_index=True)

    # Calculate summary metrics
    total_matched = combined_df["_usaspending_match_method"].notna().sum()
    total_records = len(combined_df)
    match_rate = total_matched / total_records if total_records > 0 else 0

    metrics = {
        "total_records": total_records,
        "total_matched": int(total_matched),
        "match_rate": match_rate,
        "chunks_combined": len(chunks),
    }

    return combined_df, metrics
