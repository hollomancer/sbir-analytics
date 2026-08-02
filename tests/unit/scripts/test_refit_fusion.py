"""Offline tests for the fusion refit feature builder and ladder wiring."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_benchmark.refit_fusion import LADDER, build_features, run_ladder


pytestmark = pytest.mark.fast


def _corpus() -> pd.DataFrame:
    rows = []
    for firm in range(6):
        # One true notice (on-topic text) + two same-office negatives (off-topic).
        rows.append(
            {
                "name_key": f"FIRM{firm}",
                "owner": f"FIRM{firm}:n{firm}",
                "query_abstract": "hypersonic scramjet thermal protection ceramic liner",
                "notice_text": "hypersonic scramjet thermal protection demonstration ceramic",
                "notice_type": "Justification",
                "posted_date": "2022-05-01",
                "naics_code": "541715",
                "match_rule": "piid_cite" if firm == 0 else "name_in_desc",
                "label": 1,
            }
        )
        for _neg in range(2):
            rows.append(
                {
                    "name_key": f"FIRM{firm}",
                    "owner": f"FIRM{firm}:n{firm}",
                    "query_abstract": "hypersonic scramjet thermal protection ceramic liner",
                    "notice_text": "office furniture and janitorial services procurement",
                    "notice_type": "Award Notice",
                    "posted_date": "2022-06-01",
                    "naics_code": "337214",
                    "match_rule": "name_in_desc",
                    "label": 0,
                }
            )
    return pd.DataFrame(rows)


def test_build_features_produces_ladder_columns():
    features = build_features(_corpus())
    for _stage, columns in LADDER:
        for column in columns:
            assert column in features.columns
    # On-topic true rows score higher word-similarity than off-topic negatives.
    corpus = _corpus()
    positives = features.loc[corpus["label"] == 1, "tfidf_word"]
    negatives = features.loc[corpus["label"] == 0, "tfidf_word"]
    assert positives.mean() > negatives.mean()
    # id_cited fires only on the piid_cite row.
    assert features["id_cited"].sum() == 1.0


def test_run_ladder_returns_a_stage_per_rung_with_separable_signal():
    ladder = run_ladder(_corpus())
    assert [stage["stage"] for stage in ladder] == [name for name, _ in LADDER]
    # The synthetic corpus is cleanly separable, so AUC should be high.
    assert ladder[-1]["auc"] >= 0.8
