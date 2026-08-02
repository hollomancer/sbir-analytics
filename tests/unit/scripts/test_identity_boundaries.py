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
    path = _write(
        tmp_path,
        "sbir_etl/example.py",
        "from rapidfuzz import process\n",
    )

    assert boundaries.scan_file(path, repository_root=tmp_path) == []


def test_current_repository_obeys_identity_boundaries() -> None:
    assert boundaries.scan_repository() == []
