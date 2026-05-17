"""Tests for CA bizfileOnline UCC extractor."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc.ca_extractor import (  # noqa: E402
    build_filings_from_history,
    extract_for_debtor,
)


def test_build_filings_from_history_groups_lifecycle():
    """Inhibrx Phase 0 case: initial Lien Financing Stmt + Termination."""
    detail = {
        "RECORD_NUM": "197728978614",
        "DEBTOR_NAME": "INHIBRX, INC.",
        "DEBTOR_ADDRESS": "11025 N TORREY PINES RD STE 200, LA JOLLA, CA  920371030",
        "SEC_PARTY_NAME": "EMPLOYMENT DEVELOPMENT DEPARTMENT",
        "SEC_PARTY_ADDRESS": "722 CAPITOL MALL, SACRAMENTO, CA  95814",
        "STATUS": "Active",
        "LAPSE_DATE": "08/20/2029",
    }
    history = [
        {
            "AMENDMENT_TYPE": "Lien Financing Stmt",
            "AMENDMENT_NUM": "197728978614",
            "AMENDMENT_DATE": "8/20/2019",
        },
        {
            "AMENDMENT_TYPE": "Termination",
            "AMENDMENT_NUM": "1977361234",
            "AMENDMENT_DATE": "9/23/2019",
        },
    ]
    rows = build_filings_from_history(detail, history)
    assert len(rows) == 2
    initial = next(r for r in rows if r["filing_type"] == "initial")
    termination = next(r for r in rows if r["filing_type"] == "termination")
    assert initial["filing_number"] == "197728978614"
    assert initial["parent_filing_number"] is None
    assert initial["debtor_name"] == "INHIBRX, INC."
    assert initial["filing_date"] == "2019-08-20"
    assert initial["lapse_date"] == "2029-08-20"
    assert termination["filing_number"] == "1977361234"
    assert termination["parent_filing_number"] == "197728978614"
    assert termination["filing_date"] == "2019-09-23"
    assert termination["source"] == "CA"


def test_build_filings_handles_all_filing_types():
    detail = {
        "RECORD_NUM": "INIT-1",
        "DEBTOR_NAME": "X",
        "DEBTOR_ADDRESS": "",
        "SEC_PARTY_NAME": "Y",
        "SEC_PARTY_ADDRESS": "",
        "STATUS": "Active",
        "LAPSE_DATE": None,
    }
    history = [
        {
            "AMENDMENT_TYPE": "Lien Financing Stmt",
            "AMENDMENT_NUM": "INIT-1",
            "AMENDMENT_DATE": "1/1/2020",
        },
        {"AMENDMENT_TYPE": "Amendment", "AMENDMENT_NUM": "AM-1", "AMENDMENT_DATE": "1/1/2021"},
        {"AMENDMENT_TYPE": "Continuation", "AMENDMENT_NUM": "CN-1", "AMENDMENT_DATE": "12/1/2024"},
        {"AMENDMENT_TYPE": "Assignment", "AMENDMENT_NUM": "AS-1", "AMENDMENT_DATE": "2/1/2025"},
        {"AMENDMENT_TYPE": "Termination", "AMENDMENT_NUM": "TM-1", "AMENDMENT_DATE": "1/1/2026"},
    ]
    rows = build_filings_from_history(detail, history)
    types = sorted(r["filing_type"] for r in rows)
    assert types == ["amendment", "assignment", "continuation", "initial", "termination"]


def test_build_filings_skips_unknown_amendment_types():
    detail = {
        "RECORD_NUM": "X",
        "DEBTOR_NAME": "X",
        "DEBTOR_ADDRESS": "",
        "SEC_PARTY_NAME": "Y",
        "SEC_PARTY_ADDRESS": "",
        "STATUS": "",
        "LAPSE_DATE": None,
    }
    history = [
        {
            "AMENDMENT_TYPE": "Lien Financing Stmt",
            "AMENDMENT_NUM": "X",
            "AMENDMENT_DATE": "1/1/2020",
        },
        {"AMENDMENT_TYPE": "Mystery Type", "AMENDMENT_NUM": "Y", "AMENDMENT_DATE": "2/1/2020"},
    ]
    rows = build_filings_from_history(detail, history)
    assert len(rows) == 1
    assert rows[0]["filing_type"] == "initial"


def test_build_filings_empty_history_returns_no_rows():
    detail = {
        "RECORD_NUM": "X",
        "DEBTOR_NAME": "X",
        "DEBTOR_ADDRESS": "",
        "SEC_PARTY_NAME": "",
        "SEC_PARTY_ADDRESS": "",
        "STATUS": "",
        "LAPSE_DATE": None,
    }
    assert build_filings_from_history(detail, []) == []


def test_extract_for_debtor_walks_results():
    """The extractor handles search responses with multiple result rows."""
    client = MagicMock()
    client.search.return_value = [
        {"ID": 100, "RECORD_NUM": "F1"},
        {"ID": 200, "RECORD_NUM": "F2"},
    ]
    client.detail.side_effect = [
        {
            "RECORD_NUM": "F1",
            "DEBTOR_NAME": "ACME",
            "DEBTOR_ADDRESS": "",
            "SEC_PARTY_NAME": "Bank",
            "SEC_PARTY_ADDRESS": "",
            "STATUS": "Active",
            "LAPSE_DATE": None,
        },
        {
            "RECORD_NUM": "F2",
            "DEBTOR_NAME": "ACME",
            "DEBTOR_ADDRESS": "",
            "SEC_PARTY_NAME": "Bank",
            "SEC_PARTY_ADDRESS": "",
            "STATUS": "Active",
            "LAPSE_DATE": None,
        },
    ]
    client.history.side_effect = [
        [
            {
                "AMENDMENT_TYPE": "Lien Financing Stmt",
                "AMENDMENT_NUM": "F1",
                "AMENDMENT_DATE": "1/1/2020",
            }
        ],
        [
            {
                "AMENDMENT_TYPE": "Lien Financing Stmt",
                "AMENDMENT_NUM": "F2",
                "AMENDMENT_DATE": "1/1/2021",
            }
        ],
    ]
    rows = extract_for_debtor("ACME", client=client)
    assert len(rows) == 2
    assert {r["filing_number"] for r in rows} == {"F1", "F2"}
