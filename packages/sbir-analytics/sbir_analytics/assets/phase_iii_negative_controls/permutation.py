"""Permutation separation for the Phase III census placebo.

Every predicate is the frozen one from ``phase_iii_census.criteria``. The three
clauses that do not read the permuted completion date are evaluated once, and
each draw evaluates only the two that do. Core clauses are row-wise, so the
final survivor set is their intersection regardless of order: the per-draw
final stage matches the last row of ``build_census_tables``. Fixture tests
cover that identity against the shared builder.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from ..phase_iii_census.criteria import (
    CORE_CLAUSES,
    METRIC_COLUMNS,
    CensusInputError,
    build_sensitivity_grid_from_full,
    summarize_survivors,
    validate_pair_frame,
)
from .placebo import PLACEBO_SEED, assignment_identity, build_placebo_assignment

#: Core clauses whose predicate reads ``prior_period_of_performance_end``.
#: Only these change under the placebo; the rest are evaluated once per frame.
DATE_DEPENDENT_CLAUSE_IDS: frozenset[str] = frozenset(
    {"prior_end_observable", "target_post_completion"}
)

#: The preregistered confirmatory seed list is ``R16_FIRST_SEED + i`` for
#: ``i`` in ``range(R16_DRAWS)``. It deliberately starts one past the R15 seed:
#: the R15 draw was seen before this design was written and is run separately
#: as an equivalence precondition, not as a member of the confirmatory sample.
R16_FIRST_SEED = PLACEBO_SEED + 1
R16_DRAWS = 500
R16_PRIMARY_METRIC = "surviving_pairs"
R16_FINAL_CLAUSE_ID = CORE_CLAUSES[-1].clause_id
R16_INTERVAL_CONFIDENCE = 0.95
R16_THRESHOLD_LOWER_BOUND = 0.95

FINAL_STAGE_COLUMNS = ("seed", "stage", *METRIC_COLUMNS)
CELL_COLUMNS = ("seed", "cell_id", "time_window", "agency_match", *METRIC_COLUMNS)
DIGEST_COLUMNS = ("seed", "mapping_sha256", "assignment_identity")


def preregistered_seeds(draws: int = R16_DRAWS, first_seed: int = R16_FIRST_SEED) -> list[int]:
    """The R16 seed list: consecutive integers from the first confirmatory seed."""

    if draws < 1:
        raise CensusInputError("the permutation design requires at least one draw")
    if first_seed <= PLACEBO_SEED:
        raise CensusInputError(
            "confirmatory seeds must all exceed the R15 seed; that draw was seen before "
            "the design was written and is excluded from the confirmatory sample"
        )
    return [first_seed + i for i in range(draws)]


def date_independent_mask(pairs: pd.DataFrame, data_cut_date: date) -> pd.Series:
    """AND of every core clause that does not read the permuted completion date."""

    mask = pd.Series(True, index=pairs.index, dtype=bool)
    for clause in CORE_CLAUSES:
        if clause.clause_id in DATE_DEPENDENT_CLAUSE_IDS:
            continue
        mask &= clause.predicate(pairs, data_cut_date).fillna(False).astype(bool)
    return mask


def final_stage_and_cells(
    frame: pd.DataFrame,
    data_cut_date: date,
    *,
    fixed_mask: pd.Series,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Final-stage metrics and the six cells for one frame.

    ``fixed_mask`` is the date-independent mask for the same row index; it must
    have been computed on a frame that differs from ``frame`` only in
    ``prior_period_of_performance_end``.
    """

    if not fixed_mask.index.equals(frame.index):
        raise CensusInputError("fixed_mask must share the frame's row index exactly")
    mask = fixed_mask.copy()
    for clause in CORE_CLAUSES:
        if clause.clause_id in DATE_DEPENDENT_CLAUSE_IDS:
            mask &= clause.predicate(frame, data_cut_date).fillna(False).astype(bool)
    full = frame.loc[mask].copy()
    return summarize_survivors(full), build_sensitivity_grid_from_full(full)


@dataclass(frozen=True)
class PermutationDraws:
    """Per-draw records for the actual frame and every placebo seed."""

    actual_final: pd.DataFrame
    actual_cells: pd.DataFrame
    placebo_final: pd.DataFrame
    placebo_cells: pd.DataFrame
    mapping_digests: pd.DataFrame


def _final_row(seed: int | None, stage: str, summary: dict[str, object]) -> dict[str, object]:
    return {"seed": seed, "stage": stage, **{m: summary[m] for m in METRIC_COLUMNS}}


def run_permutation_draws(
    pairs: pd.DataFrame,
    data_cut_date: date,
    seeds: Sequence[int],
    *,
    on_draw: Callable[[int], None] | None = None,
) -> PermutationDraws:
    """Run the frozen placebo family over ``seeds`` and record final-stage metrics.

    The actual frame is summarised once with the same code path. Every seed
    produces exactly one assignment, one final-stage row, one six-cell table and
    one mapping digest; a seed that cannot be deranged raises, it does not skip.
    """

    if len(set(seeds)) != len(seeds):
        raise CensusInputError("permutation seeds must be distinct")
    # build_census_tables validates the pair frame before counting
    # (criteria._iter_core_clause_survivors). The fast path must fail closed on
    # the same malformed input rather than summarising it. One validation covers
    # every draw: validate_pair_frame inspects only key and identifier columns,
    # and the placebo changes nothing but prior_period_of_performance_end.
    validate_pair_frame(pairs)
    fixed = date_independent_mask(pairs, data_cut_date)

    actual_summary, actual_cells = final_stage_and_cells(pairs, data_cut_date, fixed_mask=fixed)
    actual_final = pd.DataFrame([_final_row(None, R16_FINAL_CLAUSE_ID, actual_summary)])
    actual_cells = actual_cells.assign(seed=None)[list(CELL_COLUMNS)]

    final_rows: list[dict[str, object]] = []
    cell_frames: list[pd.DataFrame] = []
    digests: list[dict[str, object]] = []
    for seed in seeds:
        assignment = build_placebo_assignment(pairs, seed=int(seed))
        summary, cells = final_stage_and_cells(
            assignment.permuted_pairs, data_cut_date, fixed_mask=fixed
        )
        final_rows.append(_final_row(int(seed), R16_FINAL_CLAUSE_ID, summary))
        cell_frames.append(cells.assign(seed=int(seed))[list(CELL_COLUMNS)])
        digests.append(
            {
                "seed": int(seed),
                "mapping_sha256": assignment.mapping_sha256,
                "assignment_identity": assignment_identity(assignment.audit),
            }
        )
        if on_draw is not None:
            on_draw(int(seed))

    mapping_digests = pd.DataFrame(digests, columns=list(DIGEST_COLUMNS))
    require_distinct_assignments(mapping_digests, len(seeds))
    return PermutationDraws(
        actual_final=actual_final,
        actual_cells=actual_cells,
        placebo_final=pd.DataFrame(final_rows, columns=list(FINAL_STAGE_COLUMNS)),
        placebo_cells=(
            pd.concat(cell_frames, ignore_index=True)
            if cell_frames
            else pd.DataFrame(columns=list(CELL_COLUMNS))
        ),
        mapping_digests=mapping_digests,
    )


def require_distinct_assignments(digests: pd.DataFrame, expected: int) -> None:
    """Refuse a collapsed null: the same donor mapping under different seeds.

    ``mapping_sha256`` includes seed, so it is unique whenever the seeds are.
    The seed-independent identity is what this check uses. Persist it on the
    draw store; a check that only runs inside ``run_permutation_draws`` cannot
    see a planted complete store.
    """

    if expected == 0:
        return
    if "assignment_identity" not in digests.columns:
        raise CensusInputError(
            "mapping digests are missing assignment_identity; a collapsed null cannot be detected"
        )
    if digests["assignment_identity"].nunique() != expected:
        raise CensusInputError(
            "two permutation seeds produced the same assignment; refusing to continue"
        )


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""

    if trials < 1 or successes < 0 or successes > trials:
        raise CensusInputError("wilson_interval requires 0 <= successes <= trials, trials >= 1")
    if not 0.0 < confidence < 1.0:
        raise CensusInputError("confidence must lie strictly inside (0, 1)")
    z = math.sqrt(2.0) * _erfinv(confidence)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denominator
    half_width = (z / denominator) * math.sqrt(
        p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)
    )
    return max(0.0, centre - half_width), min(1.0, centre + half_width)


def _erfinv(y: float) -> float:
    """Inverse error function by Newton refinement of a rational start."""

    # Giles (2012) single-precision seed, refined to double by Newton steps.
    w = -math.log((1.0 - y) * (1.0 + y))
    if w < 5.0:
        w -= 2.5
        x = 2.81022636e-08
        for c in (
            3.43273939e-07,
            -3.5233877e-06,
            -4.39150654e-06,
            0.00021858087,
            -0.00125372503,
            -0.00417768164,
            0.246640727,
            1.50140941,
        ):
            x = c + x * w
    else:
        w = math.sqrt(w) - 3.0
        x = -0.000200214257
        for c in (
            0.000100950558,
            0.00134934322,
            -0.00367342844,
            0.00573950773,
            -0.0076224613,
            0.00943887047,
            1.00167406,
            2.83297682,
        ):
            x = c + x * w
    x *= y
    for _ in range(3):
        err = math.erf(x) - y
        x -= err / (2.0 / math.sqrt(math.pi) * math.exp(-x * x))
    return x


@dataclass(frozen=True)
class ExceedanceSummary:
    metric: str
    stage_or_cell: str
    actual: float
    draws: int
    exceeded: int
    tied: int
    interval_low: float
    interval_high: float
    interval_method: str

    @property
    def proportion(self) -> float:
        return self.exceeded / self.draws


def exceedance(
    actual_value: float,
    placebo_values: Iterable[float],
    *,
    metric: str,
    stage_or_cell: str,
    confidence: float = R16_INTERVAL_CONFIDENCE,
) -> ExceedanceSummary:
    """Share of draws the actual value strictly exceeds. Ties are not exceedances."""

    values = np.asarray(list(placebo_values), dtype=float)
    if values.size == 0:
        raise CensusInputError("exceedance requires at least one placebo draw")
    exceeded = int(np.sum(actual_value > values))
    tied = int(np.sum(actual_value == values))
    low, high = wilson_interval(exceeded, int(values.size), confidence)
    return ExceedanceSummary(
        metric=metric,
        stage_or_cell=stage_or_cell,
        actual=float(actual_value),
        draws=int(values.size),
        exceeded=exceeded,
        tied=tied,
        interval_low=low,
        interval_high=high,
        interval_method=f"wilson_{int(round(confidence * 100))}",
    )


def primary_threshold_met(
    summary: ExceedanceSummary, lower_bound: float = R16_THRESHOLD_LOWER_BOUND
) -> bool:
    """R16 decision rule: the Wilson lower bound on the exceedance share clears the floor."""

    return summary.interval_low >= lower_bound


def exceedance_table(draws: PermutationDraws) -> pd.DataFrame:
    """Primary and secondary exceedance summaries, one row per metric x stage/cell."""

    rows: list[dict[str, object]] = []
    actual_final = draws.actual_final.iloc[0]
    for metric in METRIC_COLUMNS:
        summary = exceedance(
            float(actual_final[metric]),
            draws.placebo_final[metric].astype(float),
            metric=metric,
            stage_or_cell=R16_FINAL_CLAUSE_ID,
        )
        rows.append(_summary_row(summary, primary=(metric == R16_PRIMARY_METRIC)))
    for cell_id, actual_cell in draws.actual_cells.set_index("cell_id").iterrows():
        placebo_cell = draws.placebo_cells.loc[draws.placebo_cells["cell_id"].eq(cell_id)]
        for metric in METRIC_COLUMNS:
            summary = exceedance(
                float(actual_cell[metric]),
                placebo_cell[metric].astype(float),
                metric=metric,
                stage_or_cell=str(cell_id),
            )
            rows.append(_summary_row(summary, primary=False))
    return pd.DataFrame(rows)


def _summary_row(summary: ExceedanceSummary, *, primary: bool) -> dict[str, object]:
    return {
        "metric": summary.metric,
        "stage_or_cell": summary.stage_or_cell,
        "primary": primary,
        "descriptive_only": summary.metric == "total_obligated_dollars",
        "actual": summary.actual,
        "draws": summary.draws,
        "exceeded": summary.exceeded,
        "tied": summary.tied,
        "exceedance_proportion": summary.proportion,
        "interval_low": summary.interval_low,
        "interval_high": summary.interval_high,
        "interval_method": summary.interval_method,
        "threshold_met": primary_threshold_met(summary) if primary else None,
    }
