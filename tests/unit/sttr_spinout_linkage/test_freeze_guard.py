"""Probes for the Revision-2 freeze-hash guard.

Exploratory tier: covers the guard's pass/fail behavior only, matching task
1.2's kernel-test scope ("no tests or abstractions beyond what a single
probe needs"). The fail-closed case runs against a modified copy of
`design.md`, not the real file, so this test does not itself depend on
`design.md` never changing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.sttr_spinout_linkage.freeze_guard import (
    DESIGN_PATH,
    FROZEN_DESIGN_SHA256,
    DesignNotFrozenError,
    verify_design_frozen,
)


pytestmark = pytest.mark.fast

AMENDMENTS_PATH = DESIGN_PATH.parent / "amendments.md"


def test_frozen_hash_constant_matches_the_hash_recorded_in_amendments_md() -> None:
    """The guard digest must match amendments.md's latest frozen revision."""

    text = AMENDMENTS_PATH.read_text(encoding="utf-8")
    revision_2 = text.split("## Revision 2", 1)[1]
    match = re.search(r"SHA-256:\*\*\s*`([0-9a-f]{64})`", revision_2)
    assert match is not None, "Could not find a SHA-256 hash in amendments.md's Revision 2 entry"
    assert match.group(1) == FROZEN_DESIGN_SHA256


def test_verify_design_frozen_passes_on_the_current_frozen_design_md() -> None:
    assert verify_design_frozen() == FROZEN_DESIGN_SHA256


def test_verify_design_frozen_fails_closed_on_a_modified_copy(tmp_path: Path) -> None:
    modified = tmp_path / "design.md"
    original = DESIGN_PATH.read_text(encoding="utf-8")
    modified.write_text(original + "\nunreviewed drift\n", encoding="utf-8")

    with pytest.raises(DesignNotFrozenError, match="drifted from the Revision 2 freeze"):
        verify_design_frozen(modified)


def test_verify_design_frozen_fails_closed_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DesignNotFrozenError, match="missing or unreadable"):
        verify_design_frozen(tmp_path / "does-not-exist.md")
