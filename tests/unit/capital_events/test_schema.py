"""Schema sanity tests."""

from sbir_etl.capital_events.schema import (
    EVENT_TABLE_COLUMNS,
    CapitalEvent,
    EventType,
)


def test_event_type_values():
    assert EventType.SBIR_AWARD.value == "sbir_award"
    assert EventType.FORM_D_FILING.value == "form_d_filing"
    assert EventType.MA_EVENT.value == "ma_event"
    assert EventType.USASPENDING_CONTRACT.value == "usaspending_contract"
    assert EventType.PATENT_GRANT.value == "patent_grant"
    assert EventType.UCC_FILING.value == "ucc_filing"


def test_event_table_columns_match_typeddict():
    expected = {
        "company_name",
        "event_date",
        "event_type",
        "event_subtype",
        "amount_usd",
        "counterparty",
        "source_id",
        "metadata",
    }
    assert set(EVENT_TABLE_COLUMNS) == expected
    assert EVENT_TABLE_COLUMNS[0] == "company_name"
    assert EVENT_TABLE_COLUMNS[1] == "event_date"
    assert EVENT_TABLE_COLUMNS[2] == "event_type"


def test_capital_event_can_round_trip_as_json():
    import json

    row: CapitalEvent = {
        "company_name": "Acme Inc",
        "event_date": "2024-03-15",
        "event_type": EventType.SBIR_AWARD.value,
        "event_subtype": "sbir_phase_ii",
        "amount_usd": 750000.0,
        "counterparty": "Department of Defense",
        "source_id": "DE-AR0001984",
        "metadata": json.dumps({"branch": "Army", "solicitation_year": 2024}),
    }
    parsed = json.loads(json.dumps(row))
    assert parsed["amount_usd"] == 750000.0
    assert parsed["event_type"] == "sbir_award"
