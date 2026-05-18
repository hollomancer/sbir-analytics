"""Tests for capital_events common helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events._common import data_dir, data_path, normalize_date  # noqa: E402


def test_data_dir_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)
    assert data_dir() == Path("/Users/hollomancer/projects/sbir-analytics/data")


def test_data_dir_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path


def test_data_path_joins_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    assert data_path("foo.jsonl") == tmp_path / "foo.jsonl"


def test_normalize_date_iso_passthrough():
    assert normalize_date("2024-03-15") == "2024-03-15"


def test_normalize_date_mm_dd_yyyy_slashes():
    assert normalize_date("03/15/2024") == "2024-03-15"


def test_normalize_date_iso_with_time():
    assert normalize_date("2024-03-15T10:30:00") == "2024-03-15"


def test_normalize_date_iso_with_zulu():
    assert normalize_date("2024-03-15T10:30:00Z") == "2024-03-15"


def test_normalize_date_empty_returns_empty():
    assert normalize_date("") == ""
    assert normalize_date(None) == ""


def test_normalize_date_invalid_returns_empty():
    assert normalize_date("not-a-date") == ""
    assert normalize_date("13/45/2024") == ""  # invalid date components


def test_data_path_rejects_absolute(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="must be relative"):
        data_path("/absolute/path.jsonl")
