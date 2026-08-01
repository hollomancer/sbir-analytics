"""Release gate for the Phase III negative-control and placebo arms.

This module contains a **deliberately failing** test. It is not broken, and it is
not a work-in-progress to be fixed by making it pass — it is a commitment device
described in `specs/phase-iii-negative-controls/design.md`: no Phase III census
count may be released as a validated result until evidence-backed
negative-control and placebo artifacts exist.

If you hit this while running the fast lane locally (`pytest -x` aborts the whole
suite here), deselect it:
``pytest --deselect tests/unit/phase_iii_negative_controls``.

**This branch is not intended to merge while the gate is closed.** ``unit-fast``
is a required check, so merging would turn `main` red for every unrelated PR in
the repo, and the design doc forecloses the usual escapes — removing, skipping,
or xfailing the sentinel is not a resolution. The PR stays a draft until the gate
can close.

The one design requirement a test could pin *today*, with none of the blocked
data — that the census filter takes no arm/label argument — belongs on `main` as a
real green test rather than here. See the design doc's "Arm-blind evaluation"
requirement.
"""

import pytest


pytestmark = pytest.mark.fast


def test_negative_controls_and_placebo_release_gate_is_closed() -> None:
    pytest.fail(
        "Release gate intentionally closed: replace this sentinel only with "
        "evidence-backed tests after both negative-control and placebo artifacts exist."
    )
