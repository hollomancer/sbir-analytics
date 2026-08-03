from pathlib import Path

from scripts.ci import check_architecture_boundaries as boundaries


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_core_rejects_static_and_dynamic_higher_layer_imports(tmp_path: Path) -> None:
    core = tmp_path / "sbir_etl"
    _write(
        tmp_path,
        "sbir_etl/example.py",
        "from sbir_ml.transition import scoring\n"
        "import importlib\n"
        "importlib.import_module('sbir_analytics.definitions')\n",
    )

    violations = boundaries.scan_package("sbir_etl", core, repository_root=tmp_path)

    assert [violation.imported_module for violation in violations] == [
        "sbir_ml.transition",
        "sbir_analytics.definitions",
    ]


def test_declared_downstream_dependencies_are_allowed(tmp_path: Path) -> None:
    analytics = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "from sbir_etl.models import Award\n"
        "from sbir_ml.transition import scoring\n"
        "from sbir_graph import loaders\n",
    )

    assert not boundaries.scan_package("sbir_analytics", analytics, repository_root=tmp_path)


def test_packages_cannot_import_scripts(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "sbir-ml" / "sbir_ml"
    _write(
        tmp_path,
        "packages/sbir-ml/sbir_ml/example.py",
        "from scripts.phase3_benchmark import transition_ranker\n",
    )

    violations = boundaries.scan_package("sbir_ml", package, repository_root=tmp_path)

    assert len(violations) == 1
    assert violations[0].imported_module == "scripts.phase3_benchmark"


def test_current_repository_obeys_architecture_boundaries() -> None:
    assert boundaries.scan_repository() == []


def test_script_import_exception_is_exact(tmp_path: Path) -> None:
    source_root = tmp_path / "packages/sbir-analytics/sbir_analytics"
    module = source_root / "assets/jobs/source_downloads.py"
    module.parent.mkdir(parents=True)
    module.write_text("from scripts.data.unapproved import run\n", encoding="utf-8")

    violations = boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path)

    assert [violation.imported_module for violation in violations] == ["scripts.data.unapproved"]
