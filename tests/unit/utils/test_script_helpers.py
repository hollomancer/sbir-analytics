"""Tests for sbir_etl.utils.reporting.script_helpers."""

import pytest

from sbir_etl.utils.reporting.script_helpers import (
    render_metric_table,
    serialize_dagster_metadata,
    write_gha_outputs,
)

pytestmark = pytest.mark.fast


# ==================== serialize_dagster_metadata ====================


class TestSerializeDagsterMetadata:
    def test_extracts_value_attribute(self):
        class DagsterValue:
            def __init__(self, v):
                self.value = v

        meta = {"count": DagsterValue(42), "rate": DagsterValue(0.95)}
        result = serialize_dagster_metadata(meta)
        assert result == {"count": 42, "rate": 0.95}

    def test_passes_through_plain_values(self):
        meta = {"name": "test", "count": 100}
        result = serialize_dagster_metadata(meta)
        assert result == {"name": "test", "count": 100}

    def test_mixed_dagster_and_plain(self):
        class DagsterValue:
            def __init__(self, v):
                self.value = v

        meta = {"dag": DagsterValue("wrapped"), "plain": "unwrapped"}
        result = serialize_dagster_metadata(meta)
        assert result == {"dag": "wrapped", "plain": "unwrapped"}

    def test_empty_metadata(self):
        assert serialize_dagster_metadata({}) == {}


# ==================== render_metric_table ====================


class TestRenderMetricTable:
    def test_basic_table(self):
        result = render_metric_table("Test Report", [("Records", 100), ("Rate", "95%")])
        lines = result.split("\n")
        assert lines[0] == "# Test Report"
        assert "| Records | 100 |" in result
        assert "| Rate | 95% |" in result

    def test_escapes_pipes(self):
        result = render_metric_table("T", [("a|b", "c|d")])
        assert r"a\|b" in result
        assert r"c\|d" in result

    def test_empty_rows(self):
        result = render_metric_table("Empty", [])
        assert "# Empty" in result
        assert "| Metric | Value |" in result

    def test_header_structure(self):
        result = render_metric_table("Title", [("k", "v")])
        lines = result.split("\n")
        assert lines[0] == "# Title"
        assert lines[1] == ""
        assert lines[2] == "| Metric | Value |"
        assert lines[3] == "| --- | --- |"
        assert lines[4] == "| k | v |"


# ==================== write_gha_outputs ====================


class TestWriteGhaOutputs:
    def test_writes_key_value_pairs(self, tmp_path):
        output_file = tmp_path / "output.txt"
        write_gha_outputs(output_file, {"key1": "val1", "key2": "val2"})

        content = output_file.read_text()
        assert "key1=val1\n" in content
        assert "key2=val2\n" in content

    def test_appends_to_existing(self, tmp_path):
        output_file = tmp_path / "output.txt"
        output_file.write_text("existing=line\n")
        write_gha_outputs(output_file, {"new": "value"})

        content = output_file.read_text()
        assert content.startswith("existing=line\n")
        assert "new=value\n" in content

    def test_none_path_is_noop(self):
        # Should not raise
        write_gha_outputs(None, {"key": "val"})

    def test_path_values_stringified(self, tmp_path):
        output_file = tmp_path / "output.txt"
        write_gha_outputs(output_file, {"path": tmp_path / "file.json"})

        content = output_file.read_text()
        assert "path=" in content
        assert "file.json" in content
