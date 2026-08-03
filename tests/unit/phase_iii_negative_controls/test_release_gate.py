"""Release gate for the Phase III negative-control and placebo arms.

This module contains a **deliberately failing** test. It is not broken, and it is
not a work-in-progress to be fixed by making it pass — it is a commitment device
described in `specs/phase-iii-negative-controls/design.md`: no Phase III census
count may be released as a validated result until evidence-backed
negative-control and placebo artifacts exist.

If you hit this while running the fast lane locally (`pytest -x` aborts the whole
suite here), deselect this sentinel node only:
``pytest --deselect tests/unit/phase_iii_negative_controls/test_release_gate.py::test_negative_controls_and_placebo_release_gate_is_closed``.

**This branch is not intended to merge while the gate is closed.** ``unit-fast``
is a required check, so merging would turn `main` red for every unrelated PR in
the repo, and the design doc forecloses the usual escapes — removing, skipping,
or xfailing the sentinel is not a resolution. The PR stays a draft until the gate
can close.

The green fixture tests beside this sentinel cover only the approved pure mechanics.
They do not establish source provenance, matching quality, balance, or an empirical
result and therefore cannot close this gate.
"""

import pytest


pytestmark = pytest.mark.fast


def test_negative_controls_and_placebo_release_gate_is_closed() -> None:
    pytest.fail(
        "Release gate intentionally closed: replace this sentinel only after real, "
        "provenance-backed negative-control and fixed-seed placebo artifacts exist; "
        "pure helper tests are not release evidence."
    )
