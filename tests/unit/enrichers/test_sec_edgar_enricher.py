"""Tests for SEC EDGAR enrichment logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from sbir_etl.enrichers.sec_edgar.enricher import (
    _detect_ma_events,
    _extract_financials,
    _extract_latest_fact,
    _resolve_cik,
    _search_form_d_filings,
    _search_inbound_ma_mentions,
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
    async def test_enriches_with_inbound_ma_and_form_d(self):
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(
            return_value=[
                {
                    "filer_cik": "99999",
                    "filer_name": "Big Acquirer Inc",
                    "form_type": "8-K",
                    "file_date": "2024-06-15",
                    "accession_number": "001",
                    "file_description": "Acquisition announcement",
                },
            ]
        )
        mock_client.search_form_d_filings = AsyncMock(
            return_value=[
                {
                    "cik": "55555",
                    "entity_name": "Acme Corp",
                    "file_date": "2023-09-15",
                },
            ]
        )

        profile = await enrich_company(mock_client, "Acme Corp", company_uei="UEI123")
        assert profile.company_uei == "UEI123"
        assert profile.inbound_ma_mention_count == 1
        assert "Big Acquirer Inc" in profile.inbound_ma_acquirers
        assert profile.has_form_d is True
        assert profile.form_d_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_profile_for_no_signals(self):
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(return_value=[])
        mock_client.search_form_d_filings = AsyncMock(return_value=[])

        profile = await enrich_company(mock_client, "Tiny Private LLC")
        assert profile.inbound_ma_mention_count == 0
        assert profile.has_form_d is False

    @pytest.mark.asyncio
    async def test_deduplicates_inbound_by_filer(self):
        mock_client = AsyncMock()
        # Same filer appears in multiple 8-K hits
        mock_client.search_filing_mentions = AsyncMock(
            return_value=[
                {"filer_cik": "99999", "filer_name": "Mercury Systems", "form_type": "8-K",
                 "file_date": "2024-06-15", "accession_number": "001", "file_description": ""},
                {"filer_cik": "99999", "filer_name": "Mercury Systems", "form_type": "8-K",
                 "file_date": "2024-07-01", "accession_number": "002", "file_description": ""},
                {"filer_cik": "88888", "filer_name": "Other Corp", "form_type": "8-K",
                 "file_date": "2024-08-01", "accession_number": "003", "file_description": ""},
            ]
        )
        mock_client.search_form_d_filings = AsyncMock(return_value=[])

        profile = await enrich_company(mock_client, "Target Co")
        # Should deduplicate Mercury's 2 filings into 1
        assert profile.inbound_ma_mention_count == 2
        assert len(profile.inbound_ma_acquirers) == 2


class TestSearchInboundMAMentions:
    @pytest.mark.asyncio
    async def test_finds_inbound_acquisition(self):
        """Searches across 3 filing type tiers (strong M&A, annual, ownership)."""
        mock_client = AsyncMock()
        # Return a match on the first call (strong M&A types), empty on the rest
        mock_client.search_filing_mentions = AsyncMock(
            side_effect=[
                [  # Strong M&A types (8-K, DEFM14A, etc.)
                    {
                        "filer_cik": "99999",
                        "filer_name": "LOCKHEED MARTIN CORPORATION",
                        "form_type": "8-K",
                        "file_date": "2024-06-15",
                        "accession_number": "0001-24-500",
                        "file_description": "Acquisition of Small SBIR Company",
                    },
                ],
                [],  # Annual reports (10-K, 10-Q)
                [],  # Ownership filings (SC 13D/13G)
            ]
        )

        events = await _search_inbound_ma_mentions(
            mock_client, "Small SBIR Company"
        )
        assert len(events) == 1
        assert events[0].is_target is True
        assert events[0].filer_name == "LOCKHEED MARTIN CORPORATION"
        assert events[0].event_type == MAAcquisitionType.ACQUISITION
        # Should have been called 3 times (one per filing type tier)
        assert mock_client.search_filing_mentions.call_count == 3

    @pytest.mark.asyncio
    async def test_combines_results_across_tiers(self):
        """Results from all 3 tiers are combined."""
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(
            side_effect=[
                [  # 8-K match
                    {"filer_cik": "111", "filer_name": "ACQUIRER A", "form_type": "8-K",
                     "file_date": "2024-06-15", "accession_number": "001", "file_description": ""},
                ],
                [  # 10-K match from different filer
                    {"filer_cik": "222", "filer_name": "ACQUIRER B", "form_type": "10-K",
                     "file_date": "2024-03-01", "accession_number": "002", "file_description": ""},
                ],
                [],  # No ownership filings
            ]
        )

        events = await _search_inbound_ma_mentions(mock_client, "Target Co")
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_filters_out_self_filings(self):
        """If the filer name matches the searched company, it's not an inbound M&A."""
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(
            side_effect=[
                [
                    {"filer_cik": "11111", "filer_name": "ACME CORP",
                     "form_type": "8-K", "file_date": "2024-03-01",
                     "accession_number": "001", "file_description": "Something"},
                ],
                [],
                [],
            ]
        )

        events = await _search_inbound_ma_mentions(mock_client, "Acme Corp")
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(return_value=[])

        events = await _search_inbound_ma_mentions(mock_client, "Unknown LLC")
        assert events == []


class TestSearchFormDFilings:
    @pytest.mark.asyncio
    async def test_finds_form_d(self):
        mock_client = AsyncMock()
        mock_client.search_form_d_filings = AsyncMock(
            return_value=[
                {
                    "cik": "55555",
                    "entity_name": "SBIR STARTUP INC",
                    "file_date": "2023-09-15",
                    "form_type": "D",
                },
            ]
        )

        filings = await _search_form_d_filings(mock_client, "SBIR Startup Inc")
        assert len(filings) == 1
        assert filings[0].cik == "55555"
        assert filings[0].match_confidence >= 0.85

    @pytest.mark.asyncio
    async def test_rejects_low_confidence_match(self):
        mock_client = AsyncMock()
        mock_client.search_form_d_filings = AsyncMock(
            return_value=[
                {
                    "cik": "55555",
                    "entity_name": "COMPLETELY DIFFERENT NAME",
                    "file_date": "2023-09-15",
                    "form_type": "D",
                },
            ]
        )

        filings = await _search_form_d_filings(mock_client, "SBIR Startup Inc")
        assert len(filings) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        mock_client = AsyncMock()
        mock_client.search_form_d_filings = AsyncMock(return_value=[])

        filings = await _search_form_d_filings(mock_client, "Unknown LLC")
        assert filings == []


class TestEnrichCompanySignals:
    @pytest.mark.asyncio
    async def test_company_with_inbound_ma(self):
        """Company should get inbound M&A signals from 8-K mentions."""
        mock_client = AsyncMock()
        # Found as acquisition target
        mock_client.search_filing_mentions = AsyncMock(
            return_value=[
                {
                    "filer_cik": "99999",
                    "filer_name": "BIG DEFENSE CO",
                    "form_type": "8-K",
                    "file_date": "2024-06-15",
                    "accession_number": "001",
                    "file_description": "Acquisition",
                },
            ]
        )
        mock_client.search_form_d_filings = AsyncMock(return_value=[])

        profile = await enrich_company(mock_client, "Tiny SBIR LLC")
        assert profile.inbound_ma_mention_count == 1
        assert "BIG DEFENSE CO" in profile.inbound_ma_acquirers

    @pytest.mark.asyncio
    async def test_company_with_form_d(self):
        """Company should get Form D signals."""
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(return_value=[])
        mock_client.search_form_d_filings = AsyncMock(
            return_value=[
                {
                    "cik": "77777",
                    "entity_name": "VENTURE BACKED SBIR INC",
                    "file_date": "2023-03-01",
                    "form_type": "D",
                },
            ]
        )

        profile = await enrich_company(
            mock_client, "Venture Backed SBIR Inc"
        )
        assert profile.has_form_d is True
        assert profile.form_d_cik == "77777"
        assert profile.form_d_count == 1

    @pytest.mark.asyncio
    async def test_company_with_both_signals(self):
        """A company can have both inbound M&A and Form D signals."""
        mock_client = AsyncMock()
        mock_client.search_filing_mentions = AsyncMock(
            return_value=[
                {
                    "filer_cik": "88888",
                    "filer_name": "ACQUIRER INC",
                    "form_type": "8-K",
                    "file_date": "2024-01-10",
                    "accession_number": "002",
                    "file_description": "Merger",
                },
            ]
        )
        mock_client.search_form_d_filings = AsyncMock(
            return_value=[
                {
                    "cik": "77777",
                    "entity_name": "Dual Signal Corp",
                    "file_date": "2023-06-01",
                },
            ]
        )

        profile = await enrich_company(mock_client, "Dual Signal Corp")
        assert profile.inbound_ma_mention_count == 1
        assert profile.has_form_d is True


class TestModels:
    def test_company_edgar_profile_defaults(self):
        from sbir_etl.models.sec_edgar import CompanyEdgarProfile

        profile = CompanyEdgarProfile(company_name="Test Corp")
        assert profile.is_publicly_traded is False
        assert profile.match_confidence == 0.0
        assert profile.ma_event_count == 0
        assert profile.inbound_ma_mention_count == 0
        assert profile.has_form_d is False
        assert profile.form_d_count == 0

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

    def test_edgar_ma_event_target_flag(self):
        from sbir_etl.models.sec_edgar import EdgarMAEvent

        event = EdgarMAEvent(
            cik="99999",
            filer_name="Big Corp",
            filing_date="2024-06-15",
            accession_number="001",
            is_target=True,
        )
        assert event.is_target is True
        assert event.filer_name == "Big Corp"

    def test_edgar_form_d_filing_model(self):
        from sbir_etl.models.sec_edgar import EdgarFormDFiling

        filing = EdgarFormDFiling(
            cik="55555",
            entity_name="Startup Inc",
            filing_date="2023-09-15",
            match_confidence=0.95,
        )
        assert filing.cik == "55555"
        assert filing.match_confidence == 0.95
