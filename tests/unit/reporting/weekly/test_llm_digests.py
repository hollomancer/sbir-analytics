"""Unit tests for sbir_etl.reporting.weekly.llm_digests (pure prompt-context builders)."""

import pytest

from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary,
    SAMEntityRecord,
)
from sbir_etl.enrichers.opencorporates import CorporateRecord, Officer
from sbir_etl.enrichers.pi_enrichment import ORCIDRecord, PIPatentRecord, PIPublicationRecord
from sbir_etl.enrichers.press_wire import PressRelease
from sbir_etl.reporting.weekly.llm_digests import (
    _award_digest,
    _company_history_digest,
    _pi_external_digest,
    _pi_history_digest,
)
from sbir_etl.reporting.weekly.models import CompanyResearch, SolicitationTopic


pytestmark = pytest.mark.fast


BASE_AWARD = {
    "Award Title": "Advanced Sensor Platform",
    "Company": "Acme Innovations Inc.",
    "Agency": "Department of Defense",
    "Program": "SBIR",
    "Phase": "Phase I",
    "Award Amount": "150000",
    "State": "CA",
    "Proposal Award Date": "2026-03-15",
}


class TestAwardDigestMinimal:
    def test_minimal_award_includes_core_fields_only(self):
        digest = _award_digest(dict(BASE_AWARD))

        assert "Title: Advanced Sensor Platform" in digest
        assert "Company: Acme Innovations Inc." in digest
        assert "Agency: Department of Defense" in digest
        assert "Program: SBIR Phase I" in digest
        # Optional fields absent from input should not appear
        assert "Abstract:" not in digest
        assert "Topic Code:" not in digest
        assert "Contract:" not in digest

    def test_missing_fields_render_as_na(self):
        digest = _award_digest({})
        assert "Title: N/A" in digest
        assert "Company: N/A" in digest


class TestAwardDigestAbstract:
    def test_short_abstract_not_truncated(self):
        award = dict(BASE_AWARD, Abstract="A short abstract.")
        digest = _award_digest(award)
        assert "Abstract: A short abstract." in digest

    def test_long_abstract_truncated_at_1500_chars(self):
        award = dict(BASE_AWARD, Abstract="x" * 2000)
        digest = _award_digest(award)
        assert ("x" * 1500 + "...") in digest
        assert "x" * 1501 not in digest

    def test_blank_abstract_omitted(self):
        award = dict(BASE_AWARD, Abstract="   ")
        digest = _award_digest(award)
        assert "Abstract:" not in digest


class TestAwardDigestSolicitationTopic:
    def test_solicitation_topic_included_when_available(self):
        award = dict(BASE_AWARD, **{"Topic Code": "AF241-001"})
        topics = {
            "AF241-001": SolicitationTopic(
                topic_code="AF241-001",
                solicitation_number="AF24.1",
                title="Sensor Fusion",
                description="Develop novel sensor fusion algorithms.",
                agency="AF",
                program="SBIR",
            )
        }
        digest = _award_digest(award, solicitation_topics=topics)
        assert "Solicitation Topic Title: Sensor Fusion" in digest
        assert "Solicitation Topic Description" in digest
        assert "Develop novel sensor fusion algorithms." in digest

    def test_missing_topic_code_skips_solicitation_topic_lookup(self):
        digest = _award_digest(dict(BASE_AWARD), solicitation_topics={"AF241-001": object()})
        assert "Solicitation Topic Title" not in digest

    def test_topic_code_without_matching_entry_skips_topic_block(self):
        award = dict(BASE_AWARD, **{"Topic Code": "UNKNOWN-999"})
        digest = _award_digest(award, solicitation_topics={})
        assert "Solicitation Topic Title" not in digest

    def test_supplementary_context_used_when_no_solicitation_topic(self):
        award = dict(BASE_AWARD, Contract="FA8650-23-C-0001")
        digest = _award_digest(
            award,
            usaspending_descriptions={"FA8650-23-C-0001": "Contract for advanced sensors."},
            sam_entities={
                "ACME INNOVATIONS INC.": SAMEntityRecord(
                    uei="ABC123",
                    legal_business_name="Acme Innovations Inc.",
                    dba_name=None,
                    registration_status="Active",
                    expiration_date=None,
                    business_type=None,
                    entity_structure=None,
                    naics_codes=["541715"],
                    cage_code=None,
                    exclusion_status=None,
                    state="CA",
                    congressional_district=None,
                )
            },
        )
        assert "USAspending contract description" in digest
        assert "Contract for advanced sensors." in digest
        assert "Company NAICS codes" in digest
        assert "541715" in digest

    def test_supplementary_context_suppressed_when_solicitation_topic_present(self):
        award = dict(
            BASE_AWARD,
            Contract="FA8650-23-C-0001",
            **{"Topic Code": "AF241-001"},
        )
        topics = {
            "AF241-001": SolicitationTopic(
                topic_code="AF241-001",
                solicitation_number="AF24.1",
                title="Sensor Fusion",
                description="Desc",
                agency="AF",
                program="SBIR",
            )
        }
        digest = _award_digest(
            award,
            solicitation_topics=topics,
            usaspending_descriptions={"FA8650-23-C-0001": "Contract for advanced sensors."},
        )
        assert "USAspending contract description" not in digest


class TestAwardDigestContract:
    def test_contract_adds_usaspending_link(self):
        award = dict(BASE_AWARD, Contract="FA8650-23-C-0001")
        digest = _award_digest(award)
        assert "Contract: FA8650-23-C-0001" in digest
        assert "USAspending Record: https://www.usaspending.gov/search" in digest


class TestAwardDigestCompanyResearch:
    def test_company_research_included(self):
        research = CompanyResearch(
            summary="Acme builds sensors.",
            source_urls=["https://acme.example.com"],
        )
        digest = _award_digest(dict(BASE_AWARD), company_research=research)
        assert "Company Background (from web research): Acme builds sensors." in digest
        assert "Company Sources: https://acme.example.com" in digest

    def test_no_company_research_omits_block(self):
        digest = _award_digest(dict(BASE_AWARD))
        assert "Company Background" not in digest


class TestAwardDigestCorporateRecord:
    def test_corporate_record_fields_included(self):
        record = CorporateRecord(
            company_name="Acme Innovations Inc.",
            jurisdiction="DE",
            company_number="123456",
            incorporation_date="2015-01-01",
            status="Active",
            company_type="Corporation",
            parent_company="Acme Holdings",
            officers=[Officer(name="Jane Doe", position="CEO")],
        )
        digest = _award_digest(dict(BASE_AWARD), corporate_record=record)
        assert "State corporation filing (OpenCorporates)" in digest
        assert "Incorporated: 2015-01-01" in digest
        assert "Parent company: Acme Holdings" in digest
        assert "Officers: Jane Doe" in digest

    def test_corporate_record_with_no_populated_fields_omits_block(self):
        record = CorporateRecord(
            company_name="Acme Innovations Inc.",
            jurisdiction="DE",
            company_number="123456",
        )
        digest = _award_digest(dict(BASE_AWARD), corporate_record=record)
        assert "State corporation filing (OpenCorporates)" not in digest


class TestAwardDigestPressReleases:
    def test_press_releases_included_up_to_three(self):
        releases = [
            PressRelease(title=f"Release {i}", link="https://x", source="PRNewswire")
            for i in range(5)
        ]
        digest = _award_digest(dict(BASE_AWARD), press_releases=releases)
        assert "Recent press releases:" in digest
        assert "Release 0" in digest
        assert "Release 2" in digest
        assert "Release 3" not in digest

    def test_no_press_releases_omits_block(self):
        digest = _award_digest(dict(BASE_AWARD), press_releases=[])
        assert "Recent press releases" not in digest


class TestCompanyHistoryDigest:
    def test_no_history_returns_default_message(self):
        assert _company_history_digest("Acme", None) == (
            "No prior SBIR/STTR award history found in the dataset."
        )

    def test_history_formatted_with_all_fields(self):
        history = {
            "total_awards": 5,
            "phases": ["Phase I", "Phase II"],
            "agencies": ["DoD", "NASA"],
            "programs": ["SBIR"],
            "total_funding": 1250000,
            "earliest_date": "2020-01-01",
            "latest_date": "2025-01-01",
            "sample_titles": ["Widget I", "Widget II"],
        }
        digest = _company_history_digest("Acme", history)
        assert "Total historical SBIR/STTR awards: 5" in digest
        assert "Phases achieved: Phase I, Phase II" in digest
        assert "Total historical funding: $1,250,000" in digest
        assert "Sample award titles: Widget I; Widget II" in digest

    def test_history_missing_optional_fields_use_defaults(self):
        history = {
            "total_awards": 1,
            "phases": [],
            "agencies": [],
            "programs": [],
            "total_funding": 0,
        }
        digest = _company_history_digest("Acme", history)
        assert "Phases achieved: N/A" in digest
        assert "Award date range: N/A to N/A" in digest
        assert "Sample award titles" not in digest


class TestPiHistoryDigest:
    def test_no_history_returns_default_message(self):
        assert _pi_history_digest("Jane Doe", None) == (
            "No prior SBIR/STTR award history found for this PI."
        )

    def test_history_formatted_with_all_fields(self):
        history = {
            "total_awards": 3,
            "companies": ["Acme"],
            "phases": ["Phase I"],
            "agencies": ["DoD"],
            "total_funding": 500000,
            "earliest_date": "2021-01-01",
            "latest_date": "2024-01-01",
            "sample_titles": ["Widget I"],
        }
        digest = _pi_history_digest("Jane Doe", history)
        assert "Total historical SBIR/STTR awards as PI: 3" in digest
        assert "Companies: Acme" in digest
        assert "Total funding as PI: $500,000" in digest


class TestPiExternalDigest:
    def test_no_external_data_returns_default_message(self):
        assert _pi_external_digest(None) == "No external data available for this PI."

    def test_missing_sub_records_use_default_messages(self):
        # A non-empty dict with no recognized keys still exercises every
        # "not found" branch (an empty dict short-circuits via `if not external`).
        digest = _pi_external_digest({"unused_key": True})
        assert "ORCID: No ORCID profile found for this researcher." in digest
        assert "USPTO Patents: No patents found for this inventor name." in digest
        assert "Academic publications: No Semantic Scholar profile found." in digest
        assert "Company federal awards: No USAspending records found." in digest

    def test_orcid_record_included(self):
        orcid = ORCIDRecord(
            orcid_id="0000-0001-2345-6789",
            given_name="Jane",
            family_name="Doe",
            affiliations=["MIT"],
            works_count=10,
            sample_work_titles=["Paper A"],
            funding_count=2,
            keywords=["sensors"],
        )
        digest = _pi_external_digest({"orcid": orcid})
        assert "ORCID ID: 0000-0001-2345-6789" in digest
        assert "ORCID affiliations: MIT" in digest
        assert "ORCID research keywords: sensors" in digest
        assert "ORCID sample works: Paper A" in digest

    def test_patents_record_included(self):
        patents = PIPatentRecord(
            total_patents=4,
            sample_titles=["Sensor Patent"],
            assignees=["Acme Inc"],
            date_range=("2019-01-01", "2023-01-01"),
        )
        digest = _pi_external_digest({"patents": patents})
        assert "USPTO Patents as inventor: 4" in digest
        assert "Patent assignees: Acme Inc" in digest
        assert "Patent date range: 2019-01-01 to 2023-01-01" in digest

    def test_patents_record_with_no_date_range_omits_range_line(self):
        patents = PIPatentRecord(
            total_patents=1,
            sample_titles=[],
            assignees=[],
            date_range=(None, None),
        )
        digest = _pi_external_digest({"patents": patents})
        assert "Patent date range" not in digest

    def test_publications_record_included(self):
        pubs = PIPublicationRecord(
            total_papers=8,
            h_index=5,
            citation_count=120,
            sample_titles=["Great Paper"],
            affiliations=["Stanford"],
        )
        digest = _pi_external_digest({"publications": pubs})
        assert "Academic publications: 8" in digest
        assert "h-index: 5" in digest
        assert "Total citations: 120" in digest

    def test_publications_with_no_h_index_omits_h_index_line(self):
        pubs = PIPublicationRecord(
            total_papers=1,
            h_index=None,
            citation_count=0,
            sample_titles=[],
            affiliations=[],
        )
        digest = _pi_external_digest({"publications": pubs})
        assert "h-index" not in digest

    def test_federal_awards_record_included_with_non_sbir_signals(self):
        fed = FederalAwardSummary(
            total_awards=10,
            total_funding=2_000_000,
            agencies=["DoD", "NASA"],
            award_types=["Contract"],
            date_range=("2018-01-01", "2024-01-01"),
            sbir_award_count=6,
            sbir_funding=1_000_000,
            non_sbir_award_count=4,
            non_sbir_funding=1_000_000,
            non_sbir_agencies=["DoD"],
            non_sbir_sample_descriptions=["Follow-on production contract"],
        )
        digest = _pi_external_digest({"federal_awards": fed})
        assert "Company federal awards (USAspending): 10 total" in digest
        assert "Non-SBIR federal awards (potential follow-on/Phase III): 4 ($1,000,000)" in digest
        assert "Non-SBIR awarding agencies: DoD" in digest
        assert "Sample non-SBIR award descriptions (follow-on signals):" in digest
        assert "Follow-on production contract" in digest
        assert "All federal agencies: DoD, NASA" in digest
        assert "Award types: Contract" in digest
        assert "Federal award date range: 2018-01-01 to 2024-01-01" in digest

    def test_federal_awards_with_no_non_sbir_signals_omits_those_lines(self):
        fed = FederalAwardSummary(
            total_awards=1,
            total_funding=100.0,
            agencies=[],
            award_types=[],
            date_range=(None, None),
        )
        digest = _pi_external_digest({"federal_awards": fed})
        assert "Non-SBIR awarding agencies" not in digest
        assert "Sample non-SBIR award descriptions" not in digest
        assert "All federal agencies" not in digest
        assert "Federal award date range" not in digest
