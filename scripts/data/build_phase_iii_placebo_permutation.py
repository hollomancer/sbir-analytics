#!/usr/bin/env python3
"""Run the R16 permutation-separation design for the Phase III census placebo.

The design is frozen in ``studies/phase-iii-census/validation-design.md`` and
recorded as Revision 16 of the census amendment log. This script implements it;
it does not approve it. Production execution is process-gated on a separate
repository-owner approval of the R16 run, exactly as the R15 single-draw run
was, and ``--owner-approved`` asserts that approval rather than granting it.

Sequence, all of which must succeed before any confirmatory draw is taken:

1. Verify the frozen design and amendment-log digests.
2. Load and provenance-verify the exact Phase 1 source universe and build the
   frozen exact-UEI pair frame.
3. Equivalence precondition: run seed 20260801 through the R16 path and require
   the recorded R15 placebo final-stage metrics and assignment digest, and the
   recorded R15 actual final-stage metrics. A mismatch stops the run before any
   confirmatory seed is drawn.
4. Run the preregistered seed list in fixed order, appending one final-stage row,
   one six-cell table and one digest per seed to a resumable draw store.
5. Only when every preregistered seed is present, compute the exceedance table
   and write the manifest. A partial store is not a result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_analytics.assets.phase_iii_candidates.pairing import build_uei_pairs
from sbir_analytics.assets.phase_iii_census.assets import (
    CENSUS_CONTRACT_COLUMNS,
    CENSUS_PAIR_COLUMNS,
    PHASE_II_AWARDS_PATH,
    PHASE_II_OUTPUT_ENV,
    _load_contracts,
    _verify_phase_ii_provenance,
    parse_census_data_cut_date,
    verify_frozen_spec,
)
from sbir_analytics.assets.phase_iii_census.criteria import (
    METRIC_COLUMNS,
    CensusInputError,
    validate_source_columns,
)
from sbir_analytics.assets.phase_iii_negative_controls import permutation as perm
from sbir_analytics.assets.phase_iii_negative_controls.placebo import PLACEBO_SEED
from sbir_etl.quality.study_manifest import load_study_manifest

#: The manifest is the single source of truth for the pinned design digest, so
#: the run cannot drift from the bytes study.yaml claims were evaluated.
STUDY_MANIFEST_PATH = Path("studies/phase-iii-census/study.yaml")
VALIDATION_DESIGN_PATH = "studies/phase-iii-census/validation-design.md"

#: Values recorded in studies/phase-iii-census/placebo-results-2026-08-03.md for
#: the final cumulative clause. The R16 execution path must reproduce them from
#: seed 20260801 before any confirmatory seed is drawn. Dollars compare to the
#: cent because the recorded value is printed to the cent.
R15_RECORDED = {
    "assignment_mapping_sha256": "c1c97a9c7f1c81105a17dc21888afb7493311605405272672608d950c9250119",
    "placebo_final": {
        "surviving_pairs": 546_242,
        "distinct_firms": 1_985,
        "distinct_contracts": 21_357,
        "total_obligated_dollars": 46_386_904_542.06,
    },
    "actual_final": {
        "surviving_pairs": 727_292,
        "distinct_firms": 2_369,
        "distinct_contracts": 28_665,
        "total_obligated_dollars": 55_080_851_466.46,
    },
}

OUTPUT_NAMES = {
    "actual_final": "phase_iii_permutation_actual_final.parquet",
    "actual_cells": "phase_iii_permutation_actual_cells.parquet",
    "placebo_final": "phase_iii_permutation_placebo_final.parquet",
    "placebo_cells": "phase_iii_permutation_placebo_cells.parquet",
    "mapping_digests": "phase_iii_permutation_mapping_digests.parquet",
    "exceedance": "phase_iii_permutation_exceedance.parquet",
}
STORE_NAMES = {
    "placebo_final": "draws_final.parquet",
    "placebo_cells": "draws_cells.parquet",
    "mapping_digests": "draws_digests.parquet",
}
MANIFEST_NAME = "phase_iii_permutation_manifest.json"
PRECONDITION_NAME = "phase_iii_permutation_precondition.json"
BATCH_COUNTS = {"placebo_final": 1, "placebo_cells": 6, "mapping_digests": 1}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8"
    ) as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
        temporary = Path(output.name)
    os.replace(temporary, path)


def verify_validation_design(repository_root: Path | None = None) -> dict[str, str]:
    """Verify the pinned R16 design bytes and return the digest that was evaluated.

    ``verify_frozen_spec`` covers design.md and amendments.md only. The protocol
    this run executes lives in a third artifact, pinned in study.yaml; without
    this check a run could proceed against an edited protocol and the emitted
    manifest would not say which bytes it followed.
    """

    root = repository_root or Path.cwd()
    manifest = load_study_manifest(root / STUDY_MANIFEST_PATH)
    pinned = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}
    expected = pinned.get(VALIDATION_DESIGN_PATH)
    if expected is None:
        raise CensusInputError(
            f"{VALIDATION_DESIGN_PATH} is not pinned in {STUDY_MANIFEST_PATH}; the R16 run "
            "requires the evaluated design to be a frozen artifact"
        )
    design_path = root / VALIDATION_DESIGN_PATH
    if not design_path.exists():
        raise CensusInputError(f"pinned validation design is missing at {design_path}")
    observed = _file_sha256(design_path)
    if observed != expected:
        raise CensusInputError(
            f"validation design digest mismatch: {VALIDATION_DESIGN_PATH} hashes to {observed}, "
            f"study.yaml pins {expected}. The protocol changed; a run under it would not be "
            "confirmatory."
        )
    return {"path": VALIDATION_DESIGN_PATH, "sha256": observed}


def run_fingerprint(
    freeze: dict[str, Any],
    design: dict[str, str],
    inputs: dict[str, Any],
    data_cut: Any,
) -> str:
    """Identity of everything a draw depends on, so batches cannot be mixed."""

    payload = {
        "freeze": freeze,
        "validation_design": design,
        "data_cut_date": str(data_cut),
        "inputs": {
            key: {k: v for k, v in value.items() if k in {"sha256", "rows"}}
            for key, value in inputs.items()
            if isinstance(value, dict)
        },
        "pair_rows": inputs.get("pair_rows"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(serialized).hexdigest()


def _metrics_match(observed: dict[str, object], recorded: dict[str, float]) -> list[str]:
    mismatches: list[str] = []
    for metric in METRIC_COLUMNS:
        got = observed[metric]
        want = recorded[metric]
        if metric == "total_obligated_dollars":
            ok = round(float(got), 2) == round(float(want), 2)
        else:
            ok = int(got) == int(want)
        if not ok:
            mismatches.append(f"{metric}: got {got!r}, recorded {want!r}")
    return mismatches


def run_equivalence_precondition(pairs: pd.DataFrame, data_cut: Any) -> dict[str, Any]:
    """Seed 20260801 through the R16 path must reproduce the recorded R15 values."""

    draws = perm.run_permutation_draws(pairs, data_cut, [PLACEBO_SEED])
    placebo = draws.placebo_final.iloc[0].to_dict()
    actual = draws.actual_final.iloc[0].to_dict()
    digest = str(draws.mapping_digests.iloc[0]["mapping_sha256"])

    problems = [f"placebo {m}" for m in _metrics_match(placebo, R15_RECORDED["placebo_final"])]
    problems += [f"actual {m}" for m in _metrics_match(actual, R15_RECORDED["actual_final"])]
    if digest != R15_RECORDED["assignment_mapping_sha256"]:
        problems.append(
            f"assignment digest: got {digest}, recorded {R15_RECORDED['assignment_mapping_sha256']}"
        )
    if problems:
        raise CensusInputError(
            "R16 equivalence precondition failed; the permutation path does not reproduce the "
            "recorded R15 result, so no confirmatory draw was taken: " + "; ".join(problems)
        )
    return {
        "seed": PLACEBO_SEED,
        "assignment_mapping_sha256": digest,
        "placebo_final": {m: placebo[m] for m in METRIC_COLUMNS},
        "actual_final": {m: actual[m] for m in METRIC_COLUMNS},
        "matched_recorded_r15": True,
    }


def complete_seeds(frames: dict[str, pd.DataFrame]) -> set[int]:
    """Seeds present with their full expected row count in every store frame."""

    if not frames:
        return set()
    per_frame: list[set[int]] = []
    for label, expected in BATCH_COUNTS.items():
        counts = frames[label]["seed"].astype(int).value_counts()
        per_frame.append({int(seed) for seed, n in counts.items() if int(n) == expected})
    return set.intersection(*per_frame)


def require_complete_store(frames: dict[str, pd.DataFrame], seeds: Sequence[int]) -> None:
    """Every store frame must hold exactly its expected rows for exactly ``seeds``.

    ``_load_store`` reconciles to complete seeds, so ``run`` should never reach a
    partial store here. This is the invariant that makes that reasoning checkable
    rather than assumed: summarising must never silently draw secondary intervals
    from a different number of rows than the primary statistic used.
    """

    expected_seeds = {int(seed) for seed in seeds}
    for label, per_seed in BATCH_COUNTS.items():
        counts = frames[label]["seed"].astype(int).value_counts()
        if set(counts.index) != expected_seeds or not (counts == per_seed).all():
            raise CensusInputError(
                f"draw store frame {label!r} does not hold exactly {per_seed} row(s) for each of "
                f"the {len(expected_seeds)} preregistered seeds; refusing to summarise a "
                "partial store"
            )


def _load_store(store_dir: Path) -> dict[str, pd.DataFrame]:
    """Load the draw store, truncated to seeds that are complete in all three frames.

    The three tables are written separately, so an interruption mid-batch can
    leave a seed in one frame and not another. Truncating to the intersection
    makes a torn batch recoverable — the affected seeds are simply rerun — where
    refusing to load would strand a multi-hour run.
    """

    present = {label: store_dir / name for label, name in STORE_NAMES.items()}
    existing = {label: path for label, path in present.items() if path.exists()}
    if not existing:
        return {}
    if set(existing) != set(STORE_NAMES):
        missing = sorted(set(STORE_NAMES) - set(existing))
        raise CensusInputError(
            f"draw store at {store_dir} is missing {missing}; remove the store and rerun"
        )
    frames = {label: pd.read_parquet(path) for label, path in present.items()}
    keep = complete_seeds(frames)
    for label, frame in list(frames.items()):
        trimmed = frame.loc[frame["seed"].astype(int).isin(keep)].reset_index(drop=True)
        if len(trimmed) != len(frame):
            _write_parquet_atomic(trimmed, present[label])
        frames[label] = trimmed
    return frames


def _append_store(
    store_dir: Path, existing: dict[str, pd.DataFrame], draws: perm.PermutationDraws
) -> dict[str, pd.DataFrame]:
    merged = {
        "placebo_final": pd.concat(
            [existing.get("placebo_final"), draws.placebo_final], ignore_index=True
        ),
        "placebo_cells": pd.concat(
            [existing.get("placebo_cells"), draws.placebo_cells], ignore_index=True
        ),
        "mapping_digests": pd.concat(
            [existing.get("mapping_digests"), draws.mapping_digests], ignore_index=True
        ),
    }
    for label, frame in merged.items():
        _write_parquet_atomic(frame, store_dir / STORE_NAMES[label])
    return merged


def _load_pairs() -> tuple[pd.DataFrame, dict[str, Any], Any]:
    phase_ii_path = Path(os.getenv(PHASE_II_OUTPUT_ENV) or PHASE_II_AWARDS_PATH)
    try:
        priors = pd.read_parquet(phase_ii_path)
    except OSError as exc:
        raise CensusInputError(f"Phase II prior frame is unreadable at {phase_ii_path}") from exc
    contracts, contracts_path = _load_contracts()
    sbir_awards_path, verified_phase_ii_path = _verify_phase_ii_provenance(priors, contracts_path)
    if verified_phase_ii_path.resolve() != phase_ii_path.resolve():
        raise CensusInputError("loaded Phase II path differs from verified Phase II provenance")
    data_cut = parse_census_data_cut_date()
    validate_source_columns(priors, contracts)
    pairs = build_uei_pairs(priors, contracts, columns=CENSUS_PAIR_COLUMNS)
    inputs = {
        "sbir_awards": {"path": str(sbir_awards_path), "sha256": _file_sha256(sbir_awards_path)},
        "phase_ii": {
            "path": str(phase_ii_path),
            "sha256": _file_sha256(phase_ii_path),
            "rows": len(priors),
        },
        "contracts": {
            "path": str(contracts_path),
            "sha256": _file_sha256(contracts_path),
            "rows": len(contracts),
            "projected_columns": list(CENSUS_CONTRACT_COLUMNS),
        },
        "pair_rows": len(pairs),
    }
    return pairs, inputs, data_cut


def run(
    output_dir: Path,
    *,
    owner_approved: bool = False,
    draws: int = perm.R16_DRAWS,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Execute the R16 design. See the module docstring for the gated sequence.

    ``draws`` must equal the preregistered count for a result to be written; a
    smaller value is refused rather than silently producing a partial result.
    ``batch_size`` bounds how many seeds run in this invocation; the draw store
    is resumable across invocations over the same fixed seed list, and no
    exceedance table or manifest is written until every seed is present.
    """

    if not owner_approved:
        raise CensusInputError(
            "R16 production execution remains blocked: pass owner_approved=True only after "
            "the repository owner separately approves the permutation run"
        )
    if draws != perm.R16_DRAWS:
        raise CensusInputError(
            f"the preregistered design fixes {perm.R16_DRAWS} draws; got {draws}. A different "
            "count is a different design and needs a new amendment."
        )

    freeze = verify_frozen_spec()
    design = verify_validation_design()
    pairs, inputs, data_cut = _load_pairs()
    fingerprint = run_fingerprint(freeze, design, inputs, data_cut)
    output_dir.mkdir(parents=True, exist_ok=True)
    store_dir = output_dir / "draw_store"

    precondition_path = output_dir / PRECONDITION_NAME
    if precondition_path.exists():
        precondition = json.loads(precondition_path.read_text(encoding="utf-8"))
        if not precondition.get("matched_recorded_r15"):
            raise CensusInputError("recorded precondition did not match R15; refusing to resume")
        recorded = precondition.get("run_fingerprint")
        if recorded != fingerprint:
            raise CensusInputError(
                "this run does not match the one the draw store was started under "
                f"(recorded fingerprint {recorded}, current {fingerprint}). The frozen design, "
                "the pinned validation design, the source inputs or the data cut changed; "
                "combining draws across them would report one set of inputs for rows built "
                "from another. Start a new output directory."
            )
    else:
        if store_dir.exists():
            raise CensusInputError(
                f"draw store exists at {store_dir} with no recorded precondition; refusing to "
                "resume draws whose provenance cannot be established"
            )
        precondition = run_equivalence_precondition(pairs, data_cut)
        precondition["run_fingerprint"] = fingerprint
        precondition["validation_design"] = design
        _write_json_atomic(precondition, precondition_path)

    seeds = perm.preregistered_seeds(draws)
    existing = _load_store(store_dir)
    done = complete_seeds(existing)
    if not done <= set(seeds):
        raise CensusInputError("draw store contains seeds outside the preregistered list")
    remaining = [s for s in seeds if s not in done]
    if batch_size is not None:
        remaining = remaining[:batch_size]

    if remaining:
        new = perm.run_permutation_draws(pairs, data_cut, remaining)
        existing = _append_store(store_dir, existing, new)
        done |= set(remaining)

    status: dict[str, Any] = {
        "schema_version": "phase-iii-permutation-separation-v1",
        "design_revision": "phase-0-r16",
        "freeze": freeze,
        "validation_design": design,
        "run_fingerprint": fingerprint,
        "data_cut_date": data_cut.isoformat(),
        "inputs": inputs,
        "precondition": precondition,
        "preregistered_draws": draws,
        "first_seed": seeds[0],
        "last_seed": seeds[-1],
        "draws_complete": len(done),
        "complete": len(done) == draws,
        "owner_approval_asserted_at_invocation": True,
        "first_production_run_requires_separate_owner_approval": True,
    }
    if not status["complete"]:
        status["result"] = None
        status["note"] = (
            "partial draw store; no exceedance table or result is written until every seed is present"
        )
        return status

    require_complete_store(existing, seeds)
    final = existing["placebo_final"].sort_values("seed", kind="stable").reset_index(drop=True)
    cells = (
        existing["placebo_cells"]
        .sort_values(["seed", "cell_id"], kind="stable")
        .reset_index(drop=True)
    )
    digests = existing["mapping_digests"].sort_values("seed", kind="stable").reset_index(drop=True)
    if digests["mapping_sha256"].nunique() != draws:
        raise CensusInputError(
            "two preregistered seeds produced the same assignment; refusing to summarise"
        )
    actual = perm.run_permutation_draws(pairs, data_cut, [])
    complete = perm.PermutationDraws(
        actual_final=actual.actual_final,
        actual_cells=actual.actual_cells,
        placebo_final=final,
        placebo_cells=cells,
        mapping_digests=digests,
    )
    table = perm.exceedance_table(complete)

    frames = {
        "actual_final": complete.actual_final,
        "actual_cells": complete.actual_cells,
        "placebo_final": final,
        "placebo_cells": cells,
        "mapping_digests": digests,
        "exceedance": table,
    }
    artifacts: dict[str, Any] = {}
    for label, frame in frames.items():
        path = output_dir / OUTPUT_NAMES[label]
        _write_parquet_atomic(frame, path)
        artifacts[label] = {"path": str(path), "sha256": _file_sha256(path), "rows": len(frame)}

    primary = table.loc[table["primary"]].iloc[0]
    status["artifacts"] = artifacts
    status["result"] = {
        "metric": f"{perm.R16_PRIMARY_METRIC}@{perm.R16_FINAL_CLAUSE_ID}",
        "numerator": int(primary["exceeded"]),
        "denominator": int(primary["draws"]),
        "tied": int(primary["tied"]),
        "interval_low": float(primary["interval_low"]),
        "interval_high": float(primary["interval_high"]),
        "interval_method": str(primary["interval_method"]),
        "threshold_rule": f"wilson lower bound >= {perm.R16_THRESHOLD_LOWER_BOUND}",
        "threshold_met": bool(primary["threshold_met"]),
    }
    _write_json_atomic(status, output_dir / MANIFEST_NAME)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Do not invoke for production until the repository owner approves the R16 run.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/phase_iii_permutation")
    )
    parser.add_argument(
        "--owner-approved",
        action="store_true",
        help="Assert that the repository owner separately approved the R16 production run.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Run at most this many remaining seeds now; the draw store resumes on the next call.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.output_dir, owner_approved=args.owner_approved, batch_size=args.batch_size),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
