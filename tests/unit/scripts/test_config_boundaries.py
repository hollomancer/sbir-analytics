from pathlib import Path

import pytest

from scripts.ci import check_config_boundaries as boundaries


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_module_safe_load_call_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "import yaml as y\npayload = y.safe_load('key: value')\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "sbir_etl/example.py"


def test_direct_safe_load_import_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "scripts/data/example.py",
        "from yaml import safe_load as load\npayload = load('key: value')\n",
    )

    assert len(boundaries.scan_file(path, repository_root=tmp_path)) == 1


def test_non_safe_load_readers_are_rejected(tmp_path: Path) -> None:
    """``yaml.load(..., Loader=...)`` and friends bypass the primitive just as much.

    Matching only ``safe_load`` left the pre-``safe_load`` idiom green, which is
    the spelling most likely to be reached for from habit.
    """

    for source, expected in (
        ("import yaml\npayload = yaml.load('k: v', Loader=yaml.SafeLoader)\n", "load"),
        ("import yaml\npayload = yaml.full_load('k: v')\n", "full_load"),
        ("import yaml\npayload = yaml.unsafe_load('k: v')\n", "unsafe_load"),
        ("import yaml\npayload = list(yaml.safe_load_all('k: v'))\n", "safe_load_all"),
        ("from yaml import load\npayload = load('k: v')\n", "load"),
    ):
        path = _write(tmp_path, "sbir_etl/example.py", source)

        violations = boundaries.scan_file(path, repository_root=tmp_path)

        assert len(violations) == 1, source
        assert violations[0].function_name == expected
        assert f"yaml.{expected}" in violations[0].format()


def test_shared_reader_and_yaml_writes_are_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "import yaml\n"
        "from sbir_etl.config.yaml_io import read_yaml_mapping\n"
        "text = yaml.safe_dump({'key': 'value'})\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_canonical_readers_and_tests_are_outside_the_guard(tmp_path: Path) -> None:
    canonical = _write(
        tmp_path,
        "sbir_etl/config/yaml_io.py",
        "import yaml\npayload = yaml.safe_load('key: value')\n",
    )
    test_file = _write(
        tmp_path,
        "tests/unit/test_fixture.py",
        "import yaml\npayload = yaml.safe_load('key: value')\n",
    )

    assert boundaries.scan_file(canonical, repository_root=tmp_path) == []
    assert boundaries.scan_file(test_file, repository_root=tmp_path) == []


# The whole-repo scan parses every tracked Python file; the same invariant is
# enforced on every PR by the CI quality job running the script directly.
@pytest.mark.slow
def test_current_repository_obeys_config_boundaries() -> None:
    assert boundaries.scan_repository() == []
