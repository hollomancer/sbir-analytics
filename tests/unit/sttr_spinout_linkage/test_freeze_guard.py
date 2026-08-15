"""Probes for the STTR spinout-linkage freeze-hash guard.

Exploratory tier: covers the guard's pass/fail behavior only. The fail-closed
case runs against a modified copy of `design.md`, not the real file, so this
test does not itself depend on `design.md` never changing.
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


def test_frozen_hash_constant_matches_the_latest_hash_in_amendments_md() -> None:
    """`FROZEN_DESIGN_SHA256` must match the latest design.md digest in amendments.md."""

    text = AMENDMENTS_PATH.read_text(encoding="utf-8")
    matches = re.findall(r"SHA-256:\*\*\s*`([0-9a-f]{64})`", text)
    assert matches, "Could not find any SHA-256 hash in amendments.md"
    assert matches[-1] == FROZEN_DESIGN_SHA256


def test_verify_design_frozen_passes_on_the_current_frozen_design_md() -> None:
    assert verify_design_frozen() == FROZEN_DESIGN_SHA256


def test_verify_design_frozen_fails_closed_on_a_modified_copy(tmp_path: Path) -> None:
    modified = tmp_path / "design.md"
    original = DESIGN_PATH.read_text(encoding="utf-8")
    modified.write_text(original + "\nunreviewed drift\n", encoding="utf-8")

    with pytest.raises(DesignNotFrozenError, match="drifted from the freeze"):
        verify_design_frozen(modified)


def test_verify_design_frozen_fails_closed_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DesignNotFrozenError, match="missing or unreadable"):
        verify_design_frozen(tmp_path / "does-not-exist.md")
