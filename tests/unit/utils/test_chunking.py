"""Unit tests for chunking utilities."""

import pandas as pd
import pytest

from src.utils.data.chunking import (
    ChunkIterator,
    batch_process,
    chunk_dataframe,
    chunk_iterable,
    chunk_generator,
)


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame({"a": list(range(20)), "b": list(range(20, 40))})


def test_chunk_dataframe(sample_dataframe):
    """Test chunking a DataFrame."""
    chunks = list(chunk_dataframe(sample_dataframe, chunk_size=5))
    
    assert len(chunks) == 4
    assert all(len(chunk) == 5 for chunk in chunks)  # All chunks should have 5 items


def test_chunk_dataframe_with_start_idx(sample_dataframe):
    """Test chunking a DataFrame with start index."""
    chunks = list(chunk_dataframe(sample_dataframe, chunk_size=5, start_idx=10))
    
    assert len(chunks) == 2
    assert len(chunks[0]) == 5
    assert len(chunks[1]) == 5


def test_chunk_iterable():
    """Test chunking an iterable."""
    items = list(range(10))
    chunks = list(chunk_iterable(items, chunk_size=3))
    
    assert len(chunks) == 4
    assert chunks[0] == [0, 1, 2]
    assert chunks[1] == [3, 4, 5]
    assert chunks[2] == [6, 7, 8]
    assert chunks[3] == [9]


def test_chunk_generator():
    """Test chunk_generator alias."""
    items = list(range(5))
    chunks = list(chunk_generator(items, chunk_size=2))
    
    assert len(chunks) == 3
    assert chunks[0] == [0, 1]
    assert chunks[1] == [2, 3]
    assert chunks[2] == [4]


def test_chunk_iterator_dataframe(sample_dataframe):
    """Test ChunkIterator with DataFrame."""
    iterator = ChunkIterator(sample_dataframe, chunk_size=5)
    chunks = list(iterator)
    
    assert len(chunks) == 4
    assert len(iterator) == 4
    assert iterator.get_chunk_count() == 4


def test_chunk_iterator_iterable():
    """Test ChunkIterator with iterable."""
    items = list(range(10))
    iterator = ChunkIterator(items, chunk_size=3)
    chunks = list(iterator)
    
    assert len(chunks) == 4
    assert iterator.get_chunk_count() is None  # Can't determine for iterables


def test_batch_process():
    """Test batch processing with a processor function."""
    items = list(range(10))
    
    def processor(batch):
        return sum(batch)
    
    results = list(batch_process(items, batch_size=3, processor=processor))
    
    assert len(results) == 4
    assert results[0] == 3  # 0+1+2
    assert results[1] == 12  # 3+4+5
    assert results[2] == 21  # 6+7+8
    assert results[3] == 9  # 9


def test_batch_process_with_error():
    """Test batch processing with error handling."""
    items = list(range(10))
    
    def processor(batch):
        if sum(batch) > 10:
            raise ValueError("Sum too large")
        return sum(batch)
    
    with pytest.raises(ValueError, match="Sum too large"):
        list(batch_process(items, batch_size=3, processor=processor))

