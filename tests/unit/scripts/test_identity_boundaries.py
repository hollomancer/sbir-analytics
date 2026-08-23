from pathlib import Path

import pytest

from scripts.ci import check_identity_boundaries as boundaries


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_unreviewed_direct_rapidfuzz_scorer_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "from rapidfuzz import fuzz\nscore = fuzz.token_set_ratio('a', 'b')\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "sbir_etl/example.py"


def test_plain_process_import_is_allowed(tmp_path: Path) -> None:
    # ``process`` drives the search; callers supply a scorer from
    # ``sbir_etl.identity``, so importing it is not itself a bypass.
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "from rapidfuzz import process\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_bare_package_import_is_rejected(tmp_path: Path) -> None:
    # ``import rapidfuzz`` reaches fuzz and distance by attribute access, so it
    # would otherwise bypass the guard without ever naming a scorer submodule.
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "import rapidfuzz\nscore = rapidfuzz.fuzz.token_set_ratio('a', 'b')\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "sbir_etl/example.py"


def test_scorer_submodule_import_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "sbir_etl/example.py", "import rapidfuzz.fuzz\n")

    assert len(boundaries.scan_file(path, repository_root=tmp_path)) == 1


def test_process_submodule_import_is_allowed(tmp_path: Path) -> None:
    path = _write(tmp_path, "sbir_etl/example.py", "import rapidfuzz.process\n")

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_duplicate_jurisdiction_map_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "STATES = {\n"
        "    'Alabama': 'AL',\n"
        "    'California': 'CA',\n"
        "    'Massachusetts': 'MA',\n"
        "    'New York': 'NY',\n"
        "    'Texas': 'TX',\n"
        "}\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert "jurisdiction map" in violations[0].message


def test_small_state_fixture_is_not_mistaken_for_an_implementation(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "tests/unit/example.py",
        "SAMPLE = {'Alabama': 'AL', 'California': 'CA'}\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_duplicate_exact_award_resolver_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "packages/example.py",
        "def resolve_award_identities(sbir, official):\n"
        "    return sbir.merge(official, on='award_id')\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert "exact award-key resolver" in violations[0].message


# The whole-repo scan parses every tracked Python file; the same invariant is
# enforced on every PR by the CI quality job running the script directly.
@pytest.mark.slow
def test_current_repository_obeys_identity_boundaries() -> None:
    assert boundaries.scan_repository() == []
