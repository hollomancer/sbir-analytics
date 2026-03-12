"""Tests for task executors."""

from pathlib import Path

from src.autodev.executor import ClaudeAPIExecutor, DryRunExecutor


class TestDryRunExecutor:
    def test_always_returns_true(self):
        executor = DryRunExecutor()
        assert executor("test prompt", Path("/tmp")) is True


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
