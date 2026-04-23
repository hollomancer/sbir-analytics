"""Tests for Form D XML parser and confidence scorer."""

from __future__ import annotations

from datetime import date

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    compute_form_d_confidence,
    parse_form_d_xml,
)

# ---------------------------------------------------------------------------
# Sample XML (Aspen Aerogels)
# ---------------------------------------------------------------------------

SAMPLE_XML = """\
<?xml version="1.0"?>
<edgarSubmission>
    <submissionType>D</submissionType>
    <primaryIssuer>
        <cik>0001145986</cik>
        <entityName>ASPEN AEROGELS INC</entityName>
        <issuerAddress>
            <street1>30 FORBES ROAD</street1>
            <city>NORTHBOROUGH</city>
            <stateOrCountry>MA</stateOrCountry>
            <zipCode>01532</zipCode>
        </issuerAddress>
        <issuerPhoneNumber>508-691-1111</issuerPhoneNumber>
        <jurisdictionOfInc>DELAWARE</jurisdictionOfInc>
        <entityType>Corporation</entityType>
        <yearOfInc><value>2008</value></yearOfInc>
    </primaryIssuer>
    <offeringData>
        <industryGroup><industryGroupType>Other Technology</industryGroupType></industryGroup>
        <issuerSize><revenueRange>Decline to Disclose</revenueRange></issuerSize>
        <federalExemptionsExclusions><item>06</item></federalExemptionsExclusions>
        <typeOfFiling>
            <newOrAmendment><isAmendment>false</isAmendment></newOrAmendment>
            <dateOfFirstSale><value>2011-12-06</value></dateOfFirstSale>
        </typeOfFiling>
        <typesOfSecuritiesOffered>
            <isDebtType>true</isDebtType>
            <isEquityType>false</isEquityType>
            <isOptionToAcquireType>true</isOptionToAcquireType>
        </typesOfSecuritiesOffered>
        <businessCombinationTransaction>
            <isBusinessCombinationTransaction>false</isBusinessCombinationTransaction>
        </businessCombinationTransaction>
        <minimumInvestmentAccepted>0</minimumInvestmentAccepted>
        <offeringSalesAmounts>
            <totalOfferingAmount>25000000</totalOfferingAmount>
            <totalAmountSold>15000000</totalAmountSold>
            <totalRemaining>10000000</totalRemaining>
        </offeringSalesAmounts>
        <investors>
            <hasNonAccreditedInvestors>false</hasNonAccreditedInvestors>
            <totalNumberAlreadyInvested>17</totalNumberAlreadyInvested>
        </investors>
    </offeringData>
    <relatedPersonsList>
        <relatedPersonInfo>
            <relatedPersonName>
                <firstName>Donald</firstName>
                <middleName>R.</middleName>
                <lastName>Young</lastName>
            </relatedPersonName>
            <relatedPersonAddress>
                <city>Northborough</city>
                <stateOrCountry>MA</stateOrCountry>
            </relatedPersonAddress>
            <relatedPersonRelationshipList>
                <relationship>Executive Officer</relationship>
                <relationship>Director</relationship>
            </relatedPersonRelationshipList>
        </relatedPersonInfo>
    </relatedPersonsList>
</edgarSubmission>
"""

_ACCESSION = "0001145986-11-000001"
_FILING_DATE = date(2011, 12, 10)


class TestParseFormDXml:
    """Tests for parse_form_d_xml()."""

    def _parse(self) -> dict:
        result = parse_form_d_xml(SAMPLE_XML, _ACCESSION, _FILING_DATE)
        assert result is not None
        return result

    def test_parses_issuer_fields(self):
        d = self._parse()
        assert d["entity_name"] == "ASPEN AEROGELS INC"
        assert d["entity_type"] == "Corporation"
        assert d["year_of_inc"] == 2008
        assert d["jurisdiction_of_inc"] == "DELAWARE"
        assert d["phone"] == "508-691-1111"
        assert d["cik"] == "0001145986"
        assert d["accession_number"] == _ACCESSION
        assert d["filing_date"] == _FILING_DATE

    def test_parses_address(self):
        d = self._parse()
        assert d["street1"] == "30 FORBES ROAD"
        assert d["city"] == "NORTHBOROUGH"
        assert d["state"] == "MA"
        assert d["zip_code"] == "01532"

    def test_parses_offering_data(self):
        d = self._parse()
        assert d["total_offering_amount"] == 25_000_000.0
        assert d["total_amount_sold"] == 15_000_000.0
        assert d["total_remaining"] == 10_000_000.0
        assert d["minimum_investment"] == 0.0
        assert d["num_investors"] == 17
        assert d["has_non_accredited"] is False
        assert d["is_amendment"] is False
        assert d["is_business_combination"] is False
        assert d["date_of_first_sale"] == date(2011, 12, 6)
        assert d["industry_group"] == "Other Technology"
        assert d["revenue_range"] == "Decline to Disclose"
        assert d["federal_exemption"] == "06"
        assert "debt" in d["securities_types"]
        assert "options" in d["securities_types"]
        assert "equity" not in d["securities_types"]

    def test_parses_related_persons(self):
        d = self._parse()
        persons = d["related_persons"]
        assert len(persons) == 1
        p = persons[0]
        # Name is concatenation of first + middle + last
        assert p["name"] == "Donald R. Young"
        # Title is relationships joined with ", "
        assert p["title"] == "Executive Officer, Director"
        assert p["city"] == "Northborough"
        assert p["state"] == "MA"

    def test_returns_none_for_invalid_xml(self):
        result = parse_form_d_xml("<<<not xml>>>", _ACCESSION, _FILING_DATE)
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = parse_form_d_xml("", _ACCESSION, _FILING_DATE)
        assert result is None


class TestComputeFormDConfidence:
    """Tests for compute_form_d_confidence()."""

    _RELATED = [
        {
            "name": "Donald R. Young",
            "title": "Executive Officer, Director",
            "city": "Northborough",
            "state": "MA",
        }
    ]

    def test_high_confidence_with_person_match(self):
        """PI 'Donald Young' should fuzzily match 'Donald R. Young' → high tier."""
        result = compute_form_d_confidence(
            name_score=0.90,
            pi_names=["Donald Young"],
            related_persons=self._RELATED,
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2012,
            form_d_dates=[date(2011, 12, 10)],
            year_of_inc=2008,
        )
        assert result.tier == "high"
        assert result.person_score is not None
        assert result.person_score > 0.85
        assert result.person_match_detail is not None
        assert "Donald Young" in result.person_match_detail
        assert "Donald R. Young" in result.person_match_detail
        assert result.state_score == 1.0
        assert result.temporal_score == 1.0
        assert result.year_of_inc_score == 1.0

    def test_medium_confidence_state_only(self):
        """State match with no person data → medium tier (state is secondary signal)."""
        result = compute_form_d_confidence(
            name_score=0.70,
            pi_names=[],
            related_persons=[],
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2013,
            form_d_dates=[date(2012, 1, 1)],
            year_of_inc=None,
        )
        assert result.tier == "medium"
        assert result.person_score is None
        assert result.state_score == 1.0
        assert result.temporal_score == 1.0
        assert result.year_of_inc_score is None

    def test_low_confidence_state_mismatch(self):
        """State mismatch, no person match, old filing, bad year_of_inc → low tier."""
        result = compute_form_d_confidence(
            name_score=0.50,
            pi_names=["Jane Smith"],
            related_persons=[{"name": "Bob Johnson", "title": "Director", "city": "Dallas", "state": "TX"}],
            sbir_state="MA",
            biz_states=["TX"],
            earliest_sbir_award_year=2013,
            form_d_dates=[date(2005, 6, 1)],
            year_of_inc=2015,
        )
        assert result.tier == "low"
        assert result.state_score == 0.0
        assert result.temporal_score == 0.0
        assert result.year_of_inc_score == 0.0

    def test_person_match_drives_high_tier(self):
        """Strong person match → high tier regardless of state or temporal signals."""
        result = compute_form_d_confidence(
            name_score=0.60,
            pi_names=["Donald Young"],
            related_persons=self._RELATED,
            sbir_state="CA",
            biz_states=["MA"],  # state mismatch
            earliest_sbir_award_year=2020,
            form_d_dates=[date(2011, 12, 10)],  # big temporal gap
            year_of_inc=None,
        )
        assert result.person_score is not None
        assert result.person_score >= 0.70
        assert result.tier == "high"
        assert result.state_score == 0.0

    def test_address_match_drives_high_tier(self):
        """ZIP match → high tier even without person match (HHS/academic PI case)."""
        result = compute_form_d_confidence(
            name_score=0.95,
            pi_names=["Academic Professor"],
            related_persons=[{"name": "CEO Person", "title": "Executive Officer"}],
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2015,
            form_d_dates=[date(2016, 1, 1)],
            year_of_inc=2010,
            sbir_zip="01532",
            form_d_zips=["01532"],
        )
        assert result.person_score is not None
        assert result.person_score < 0.7  # PI doesn't match executive
        assert result.address_score == 1.0
        assert result.tier == "high"

    def test_address_mismatch_no_promotion(self):
        """ZIP mismatch without person match → medium (state match) not high."""
        result = compute_form_d_confidence(
            name_score=0.95,
            pi_names=[],
            related_persons=[],
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2015,
            form_d_dates=[date(2016, 1, 1)],
            year_of_inc=None,
            sbir_zip="01532",
            form_d_zips=["90210"],
        )
        assert result.address_score == 0.0
        assert result.tier == "medium"

    def test_missing_signals_default_neutral(self):
        """Empty PI list, no state, no year_of_inc, no dates → all signals neutral.

        With rule-based tiers: person defaults to 0.5 (< 0.7), address
        defaults to 0.5 (< 1.0), and state defaults to 0.5 (≥ 0.5)
        → medium tier.
        """
        result = compute_form_d_confidence(
            name_score=0.60,
            pi_names=[],
            related_persons=[],
            sbir_state=None,
            biz_states=[],
            earliest_sbir_award_year=2015,
            form_d_dates=[],
            year_of_inc=None,
        )
        # composite = 0.15*0.60 + 0.35*0.5 + 0.15*0.5 + 0.15*0.5 + 0.10*0.5 + 0.10*0.5
        #           = 0.09 + 0.175 + 0.075 + 0.075 + 0.05 + 0.05 = 0.515
        assert result.tier == "medium"
        assert result.person_score is None
        assert result.state_score is None
        assert result.address_score is None
        assert result.temporal_score is None
        assert result.year_of_inc_score is None
        assert abs(result.score - 0.515) < 0.001
