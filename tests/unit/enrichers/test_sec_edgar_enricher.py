"""Tests for SEC EDGAR enrichment logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from sbir_etl.enrichers.sec_edgar.enricher import (
    _detect_ma_events,
    _extract_financials,
    _extract_latest_fact,
    _resolve_cik,
    enrich_company,
)
from sbir_etl.models.sec_edgar import MAAcquisitionType


class TestExtractLatestFact:
    def test_extracts_revenue(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"val": 1000000, "end": "2023-12-31", "form": "10-K"},
                                {"val": 800000, "end": "2022-12-31", "form": "10-K"},
                            ]
                        }
                    }
                }
            }
        }
        value, d = _extract_latest_fact(facts, ["Revenues"])
        assert value == 1000000.0
        assert d == date(2023, 12, 31)

    def test_returns_none_for_missing_concept(self):
        facts = {"facts": {"us-gaap": {}}}
        value, d = _extract_latest_fact(facts, ["NonexistentConcept"])
        assert value is None
        assert d is None

    def test_skips_non_annual_forms(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"val": 500000, "end": "2023-06-30", "form": "S-1"},
                            ]
                        }
                    }
                }
            }
        }
        value, d = _extract_latest_fact(facts, ["Revenues"])
        assert value is None

    def test_tries_fallback_concepts(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "SalesRevenueNet": {
                        "units": {
                            "USD": [
                                {"val": 2000000, "end": "2023-12-31", "form": "10-K"},
                            ]
                        }
                    }
                }
            }
        }
        value, _ = _extract_latest_fact(
            facts, ["Revenues", "SalesRevenueNet"]
        )
        assert value == 2000000.0


class TestExtractFinancials:
    def test_extracts_full_financials(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [{"val": 5000000, "end": "2024-12-31", "form": "10-K"}]
                        }
                    },
                    "ResearchAndDevelopmentExpense": {
                        "units": {
                            "USD": [{"val": 1000000, "end": "2024-12-31", "form": "10-K"}]
                        }
                    },
                    "Assets": {
                        "units": {
                            "USD": [{"val": 10000000, "end": "2024-12-31", "form": "10-K"}]
                        }
                    },
                }
            }
        }
        result = _extract_financials("12345", facts)
        assert result is not None
        assert result.cik == "12345"
        assert result.revenue == 5000000.0
        assert result.rd_expense == 1000000.0
        assert result.total_assets == 10000000.0

    def test_returns_none_when_no_data(self):
        facts = {"facts": {"us-gaap": {}}}
        result = _extract_financials("12345", facts)
        assert result is None


class TestDetectMAEvents:
    def test_detects_acquisition_8k(self):
        filings = [
            {
                "form_type": "8-K",
                "filing_date": "2024-06-15",
                "accession_number": "0001-24-100",
                "description": "Item 2.01: Completion of Acquisition of XYZ Corp",
            },
        ]
        events = _detect_ma_events("12345", filings)
        assert len(events) == 1
        assert events[0].event_type == MAAcquisitionType.ACQUISITION
        assert "2.01" in events[0].items_reported

    def test_detects_merger_8k(self):
        filings = [
            {
                "form_type": "8-K",
                "filing_date": "2024-03-01",
                "accession_number": "0001-24-200",
                "description": "Item 1.01: Merger Agreement with ABC Inc",
            },
        ]
        events = _detect_ma_events("12345", filings)
        assert len(events) == 1
        assert events[0].event_type == MAAcquisitionType.MERGER
        assert "1.01" in events[0].items_reported

    def test_ignores_non_8k(self):
        filings = [
            {
                "form_type": "10-K",
                "filing_date": "2024-03-15",
                "accession_number": "001",
                "description": "Annual Report",
            },
        ]
        events = _detect_ma_events("12345", filings)
        assert len(events) == 0

    def test_ignores_non_ma_8k(self):
        filings = [
            {
                "form_type": "8-K",
                "filing_date": "2024-03-15",
                "accession_number": "001",
                "description": "Item 5.02: Departure of Directors",
            },
        ]
        events = _detect_ma_events("12345", filings)
        assert len(events) == 0


class TestResolveCIK:
    @pytest.mark.asyncio
    async def test_resolves_high_confidence(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(
            return_value=[
                {"cik": "12345", "entity_name": "ACME CORPORATION", "ticker": "ACME"},
            ]
        )

        result = await _resolve_cik(mock_client, "Acme Corporation")
        assert result is not None
        assert result["cik"] == "12345"
        assert result["match_score"] >= 0.9
        assert result["match_method"] == "name_fuzzy_auto"

    @pytest.mark.asyncio
    async def test_resolves_low_confidence(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(
            return_value=[
                {"cik": "12345", "entity_name": "QUANTUM HORIZONS DEFENSE TECH", "ticker": None},
            ]
        )

        result = await _resolve_cik(
            mock_client, "Quantum Defense Technologies", high_threshold=95, low_threshold=60
        )
        assert result is not None
        assert result["match_method"] == "name_fuzzy_review"

    @pytest.mark.asyncio
    async def test_returns_none_below_threshold(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(
            return_value=[
                {"cik": "12345", "entity_name": "TOTALLY DIFFERENT COMPANY", "ticker": None},
            ]
        )

        result = await _resolve_cik(mock_client, "Acme Corp")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_results(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(return_value=[])

        result = await _resolve_cik(mock_client, "Acme Corp")
        assert result is None


class TestEnrichCompany:
    @pytest.mark.asyncio
    async def test_enriches_public_company(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(
            return_value=[
                {"cik": "12345", "entity_name": "ACME CORP", "ticker": "ACME"},
            ]
        )
        mock_client.get_company_facts = AsyncMock(
            return_value={
                "sic": "3674",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    {"val": 50000000, "end": "2024-12-31", "form": "10-K"},
                                ]
                            }
                        },
                    }
                },
            }
        )
        mock_client.get_recent_filings = AsyncMock(
            return_value=[
                {
                    "form_type": "10-K",
                    "filing_date": "2024-03-15",
                    "accession_number": "001",
                    "description": "Annual Report",
                },
            ]
        )

        profile = await enrich_company(mock_client, "Acme Corp", company_uei="UEI123")
        assert profile.is_publicly_traded is True
        assert profile.cik == "12345"
        assert profile.ticker == "ACME"
        assert profile.latest_revenue == 50000000.0
        assert profile.total_filings == 1
        assert profile.company_uei == "UEI123"

    @pytest.mark.asyncio
    async def test_returns_empty_profile_for_private(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(return_value=[])

        profile = await enrich_company(mock_client, "Tiny Private LLC")
        assert profile.is_publicly_traded is False
        assert profile.cik is None
        assert profile.latest_revenue is None

    @pytest.mark.asyncio
    async def test_skips_financials_when_disabled(self):
        mock_client = AsyncMock()
        mock_client.search_companies = AsyncMock(
            return_value=[
                {"cik": "12345", "entity_name": "ACME CORP", "ticker": None},
            ]
        )
        mock_client.get_recent_filings = AsyncMock(return_value=[])

        profile = await enrich_company(
            mock_client, "Acme Corp", fetch_financials=False
        )
        assert profile.is_publicly_traded is True
        mock_client.get_company_facts.assert_not_called()


class TestModels:
    def test_company_edgar_profile_defaults(self):
        from sbir_etl.models.sec_edgar import CompanyEdgarProfile

        profile = CompanyEdgarProfile(company_name="Test Corp")
        assert profile.is_publicly_traded is False
        assert profile.match_confidence == 0.0
        assert profile.ma_event_count == 0

    def test_edgar_financials_model(self):
        from sbir_etl.models.sec_edgar import EdgarFinancials

        fin = EdgarFinancials(
            cik="12345",
            fiscal_year=2024,
            revenue=1000000.0,
            rd_expense=200000.0,
        )
        assert fin.cik == "12345"
        assert fin.revenue == 1000000.0

    def test_filing_type_enum(self):
        from sbir_etl.models.sec_edgar import FilingType

        assert FilingType.FORM_10K == "10-K"
        assert FilingType.FORM_8K == "8-K"

    def test_match_confidence_validation(self):
        from sbir_etl.models.sec_edgar import CompanyEdgarProfile

        with pytest.raises(ValueError):
            CompanyEdgarProfile(
                company_name="Test", match_confidence=1.5
            )
