# Form D XML Extraction & Confidence Scoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch Form D XML filings for SBIR companies matched via bulk index, extract structured offering/person data, and assign confidence tiers using PI-to-related-person matching and other signals.

**Architecture:** A new `--form-d-xml` pass in the scan pipeline reads the bulk index output (`data/form_d_index.jsonl`), fetches `primary_doc.xml` for each filing, parses into `FormDOffering` models, computes `FormDMatchConfidence` scores from PI names + state + temporal signals, and writes tiered results to JSONL.

**Tech Stack:** Python 3.11, httpx (async HTTP), xml.etree.ElementTree (XML parsing), rapidfuzz (name matching), pydantic (models)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `sbir_etl/models/sec_edgar.py` | Modify | Add `FormDOffering` and `FormDMatchConfidence` models |
| `sbir_etl/enrichers/sec_edgar/client.py` | Modify | Add `fetch_form_d_xml()` method |
| `sbir_etl/enrichers/sec_edgar/form_d_scoring.py` | Create | `parse_form_d_xml()` and `compute_form_d_confidence()` |
| `scripts/data/fetch_form_d_details.py` | Create | `--form-d-xml` pass script (reads index JSONL, fetches XMLs, scores, writes output) |
| `tests/unit/enrichers/test_form_d_scoring.py` | Create | Tests for XML parsing and confidence scoring |
| `tests/unit/enrichers/test_sec_edgar_client.py` | Modify | Add test for `fetch_form_d_xml()` |

---

### Task 1: Add FormDOffering and FormDMatchConfidence models

**Files:**
- Modify: `sbir_etl/models/sec_edgar.py:128-143`

- [ ] **Step 1: Add FormDOffering model after EdgarFormDFiling**

Add at line 144 (after the existing `EdgarFormDFiling` class):

```python
class FormDOffering(BaseModel):
    """Structured data extracted from a Form D XML filing."""

    # Identifiers
    cik: str = Field(..., description="CIK of the Form D filer")
    accession_number: str = Field(..., description="SEC accession number")
    filing_date: date = Field(..., description="Date filed with SEC")

    # Issuer
    entity_name: str = Field(..., description="Entity name from XML")
    entity_type: str | None = Field(None, description="Corporation, LLC, LP, etc.")
    year_of_inc: int | None = Field(None, description="Year of incorporation")
    jurisdiction_of_inc: str | None = Field(None, description="State/country of incorporation")

    # Address
    street1: str | None = Field(None, description="Street address")
    city: str | None = Field(None, description="City")
    state: str | None = Field(None, description="2-letter state code")
    zip_code: str | None = Field(None, description="ZIP code")
    phone: str | None = Field(None, description="Issuer phone number")

    # Offering details
    industry_group: str | None = Field(None, description="e.g., 'Other Technology', 'Biotechnology'")
    revenue_range: str | None = Field(None, description="e.g., 'Decline to Disclose', '$1-$5M'")
    date_of_first_sale: date | None = Field(None, description="When securities were first sold")
    securities_types: list[str] = Field(default_factory=list, description="e.g., ['debt', 'equity']")
    federal_exemption: str | None = Field(None, description="Reg D rule: '06'=506(b), '06b'=506(c)")

    # Amounts
    total_offering_amount: float | None = Field(None, description="Target raise amount (USD)")
    total_amount_sold: float | None = Field(None, description="Amount actually raised (USD)")
    total_remaining: float | None = Field(None, description="Amount still available (USD)")
    minimum_investment: float | None = Field(None, description="Minimum investment accepted (USD)")

    # Investors
    num_investors: int | None = Field(None, description="Number of investors")
    has_non_accredited: bool | None = Field(None, description="Whether non-accredited investors participated")

    # People
    related_persons: list[dict] = Field(
        default_factory=list,
        description="Officers/directors/promoters: [{name, title, city, state}]",
    )

    # Flags
    is_amendment: bool = Field(default=False, description="Whether this is a D/A amendment")
    is_business_combination: bool = Field(default=False, description="Business combination transaction flag")

    model_config = ConfigDict(validate_assignment=True)


class FormDMatchConfidence(BaseModel):
    """Confidence assessment for a Form D match to an SBIR company."""

    tier: str = Field(..., description="'high', 'medium', or 'low'")
    score: float = Field(..., ge=0.0, le=1.0, description="Composite confidence score")

    # Individual signals (None if not evaluable)
    name_score: float = Field(..., description="Fuzzy name match score")
    person_score: float | None = Field(None, description="Best PI-to-related-person match")
    person_match_detail: str | None = Field(None, description="e.g., \"PI 'J Smith' <> Dir 'John Smith' (92%)\"")
    state_score: float | None = Field(None, description="biz_states overlap with SBIR state")
    temporal_score: float | None = Field(None, description="Form D date vs SBIR award date plausibility")
    year_of_inc_score: float | None = Field(None, description="year_of_inc vs earliest SBIR award year")

    model_config = ConfigDict(validate_assignment=True)
```

- [ ] **Step 2: Verify model imports work**

Run: `.venv/bin/python -c "from sbir_etl.models.sec_edgar import FormDOffering, FormDMatchConfidence; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sbir_etl/models/sec_edgar.py
git commit -m "feat(edgar): add FormDOffering and FormDMatchConfidence models"
```

---

### Task 2: Add fetch_form_d_xml to EDGAR client

**Files:**
- Modify: `sbir_etl/enrichers/sec_edgar/client.py:413` (after `fetch_filing_document`)
- Test: `tests/unit/enrichers/test_sec_edgar_client.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/enrichers/test_sec_edgar_client.py`:

```python
class TestFetchFormDXml:
    """Tests for fetch_form_d_xml method."""

    SAMPLE_FORM_D_XML = """<?xml version="1.0"?>
    <edgarSubmission>
        <schemaVersion>X0704</schemaVersion>
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
            <yearOfInc>
                <value>2008</value>
            </yearOfInc>
        </primaryIssuer>
        <offeringData>
            <industryGroup>
                <industryGroupType>Other Technology</industryGroupType>
            </industryGroup>
            <issuerSize>
                <revenueRange>Decline to Disclose</revenueRange>
            </issuerSize>
            <federalExemptionsExclusions>
                <item>06</item>
            </federalExemptionsExclusions>
            <typeOfFiling>
                <newOrAmendment>
                    <isAmendment>false</isAmendment>
                </newOrAmendment>
                <dateOfFirstSale>
                    <value>2011-12-06</value>
                </dateOfFirstSale>
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
    </edgarSubmission>"""

    @pytest.mark.asyncio
    async def test_fetch_form_d_xml_success(self):
        """Should fetch and return raw XML text."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = self.SAMPLE_FORM_D_XML

        client = _make_test_client()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.fetch_form_d_xml("1145986", "0001145986-11-000003")
        assert result is not None
        assert "<entityName>ASPEN AEROGELS INC</entityName>" in result

    @pytest.mark.asyncio
    async def test_fetch_form_d_xml_404_returns_none(self):
        """Should return None on HTTP error."""
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        client = _make_test_client()
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.fetch_form_d_xml("0000000", "0000000000-00-000000")
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/enrichers/test_sec_edgar_client.py::TestFetchFormDXml -v`
Expected: FAIL — `fetch_form_d_xml` not defined

- [ ] **Step 3: Implement fetch_form_d_xml**

Add after `fetch_filing_document` (line ~413) in `sbir_etl/enrichers/sec_edgar/client.py`:

```python
    async def fetch_form_d_xml(
        self,
        cik: str,
        accession: str,
    ) -> str | None:
        """Fetch the raw XML text of a Form D filing.

        Args:
            cik: CIK (zero-padded or not).
            accession: Accession number (e.g., '0001145986-11-000003').

        Returns:
            Raw XML string, or None on error.
        """
        accession_path = accession.replace("-", "")
        cik_padded = cik.zfill(10)
        url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik_padded}/{accession_path}/primary_doc.xml"
        )

        retry_attempts = cast(int, self.api_config.get("retry_attempts", 3))
        retry_backoff = cast(float, self.api_config.get("retry_backoff_seconds", 2.0))

        @retry(
            stop=stop_after_attempt(max(1, retry_attempts)),
            wait=wait_exponential(multiplier=retry_backoff, min=retry_backoff, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _do_fetch() -> httpx.Response:
            await self._wait_for_rate_limit()
            headers = self._build_headers()
            headers["Accept"] = "application/xml, text/xml, */*"
            return await self._client.get(
                url, headers=headers, follow_redirects=True
            )

        try:
            response = await _do_fetch()
            if response.status_code != 200:
                return None
            return response.text
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug(f"Failed to fetch Form D XML {url}: {e}")
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/enrichers/test_sec_edgar_client.py::TestFetchFormDXml -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sbir_etl/enrichers/sec_edgar/client.py tests/unit/enrichers/test_sec_edgar_client.py
git commit -m "feat(edgar): add fetch_form_d_xml client method"
```

---

### Task 3: Create XML parser and confidence scorer

**Files:**
- Create: `sbir_etl/enrichers/sec_edgar/form_d_scoring.py`
- Create: `tests/unit/enrichers/test_form_d_scoring.py`

- [ ] **Step 1: Write the XML parsing test**

Create `tests/unit/enrichers/test_form_d_scoring.py`:

```python
"""Tests for Form D XML parsing and confidence scoring."""

from __future__ import annotations

from datetime import date

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    compute_form_d_confidence,
    parse_form_d_xml,
)

# Reuse the sample XML from the client test
SAMPLE_XML = """<?xml version="1.0"?>
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
        <yearOfInc>
            <value>2008</value>
        </yearOfInc>
    </primaryIssuer>
    <offeringData>
        <industryGroup>
            <industryGroupType>Other Technology</industryGroupType>
        </industryGroup>
        <issuerSize>
            <revenueRange>Decline to Disclose</revenueRange>
        </issuerSize>
        <federalExemptionsExclusions>
            <item>06</item>
        </federalExemptionsExclusions>
        <typeOfFiling>
            <newOrAmendment>
                <isAmendment>false</isAmendment>
            </newOrAmendment>
            <dateOfFirstSale>
                <value>2011-12-06</value>
            </dateOfFirstSale>
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
</edgarSubmission>"""


class TestParseFormDXml:
    def test_parses_issuer_fields(self):
        result = parse_form_d_xml(SAMPLE_XML, accession="0001145986-11-000003", filing_date="2011-12-21")
        assert result["entity_name"] == "ASPEN AEROGELS INC"
        assert result["entity_type"] == "Corporation"
        assert result["year_of_inc"] == 2008
        assert result["jurisdiction_of_inc"] == "DELAWARE"
        assert result["city"] == "NORTHBOROUGH"
        assert result["state"] == "MA"
        assert result["zip_code"] == "01532"
        assert result["phone"] == "508-691-1111"

    def test_parses_offering_data(self):
        result = parse_form_d_xml(SAMPLE_XML, accession="0001145986-11-000003", filing_date="2011-12-21")
        assert result["industry_group"] == "Other Technology"
        assert result["revenue_range"] == "Decline to Disclose"
        assert result["total_offering_amount"] == 25_000_000.0
        assert result["total_amount_sold"] == 15_000_000.0
        assert result["total_remaining"] == 10_000_000.0
        assert result["minimum_investment"] == 0.0
        assert result["num_investors"] == 17
        assert result["has_non_accredited"] is False
        assert "debt" in result["securities_types"]
        assert "options" in result["securities_types"]
        assert "equity" not in result["securities_types"]
        assert result["federal_exemption"] == "06"
        assert result["date_of_first_sale"] == "2011-12-06"
        assert result["is_amendment"] is False
        assert result["is_business_combination"] is False

    def test_parses_related_persons(self):
        result = parse_form_d_xml(SAMPLE_XML, accession="0001145986-11-000003", filing_date="2011-12-21")
        assert len(result["related_persons"]) == 1
        person = result["related_persons"][0]
        assert person["name"] == "Donald R. Young"
        assert "Executive Officer" in person["title"]
        assert "Director" in person["title"]
        assert person["state"] == "MA"

    def test_returns_none_for_invalid_xml(self):
        result = parse_form_d_xml("<not-valid>", accession="x", filing_date="2024-01-01")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = parse_form_d_xml("", accession="x", filing_date="2024-01-01")
        assert result is None


class TestComputeFormDConfidence:
    def test_high_confidence_with_person_match(self):
        """Person match alone should yield high confidence."""
        result = compute_form_d_confidence(
            name_score=0.90,
            pi_names=["Donald Young"],
            related_persons=[{"name": "Donald R. Young", "title": "Executive Officer", "state": "MA"}],
            sbir_state="MA",
            biz_states=["MA"],
            earliest_sbir_award_year=2005,
            form_d_dates=[date(2011, 12, 21)],
            year_of_inc=2008,
        )
        assert result.tier == "high"
        assert result.person_score is not None
        assert result.person_score >= 0.85
        assert "Donald" in (result.person_match_detail or "")

    def test_medium_confidence_state_only(self):
        """State match + temporal match without person data = medium."""
        result = compute_form_d_confidence(
            name_score=0.90,
            pi_names=[],
            related_persons=[{"name": "Jane Doe", "title": "CEO", "state": "CA"}],
            sbir_state="CA",
            biz_states=["CA"],
            earliest_sbir_award_year=2010,
            form_d_dates=[date(2012, 6, 1)],
            year_of_inc=2009,
        )
        assert result.tier == "medium"
        assert result.state_score == 1.0
        assert result.temporal_score == 1.0

    def test_low_confidence_state_mismatch(self):
        """State mismatch + no person match + old filing = low."""
        result = compute_form_d_confidence(
            name_score=0.86,
            pi_names=["Alice Smith"],
            related_persons=[{"name": "Bob Jones", "title": "CEO", "state": "TX"}],
            sbir_state="MA",
            biz_states=["TX"],
            earliest_sbir_award_year=2020,
            form_d_dates=[date(2010, 1, 1)],
            year_of_inc=2022,
        )
        assert result.tier == "low"
        assert result.state_score == 0.0
        assert result.year_of_inc_score == 0.0

    def test_person_match_overrides_to_high(self):
        """Even with state mismatch, strong person match = high."""
        result = compute_form_d_confidence(
            name_score=0.88,
            pi_names=["John Smith"],
            related_persons=[{"name": "John Smith", "title": "Director", "state": "TX"}],
            sbir_state="CA",
            biz_states=["TX"],
            earliest_sbir_award_year=2015,
            form_d_dates=[date(2016, 1, 1)],
            year_of_inc=None,
        )
        assert result.tier == "high"
        assert result.person_score is not None
        assert result.person_score >= 0.85

    def test_missing_signals_default_neutral(self):
        """Missing signals should not penalize or reward."""
        result = compute_form_d_confidence(
            name_score=0.90,
            pi_names=[],
            related_persons=[],
            sbir_state=None,
            biz_states=[],
            earliest_sbir_award_year=2015,
            form_d_dates=[date(2016, 1, 1)],
            year_of_inc=None,
        )
        assert result.person_score is None
        assert result.state_score is None
        assert result.year_of_inc_score is None
        assert result.tier == "medium"  # neutral defaults → ~0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/enrichers/test_form_d_scoring.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement parse_form_d_xml and compute_form_d_confidence**

Create `sbir_etl/enrichers/sec_edgar/form_d_scoring.py`:

```python
"""Form D XML parsing and confidence scoring.

Parses structured data from SEC Form D XML filings and computes
confidence scores for matching Form D filers to SBIR companies
using multiple weak signals aggregated into tiers.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from loguru import logger
from rapidfuzz import fuzz

from ...models.sec_edgar import FormDMatchConfidence

# Title prefixes/suffixes to strip before name matching
_NAME_NOISE = re.compile(
    r"^(Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Prof\.?)\s+|"
    r",?\s*(Ph\.?D\.?|M\.?D\.?|Jr\.?|Sr\.?|III?|IV|, PI)$",
    re.IGNORECASE,
)


def _text(el: ET.Element | None, tag: str) -> str | None:
    """Get text content of a child element, or None."""
    if el is None:
        return None
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _float(el: ET.Element | None, tag: str) -> float | None:
    """Get float content of a child element, or None."""
    text = _text(el, tag)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bool(el: ET.Element | None, tag: str) -> bool | None:
    """Get boolean content of a child element, or None."""
    text = _text(el, tag)
    if text is None:
        return None
    return text.lower() == "true"


def _int(el: ET.Element | None, tag: str) -> int | None:
    """Get int content of a child element, or None."""
    text = _text(el, tag)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_form_d_xml(
    xml_text: str,
    *,
    accession: str,
    filing_date: str,
) -> dict | None:
    """Parse a Form D XML filing into a flat dict.

    Args:
        xml_text: Raw XML string from primary_doc.xml.
        accession: SEC accession number.
        filing_date: Filing date string (YYYY-MM-DD).

    Returns:
        Dict with all FormDOffering fields, or None on parse error.
    """
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    issuer = root.find("primaryIssuer")
    if issuer is None:
        return None

    address = issuer.find("issuerAddress")
    offering = root.find("offeringData")
    filing_info = offering.find("typeOfFiling") if offering is not None else None
    sales = offering.find("offeringSalesAmounts") if offering is not None else None
    investors = offering.find("investors") if offering is not None else None
    securities = offering.find("typesOfSecuritiesOffered") if offering is not None else None

    # Parse year of incorporation
    year_el = issuer.find("yearOfInc")
    year_of_inc = _int(year_el, "value") if year_el is not None else None

    # Parse securities types
    sec_types = []
    if securities is not None:
        if _bool(securities, "isDebtType"):
            sec_types.append("debt")
        if _bool(securities, "isEquityType"):
            sec_types.append("equity")
        if _bool(securities, "isOptionToAcquireType"):
            sec_types.append("options")
        if _bool(securities, "isMineralPropertyType"):
            sec_types.append("mineral_property")
        if _bool(securities, "isPooledInvestmentFundType"):
            sec_types.append("pooled_fund")
        if _bool(securities, "isTenantInCommonType"):
            sec_types.append("tenant_in_common")
        if _bool(securities, "isOtherType"):
            sec_types.append("other")

    # Parse date of first sale
    date_of_first_sale = None
    if filing_info is not None:
        sale_el = filing_info.find("dateOfFirstSale")
        if sale_el is not None:
            date_of_first_sale = _text(sale_el, "value")

    # Parse related persons
    related_persons = []
    persons_list = root.find("relatedPersonsList")
    if persons_list is not None:
        for person_info in persons_list.findall("relatedPersonInfo"):
            name_el = person_info.find("relatedPersonName")
            addr_el = person_info.find("relatedPersonAddress")
            rels_el = person_info.find("relatedPersonRelationshipList")

            first = _text(name_el, "firstName") or ""
            middle = _text(name_el, "middleName") or ""
            last = _text(name_el, "lastName") or ""
            parts = [p for p in [first, middle, last] if p]
            full_name = " ".join(parts)

            titles = []
            if rels_el is not None:
                for rel in rels_el.findall("relationship"):
                    if rel.text:
                        titles.append(rel.text.strip())

            related_persons.append({
                "name": full_name,
                "title": ", ".join(titles),
                "city": _text(addr_el, "city") or "",
                "state": _text(addr_el, "stateOrCountry") or "",
            })

    # Parse amendment flag
    is_amendment = False
    if filing_info is not None:
        amend_el = filing_info.find("newOrAmendment")
        if amend_el is not None:
            is_amendment = _bool(amend_el, "isAmendment") or False

    return {
        "cik": _text(issuer, "cik") or "",
        "accession_number": accession,
        "filing_date": filing_date,
        "entity_name": _text(issuer, "entityName") or "",
        "entity_type": _text(issuer, "entityType"),
        "year_of_inc": year_of_inc,
        "jurisdiction_of_inc": _text(issuer, "jurisdictionOfInc"),
        "street1": _text(address, "street1") if address else None,
        "city": _text(address, "city") if address else None,
        "state": _text(address, "stateOrCountry") if address else None,
        "zip_code": _text(address, "zipCode") if address else None,
        "phone": _text(issuer, "issuerPhoneNumber"),
        "industry_group": _text(
            offering.find("industryGroup") if offering is not None else None,
            "industryGroupType",
        ),
        "revenue_range": _text(
            offering.find("issuerSize") if offering is not None else None,
            "revenueRange",
        ),
        "date_of_first_sale": date_of_first_sale,
        "securities_types": sec_types,
        "federal_exemption": _text(
            offering.find("federalExemptionsExclusions") if offering is not None else None,
            "item",
        ),
        "total_offering_amount": _float(sales, "totalOfferingAmount") if sales else None,
        "total_amount_sold": _float(sales, "totalAmountSold") if sales else None,
        "total_remaining": _float(sales, "totalRemaining") if sales else None,
        "minimum_investment": _float(offering, "minimumInvestmentAccepted") if offering else None,
        "num_investors": _int(investors, "totalNumberAlreadyInvested") if investors else None,
        "has_non_accredited": _bool(investors, "hasNonAccreditedInvestors") if investors else None,
        "related_persons": related_persons,
        "is_amendment": is_amendment,
        "is_business_combination": _bool(
            offering.find("businessCombinationTransaction") if offering is not None else None,
            "isBusinessCombinationTransaction",
        ) or False,
    }


def _normalize_person_name(name: str) -> str:
    """Normalize a person name for fuzzy matching.

    Strips titles (Dr., Ph.D., Jr.), middle initials with periods,
    and normalizes whitespace.
    """
    cleaned = _NAME_NOISE.sub("", name).strip()
    # Remove standalone single-letter initials (e.g., "R." in "Donald R. Young")
    cleaned = re.sub(r"\b[A-Z]\.\s*", "", cleaned)
    return " ".join(cleaned.split())


def _best_person_match(
    pi_names: list[str],
    related_persons: list[dict],
) -> tuple[float, str | None]:
    """Find the best fuzzy match between SBIR PI names and Form D persons.

    Returns (best_score_0_to_1, detail_string_or_None).
    """
    if not pi_names or not related_persons:
        return 0.0, None

    best_score = 0.0
    best_detail = None

    for pi_raw in pi_names:
        pi_norm = _normalize_person_name(pi_raw)
        if len(pi_norm) < 3:
            continue
        for person in related_persons:
            person_name = person.get("name", "")
            person_norm = _normalize_person_name(person_name)
            if len(person_norm) < 3:
                continue

            score = fuzz.token_set_ratio(pi_norm.upper(), person_norm.upper())
            if score > best_score:
                best_score = score
                title = person.get("title", "")
                best_detail = f"PI '{pi_raw}' <> {title} '{person_name}' ({score}%)"

    return best_score / 100.0, best_detail


def compute_form_d_confidence(
    name_score: float,
    pi_names: list[str],
    related_persons: list[dict],
    sbir_state: str | None,
    biz_states: list[str],
    earliest_sbir_award_year: int,
    form_d_dates: list[date],
    year_of_inc: int | None,
) -> FormDMatchConfidence:
    """Compute confidence score for a Form D match to an SBIR company.

    Aggregates multiple weak signals into a composite score and tier.

    Args:
        name_score: Fuzzy name match score (0.0-1.0) from index matching.
        pi_names: SBIR PI names for this company.
        related_persons: All related persons across all Form D filings.
        sbir_state: 2-letter state from SBIR award, or None.
        biz_states: Business states from Form D filings.
        earliest_sbir_award_year: Year of earliest SBIR award.
        form_d_dates: Filing dates of all Form D filings.
        year_of_inc: Year of incorporation from Form D XML, or None.

    Returns:
        FormDMatchConfidence with tier, score, and individual signals.
    """
    # 1. Person matching
    person_score_raw, person_detail = _best_person_match(pi_names, related_persons)
    person_score = person_score_raw if (pi_names and related_persons) else None

    # 2. State matching
    state_score: float | None = None
    if sbir_state and biz_states:
        sbir_upper = sbir_state.upper()
        state_score = 1.0 if any(s.upper() == sbir_upper for s in biz_states) else 0.0

    # 3. Temporal plausibility
    temporal_score: float | None = None
    if form_d_dates:
        earliest_fd_year = min(d.year for d in form_d_dates)
        gap = earliest_sbir_award_year - earliest_fd_year  # positive = FD before SBIR
        if gap <= 2:
            # Form D within 2 years before or any time after SBIR
            temporal_score = 1.0
        elif gap <= 5:
            temporal_score = 0.5
        else:
            temporal_score = 0.0

    # 4. Year of incorporation
    yoi_score: float | None = None
    if year_of_inc is not None:
        yoi_score = 1.0 if year_of_inc <= earliest_sbir_award_year else 0.0

    # 5. Composite score
    composite = (
        0.15 * name_score
        + 0.40 * (person_score if person_score is not None else 0.5)
        + 0.20 * (state_score if state_score is not None else 0.5)
        + 0.15 * (temporal_score if temporal_score is not None else 0.5)
        + 0.10 * (yoi_score if yoi_score is not None else 0.5)
    )

    # 6. Tier assignment
    if (person_score is not None and person_score >= 0.85) or composite >= 0.75:
        tier = "high"
    elif composite >= 0.50:
        tier = "medium"
    else:
        tier = "low"

    return FormDMatchConfidence(
        tier=tier,
        score=round(composite, 4),
        name_score=round(name_score, 4),
        person_score=round(person_score, 4) if person_score is not None else None,
        person_match_detail=person_detail if person_score and person_score >= 0.5 else None,
        state_score=state_score,
        temporal_score=temporal_score,
        year_of_inc_score=yoi_score,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/enrichers/test_form_d_scoring.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add sbir_etl/enrichers/sec_edgar/form_d_scoring.py tests/unit/enrichers/test_form_d_scoring.py
git commit -m "feat(edgar): add Form D XML parser and confidence scorer"
```

---

### Task 4: Create the Form D details fetch script

**Files:**
- Create: `scripts/data/fetch_form_d_details.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Fetch Form D XML details and compute confidence scores for SBIR matches.

Reads the bulk index output (data/form_d_index.jsonl), fetches
primary_doc.xml for each filing, parses structured data, and computes
confidence tiers using PI-to-related-person matching and other signals.

Usage:
    # Full fetch (all filings per company)
    python scripts/data/fetch_form_d_details.py

    # Latest filing only (faster)
    python scripts/data/fetch_form_d_details.py --latest-only

    # Resume from partial run
    python scripts/data/fetch_form_d_details.py --resume

    # Custom input/output
    python scripts/data/fetch_form_d_details.py \
        --input data/form_d_index.jsonl \
        --output data/form_d_details.jsonl
"""

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sbir_etl.enrichers.sec_edgar.client import EdgarAPIClient
from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    compute_form_d_confidence,
    parse_form_d_xml,
)


def load_earliest_award_years(awards_csv: str) -> dict[str, int]:
    """Load the earliest SBIR award year per company."""
    years: dict[str, int] = {}
    with open(awards_csv, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            name = row.get("Company", "").strip()
            year_str = row.get("Award Year", "").strip()
            if not name or not year_str:
                continue
            try:
                year = int(year_str)
            except ValueError:
                continue
            if name not in years or year < years[name]:
                years[name] = year
    return years


def load_checkpoint(path: Path) -> set[str]:
    """Load already-processed company names from output file."""
    done: set[str] = set()
    if not path.exists():
        return done
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                done.add(rec["company_name"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Form D XML details and compute confidence scores",
    )
    parser.add_argument(
        "--input", default="data/form_d_index.jsonl",
        help="Input JSONL from fetch_form_d_index.py",
    )
    parser.add_argument(
        "--output", default="data/form_d_details.jsonl",
        help="Output JSONL with XML details and confidence scores",
    )
    parser.add_argument("--awards", default="/tmp/sbir_awards_full.csv",
                        help="SBIR awards CSV (for earliest award year)")
    parser.add_argument("--latest-only", action="store_true",
                        help="Fetch only the latest Form D filing per company")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing output")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Companies to process concurrently")
    parser.add_argument("--contact-email", default="conrad@hollomon.dev",
                        help="Email for SEC User-Agent")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"Error: {input_path} not found. Run fetch_form_d_index.py first.")
        sys.exit(1)

    # Load input data
    print(f"Loading Form D index from {input_path}...")
    companies = []
    with open(input_path) as f:
        for line in f:
            companies.append(json.loads(line))
    print(f"  {len(companies):,} companies with Form D matches")

    # Load earliest award years
    print(f"Loading award years from {args.awards}...")
    award_years = load_earliest_award_years(args.awards)
    print(f"  {len(award_years):,} companies with award year data")

    # Load checkpoint
    done: set[str] = set()
    if args.resume:
        done = load_checkpoint(output_path)
        print(f"  Resuming: {len(done):,} already processed")

    remaining = [c for c in companies if c["company_name"] not in done]
    print(f"  {len(remaining):,} companies to process\n")

    # Initialize client
    config = {
        "efts_url": "https://efts.sec.gov/LATEST",
        "rate_limit_per_minute": 600,
        "timeout_seconds": 30,
        "contact_email": args.contact_email,
    }
    client = EdgarAPIClient(config=config)

    # Process
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    tiers = {"high": 0, "medium": 0, "low": 0}
    fetch_errors = 0
    processed = 0
    start_time = time.time()

    async def process_company(company: dict, out) -> None:
        nonlocal fetch_errors, processed

        async with semaphore:
            name = company["company_name"]
            pi_names = company.get("pi_names", [])
            sbir_state = company.get("state")
            earliest_year = award_years.get(name, 2000)

            filings = company.get("form_d_filings", [])
            if args.latest_only:
                filings = filings[-1:]  # sorted by date, last is latest

            # Fetch and parse XML for each filing
            offerings = []
            all_persons = []
            all_biz_states = set()
            all_dates = []
            year_of_inc = None
            best_name_score = 0.0

            for filing in filings:
                cik = filing["cik"]
                accession = filing["accession_number"]
                filing_date = filing["date_filed"]

                # Compute name score from filer name vs SBIR name
                from rapidfuzz import fuzz as _fuzz
                score = _fuzz.token_set_ratio(
                    name.upper(), filing["filer_name"].upper()
                ) / 100.0
                if score > best_name_score:
                    best_name_score = score

                xml_text = await client.fetch_form_d_xml(cik, accession)
                if xml_text is None:
                    async with write_lock:
                        fetch_errors += 1
                    continue

                parsed = parse_form_d_xml(
                    xml_text, accession=accession, filing_date=filing_date,
                )
                if parsed is None:
                    continue

                offerings.append(parsed)
                all_persons.extend(parsed.get("related_persons", []))
                if parsed.get("state"):
                    all_biz_states.add(parsed["state"])
                try:
                    all_dates.append(date.fromisoformat(filing_date))
                except ValueError:
                    pass
                if parsed.get("year_of_inc") is not None and year_of_inc is None:
                    year_of_inc = parsed["year_of_inc"]

            # Compute confidence
            if best_name_score < 0.85:
                best_name_score = 0.85  # minimum gate from index matching

            confidence = compute_form_d_confidence(
                name_score=best_name_score,
                pi_names=pi_names,
                related_persons=all_persons,
                sbir_state=sbir_state,
                biz_states=sorted(all_biz_states),
                earliest_sbir_award_year=earliest_year,
                form_d_dates=all_dates,
                year_of_inc=year_of_inc,
            )

            # Compute total raised across all offerings
            total_raised = sum(
                o.get("total_amount_sold") or 0 for o in offerings
            )

            rec = {
                "company_name": name,
                "form_d_cik": filings[0]["cik"] if filings else None,
                "offering_count": len(offerings),
                "total_raised": total_raised if total_raised > 0 else None,
                "match_confidence": confidence.model_dump(),
                "offerings": offerings,
            }

            async with write_lock:
                tiers[confidence.tier] += 1
                processed += 1
                out.write(json.dumps(rec) + "\n")
                out.flush()

    # Process in batches
    batch_size = 100
    with open(output_path, "a" if args.resume else "w") as out:
        for batch_start in range(0, len(remaining), batch_size):
            batch = remaining[batch_start:batch_start + batch_size]
            tasks = [process_company(c, out) for c in batch]
            await asyncio.gather(*tasks)

            elapsed = time.time() - start_time
            done_count = batch_start + len(batch)
            rate = done_count / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - done_count) / rate / 60 if rate > 0 else 0
            print(
                f"  {processed:,}/{len(remaining):,} ({rate:.1f}/s, ETA {eta:.0f}min) "
                f"high={tiers['high']} med={tiers['medium']} low={tiers['low']} "
                f"xml_err={fetch_errors}"
            )

    await client.aclose()
    elapsed = time.time() - start_time

    # Summary
    total = sum(tiers.values())
    print(f"\n{'=' * 60}")
    print(f"FORM D XML PASS COMPLETE — {total:,} companies in {elapsed / 60:.1f} min")
    print(f"{'=' * 60}")
    print(f"High confidence:   {tiers['high']:,} ({tiers['high']/max(total,1)*100:.1f}%)")
    print(f"Medium confidence:  {tiers['medium']:,} ({tiers['medium']/max(total,1)*100:.1f}%)")
    print(f"Low confidence:     {tiers['low']:,} ({tiers['low']/max(total,1)*100:.1f}%)")
    print(f"XML fetch errors:   {fetch_errors:,}")
    print(f"Output:             {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify script parses**

Run: `.venv/bin/python3 scripts/data/fetch_form_d_details.py --help`
Expected: help text with all options

- [ ] **Step 3: Commit**

```bash
git add scripts/data/fetch_form_d_details.py
git commit -m "feat(edgar): add Form D XML fetch and confidence scoring script"
```

---

### Task 5: Smoke test on real data

**Files:** None (testing only)

- [ ] **Step 1: Run all unit tests**

Run: `.venv/bin/python -m pytest tests/unit/enrichers/test_form_d_scoring.py tests/unit/enrichers/test_sec_edgar_client.py tests/unit/enrichers/test_sec_edgar_enricher.py -v`
Expected: all PASS

- [ ] **Step 2: Run smoke test with 10 companies**

Run:
```bash
# Create a small test input from the bulk index
head -10 data/form_d_index.jsonl > /tmp/form_d_smoke_test_input.jsonl

.venv/bin/python3 scripts/data/fetch_form_d_details.py \
    --input /tmp/form_d_smoke_test_input.jsonl \
    --output /tmp/form_d_smoke_test_output.jsonl \
    --awards /tmp/sbir_awards_full.csv \
    --concurrency 4
```

Expected: completes with tier counts, no crashes

- [ ] **Step 3: Inspect output quality**

Run:
```bash
.venv/bin/python3 -c "
import json
with open('/tmp/form_d_smoke_test_output.jsonl') as f:
    for line in f:
        r = json.loads(line)
        c = r['match_confidence']
        print(f'{r[\"company_name\"]:40s} tier={c[\"tier\"]:6s} score={c[\"score\"]:.2f} person={c.get(\"person_score\", \"n/a\")} offerings={r[\"offering_count\"]}')
"
```

Expected: mix of tiers, person scores populated where PI data exists

- [ ] **Step 4: Final commit with any smoke-test fixes**

```bash
git add -u
git commit -m "fix(edgar): smoke test fixes for Form D XML pass"
```

(Skip this step if no fixes needed)

- [ ] **Step 5: Push**

```bash
git push
```
