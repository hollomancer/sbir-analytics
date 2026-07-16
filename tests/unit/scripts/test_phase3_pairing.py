"""Tests for Phase III benchmark pairing and scoring."""

import json

import pandas as pd

from scripts.phase3_benchmark.build_pairs_and_score import (
    PROXY_LABEL,
    build_benchmark_pairs,
    evaluate_scores,
    run,
    score_pairs,
)


def _phase_ii() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "A-OLD",
                "recipient_uei": "UEI-A",
                "company_name": "Alpha",
                "abstract": "autonomous navigation sensor fusion",
                "award_date": "2020-01-01",
            },
            {
                "award_id": "A-FUTURE",
                "recipient_uei": "UEI-A",
                "company_name": "Alpha",
                "abstract": "future unrelated award",
                "award_date": "2025-01-01",
            },
            {
                "award_id": "B-OLD",
                "recipient_uei": "UEI-B",
                "company_name": "Beta",
                "abstract": "advanced turbine coating",
                "award_date": "2021-01-01",
            },
        ]
    )


def _phase_iii() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PIID": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W1",
                "UEI": "UEI-A",
                "contractingOfficeID": "OFFICE-1",
                "descriptionOfContractRequirement": "navigation sensor fusion production",
                "signedDate": "2023-01-01",
            },
            {
                "PIID": "0001",
                "agencyID": "2100",
                "referenced_idv_piid": "W1",
                "UEI": "UEI-A",
                "contractingOfficeID": "OFFICE-1",
                "descriptionOfContractRequirement": "navigation sensor fusion production update",
                "signedDate": "2024-01-01",
            },
            {
                "PIID": "0002",
                "agencyID": "2100",
                "referenced_idv_piid": "W2",
                "UEI": "UEI-B",
                "contractingOfficeID": "OFFICE-1",
                "descriptionOfContractRequirement": "turbine coating production",
                "signedDate": "2024-02-01",
            },
        ]
    )


def test_pairs_collapse_transactions_and_never_select_future_phase_ii():
    pairs = build_benchmark_pairs(_phase_ii(), _phase_iii(), seed=7)
    positives = pairs.loc[pairs["stratum"].eq("P1")]

    assert len(positives) == 2
    alpha = positives.loc[positives["phase_iii_uei"].eq("UEI-A")].iloc[0]
    assert alpha["phase_ii_award_id"] == "A-OLD"
    assert alpha["phase_iii_date"] == pd.Timestamp("2024-01-01", tz="UTC")
    assert (positives["phase_ii_date"] <= positives["phase_iii_date"]).all()
    assert positives["label_semantics"].eq(PROXY_LABEL).all()


def test_pairing_and_metrics_are_deterministic():
    first = score_pairs(build_benchmark_pairs(_phase_ii(), _phase_iii(), seed=9))
    second = score_pairs(build_benchmark_pairs(_phase_ii(), _phase_iii(), seed=9))

    pd.testing.assert_frame_equal(first, second)
    first_metrics = evaluate_scores(first, seed=9, bootstrap_samples=20)
    second_metrics = evaluate_scores(second, seed=9, bootstrap_samples=20)
    assert first_metrics == second_metrics
    assert first_metrics["positive_pairs"] == 2
    assert first_metrics["negative_pairs"] == 2


def test_run_writes_pairs_and_metrics(tmp_path):
    phase_ii_path = tmp_path / "phase_ii.csv"
    phase_iii_path = tmp_path / "phase_iii.parquet"
    pairs_path = tmp_path / "pairs.parquet"
    metrics_path = tmp_path / "metrics.json"
    _phase_ii().to_csv(phase_ii_path, index=False)
    _phase_iii().to_parquet(phase_iii_path, index=False)

    result = run(
        phase_ii_path=phase_ii_path,
        phase_iii_path=phase_iii_path,
        pairs_output=pairs_path,
        metrics_output=metrics_path,
        seed=3,
        bootstrap_samples=10,
    )

    assert pairs_path.exists()
    assert json.loads(metrics_path.read_text()) == result
