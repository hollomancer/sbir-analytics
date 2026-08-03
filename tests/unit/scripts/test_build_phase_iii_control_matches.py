"""Tests for the pre-outcome control-matching materializer."""

import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_phase_iii_control_matches.py"
SPEC = importlib.util.spec_from_file_location("build_phase_iii_control_matches", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _contract(
    uei: str,
    date: str,
    *,
    psc: str,
    research: str | None,
    categories: str,
) -> dict[str, object]:
    return {
        "contract_id": f"{uei}-{date}-{psc}",
        "piid": "PIID",
        "transaction_unique_id": f"TX-{uei}-{date}-{psc}",
        "generated_unique_award_id": f"AW-{uei}",
        "agency": "Agency",
        "sub_agency": "Subagency",
        "vendor_name": "Firm",
        "vendor_uei": uei,
        "vendor_cage": None,
        "vendor_duns": None,
        "action_date": date,
        "start_date": date,
        "end_date": None,
        "obligation_amount": 1.0,
        "is_deobligation": False,
        "competition_type": "other",
        "description": "not read",
        "parent_contract_id": None,
        "parent_contract_agency": None,
        "contract_award_type": "A",
        "research": research,
        "naics_code": "541715",
        "product_or_service_code": psc,
        "matched_vendor": None,
        "metadata": {
            "business_categories": categories,
            "recipient_state": "VA",
        },
    }


def test_loader_exposes_only_earliest_rows_but_screens_codes_across_history(tmp_path: Path) -> None:
    path = tmp_path / "contracts.parquet"
    pd.DataFrame(
        [
            _contract(
                "CONTROLUEI01",
                "2010-01-01",
                psc="A123",
                research=None,
                categories="{small_business}",
            ),
            _contract(
                "CONTROLUEI01",
                "2015-01-01",
                psc="R425",
                research="SR2",
                categories="{manufacturer_of_goods}",
            ),
            _contract(
                "CONTROLUEI02",
                "2012-02-02",
                psc="R425",
                research="RD",
                categories="{small_business}",
            ),
        ]
    ).to_parquet(path, index=False)

    earliest, coded = module._load_pre_outcome_contract_rows(path)

    assert earliest[["vendor_uei", "action_date", "product_or_service_code"]].to_dict(
        orient="records"
    ) == [
        {
            "vendor_uei": "CONTROLUEI01",
            "action_date": pd.Timestamp("2010-01-01"),
            "product_or_service_code": "A123",
        },
        {
            "vendor_uei": "CONTROLUEI02",
            "action_date": pd.Timestamp("2012-02-02"),
            "product_or_service_code": "R425",
        },
    ]
    assert coded.to_dict(orient="records") == [{"vendor_uei": "CONTROLUEI01", "research": "SR2"}]
