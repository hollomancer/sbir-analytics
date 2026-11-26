"""Tests for the single data-root resolver, ``sbir_etl.config.loader.data_root``."""

from pathlib import Path

import pytest

from sbir_etl.config.loader import DATA_ROOT_ENV, data_root, get_config, reload_config
from sbir_etl.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    monkeypatch.delenv("SBIR_DATA_DIR", raising=False)


def _config_dir(tmp_path: Path, paths_yaml: str) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "base.yaml").write_text(paths_yaml, encoding="utf-8")
    return config_dir


def test_env_variable_wins_over_config(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path, "paths:\n  data_root: /from/config\n")
    monkeypatch.setenv(DATA_ROOT_ENV, "/from/env")
    assert data_root(config_dir=config_dir) == Path("/from/env")


def test_config_value_used_when_env_unset(tmp_path):
    config_dir = _config_dir(tmp_path, "paths:\n  data_root: /from/config\n")
    assert data_root(config_dir=config_dir) == Path("/from/config")


def test_schema_default_used_when_config_omits_the_key(tmp_path):
    config_dir = _config_dir(tmp_path, "pipeline:\n  name: x\n")
    assert data_root(config_dir=config_dir) == Path("data")


def test_repository_config_keeps_the_relative_data_default():
    assert data_root() == Path("data")


def test_blank_env_variable_falls_through_to_config(monkeypatch, tmp_path):
    config_dir = _config_dir(tmp_path, "paths:\n  data_root: /from/config\n")
    monkeypatch.setenv(DATA_ROOT_ENV, "  ")
    assert data_root(config_dir=config_dir) == Path("/from/config")


def test_env_variable_is_read_on_every_call_despite_cached_config(monkeypatch):
    monkeypatch.setenv(DATA_ROOT_ENV, "/first")
    reload_config()
    try:
        get_config()  # caches a config that includes /first
        assert data_root() == Path("/first")
        monkeypatch.setenv(DATA_ROOT_ENV, "/second")
        assert data_root() == Path("/second")
        monkeypatch.delenv(DATA_ROOT_ENV)
        assert data_root() == Path("data")
    finally:
        reload_config()


def test_retired_sbir_data_dir_raises_and_names_new_variable(monkeypatch):
    monkeypatch.setenv("SBIR_DATA_DIR", "/old")
    monkeypatch.setenv(DATA_ROOT_ENV, "/new")
    with pytest.raises(ConfigurationError, match=DATA_ROOT_ENV):
        data_root()


def test_job_modules_resolve_their_paths_under_the_data_root(monkeypatch):
    """The three Dagster job modules build their paths from the shared resolver."""
    from sbir_analytics.assets.jobs import (
        phase_transition_archive,
        source_downloads,
        weekly_awards_report,
    )

    monkeypatch.setenv(DATA_ROOT_ENV, "/srv/data")
    for module in (weekly_awards_report, source_downloads, phase_transition_archive):
        assert module.data_root is data_root
        assert module.data_root() == Path("/srv/data")
