"""Tests for UCC data path resolution."""

import pytest

from sbir_etl.config.loader import DATA_ROOT_ENV
from sbir_etl.exceptions import ConfigurationError
from sbir_etl.ucc._common import data_dir, data_path


def test_data_dir_follows_server_data_root_variable(monkeypatch, tmp_path):
    """The server sets only SBIR_ETL__PATHS__DATA_ROOT; the UCC tools must honor it."""
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


def test_data_path_rejects_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
    with pytest.raises(ValueError, match="must be relative"):
        data_path("/etc/passwd")
