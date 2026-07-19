"""Fixtures for award identity, list strata, and capture sensitivity."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_benchmark.capture_sensitivity import capture_sensitivity
from scripts.phase3_benchmark.undercount_award_grain import (
    authoritative_coded_keys,
    reconstruct_coded_award_key,
    undercount,
)


def _coded() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order_piid": "P1",
                "order_agency": "9700",
                "idv_piid": "",
                "idv_agency": "",
                "contract_award_unique_key": "CONT_AWD_P1_9700_-NONE-_-NONE-",
                "research": "SR3",
            },
            {
                "order_piid": "P2",
                "order_agency": "9700",
                "idv_piid": "IDV1",
                "idv_agency": "9700",
                "contract_award_unique_key": "CONT_AWD_P2_9700_IDV1_9700",
                "research": "ST3",
            },
        ]
    )


def _described() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "generated_internal_id": "CONT_AWD_P1_9700_-NONE-_-NONE-",
                "description_signal": "SBIR",
                "award_type_group": "contract",
            },
            {
                "generated_internal_id": "CONT_AWD_P3_9700_-NONE-_-NONE-",
                "description_signal": "SBIR",
                "award_type_group": "contract",
            },
            {
                "generated_internal_id": "CONT_AWD_P2_9700_IDV1_9700",
                "description_signal": "STTR",
                "award_type_group": "contract",
            },
            {
                "generated_internal_id": "CONT_IDV_V1_9700_-NONE-_-NONE-",
                "description_signal": "SBIR",
                "award_type_group": "idv",
            },
        ]
    )


def test_native_key_is_authoritative_and_reconstruction_is_validation_only() -> None:
    assert list(authoritative_coded_keys(_coded())) == [
        "CONT_AWD_P1_9700_-NONE-_-NONE-",
        "CONT_AWD_P2_9700_IDV1_9700",
    ]
    assert reconstruct_coded_award_key(_coded()).iloc[0].startswith("CONT_AWD_P1")
    broken = _coded()
    broken.loc[0, "contract_award_unique_key"] = "CONT_AWD_WRONG"
    with pytest.raises(ValueError, match="disagreement"):
        authoritative_coded_keys(broken)


def test_undercount_emits_program_strata_and_excludes_idvs() -> None:
    result = undercount(_coded(), _described())
    assert result["strata"]["SBIR"]["description_only_flags"] == 1
    assert result["strata"]["STTR"]["description_only_flags"] == 0
    assert result["combined"]["description_only_flags"] == 1
    assert result["idv_rows_excluded"] == 1


def test_capture_sensitivity_reproduces_chapman_and_or_grid() -> None:
    result = capture_sensitivity(5530, 141, 821)
    assert result["chapman_or1_scenario"]["dark"] == pytest.approx(948.5766423)
    dark = [row["dark"] for row in result["odds_ratio_sensitivity"]]
    assert dark == pytest.approx([474.866, 949.732, 1899.464, 4748.660], rel=1e-5)
    fp = result["description_false_positive_sensitivity"]
    assert fp[2]["chapman_or1_dark"] < fp[0]["chapman_or1_dark"]
