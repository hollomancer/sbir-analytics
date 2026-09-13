"""Tests for Form D XML parser and confidence scorer."""

from __future__ import annotations

from datetime import date

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_CORROBORATED_PERSON_V2,
    FORM_D_TIER_RULE_PERSON_OR_ZIP_V1,
    assign_form_d_tier,
    compute_form_d_confidence,
    describe_form_d_signal_scope,
    parse_form_d_xml,
    require_form_d_rule_version,
)
from tests.unit.identity.test_company_names import MUST_NOT_MATCH

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

    def test_high_confidence_with_person_and_state_match(self):
        """PI match corroborated by state overlap reaches record-level high."""
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
            related_persons=[
                {"name": "Bob Johnson", "title": "Director", "city": "Dallas", "state": "TX"}
            ],
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

    def test_person_only_match_no_longer_reaches_high(self):
        """A fuzzy person match with no corroborating signal lands on medium, not high.

        Regression test for #714: ordinary name variation (nicknames, initials,
        shared given names) clears the person-score threshold for both true and
        false matches, so a person hit alone must not be sufficient for high tier.
        Here the state mismatches and there is no ZIP data, so nothing corroborates
        the person match.
        """
        result = compute_form_d_confidence(
            name_score=0.60,
            pi_names=["Donald Young"],
            related_persons=self._RELATED,
            sbir_state="CA",
            biz_states=["MA"],  # state mismatch — no corroboration
            earliest_sbir_award_year=2020,
            form_d_dates=[date(2011, 12, 10)],  # big temporal gap
            year_of_inc=None,
        )
        assert result.person_score is not None
        assert result.person_score >= 0.70
        assert result.tier == "medium"
        assert result.rule_version == FORM_D_TIER_RULE_CORROBORATED_PERSON_V2
        assert result.state_score == 0.0

    @pytest.mark.parametrize(
        ("pi_name", "related_name"),
        [
            ("Robert Chen", "Roberta Chen"),
            ("John Smith", "Jonathan Smith"),
            ("M. Patel", "Mark Patel"),
            ("David Kim", "Daniel Kim"),
        ],
    )
    def test_realistic_person_name_collisions_require_corroboration(
        self, pi_name: str, related_name: str
    ) -> None:
        """Plausible distinct people can clear 0.70 and must not reach high alone."""

        result = compute_form_d_confidence(
            name_score=0.90,
            pi_names=[pi_name],
            related_persons=[
                {
                    "name": related_name,
                    "title": "Executive Officer",
                    "city": "Boston",
                    "state": "MA",
                }
            ],
            sbir_state="CA",
            biz_states=["MA"],
            earliest_sbir_award_year=2020,
            form_d_dates=[date(2010, 1, 1)],
            year_of_inc=None,
        )

        assert result.person_score is not None
        assert result.person_score >= 0.70
        assert result.state_score == 0.0
        assert result.address_score is None
        assert result.tier == "medium"

    def test_person_match_with_corroboration_reaches_high(self):
        """A fuzzy person match plus a corroborating state overlap still reaches high."""
        result = compute_form_d_confidence(
            name_score=0.60,
            pi_names=["Donald Young"],
            related_persons=self._RELATED,
            sbir_state="MA",
            biz_states=["MA"],  # state overlap corroborates the person hit
            earliest_sbir_award_year=2020,
            form_d_dates=[date(2011, 12, 10)],
            year_of_inc=None,
        )
        assert result.person_score is not None
        assert result.person_score >= 0.70
        assert result.state_score == 1.0
        assert result.tier == "high"

    def test_address_match_drives_high_tier(self):
        """ZIP match reaches record-level high even without a person match."""
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

    def test_absent_person_and_address_never_promote_to_high(self):
        """Missing person and address signals must never combine into high tier.

        Both default to 0.5 in the composite score, but the tier rule must check
        the real signal values — not the defaults — so two absent signals can
        never accidentally clear the 0.7/1.0 tier thresholds. Only the real state
        overlap here should drive the tier, and it can only reach medium.
        """
        result = compute_form_d_confidence(
            name_score=0.60,
            pi_names=[],
            related_persons=[],
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2015,
            form_d_dates=[date(2016, 1, 1)],
            year_of_inc=None,
        )
        assert result.person_score is None
        assert result.address_score is None
        assert result.state_score == 1.0
        assert result.tier == "medium"

    def test_historical_person_or_zip_rule_remains_named_and_reproducible(self) -> None:
        assert (
            assign_form_d_tier(
                person_score=0.8,
                address_score=0.0,
                state_score=0.0,
                rule_version=FORM_D_TIER_RULE_PERSON_OR_ZIP_V1,
            )
            == "high"
        )

    def test_unknown_tier_rule_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported Form D tier rule"):
            assign_form_d_tier(
                person_score=1.0,
                address_score=1.0,
                state_score=1.0,
                rule_version="silent-policy-drift",
            )

    def test_unknown_expected_rule_cannot_bless_a_stored_value(self) -> None:
        with pytest.raises(ValueError, match="Unsupported expected Form D tier rule"):
            require_form_d_rule_version(
                "silent-policy-drift",
                expected_rule_version="silent-policy-drift",
            )


def test_signal_scope_exposes_cross_filing_and_cross_cik_aggregation() -> None:
    scope = describe_form_d_signal_scope(
        [
            {"accession_number": "A", "cik": "000123"},
            {"accession_number": "B", "cik": "000456"},
        ]
    )

    assert scope == {
        "unit": "company-record",
        "offering_count": 2,
        "distinct_ciks": ["123", "456"],
        "signals_may_span_filings": True,
        "signals_may_span_ciks": True,
    }


# --- Adversarial audit: person-match path -----------------------------------
#
# ``compute_form_d_confidence`` has no company-name-matching function of its
# own -- ``name_score`` is a caller-supplied float that only feeds the
# composite ranking score, never the tier (see the "Composite" vs "Tier"
# comments in form_d_scoring.py). The one place inside this file where a
# fuzzy string score decides a tier is the person-match signal
# (form_d_scoring.py:282, ``fuzz.token_set_ratio`` on PI name vs Form D
# related-person name), gated by the tier rule at form_d_scoring.py:339-344:
# ``person_score >= 0.7`` (or a ZIP match) gives "high"; state overlap alone
# gives "medium"; otherwise "low".
#
# This section runs the identity primitive's MUST_NOT_MATCH pairs (see
# tests/unit/identity/test_company_names.py) through that exact code path,
# standing in for two distinct people whose names happen to share tokens the
# way these company names do -- the only case this file has that reuses the
# unguarded ``fuzz.token_set_ratio`` call the primitive audit was built to
# probe. ``sbir_state``/``biz_states`` are set to non-overlapping values so
# state_score is an explicit 0.0 rather than the None-default 0.5 fallback
# (see test_missing_signals_default_neutral above); that isolates the tier
# outcome to the person-match signal alone.
#
# Audit result (2026-09-10, re-run after #717): 8/9 pairs land on "low"
# (score < 0.7) -- the scorer working as intended. One pair, ADELPHI
# TECHNOLOGY / ADEPT TECHNOLOGY, scores person_score=0.8824, the same score
# the identity primitive documents as its own worst case (0.882, see
# test_company_names.py::test_distinct_firms_do_not_score_as_the_same_firm).
# Under the retired `person-or-zip-v1` rule that crossed into "high". The
# current `corroborated-person-v2` rule requires an exact ZIP or state
# overlap before a person score alone can reach high, so this pair now stops
# at "medium" -- the caller-threshold defect this audit found is fixed, and
# this table pins the corrected behavior.
FORM_D_PERSON_MATCH_EXPECTED_TIER = {
    "3D Control Systems, Inc.": "low",
    "ADELPHI TECHNOLOGY": "medium",  # corroboration required; see note above
    "Nanomimetics": "low",
    "Pronghorn Technologies": "low",
    "ADT Pharmaceuticals": "low",
    "COMPASS SYSTEMS": "low",
    "Linked, Inc.": "low",
    "BAL": "low",
    "SiliconCore Technology, Inc.": "low",
}


@pytest.mark.parametrize("left,right,reason", MUST_NOT_MATCH)
def test_person_match_tier_for_distinct_firms_used_as_names(
    left: str, right: str, reason: str
) -> None:
    """Feed adversarial company-name pairs through the person-match signal.

    See the module-level comment above this block for why this is the
    right adversarial probe for this file, and for the one pair (ADELPHI
    TECHNOLOGY / ADEPT TECHNOLOGY) that currently reaches "high".
    """
    result = compute_form_d_confidence(
        name_score=0.0,
        pi_names=[left],
        related_persons=[{"name": right, "title": "Executive Officer"}],
        sbir_state="CA",
        biz_states=["NY"],
        earliest_sbir_award_year=2015,
        form_d_dates=[],
        year_of_inc=None,
    )
    expected = FORM_D_PERSON_MATCH_EXPECTED_TIER[left]
    assert result.tier == expected, (
        f"{left!r} vs {right!r} scored person_score={result.person_score} "
        f"-> tier={result.tier} (expected {expected}): {reason}"
    )
