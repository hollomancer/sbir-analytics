"""Tests for the large-file guard."""

import subprocess
from pathlib import Path

from scripts.ci import check_file_sizes as guard


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _track(root: Path, relative: str, size: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    _git(root, "add", relative)


def test_small_tracked_files_pass(tmp_path):
    root = _repo(tmp_path)
    _track(root, "a.txt", 10)
    _track(root, "pkg/b.py", 2048)
    assert guard.scan(repository_root=root, max_bytes=1024 * 1024) == []


def test_oversized_tracked_file_fails(tmp_path):
    root = _repo(tmp_path)
    _track(root, "big.json", 2 * 1024 * 1024)
    violations = guard.scan(repository_root=root, max_bytes=1024 * 1024)
    assert len(violations) == 1
    assert violations[0].path == "big.json"
    assert "exceeds" in violations[0].message


def test_gitignored_large_file_is_not_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / ".gitignore").write_text("*.parquet\n")
    _git(root, "add", ".gitignore")
    # A large local parquet that git does not track must be invisible to the guard.
    (root / "data.parquet").write_bytes(b"x" * (3 * 1024 * 1024))
    assert guard.scan(repository_root=root, max_bytes=1024 * 1024) == []


def test_tracked_symlink_measures_link_not_target(tmp_path):
    root = _repo(tmp_path)
    target = tmp_path.parent / "large-target.bin"
    target.write_bytes(b"x" * 2048)
    (root / "large-target-link").symlink_to(target)
    _git(root, "add", "large-target-link")

    assert guard.scan(repository_root=root, max_bytes=512) == []


def test_allowlisted_oversized_file_passes(tmp_path):
    root = _repo(tmp_path)
    _track(root, "big.bin", 2 * 1024 * 1024)
    allow = {"big.bin": "intentional fixture"}
    assert guard.scan(repository_root=root, max_bytes=1024 * 1024, allowlist=allow) == []


def test_stale_allowlist_entry_fails(tmp_path):
    root = _repo(tmp_path)
    _track(root, "small.txt", 10)
    allow = {"gone.bin": "no longer present"}
    violations = guard.scan(repository_root=root, max_bytes=1024 * 1024, allowlist=allow)
    assert len(violations) == 1
    assert "stale" in violations[0].message
    assert violations[0].path == "gone.bin"


def test_allowlisted_entry_now_under_ceiling_is_stale(tmp_path):
    root = _repo(tmp_path)
    _track(root, "shrunk.bin", 10)
    allow = {"shrunk.bin": "used to be big"}
    violations = guard.scan(repository_root=root, max_bytes=1024 * 1024, allowlist=allow)
    assert len(violations) == 1
    assert "stale" in violations[0].message


def test_real_repository_passes():
    assert guard.scan() == []
