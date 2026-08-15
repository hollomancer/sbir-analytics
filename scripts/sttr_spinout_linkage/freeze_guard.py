"""Freeze-hash guard for the STTR spinout-linkage design (Revision 1).

`specs/sttr-spinout-linkage/amendments.md`'s Revision 1 entry freezes
`specs/sttr-spinout-linkage/design.md` at its raw-byte SHA-256 and requires
"a materializing asset [to] recompute this hash against the working copy
before running and fail closed on any mismatch" -- including a mismatch
caused by a well-intentioned edit to `design.md` that was never recorded as a
further amendment. `verify_design_frozen` is that check.

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
    """`design.md`'s working-copy bytes no longer match the Revision 1 freeze
    recorded in `amendments.md`."""


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "sbir_etl").exists():
            return candidate
    raise RuntimeError("Not inside the sbir-analytics checkout")


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
DESIGN_PATH = _REPO_ROOT / "specs" / "sttr-spinout-linkage" / "design.md"

# specs/sttr-spinout-linkage/amendments.md, "## Revision 1 -- FREEZE", the
# "Frozen file" bullet: raw-byte SHA-256 of design.md at freeze time
# (2026-08-14). Do not hand-edit this constant on a design.md change --
# amendments.md's append-only rule requires a new numbered revision first;
# update both together. `test_freeze_guard.py` asserts this constant still
# matches what is parseable out of amendments.md.
FROZEN_DESIGN_SHA256 = "52d8b531d56f3b91e1d3b0946e1ac91dd6f5dfeab371e3d48f87dc5e6095ac49"


def verify_design_frozen(design_path: Path = DESIGN_PATH) -> str:
    """Fail closed unless `design_path`'s raw bytes match the Revision 1 freeze.

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
            f"design.md has drifted from the Revision 1 freeze recorded in "
            f"amendments.md: expected SHA-256 {FROZEN_DESIGN_SHA256}, found {actual}. "
            "Record a new numbered amendment in amendments.md before proceeding."
        )
    return actual
