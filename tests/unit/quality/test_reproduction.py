"""A rebuild against a live upstream must be classifiable, not just compared.

The motivating case: transition-scoring's fusion corpus rebuilt to 822 rows /
137 positives / 100 firms against a frozen 828 / 138 / 101, and the repository
could not say whether that was a reproduction or a regression.
"""

import pytest

from sbir_etl.quality.reproduction import (
    RebuildObservation,
    RebuildVerdict,
    classify_rebuild,
)
from sbir_etl.quality.study_manifest import ReproductionTolerance


def _tolerances(**bands: int) -> dict[str, ReproductionTolerance]:
    return {
        quantity: ReproductionTolerance(
            quantity=quantity,
            absolute_band=band,
            derivation="Set for this test.",
        )
        for quantity, band in bands.items()
    }


def test_unchanged_upstream_and_kept_is_exact() -> None:
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 428147, 428147),
        kept=RebuildObservation("rows_kept", 17, 17),
        tolerances=_tolerances(rows_scanned=100, rows_kept=1),
        identity_agrees=True,
    )
    assert result.verdict is RebuildVerdict.EXACT
    assert result.passed


def test_moved_upstream_and_moved_kept_in_band_is_drift() -> None:
    """The world changed and the pipeline tracked it. A finding, not a defect."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 428147, 428102),
        kept=RebuildObservation("rows_kept", 17, 16),
        tolerances=_tolerances(rows_scanned=100, rows_kept=1),
        identity_agrees=True,
    )
    assert result.verdict is RebuildVerdict.UPSTREAM_DRIFT
    assert result.passed


def test_unchanged_upstream_with_moved_kept_is_a_regression() -> None:
    """This fails regardless of tolerance: the upstream did not move, so we did."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 428147, 428147),
        kept=RebuildObservation("rows_kept", 17, 16),
        tolerances=_tolerances(rows_scanned=100, rows_kept=99),
        identity_agrees=True,
    )
    assert result.verdict is RebuildVerdict.PIPELINE_REGRESSION
    assert not result.passed


def test_moved_upstream_with_unchanged_kept_is_drift_that_missed_us() -> None:
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 428147, 428102),
        kept=RebuildObservation("rows_kept", 17, 17),
        tolerances=_tolerances(rows_scanned=100, rows_kept=1),
        identity_agrees=True,
    )
    assert result.verdict is RebuildVerdict.UPSTREAM_DRIFT
    assert result.passed


def test_equal_counts_over_different_rows_fails() -> None:
    """The case a count-only comparison silently passes.

    An upstream can revise a record in place. Every count holds and the kept set
    is not the same set, so counts agreeing is not agreement.
    """
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 428147, 428147),
        kept=RebuildObservation("rows_kept", 17, 17),
        tolerances=_tolerances(rows_scanned=100, rows_kept=1),
        identity_agrees=False,
    )
    assert result.verdict is RebuildVerdict.IDENTITY_DIVERGENCE
    assert not result.passed


def test_identity_divergence_outranks_an_exact_count_match() -> None:
    """Identity is checked first, so it cannot be masked by agreeing counts."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 1, 1),
        kept=RebuildObservation("rows_kept", 1, 1),
        tolerances=_tolerances(rows_scanned=0, rows_kept=0),
        identity_agrees=False,
    )
    assert result.verdict is RebuildVerdict.IDENTITY_DIVERGENCE


@pytest.mark.parametrize(
    "rebuild_kept,expected",
    [
        # baseline is 138 and the declared band is 2.
        pytest.param(137, RebuildVerdict.UPSTREAM_DRIFT, id="inside-band-delta-1"),
        pytest.param(136, RebuildVerdict.UPSTREAM_DRIFT, id="equal-to-band-delta-2"),
        pytest.param(135, RebuildVerdict.OUTSIDE_TOLERANCE, id="outside-band-delta-3"),
        pytest.param(140, RebuildVerdict.UPSTREAM_DRIFT, id="equal-to-band-upward"),
        pytest.param(141, RebuildVerdict.OUTSIDE_TOLERANCE, id="outside-band-upward"),
    ],
)
def test_tolerance_boundary_is_inclusive(rebuild_kept: int, expected: RebuildVerdict) -> None:
    """A band of 2 admits a move of 2 and refuses a move of 3."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 3369754, 3369700),
        kept=RebuildObservation("positives", 138, rebuild_kept),
        tolerances=_tolerances(rows_scanned=100, positives=2),
        identity_agrees=True,
    )
    assert result.verdict is expected


def test_a_quantity_with_no_declared_tolerance_fails() -> None:
    """Silence is not permission; an undeclared quantity cannot be in band."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 100, 99),
        kept=RebuildObservation("positives", 138, 137),
        tolerances=_tolerances(rows_scanned=100),
        identity_agrees=True,
    )
    assert result.verdict is RebuildVerdict.OUTSIDE_TOLERANCE
    assert any("no declared tolerance" in reason for reason in result.reasons)


def test_the_motivating_rebuild_is_now_determinate() -> None:
    """Done-when item 5, and the case that proves the mechanism earns its keep.

    transition-scoring's corpus was rebuilt twice. The first rebuild produced
    822 rows / 137 positives / 100 firms against a frozen 828 / 138 / 101 and
    was reported by hand as probable upstream drift. The second reproduced the
    frozen corpus exactly.

    The first pull was incomplete: FY2022 scanned 242,161 rows where the second
    scanned 351,131, dropping about 109,000 source rows and one award-grain
    notice with them. A count-only comparison sees 138 -> 137, finds it small,
    and calls it drift -- which is precisely the wrong answer a human gave.
    """
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 3_897_224, 3_788_254),
        kept=RebuildObservation("positives", 138, 137),
        tolerances=_tolerances(rows_scanned=10_000, positives=2),
        identity_agrees=True,
    )

    assert result.verdict is RebuildVerdict.OUTSIDE_TOLERANCE
    assert not result.passed
    assert any("rows_scanned moved by 108970" in reason for reason in result.reasons)


def test_the_complete_rebuild_is_exact() -> None:
    """The second rebuild, against the retrieval manifest committed with it."""
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 3_897_224, 3_897_224),
        kept=RebuildObservation("positives", 138, 138),
        tolerances=_tolerances(rows_scanned=10_000, positives=2),
        identity_agrees=True,
    )

    assert result.verdict is RebuildVerdict.EXACT
    assert result.passed


def test_a_small_kept_delta_does_not_excuse_a_large_upstream_delta() -> None:
    """The failure mode the hand diagnosis fell into, stated as a test.

    A kept count inside its band is not agreement when the upstream measure is
    far outside its own. The retrieval is what broke, and the kept count only
    looks reassuring because most of the dropped rows were never going to be
    kept.
    """
    result = classify_rebuild(
        upstream=RebuildObservation("rows_scanned", 3_897_224, 3_788_254),
        kept=RebuildObservation("positives", 138, 138),
        tolerances=_tolerances(rows_scanned=10_000, positives=2),
        identity_agrees=True,
    )

    assert result.verdict is RebuildVerdict.OUTSIDE_TOLERANCE
    assert not result.passed
