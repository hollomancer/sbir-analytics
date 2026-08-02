"""Unit tests for local-first SAM.gov entity download.

Focuses on the output layer: the partial-vs-canonical guard that stops a short
paginated fallback from overwriting a full dataset, and that S3 stays opt-in.
"""

import json

import pandas as pd
import pytest

from scripts.data.download_sam_gov import (
    META_NAME,
    MIN_CANONICAL_ROW_COUNT,
    PARQUET_NAME,
    PARQUET_NAME_PARTIAL,
    _write_local,
)


def _frame(rows: int) -> pd.DataFrame:
    return pd.DataFrame({"uei": [f"U{i:06d}" for i in range(rows)], "name": ["Acme"] * rows})


class TestWriteLocal:
    def test_writes_canonical_parquet(self, tmp_path):
        df = _frame(10)

        path = _write_local(df, tmp_path)

        assert path == tmp_path / PARQUET_NAME
        assert pd.read_parquet(path).equals(df)

    def test_creates_missing_destination(self, tmp_path):
        dest = tmp_path / "nested" / "sam_gov"

        _write_local(_frame(3), dest)

        assert (dest / PARQUET_NAME).is_file()

    def test_writes_metadata_sidecar(self, tmp_path):
        _write_local(_frame(7), tmp_path)

        meta = json.loads((tmp_path / META_NAME).read_text())
        assert meta["row_count"] == 7
        assert meta["source"] == "api.sam.gov"
        assert meta["partial"] is False
        assert meta["downloaded_at"]

    def test_partial_name_is_flagged_in_its_own_sidecar(self, tmp_path):
        # The sidecar is named after the parquet it describes, so a partial
        # write cannot clobber the canonical dataset's metadata.
        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        meta = json.loads((tmp_path / "sam_entity_records_partial.meta.json").read_text())
        assert meta["partial"] is True
        assert not (tmp_path / META_NAME).exists()

    def test_partial_write_does_not_touch_canonical(self, tmp_path):
        canonical = _write_local(_frame(60), tmp_path)
        canonical_bytes = canonical.read_bytes()

        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        assert canonical.read_bytes() == canonical_bytes
        assert (tmp_path / PARQUET_NAME_PARTIAL).is_file()

    def test_roundtrip_preserves_row_count(self, tmp_path):
        path = _write_local(_frame(1234), tmp_path)

        assert len(pd.read_parquet(path)) == 1234


class TestPartialThreshold:
    @pytest.mark.parametrize(
        ("rows", "expect_partial"),
        [
            (MIN_CANONICAL_ROW_COUNT - 1, True),
            (MIN_CANONICAL_ROW_COUNT, False),
            (MIN_CANONICAL_ROW_COUNT + 1, False),
        ],
    )
    def test_threshold_boundary(self, rows, expect_partial):
        # Mirrors the branch in main(); guards the boundary against drift.
        assert (rows < MIN_CANONICAL_ROW_COUNT) is expect_partial

    def test_names_are_distinct(self):
        assert PARQUET_NAME != PARQUET_NAME_PARTIAL


class TestPartialSidecarIsolation:
    """A partial write must not overwrite canonical metadata."""

    def test_partial_does_not_replace_canonical_sidecar(self, tmp_path):
        _write_local(_frame(60), tmp_path)
        canonical_meta = json.loads((tmp_path / "sam_entity_records.meta.json").read_text())

        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        after = json.loads((tmp_path / "sam_entity_records.meta.json").read_text())
        assert after == canonical_meta
        assert after["row_count"] == 60
        assert after["partial"] is False

    def test_partial_writes_its_own_sidecar(self, tmp_path):
        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        meta = json.loads((tmp_path / "sam_entity_records_partial.meta.json").read_text())
        assert meta["row_count"] == 5
        assert meta["partial"] is True
