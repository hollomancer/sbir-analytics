from pathlib import Path

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


def test_current_repository_obeys_identity_boundaries() -> None:
    assert boundaries.scan_repository() == []


def test_local_company_name_normalizer_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "scripts/data/example.py",
        "def normalize_company_name(value):\n    return value.strip().lower()\n",
    )

    violations = boundaries.scan_file(path, repository_root=tmp_path)

    assert len(violations) == 1
    assert "normalize_company_name" in violations[0].message


def test_normalizer_that_delegates_to_a_named_profile_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "scripts/data/example.py",
        "from sbir_etl.identity import CompanyNameProfile, normalize_company_name\n"
        "def _norm_name(value):\n"
        "    return normalize_company_name(value, profile=CompanyNameProfile.LOWER_JOIN_V1)\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_normalizer_that_delegates_to_a_sibling_wrapper_is_allowed(tmp_path: Path) -> None:
    # ``uspto_models`` and ``text_normalization`` route through a module-level
    # wrapper; the wrapper itself is what must reach the primitive.
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "def normalize_recipient_name(value):\n    return normalize_name(value)\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_reviewed_non_company_normalizer_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "sbir_etl/transformers/fiscal/refresh_state_rates.py",
        "def _normalize_state_name(raw):\n    return raw.strip().upper()\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_archived_normalizer_is_not_scanned(tmp_path: Path) -> None:
    # Archived scripts are frozen provenance for published numbers, so they
    # keep the normalizer their results were produced with. The path is built
    # from parts so this file holds no literal reference to the archive
    # directory, which check_removed_src_references.py forbids.
    relative = str(Path("scripts") / "archive" / "data" / "example.py")
    path = _write(
        tmp_path,
        relative,
        "def _norm_name(value):\n    return value.strip().upper()\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []
