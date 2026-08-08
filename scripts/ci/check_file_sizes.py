#!/usr/bin/env python3
"""Fail when a git-tracked file exceeds the repository's size ceiling.

`.gitignore` fences the known bulk formats (parquet, data/, reports/, db,
duckdb, artifacts/), but it is pattern-based: a large file in an unforeseen
format or path can still be committed. This guard is the size-based backstop —
it inspects what git actually tracks (i.e. what reaches GitHub) and rejects
anything over the ceiling, regardless of extension.

Only tracked files are checked: a local, gitignored corpus under data/ never
reaches GitHub and must not trip the guard, so a filesystem walk would be
wrong. `git ls-files` is the authoritative "what is in the repo" list.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB — far above any legitimate text/config
                                  # file, far below any real data artifact.

# Paths intentionally allowed to exceed the ceiling, each with a reason.
# A tracked file over the ceiling that is NOT listed here fails the guard; an
# entry here that is absent or no longer over the ceiling also fails, so the
# list cannot silently rot (same discipline as the tier-boundary allowlist).
SIZE_ALLOWLIST: dict[str, str] = {}


@dataclass(frozen=True)
class SizeViolation:
    """One oversized tracked file or one stale allowlist entry."""

    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


def tracked_files(repository_root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return git-tracked paths (POSIX, repo-relative)."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [entry for entry in result.stdout.split("\0") if entry]


def scan(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    max_bytes: int = MAX_FILE_BYTES,
    allowlist: dict[str, str] = SIZE_ALLOWLIST,
) -> list[SizeViolation]:
    """Flag tracked files over the ceiling and stale allowlist entries."""

    violations: list[SizeViolation] = []
    used_allowlist: set[str] = set()
    limit_mib = max_bytes / (1024 * 1024)

    for relative in tracked_files(repository_root):
        path = repository_root / relative
        if not path.is_file():  # symlink or deleted-but-staged edge case
            continue
        size = path.stat().st_size
        if size <= max_bytes:
            continue
        if relative in allowlist:
            used_allowlist.add(relative)
            continue
        violations.append(
            SizeViolation(
                relative,
                f"{size / (1024 * 1024):.1f} MiB exceeds the {limit_mib:.0f} MiB "
                "ceiling; keep large artifacts out of git (store bytes off-repo "
                "and pin a hash), or add a justified SIZE_ALLOWLIST entry",
            )
        )

    for allowed_path in sorted(allowlist):
        if allowed_path not in used_allowlist:
            violations.append(
                SizeViolation(
                    allowed_path,
                    "stale SIZE_ALLOWLIST entry (file absent or no longer over the ceiling)",
                )
            )

    return sorted(violations, key=lambda item: item.path)


def main() -> int:
    violations = scan()
    if violations:
        print("Oversized tracked files were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("File-size checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
