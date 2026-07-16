"""Build a research-only Phase III match benchmark and lexical baseline."""

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from sbir_etl.utils.award_identity import award_key_series, collapse_transactions_to_award_grain


STOP_WORDS = frozenset(
    "the a an of and or for to in on with by from is are this that be as at using use used "
    "system systems method methods technology development program phase sbir sttr research "
    "small business innovation".split()
)
PROXY_LABEL = "same-firm proxy positive; derivation is not independently verified"
NEGATIVE_LABEL = "different-firm same-office hard negative"


def _column(frame: pd.DataFrame, *names: str, required: bool = True) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    if required:
        raise ValueError(f"missing required column; need one of {names}")
    return pd.Series([None] * len(frame), index=frame.index)


def _normalize(value: object) -> str:
    if value is None or value is pd.NA:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "NAN", "NAT", "NONE", "<NA>"} else text


def _phase_ii_dates(frame: pd.DataFrame) -> pd.Series:
    exact_names = (
        "award_date",
        "Award Date",
        "award_start_date",
        "Award Start Date",
        "Proposal Award Date",
    )
    exact = next((name for name in exact_names if name in frame.columns), None)
    dates = (
        pd.to_datetime(frame[exact], errors="coerce", utc=True)
        if exact
        else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    )
    year_name = next((name for name in ("award_year", "Award Year") if name in frame), None)
    if year_name:
        # A year-only record is conservatively available at year end, preventing
        # same-year awards after the target from leaking into the benchmark.
        year_end = pd.to_datetime(
            frame[year_name].map(lambda value: f"{_normalize(value)}-12-31"),
            errors="coerce",
            utc=True,
        )
        dates = dates.fillna(year_end)
    return dates


def _prepare_phase_ii(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = pd.DataFrame(
        {
            "phase_ii_award_id": _column(frame, "award_id", "Award ID", "Agency Tracking Number"),
            "uei": _column(frame, "recipient_uei", "UEI"),
            "company": _column(frame, "company_name", "Company", required=False),
            "abstract": _column(frame, "abstract", "Abstract"),
            "phase_ii_date": _phase_ii_dates(frame),
        }
    )
    prepared["uei"] = prepared["uei"].map(_normalize).str.upper()
    prepared["abstract"] = prepared["abstract"].map(_normalize)
    prepared = prepared.loc[
        prepared["uei"].ne("") & prepared["abstract"].ne("") & prepared["phase_ii_date"].notna()
    ].copy()
    return prepared.sort_values("phase_ii_date", kind="mergesort")


def _prepare_phase_iii(frame: pd.DataFrame) -> pd.DataFrame:
    keys = award_key_series(frame)
    collapsed = collapse_transactions_to_award_grain(frame, award_keys=keys)
    prepared = pd.DataFrame(
        {
            "phase_iii_award_key": collapsed["_award_key"],
            "uei": _column(collapsed, "UEI", "recipient_uei", "vendor_uei"),
            "vendor": _column(collapsed, "vendorName", "recipient_name", required=False),
            "office": _column(
                collapsed,
                "contractingOfficeID",
                "awarding_office_code",
                "awarding_office_name",
            ),
            "description": _column(
                collapsed,
                "descriptionOfContractRequirement",
                "transaction_description",
                "description",
            ),
            "phase_iii_date": pd.to_datetime(
                _column(collapsed, "signedDate", "action_date", "award_date"),
                errors="coerce",
                utc=True,
            ),
            "piid": _column(collapsed, "PIID", "piid", required=False),
        }
    )
    prepared["uei"] = prepared["uei"].map(_normalize).str.upper()
    prepared["office"] = prepared["office"].map(_normalize).str.upper()
    prepared["description"] = prepared["description"].map(_normalize)
    missing_date = prepared["phase_iii_date"].isna()
    if missing_date.any():
        raise ValueError(
            f"Phase III rows lack an action date at rows {list(prepared.index[missing_date])[:5]}"
        )
    return prepared.loc[
        prepared["uei"].ne("") & prepared["office"].ne("") & prepared["description"].ne("")
    ].copy()


def _latest_prior(group: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series | None:
    eligible = group.loc[group["phase_ii_date"] <= as_of]
    return None if eligible.empty else eligible.iloc[-1]


def build_benchmark_pairs(
    phase_ii: pd.DataFrame,
    phase_iii: pd.DataFrame,
    *,
    seed: int = 20260708,
) -> pd.DataFrame:
    """Build same-firm proxy positives and deterministic same-office negatives."""

    priors = _prepare_phase_ii(phase_ii)
    targets = _prepare_phase_iii(phase_iii)
    prior_groups = dict(iter(priors.groupby("uei", sort=False)))

    positives: list[dict[str, object]] = []
    for target in targets.sort_values("phase_iii_award_key").itertuples(index=False):
        group = prior_groups.get(target.uei)
        prior = (
            None
            if group is None
            else _latest_prior(group, cast(pd.Timestamp, target.phase_iii_date))
        )
        if prior is None:
            continue
        positives.append(
            {
                "pair_id": f"{target.phase_iii_award_key}|P1",
                "stratum": "P1",
                "label": 1,
                "label_semantics": PROXY_LABEL,
                "phase_iii_award_key": target.phase_iii_award_key,
                "phase_iii_uei": target.uei,
                "phase_ii_uei": prior["uei"],
                "office": target.office,
                "phase_ii_award_id": prior["phase_ii_award_id"],
                "phase_ii_date": prior["phase_ii_date"],
                "phase_iii_date": target.phase_iii_date,
                "abstract": prior["abstract"],
                "description": target.description,
                "piid": target.piid,
            }
        )

    positive_frame = pd.DataFrame(positives)
    if positive_frame.empty:
        return positive_frame

    firms_by_office = {
        office: sorted(group["phase_iii_uei"].unique())
        for office, group in positive_frame.groupby("office", sort=False)
    }
    rng = np.random.default_rng(seed)
    negatives: list[dict[str, object]] = []
    for positive in positive_frame.itertuples(index=False):
        other_firms = [
            uei for uei in firms_by_office[positive.office] if uei != positive.phase_iii_uei
        ]
        if not other_firms:
            continue
        other_uei = other_firms[int(rng.integers(len(other_firms)))]
        prior = _latest_prior(
            prior_groups[other_uei],
            cast(pd.Timestamp, positive.phase_iii_date),
        )
        if prior is None:
            continue
        negatives.append(
            {
                "pair_id": f"{positive.phase_iii_award_key}|N1",
                "stratum": "N1",
                "label": 0,
                "label_semantics": NEGATIVE_LABEL,
                "phase_iii_award_key": positive.phase_iii_award_key,
                "phase_iii_uei": positive.phase_iii_uei,
                "phase_ii_uei": prior["uei"],
                "office": positive.office,
                "phase_ii_award_id": prior["phase_ii_award_id"],
                "phase_ii_date": prior["phase_ii_date"],
                "phase_iii_date": positive.phase_iii_date,
                "abstract": prior["abstract"],
                "description": positive.description,
                "piid": positive.piid,
            }
        )
    return pd.concat([positive_frame, pd.DataFrame(negatives)], ignore_index=True)


def tokens(text: object) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", _normalize(text).lower())
        if len(word) > 2 and word not in STOP_WORDS
    }


def jaccard(left: object, right: object) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def score_pairs(pairs: pd.DataFrame) -> pd.DataFrame:
    scored = pairs.copy()
    scored["lexical_jaccard"] = [
        jaccard(row.abstract, row.description) for row in scored.itertuples(index=False)
    ]
    return scored


def auc_mann_whitney(positive: np.ndarray, negative: np.ndarray) -> float:
    if not len(positive) or not len(negative):
        raise ValueError("AUC requires at least one positive and one negative")
    values = np.concatenate([positive, negative])
    ranks = pd.Series(values).rank(method="average").to_numpy()
    positive_rank_sum = float(ranks[: len(positive)].sum())
    numerator = positive_rank_sum - len(positive) * (len(positive) + 1) / 2
    return numerator / (len(positive) * len(negative))


def evaluate_scores(
    scored: pd.DataFrame,
    *,
    seed: int = 20260708,
    bootstrap_samples: int = 1000,
) -> dict[str, object]:
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be at least 1")
    positive = scored.loc[scored["label"].eq(1), "lexical_jaccard"].to_numpy(float)
    negative = scored.loc[scored["label"].eq(0), "lexical_jaccard"].to_numpy(float)
    auc = auc_mann_whitney(positive, negative)
    rng = np.random.default_rng(seed)
    samples = np.array(
        [
            auc_mann_whitney(
                rng.choice(positive, len(positive), replace=True),
                rng.choice(negative, len(negative), replace=True),
            )
            for _ in range(bootstrap_samples)
        ]
    )
    low, high = np.percentile(samples, [2.5, 97.5])
    return {
        "label_warning": PROXY_LABEL,
        "positive_pairs": int(len(positive)),
        "negative_pairs": int(len(negative)),
        "lexical_auc": float(auc),
        "lexical_auc_95pct_ci": [float(low), float(high)],
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
    }


def _read_frame(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def run(
    *,
    phase_ii_path: Path,
    phase_iii_path: Path,
    pairs_output: Path,
    metrics_output: Path,
    seed: int,
    bootstrap_samples: int,
) -> dict[str, object]:
    pairs = build_benchmark_pairs(
        _read_frame(phase_ii_path),
        _read_frame(phase_iii_path),
        seed=seed,
    )
    scored = score_pairs(pairs)
    metrics = evaluate_scores(scored, seed=seed, bootstrap_samples=bootstrap_samples)
    _write_frame(scored, pairs_output)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-ii", type=Path, required=True)
    parser.add_argument("--phase-iii", type=Path, required=True)
    parser.add_argument("--pairs-out", type=Path, required=True)
    parser.add_argument("--metrics-out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260708)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(
        phase_ii_path=args.phase_ii,
        phase_iii_path=args.phase_iii,
        pairs_output=args.pairs_out,
        metrics_output=args.metrics_out,
        seed=args.seed,
        bootstrap_samples=args.bootstrap_samples,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
