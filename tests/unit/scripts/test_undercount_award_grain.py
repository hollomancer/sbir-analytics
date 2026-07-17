"""Fixture test for the award-grain Phase III undercount (PR #449 identity contract).

Proves, on a self-contained synthetic frame, that the undercount is computed at AWARD grain through
``award_key_series`` — transaction/modification rows collapse, standalone contracts (no parent IDV)
are handled, and the described-but-not-coded set is exact.
"""

from __future__ import annotations

import pandas as pd

from scripts.phase3_benchmark.undercount_award_grain import (
    reconstruct_coded_award_key,
    undercount,
)


def _coded() -> pd.DataFrame:
    # A = standalone (no IDV); B = order under a parent IDV; A appears twice (transaction rows).
    return pd.DataFrame(
        [
            {"order_piid": "P1", "order_agency": "9700", "idv_piid": "", "idv_agency": ""},
            {"order_piid": "P1", "order_agency": "9700", "idv_piid": "", "idv_agency": ""},  # mod
            {"order_piid": "P2", "order_agency": "9700", "idv_piid": "IDV1", "idv_agency": "9700"},
        ]
    )


def _described() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "generated_internal_id": [
                "CONT_AWD_P1_9700_-NONE-_-NONE-",  # matches coded A  -> coded
                "CONT_AWD_P2_9700_IDV1_9700",       # matches coded B  -> coded
                "CONT_AWD_P3_9700_-NONE-_-NONE-",  # not coded        -> UNDERCOUNT
            ]
        }
    )


def test_reconstructed_coded_key_uses_none_sentinel_for_standalone() -> None:
    keys = reconstruct_coded_award_key(_coded())
    assert keys.iloc[0] == "CONT_AWD_P1_9700_-NONE-_-NONE-"
    assert keys.iloc[2] == "CONT_AWD_P2_9700_IDV1_9700"


def test_undercount_is_award_grain_and_exact() -> None:
    stats = undercount(_coded(), _described())
    assert stats["coded_transactions"] == 3      # includes the duplicate modification row
    assert stats["coded_awards"] == 2            # collapsed to award grain
    assert stats["described_awards"] == 3
    assert stats["described_coded_overlap"] == 2  # A and B join across the two sources
    assert stats["undercount"] == 1               # only P3 is described-but-not-coded
