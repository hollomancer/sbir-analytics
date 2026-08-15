"""Freeze-hash guard for the STTR spinout-linkage design.

`specs/sttr-spinout-linkage/amendments.md` freezes
`specs/sttr-spinout-linkage/design.md` at a raw-byte SHA-256 and requires
"a materializing asset [to] recompute this hash against the working copy
before running and fail closed on any mismatch" -- including a mismatch
caused by a well-intentioned edit to `design.md` that was never recorded as a
further amendment. `verify_design_frozen` is that check.

Revision 1 is the freeze-authorization record. Later numbered revisions may
refresh the working-copy digest (doc hygiene, non-criteria wording) without
thawing the cascade; the guard always checks against the **latest** digest
recorded in `amendments.md`.

Call it first, before touching any frozen criterion -- the cascade order, the
D1-D5 evidence-dimension table, the similarity method, the partner-type
precedence, or the D2 window. This module's own `d1_spine` loader calls it;
every D2-D5 dimension-scorer and cascade-assembly PR that follows (task 1.3+)
should do the same as its first line.

Mirrors the hash-verification pattern already used by
`packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/assets.py`
(`verify_frozen_spec` / `_verified_raw_digest`), scaled down to this spec's
single frozen file -- this spec's `amendments.md` records no self-hash for
itself the way the census spec's does, so only `design.md` is verified here.

Epistemic tier: exploratory (`specs/sttr-spinout-linkage/tasks.md` header).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class DesignNotFrozenError(RuntimeError):
    """`design.md`'s working-copy bytes no longer match the latest freeze
    digest recorded in `amendments.md`."""


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
DESIGN_PATH = _REPO_ROOT / "specs" / "sttr-spinout-linkage" / "design.md"
AMENDMENTS_PATH = DESIGN_PATH.parent / "amendments.md"

# Latest design.md digest recorded in amendments.md (Revision 2 as of
# 2026-08-15). Do not hand-edit this constant on a design.md change --
# amendments.md's append-only rule requires a new numbered revision first;
# update both together. `test_freeze_guard.py` asserts this constant still
# matches the latest SHA-256 parseable out of amendments.md.
FROZEN_DESIGN_SHA256 = "8e754731f0d0841e5f48c425e269bc9db59191e761bcd8df7292032f9f78ff07"


def verify_design_frozen(design_path: Path = DESIGN_PATH) -> str:
    """Fail closed unless `design_path`'s raw bytes match the latest freeze digest.

    Returns the verified SHA-256 hex digest on success.
    """

    try:
        content = design_path.read_bytes()
    except OSError as exc:
        raise DesignNotFrozenError(
            f"Frozen design spec is missing or unreadable at {design_path}: {exc}"
        ) from exc
    actual = hashlib.sha256(content).hexdigest()
    if actual != FROZEN_DESIGN_SHA256:
        raise DesignNotFrozenError(
            f"design.md has drifted from the freeze recorded in "
            f"amendments.md: expected SHA-256 {FROZEN_DESIGN_SHA256}, found {actual}. "
            "Record a new numbered amendment in amendments.md before proceeding."
        )
    return actual
