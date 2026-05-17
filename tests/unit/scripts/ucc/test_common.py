"""Tests for cross-worktree data path resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc._common import DEFAULT_DATA_DIR, data_dir, data_path  # noqa: E402


def test_data_dir_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)
    # Default resolves to the repo's own data/ dir.
    assert data_dir() == DEFAULT_DATA_DIR
    assert data_dir().name == "data"


def test_data_dir_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_data_path_joins_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_path("foo.jsonl") == tmp_path / "foo.jsonl"


def test_data_path_rejects_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    import pytest

    with pytest.raises(ValueError, match="must be relative"):
        data_path("/etc/passwd")
