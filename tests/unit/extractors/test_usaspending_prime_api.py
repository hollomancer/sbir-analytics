from datetime import date

import pandas as pd
import pytest

from sbir_etl.extractors.usaspending_prime_api import (
    fetch_usaspending_prime_snapshot,
    load_usaspending_prime_snapshot,
)


class FakeUSAspendingClient:
    def __init__(self) -> None:
        self.search_calls = 0
        self.transaction_calls = 0
        self.agency_calls = 0

    async def get_toptier_agencies(self):
        self.agency_calls += 1
        return {
            "results": [
                {
                    "agency_id": 1173,
                    "toptier_code": "097",
                    "agency_name": "Department of Defense",
                    "abbreviation": "DOD",
                    "agency_slug": "department-of-defense",
                },
            ]
        }

    async def search_awards(self, *, filters, fields, page, limit, sort, order):
        self.search_calls += 1
        assert fields and page == 1 and limit == 100 and sort == "Award ID" and order == "asc"
        is_contract = filters["award_type_codes"] == ["A", "B", "C", "D"]
        is_awarding = filters["agencies"][0]["type"] == "awarding"
        results = []
        if is_contract and is_awarding:
            results = [
                {
                    "generated_internal_id": "CONT_AWD_FAKE_9700",
                    "Award ID": "FAKE-001",
                    "Recipient Name": "Example Materials Inc",
                    "Recipient UEI": "ABCDEFGHIJKL",
                    "Award Amount": 50.0,
                    "Start Date": "2025-01-01",
                    "End Date": "2026-12-31",
                    "Awarding Agency": "Department of Defense",
                    "awarding_agency_id": 1173,
                    "Awarding Sub Agency": "Department of the Air Force",
                    "Funding Agency": "Department of Defense",
                    "Funding Sub Agency": "Department of the Air Force",
                    "Description": "Test procurement",
                    "naics_code": "541715",
                    "product_or_service_code": "AC13",
                },
                {
                    "generated_internal_id": "CONT_AWD_FALSE_MATCH",
                    "Award ID": "FALSE",
                    "Recipient Name": "Substring false match",
                    "Recipient UEI": "ZZZZZZZZZZZZ",
                },
            ]
        return {"results": results, "page_metadata": {"hasNext": False}}

    async def get_award_transactions(self, generated_award_id, *, page, limit):
        self.transaction_calls += 1
        assert generated_award_id == "CONT_AWD_FAKE_9700"
        assert page == 1 and limit == 5000
        return {
            "results": [
                {
                    "id": "CONT_TX_BEFORE_WINDOW",
                    "type": "D",
                    "type_description": "DEFINITIVE CONTRACT",
                    "action_date": "2006-09-30",
                    "action_type": "A",
                    "action_type_description": "NEW",
                    "modification_number": "EARLY",
                    "description": "Predates searchable window",
                    "federal_action_obligation": 999.0,
                },
                {
                    "id": "CONT_TX_1",
                    "type": "D",
                    "type_description": "DEFINITIVE CONTRACT",
                    "action_date": "2025-09-30",
                    "action_type": "A",
                    "action_type_description": "NEW",
                    "modification_number": "0",
                    "description": "Initial action",
                    "federal_action_obligation": 100.0,
                },
                {
                    "id": "CONT_TX_2",
                    "type": "D",
                    "type_description": "DEFINITIVE CONTRACT",
                    "action_date": "2025-10-01",
                    "action_type": "M",
                    "action_type_description": "DEOBLIGATION",
                    "modification_number": "P00001",
                    "description": "Signed correction",
                    "federal_action_obligation": -50.0,
                },
            ],
            "page_metadata": {"hasNext": False},
        }


def _awardees() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
            }
        ]
    )


@pytest.mark.asyncio
async def test_snapshot_preserves_signed_transactions_and_exact_uei_match(tmp_path) -> None:
    client = FakeUSAspendingClient()
    snapshot = tmp_path / "prime"

    manifest = await fetch_usaspending_prime_snapshot(
        _awardees(),
        snapshot,
        end_date=date(2026, 8, 3),
        client=client,  # type: ignore[arg-type]
        max_concurrency=2,
    )
    frame = load_usaspending_prime_snapshot(snapshot)

    assert manifest["matched_prime_award_count"] == 1
    assert manifest["source_transaction_count"] == 3
    assert manifest["prime_transaction_count"] == 2
    assert manifest["out_of_window_transaction_count"] == 1
    assert manifest["negative_transaction_count"] == 1
    assert client.search_calls == 8
    assert client.transaction_calls == 1
    assert frame["prime_transaction_id"].is_unique
    assert frame["signed_obligation_amount"].sum() == 50.0
    assert frame["is_deobligation"].sum() == 1
    assert set(frame["fiscal_year"]) == {2025, 2026}
    assert frame["recipient_match_method"].eq("exact_uei").all()
    assert frame["dod_toptier_cgac_code"].eq("097").all()
    assert not frame["dod_award_id"].eq("FALSE").any()

    await fetch_usaspending_prime_snapshot(
        _awardees(),
        snapshot,
        end_date=date(2026, 8, 3),
        client=client,  # type: ignore[arg-type]
        max_concurrency=2,
    )
    assert client.search_calls == 8
    assert client.transaction_calls == 1


@pytest.mark.asyncio
async def test_recipient_identity_conflicts_fail_closed(tmp_path) -> None:
    awardees = pd.DataFrame(
        [
            {"nsf_organization_id": "uei:ONE", "nsf_awardee_uei": "ABCDEFGHIJKL"},
            {"nsf_organization_id": "uei:TWO", "nsf_awardee_uei": "ABCDEFGHIJKL"},
        ]
    )
    with pytest.raises(ValueError, match="multiple NSF organization"):
        await fetch_usaspending_prime_snapshot(
            awardees,
            tmp_path / "prime",
            end_date=date(2026, 8, 3),
            client=FakeUSAspendingClient(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_loader_rejects_snapshot_corruption(tmp_path) -> None:
    snapshot = tmp_path / "prime"
    await fetch_usaspending_prime_snapshot(
        _awardees(),
        snapshot,
        end_date=date(2026, 8, 3),
        client=FakeUSAspendingClient(),  # type: ignore[arg-type]
    )
    (snapshot / "prime_transaction_index.json").write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_usaspending_prime_snapshot(snapshot)
