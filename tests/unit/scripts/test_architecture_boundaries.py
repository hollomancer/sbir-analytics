from pathlib import Path

import pytest

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


# The whole-repo scan parses every tracked Python file; the same invariant is
# enforced on every PR by the CI quality job running the script directly.
@pytest.mark.slow
def test_current_repository_obeys_architecture_boundaries() -> None:
    assert boundaries.scan_repository() == []


def test_script_import_exception_is_exact(tmp_path: Path) -> None:
    source_root = tmp_path / "packages/sbir-analytics/sbir_analytics"
    module = source_root / "assets/jobs/source_downloads.py"
    module.parent.mkdir(parents=True)
    module.write_text("from scripts.data.unapproved import run\n", encoding="utf-8")

    violations = boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path)

    assert [violation.imported_module for violation in violations] == ["scripts.data.unapproved"]


def test_packages_cannot_execute_repository_scripts(tmp_path: Path) -> None:
    package = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "script = Path('scripts') / 'data' / 'unapproved.py'\n"
        "subprocess.run([sys.executable, str(script)])\n",
    )

    violations = boundaries.scan_package("sbir_analytics", package, repository_root=tmp_path)

    assert len(violations) == 1
    assert violations[0].dependency_kind == "execute"
    assert violations[0].imported_module == "scripts/data/unapproved.py"


def test_script_execution_exception_is_exact(tmp_path: Path) -> None:
    source_root = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/assets/jobs/weekly_awards_report.py",
        "import subprocess\nsubprocess.run(['python', 'scripts/data/unapproved.py'])\n",
    )

    violations = boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path)

    assert [violation.imported_module for violation in violations] == ["scripts/data/unapproved.py"]


def test_execution_guard_ignores_script_paths_outside_the_subprocess_call(
    tmp_path: Path,
) -> None:
    """A `scripts/` literal is only a bridge when it is what gets spawned.

    The scan used to gate on "this file calls subprocess anywhere", then take
    any `scripts/*.py` literal in the module as the target — so an unrelated
    reference in a file that shells out for some other reason was reported.
    """

    source_root = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "import subprocess\n"
        "from pathlib import Path\n"
        "DOCS_REFERENCE = Path('scripts') / 'data' / 'unrelated.py'\n"
        "subprocess.run(['echo', 'hello'])\n",
    )

    assert boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path) == []


def test_execution_guard_resolves_a_command_built_in_a_local(tmp_path: Path) -> None:
    """Building argv in a local before spawning it is still a bridge."""

    source_root = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "repo = Path('/repo')\n"
        "script = repo / 'scripts' / 'data' / 'unapproved.py'\n"
        "cmd = [sys.executable, str(script), '--area', 'quantum']\n"
        "subprocess.run(cmd, cwd=str(repo))\n",
    )

    violations = boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path)

    assert [violation.imported_module for violation in violations] == ["scripts/data/unapproved.py"]


def test_execution_guard_does_not_guess_at_a_rebound_command(tmp_path: Path) -> None:
    """Two assignments to one name means static analysis cannot say which ran."""

    source_root = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "import subprocess\n"
        "cmd = ['python', 'scripts/data/first.py']\n"
        "cmd = ['python', 'scripts/data/second.py']\n"
        "subprocess.run(cmd)\n",
    )

    assert boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path) == []


def test_execution_guard_terminates_on_a_self_referential_name(tmp_path: Path) -> None:
    """Name resolution must not loop on `a = a` or a mutual cycle."""

    source_root = tmp_path / "packages" / "sbir-analytics" / "sbir_analytics"
    _write(
        tmp_path,
        "packages/sbir-analytics/sbir_analytics/example.py",
        "import subprocess\nfirst = second\nsecond = first\nsubprocess.run(first)\n",
    )

    assert boundaries.scan_package("sbir_analytics", source_root, repository_root=tmp_path) == []
