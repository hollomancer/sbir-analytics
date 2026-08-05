"""Tests for synchronized release and runtime version validation."""

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ci" / "check_versioning.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_versioning", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _configure_fixture(monkeypatch, tmp_path: Path, *, runtime: str, pipeline: str) -> None:
    project_paths = {}
    for name in mod.PROJECTS:
        path = tmp_path / name / "pyproject.toml"
        path.parent.mkdir()
        path.write_text(f'[project]\nname = "{name}"\nversion = "0.1.1"\n', encoding="utf-8")
        project_paths[name] = path

    lock_file = tmp_path / "uv.lock"
    lock_file.write_text(
        "".join(f'[[package]]\nname = "{name}"\nversion = "0.1.1"\n' for name in project_paths),
        encoding="utf-8",
    )
    runtime_file = tmp_path / "sbir_etl" / "__init__.py"
    runtime_file.parent.mkdir()
    runtime_file.write_text(f'__version__ = "{runtime}"\n', encoding="utf-8")
    base_config = tmp_path / "config" / "base.yaml"
    base_config.parent.mkdir()
    base_config.write_text(
        f'pipeline:\n  name: "sbir-analytics"\n  version: "{pipeline}"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "PROJECTS", project_paths)
    monkeypatch.setattr(mod, "LOCK_FILE", lock_file)
    monkeypatch.setattr(mod, "RUNTIME_VERSION_FILE", runtime_file)
    monkeypatch.setattr(mod, "BASE_CONFIG_FILE", base_config)


def test_validate_accepts_synchronized_runtime_versions(monkeypatch, tmp_path: Path) -> None:
    _configure_fixture(monkeypatch, tmp_path, runtime="0.1.1", pipeline="0.1.1")

    assert mod.validate("v0.1.1") == []


def test_validate_rejects_stale_python_runtime_version(monkeypatch, tmp_path: Path) -> None:
    _configure_fixture(monkeypatch, tmp_path, runtime="0.1.0", pipeline="0.1.1")

    assert "sbir_etl.__version__ is '0.1.0'; expected '0.1.1'" in mod.validate()


def test_validate_rejects_stale_pipeline_config_version(monkeypatch, tmp_path: Path) -> None:
    _configure_fixture(monkeypatch, tmp_path, runtime="0.1.1", pipeline="0.1.0")

    assert "config/base.yaml pipeline.version is '0.1.0'; expected '0.1.1'" in mod.validate()
