"""Tests for capital_events common helpers."""

import pytest

from sbir_etl.capital_events._common import data_dir, data_path, normalize_date
from sbir_etl.config.loader import DATA_ROOT_ENV
from sbir_etl.exceptions import ConfigurationError


def test_data_dir_follows_server_data_root_variable(monkeypatch, tmp_path):
    """The server sets only SBIR_ETL__PATHS__DATA_ROOT; capital events must honor it."""
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    assert data_dir() == tmp_path


def test_data_dir_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    assert str(data_dir()) == "data"


def test_retired_sbir_data_dir_raises_and_names_new_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_DATA_DIR", str(tmp_path))
    with pytest.raises(ConfigurationError, match=DATA_ROOT_ENV):
        data_dir()


def test_data_path_joins_filename(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
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
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    with pytest.raises(ValueError, match="must be relative"):
        data_path("/absolute/path.jsonl")
