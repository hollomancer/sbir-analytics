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
- Graceful degradation with dynamic chunk resizing
- Spill-to-disk support for memory-constrained environments
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import pandas as pd
from loguru import logger

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

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

        # Memory pressure tracking
        self.current_chunk_size = self.chunk_size
        self.spill_dir = Path("reports/spill")
        self.memory_pressure_warnings = 0
        self.chunk_size_reductions = 0
        self.chunks_spilled = 0
