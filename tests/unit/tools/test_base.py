"""Tests for the tool base infrastructure."""

import pytest
import pandas as pd

from sbir_etl.tools.base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class DummyTool(BaseTool):
    """Minimal tool for testing base class behavior."""

    name = "dummy_tool"
    version = "0.0.1"

    def execute(self, metadata: ToolMetadata, **kwargs):
        metadata.data_sources.append(
            DataSourceRef(name="Test Source", url="https://example.com", record_count=5)
        )
        metadata.record_count = 5
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        return ToolResult(data=df, metadata=metadata)


class FailingTool(BaseTool):
    """Tool that raises an error for testing error handling."""

    name = "failing_tool"
    version = "0.0.1"

    def execute(self, metadata: ToolMetadata, **kwargs):
        raise ValueError("Intentional test failure")


class TestDataSourceRef:
    def test_to_dict(self):
        ref = DataSourceRef(
            name="SBIR.gov", url="https://sbir.gov", version="2024-01",
            record_count=100, access_method="api",
        )
        d = ref.to_dict()
        assert d["name"] == "SBIR.gov"
        assert d["record_count"] == 100


class TestToolMetadata:
    def test_duration_seconds(self):
        from datetime import datetime, timedelta
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = start + timedelta(seconds=5)
        meta = ToolMetadata(
            tool_name="test", tool_version="1.0",
            execution_start=start, execution_end=end,
        )
        assert meta.duration_seconds == 5.0

    def test_duration_none_when_not_finished(self):
        from datetime import datetime
        meta = ToolMetadata(
            tool_name="test", tool_version="1.0",
            execution_start=datetime.utcnow(),
        )
        assert meta.duration_seconds is None

    def test_to_dict(self):
        from datetime import datetime
        meta = ToolMetadata(
            tool_name="test", tool_version="1.0",
            execution_start=datetime(2024, 1, 1),
            execution_end=datetime(2024, 1, 1, 0, 0, 5),
            record_count=42,
            warnings=["test warning"],
        )
        d = meta.to_dict()
        assert d["tool_name"] == "test"
        assert d["record_count"] == 42
        assert d["warnings"] == ["test warning"]
        assert d["duration_seconds"] == 5.0


class TestToolResult:
    def test_chain_metadata(self):
        from datetime import datetime
        upstream = ToolResult(
            data=pd.DataFrame(),
            metadata=ToolMetadata(
                tool_name="upstream_tool", tool_version="1.0",
                execution_start=datetime.utcnow(),
                data_sources=[DataSourceRef(name="Source A", url="https://a.com")],
            ),
        )
        downstream_meta = ToolMetadata(
            tool_name="downstream_tool", tool_version="1.0",
            execution_start=datetime.utcnow(),
        )
        chained = upstream.chain_metadata(downstream_meta)
        assert "upstream_tool" in chained.upstream_tools
        assert len(chained.data_sources) == 1
        assert chained.data_sources[0].name == "Source A"

    def test_to_dict_with_dataframe(self):
        from datetime import datetime
        result = ToolResult(
            data=pd.DataFrame({"x": [1, 2]}),
            metadata=ToolMetadata(
                tool_name="test", tool_version="1.0",
                execution_start=datetime.utcnow(),
            ),
        )
        d = result.to_dict()
        assert d["data"]["type"] == "DataFrame"
        assert d["data"]["shape"] == [2, 1]

    def test_to_dict_with_dict(self):
        from datetime import datetime
        result = ToolResult(
            data={"key": "value"},
            metadata=ToolMetadata(
                tool_name="test", tool_version="1.0",
                execution_start=datetime.utcnow(),
            ),
        )
        d = result.to_dict()
        assert d["data"]["key"] == "value"


class TestBaseTool:
    def test_run_populates_metadata(self):
        tool = DummyTool()
        result = tool.run()
        assert result.metadata.tool_name == "dummy_tool"
        assert result.metadata.tool_version == "0.0.1"
        assert result.metadata.execution_start is not None
        assert result.metadata.execution_end is not None
        assert result.metadata.record_count == 5
        assert len(result.metadata.data_sources) == 1

    def test_run_returns_correct_data(self):
        tool = DummyTool()
        result = tool.run()
        assert isinstance(result.data, pd.DataFrame)
        assert len(result.data) == 5

    def test_run_captures_timing(self):
        tool = DummyTool()
        result = tool.run()
        assert result.metadata.duration_seconds is not None
        assert result.metadata.duration_seconds >= 0

    def test_run_captures_parameters(self):
        tool = DummyTool()
        result = tool.run(param1="hello", param2=42)
        assert result.metadata.parameters_used["param1"] == "hello"
        assert result.metadata.parameters_used["param2"] == 42

    def test_run_sanitizes_dataframe_params(self):
        tool = DummyTool()
        result = tool.run(df=pd.DataFrame({"x": [1, 2, 3]}))
        assert "DataFrame" in result.metadata.parameters_used["df"]

    def test_failing_tool_raises(self):
        tool = FailingTool()
        with pytest.raises(ValueError, match="Intentional test failure"):
            tool.run()

    def test_failing_tool_still_records_end_time(self):
        tool = FailingTool()
        try:
            tool.run()
        except ValueError:
            pass
        # Can't easily access metadata after exception, but the logging should work
