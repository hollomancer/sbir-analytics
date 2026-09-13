"""Classify a rebuild against a drifting upstream.

A study whose input is a live public source cannot be reproduced bit-exactly:
the source is updated by someone else. What it can do is distinguish a
difference the world caused from a difference this repository caused, and say
which one it saw.

That distinction needs two measurements, not one. ``upstream_measure`` is taken
before any filtering this repository does, so it tracks the source itself;
``kept`` is taken after, so it tracks the pipeline. Their combination is what
makes a difference diagnosable -- and neither is sufficient alone, because an
upstream can revise a record in place without moving any count.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from sbir_etl.quality.study_manifest import ReproductionTolerance


class RebuildVerdict(StrEnum):
    """What a rebuild comparison concluded."""

    EXACT = "exact"
    UPSTREAM_DRIFT = "upstream_drift"
    PIPELINE_REGRESSION = "pipeline_regression"
    IDENTITY_DIVERGENCE = "identity_divergence"
    OUTSIDE_TOLERANCE = "outside_tolerance"


@dataclass(frozen=True)
class RebuildObservation:
    """One measured quantity, at baseline and on the rebuild."""

    quantity: str
    baseline: int
    rebuild: int

    @property
    def delta(self) -> int:
        return self.rebuild - self.baseline


@dataclass(frozen=True)
class RebuildComparison:
    """The result of classifying one rebuild."""

    verdict: RebuildVerdict
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Only an exact match or in-band upstream drift is agreement."""
        return self.verdict in {RebuildVerdict.EXACT, RebuildVerdict.UPSTREAM_DRIFT}


def classify_rebuild(
    *,
    upstream: RebuildObservation,
    kept: RebuildObservation,
    tolerances: dict[str, ReproductionTolerance],
    identity_agrees: bool,
) -> RebuildComparison:
    """Return the verdict for one rebuild of one live source.

    ``identity_agrees`` reports whether the kept rows are the same rows at the
    source's declared ``identity_grain``, not merely the same number of rows. It
    is checked before the counts, because equal counts over different rows is
    the case a count-only comparison silently passes.
    """

    upstream_moved = upstream.delta != 0
    kept_moved = kept.delta != 0

    if not identity_agrees:
        return RebuildComparison(
            RebuildVerdict.IDENTITY_DIVERGENCE,
            [
                f"kept rows differ at the declared identity grain "
                f"(counts {kept.baseline} -> {kept.rebuild}); equal counts over "
                "different rows is not agreement"
            ],
        )

    if not upstream_moved and kept_moved:
        return RebuildComparison(
            RebuildVerdict.PIPELINE_REGRESSION,
            [
                f"{upstream.quantity} held at {upstream.baseline} while "
                f"{kept.quantity} moved {kept.baseline} -> {kept.rebuild}; the "
                "upstream did not change, so this repository's behaviour did"
            ],
        )

    if not upstream_moved and not kept_moved:
        return RebuildComparison(RebuildVerdict.EXACT, [])

    breaches = []
    for observation in (upstream, kept):
        tolerance = tolerances.get(observation.quantity)
        if tolerance is None:
            breaches.append(
                f"no declared tolerance for {observation.quantity!r}, which moved "
                f"{observation.baseline} -> {observation.rebuild}"
            )
            continue
        if abs(observation.delta) > tolerance.absolute_band:
            breaches.append(
                f"{observation.quantity} moved by {abs(observation.delta)}, outside "
                f"the declared band of {tolerance.absolute_band}"
            )

    if breaches:
        return RebuildComparison(RebuildVerdict.OUTSIDE_TOLERANCE, breaches)

    return RebuildComparison(
        RebuildVerdict.UPSTREAM_DRIFT,
        [
            f"{upstream.quantity} moved {upstream.baseline} -> {upstream.rebuild} and "
            f"{kept.quantity} moved {kept.baseline} -> {kept.rebuild}, both within "
            "their declared bands, with kept-row identity agreeing"
        ],
    )


__all__ = [
    "RebuildComparison",
    "RebuildObservation",
    "RebuildVerdict",
    "classify_rebuild",
]
