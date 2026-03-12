"""Tests for task executors."""

from pathlib import Path

from src.autodev.executor import (
    ClaudeAPIExecutor,
    ClaudeCodeExecutor,
    DryRunExecutor,
    ExecutionResult,
)


class TestExecutionResult:
    def test_bool_true(self):
        result = ExecutionResult(success=True)
        assert bool(result) is True

    def test_bool_false(self):
        result = ExecutionResult(success=False)
        assert bool(result) is False

    def test_total_tokens(self):
        result = ExecutionResult(success=True, input_tokens=1000, output_tokens=500)
        assert result.total_tokens == 1500

    def test_default_zero_tokens(self):
        result = ExecutionResult(success=True)
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 0


class TestDryRunExecutor:
    def test_always_returns_success(self):
        executor = DryRunExecutor()
        result = executor("test prompt", Path("/tmp"))
        assert result.success is True
        assert result.input_tokens == 0
        assert result.output_tokens == 0


class TestClaudeCodeExecutorTokenParsing:
    def test_parse_json_output(self):
        output = '{"result": "ok", "usage": {"input_tokens": 1234, "output_tokens": 567}}'
        input_t, output_t = ClaudeCodeExecutor._parse_token_usage(output)
        assert input_t == 1234
        assert output_t == 567

    def test_parse_no_usage(self):
        output = '{"result": "ok"}'
        input_t, output_t = ClaudeCodeExecutor._parse_token_usage(output)
        assert input_t == 0
        assert output_t == 0

    def test_parse_invalid_json(self):
        output = "not json at all"
        input_t, output_t = ClaudeCodeExecutor._parse_token_usage(output)
        assert input_t == 0
        assert output_t == 0

    def test_parse_empty_string(self):
        input_t, output_t = ClaudeCodeExecutor._parse_token_usage("")
        assert input_t == 0
        assert output_t == 0


class TestClaudeAPIExecutorPathTraversal:
    def test_blocks_path_traversal(self, tmp_path):
        executor = ClaudeAPIExecutor()
        op = {"action": "create", "file": "../../etc/passwd", "content": "malicious"}
        result = executor._apply_operation(op, tmp_path)
        assert result is False
        assert not (tmp_path / "../../etc/passwd").exists()

    def test_blocks_writes_outside_src_tests(self, tmp_path):
        executor = ClaudeAPIExecutor()
        op = {"action": "create", "file": "config/evil.yaml", "content": "bad"}
        result = executor._apply_operation(op, tmp_path)
        assert result is False

    def test_allows_writes_to_src(self, tmp_path):
        (tmp_path / "src").mkdir()
        executor = ClaudeAPIExecutor()
        op = {"action": "create", "file": "src/new_module.py", "content": "# ok"}
        result = executor._apply_operation(op, tmp_path)
        assert result is True
        assert (tmp_path / "src" / "new_module.py").read_text() == "# ok"

    def test_allows_writes_to_tests(self, tmp_path):
        (tmp_path / "tests").mkdir()
        executor = ClaudeAPIExecutor()
        op = {"action": "create", "file": "tests/test_new.py", "content": "# test"}
        result = executor._apply_operation(op, tmp_path)
        assert result is True

    def test_edit_within_src(self, tmp_path):
        (tmp_path / "src").mkdir()
        target = tmp_path / "src" / "mod.py"
        target.write_text("old_code")
        executor = ClaudeAPIExecutor()
        op = {"action": "edit", "file": "src/mod.py", "search": "old_code", "replace": "new_code"}
        result = executor._apply_operation(op, tmp_path)
        assert result is True
        assert target.read_text() == "new_code"
