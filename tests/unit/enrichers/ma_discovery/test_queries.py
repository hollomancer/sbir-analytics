"""Tests for M&A search-query generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sbir_etl.enrichers.ma_discovery.queries import (
    build_query_csv,
    generate_queries,
    query_rows_from_events,
)
from sbir_etl.identity import CompanyNameProfile, normalize_company_name


pytestmark = pytest.mark.fast


def test_generate_queries_empty_names_return_nothing() -> None:
    assert generate_queries(None, "Mercury Systems") == []
    assert generate_queries("Physical Optics", None) == []
    assert generate_queries("", "Mercury Systems") == []
    assert generate_queries("Physical Optics", "") == []
    assert generate_queries("Inc.", "LLC") == []


def test_generate_queries_uses_suffix_stripped_identity_names() -> None:
    company = "Physical Optics Corporation"
    acquirer = "Mercury Systems, Inc."
    queries = generate_queries(company, acquirer)

    cleaned_company = normalize_company_name(company, profile=CompanyNameProfile.RECIPIENT_V1)
    cleaned_acquirer = normalize_company_name(acquirer, profile=CompanyNameProfile.RECIPIENT_V1)
    assert cleaned_company == "physical optics"
    assert cleaned_acquirer == "mercury systems"
    assert len(queries) == 4

    blob = " ".join(queries)
    assert cleaned_company in blob
    assert cleaned_acquirer in blob
    assert "corporation" not in blob
    assert "inc" not in blob
    assert company not in blob
    assert acquirer not in blob


def test_query_rows_only_include_acquirer_without_form_d(tmp_path: Path) -> None:
    events = [
        {
            "company_name": "Physical Optics Corporation",
            "acquirer": "Mercury Systems, Inc.",
        },
        {
            "company_name": "Form D Firm Inc",
            "acquirer": "Big Buyer Corp",
            "form_d_detail": {"accession": "0001"},
        },
        {
            "company_name": "No Buyer LLC",
            "acquirer": None,
        },
        {
            "company_name": "Empty Buyer LLC",
            "acquirer": "",
        },
    ]

    rows = query_rows_from_events(events)
    assert {row["company_name"] for row in rows} == {"Physical Optics Corporation"}
    assert all(row["acquirer"] == "Mercury Systems, Inc." for row in rows)
    assert len(rows) == 4
    assert all("query" in row and row["query"] for row in rows)

    output = tmp_path / "ma_search_queries.csv"
    written = build_query_csv(events, output)
    assert written == 4
    text = output.read_text()
    assert "Physical Optics Corporation" in text
    assert "Form D Firm Inc" not in text
    assert "No Buyer LLC" not in text
