"""Chunking utilities for processing large datasets in batches.

This module provides utilities for chunking DataFrames, iterables, and
other data structures to enable memory-efficient processing.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator
from typing import Any

import pandas as pd
from loguru import logger


def chunk_dataframe(
    df: pd.DataFrame, chunk_size: int, start_idx: int = 0
) -> Generator[pd.DataFrame, None, None]:
    """Chunk a DataFrame into smaller DataFrames.
    
    Args:
        df: DataFrame to chunk
        chunk_size: Number of rows per chunk
        start_idx: Starting index (for resuming chunking)
        
    Yields:
        DataFrame chunks of size chunk_size (or smaller for last chunk)
    """
    total_rows = len(df)
    for start in range(start_idx, total_rows, chunk_size):
        end = min(start + chunk_size, total_rows)
        chunk = df.iloc[start:end].copy()
        yield chunk


def chunk_iterable(
    items: Iterable[Any], chunk_size: int
) -> Generator[list[Any], None, None]:
    """Chunk an iterable into lists of fixed size.
    
    Args:
        items: Iterable to chunk
        chunk_size: Number of items per chunk
        
    Yields:
        Lists of items, each of size chunk_size (or smaller for last chunk)
    """
    chunk = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    
    # Yield remaining items
    if chunk:
        yield chunk


def chunk_generator(
    items: Iterable[Any], chunk_size: int
) -> Generator[list[Any], None, None]:
    """Alias for chunk_iterable for backward compatibility."""
    return chunk_iterable(items, chunk_size)


class ChunkIterator:
    """Generic chunk iterator for DataFrames and other iterables.
    
    Provides a consistent interface for chunking different data types.
    """
    
    def __init__(
        self,
        data: pd.DataFrame | Iterable[Any],
        chunk_size: int,
        start_idx: int = 0,
    ):
        """Initialize chunk iterator.
        
        Args:
            data: DataFrame or iterable to chunk
            chunk_size: Number of items per chunk
            start_idx: Starting index (for DataFrames only)
        """
        self.data = data
        self.chunk_size = chunk_size
        self.start_idx = start_idx
        self._is_dataframe = isinstance(data, pd.DataFrame)
    
    def __iter__(self) -> Generator[pd.DataFrame | list[Any], None, None]:
        """Iterate over chunks."""
        if self._is_dataframe:
            yield from chunk_dataframe(self.data, self.chunk_size, self.start_idx)
        else:
            yield from chunk_iterable(self.data, self.chunk_size)
    
    def __len__(self) -> int:
        """Return number of chunks."""
        if self._is_dataframe:
            total = len(self.data)
            return (total - self.start_idx + self.chunk_size - 1) // self.chunk_size
        else:
            # For iterables, we can't determine length without consuming
            raise TypeError("Cannot determine length for non-DataFrame iterables")
    
    def get_chunk_count(self) -> int | None:
        """Get number of chunks, or None if not determinable.
        
        Returns:
            Number of chunks for DataFrames, None for iterables
        """
        if self._is_dataframe:
            return len(self)
        return None


def batch_process(
    items: Iterable[Any],
    batch_size: int,
    processor: callable,
    *args: Any,
    **kwargs: Any,
) -> Generator[Any, None, None]:
    """Process items in batches using a processor function.
    
    Args:
        items: Items to process
        batch_size: Number of items per batch
        processor: Function to process each batch (batch, *args, **kwargs)
        *args: Additional positional arguments for processor
        **kwargs: Additional keyword arguments for processor
        
    Yields:
        Results from processor function for each batch
    """
    for chunk in chunk_iterable(items, batch_size):
        try:
            result = processor(chunk, *args, **kwargs)
            yield result
        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            raise

