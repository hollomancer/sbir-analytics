# Form D XML Extraction & Confidence Scoring — Design Spec

**Date:** 2026-04-21
**Branch:** `claude/integrate-sec-edgar-sbir-6Krd1`
**PR:** #227

## Goal

Extract structured data from Form D XML filings for SBIR companies and
assign tiered confidence scores to Form D matches using evidence
aggregation — replacing the current binary state filter with a
multi-signal scoring framework.

## Context

The existing EDGAR scan identifies ~3,900 SBIR companies with Form D
filings via EFTS full-text search. EFTS returns metadata only (CIK,
entity name, filing date, biz_states). The actual Form D XML at
`primary_doc.xml` contains structured data: offering amounts, securities
types, investor counts, and — critically — a `relatedPersonsList` with
named officers, directors, and promoters.

### Why score, not filter

The current binary state filter trades two error types against each other:
tightening it kills true positives from companies that relocated;
loosening it readmits homographs. This is the wrong axis of optimization.

Instead, we aggregate multiple weak signals into a confidence score and
report results in tiers (High / Medium / Low). This lets downstream
consumers choose their own precision/recall tradeoff and makes the
methodology defensible under review — a critic attacks a tier, not
the headline number.

### The PI signal

SBIR awards have PI (Principal Investigator) names for 97.8% of
companies, with 98.1% in clean "First Last" format. Form D filings
require disclosure of related persons (officers, directors, promoters)
by name. Two unrelated "Apex Technologies Inc" entities filing Form D
almost never share a named officer with an SBIR PI. This is a structural
disambiguator that doesn't depend on location.

The earlier finding that "PI names show zero hits in SEC filings" was
about EFTS full-text search of corporate filing prose — a different use
case entirely. PI-to-related-person matching compares structured name
fields from two databases, which is the right shape for this problem.

## Approach

Add a `--form-d-xml` second-pass to the existing `scan_sbir_edgar.py`,
following the established `--city-pass` pattern. This keeps the fast EFTS
scan separate from the slower XML fetch. After fetching, compute a
confidence score per company using multiple signals.

## Data Model

### `FormDOffering`

New model in `sbir_etl/models/sec_edgar.py`:

```python
class FormDOffering(BaseModel):
    """Structured data extracted from a Form D XML filing."""

    # Identifiers
    cik: str
    accession_number: str
    filing_date: date

    # Issuer
    entity_name: str
    entity_type: str | None          # Corporation, LLC, LP
    year_of_inc: int | None
    jurisdiction_of_inc: str | None   # DE, CA, etc.

    # Address
    street1: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None

    # Offering details
    industry_group: str | None        # "Other Technology", "Biotechnology"
    revenue_range: str | None         # "Decline to Disclose", "$1-$5M"
    date_of_first_sale: date | None
    securities_types: list[str]       # ["debt", "equity", "options"]
    federal_exemption: str | None     # "06" = Rule 506(b), "06b" = 506(c)

    # Amounts
    total_offering_amount: float | None
    total_amount_sold: float | None
    total_remaining: float | None
    minimum_investment: float | None

    # Investors
    num_investors: int | None
    has_non_accredited: bool | None

    # People (structured for entity resolution)
    related_persons: list[dict]       # [{name, title, city, state}]

    # Flags
    is_amendment: bool
    is_business_combination: bool
```

### `FormDMatchConfidence`

New model for the confidence scoring output:

```python
class FormDMatchConfidence(BaseModel):
    """Confidence assessment for a Form D match to an SBIR company."""

    # Overall
    tier: str                         # "high", "medium", "low"
    score: float                      # 0.0–1.0 composite score

    # Individual signals (each 0.0–1.0, None if not evaluable)
    name_score: float                 # Fuzzy name match (baseline, required)
    person_score: float | None        # Best PI-to-related-person match
    person_match_detail: str | None   # e.g., "PI 'John Smith' ↔ Director 'John R. Smith' (92%)"
    state_score: float | None         # biz_states ∩ SBIR award state
    temporal_score: float | None      # Form D date vs SBIR award date plausibility
    year_of_inc_score: float | None   # year_of_inc vs earliest SBIR award year
```

### `CompanyEdgarProfile` additions

```python
form_d_offerings: list[FormDOffering] = Field(default_factory=list)
form_d_match_confidence: FormDMatchConfidence | None = Field(None)
```

## Confidence Scoring

### Signal weights

| Signal | Weight | Notes |
|--------|--------|-------|
| Name fuzzy ≥ 85% | Baseline | Required gate; already applied in EFTS pass |
| PI ↔ related_person match | Strongest | Near-pathological if present. Fuzzy match (≥85%) on normalized names. Any PI matching any related person across any Form D filing counts. |
| biz_states ∩ SBIR state ≠ ∅ | Moderate | Tolerates multi-office (any match, not all). biz_states is principal place of business, not registered agent. |
| Form D date ≥ SBIR award date | Moderate | Filing should postdate (or be within ~2 years before) earliest SBIR award. A Form D 5+ years before first award is a red flag. |
| year_of_inc ≤ SBIR award year | Weak | Sanity check. If year_of_inc postdates earliest SBIR award, almost certainly a different entity. |

### Signals explicitly excluded

- **`jurisdiction_of_inc = DE`**: Near-universal for VC-track companies.
  Uninformative as match or mismatch signal. Stored in `FormDOffering`
  for reference but not scored.

### Scoring algorithm

```python
def compute_form_d_confidence(
    name_score: float,              # from EFTS fuzzy match (0.85–1.0)
    pi_names: list[str],            # SBIR PI names for this company
    related_persons: list[dict],    # from all Form D filings
    sbir_state: str | None,         # 2-letter code
    biz_states: list[str],          # from Form D
    earliest_sbir_award_year: int,  # earliest award year
    form_d_dates: list[date],       # all Form D filing dates
    year_of_inc: int | None,        # from Form D XML
) -> FormDMatchConfidence:
```

1. **Person matching**: For each PI name, fuzzy-match against each
   related person's name (after normalizing titles like Dr./Ph.D.,
   stripping suffixes). Best match score across all pairs becomes
   `person_score`. Score of ≥85% on any pair = strong positive.

2. **State matching**: If `sbir_state` and `biz_states` both present,
   score 1.0 if any overlap, 0.0 if no overlap, None if either missing.
   Multi-state tolerance: `biz_states` can have multiple entries.

3. **Temporal plausibility**: Score based on gap between earliest
   Form D date and earliest SBIR award date.
   - Form D within 2 years before to any time after SBIR: 1.0
   - Form D 2–5 years before SBIR: 0.5
   - Form D 5+ years before SBIR: 0.0

4. **Year of incorporation**: Score 1.0 if year_of_inc ≤ earliest
   SBIR award year, 0.0 if year_of_inc > SBIR award year, None if
   year_of_inc unavailable.

5. **Composite score**: Weighted combination:
   ```
   composite = (
       0.15 * name_score +
       0.40 * (person_score or 0.5) +
       0.20 * (state_score or 0.5) +
       0.15 * (temporal_score or 0.5) +
       0.10 * (year_of_inc_score or 0.5)
   )
   ```
   Missing signals default to 0.5 (neutral) so they don't penalize
   or reward.

6. **Tier assignment**:
   - **High**: composite ≥ 0.75, OR person_score ≥ 0.85 (person match
     alone is sufficient)
   - **Medium**: composite ≥ 0.50
   - **Low**: composite < 0.50

### Impact on existing binary state filter

The current state filter in `_search_form_d_filings` (added this session)
is removed. State becomes one signal among several in the confidence
score. This means the `--form-d-xml` pass re-evaluates all EFTS Form D
matches — including ones the state filter would have dropped — and
assigns confidence tiers instead.

To support this, the main EFTS scan should stop applying the state
filter on Form D and instead pass all name-matched results through.
The confidence scoring in the `--form-d-xml` pass replaces it.

## Client Changes

### `search_form_d_filings` — extract accession number

Add `adsh` from the EFTS `_source` to the returned dict. Already in the
response; not currently extracted. No extra API call.

```python
results.append({
    "cik": cik,
    "entity_name": entity_name,
    "file_date": source.get("file_date", None),
    "form_type": "D",
    "biz_locations": source.get("biz_locations", []),
    "biz_states": source.get("biz_states", []),
    "accession_number": source.get("adsh", ""),  # NEW
})
```

### New method: `fetch_form_d_xml`

```python
async def fetch_form_d_xml(self, cik: str, accession: str) -> dict | None:
    """Fetch and parse a Form D XML filing.

    Fetches primary_doc.xml from the EDGAR archives and parses it with
    xml.etree.ElementTree into a flat dict matching FormDOffering fields.

    Uses the same retry/rate-limit pattern as fetch_filing_document.
    """
```

URL: `https://www.sec.gov/Archives/edgar/data/{cik_padded}/{accession_no_dashes}/primary_doc.xml`

XML parsing extracts:
- `/edgarSubmission/primaryIssuer/*` — entity name, address, phone, type, year
- `/edgarSubmission/offeringData/*` — amounts, securities, investors, exemptions
- `/edgarSubmission/relatedPersonsList/relatedPersonInfo/*` — names, titles, addresses

Returns `None` on HTTP error or parse failure.

## Scan Script Changes

### New `--form-d-xml` pass

```bash
# All filings, with confidence scoring
python scripts/data/scan_sbir_edgar.py \
    --awards /tmp/sbir_awards_full.csv \
    --form-d-xml \
    --resume

# Latest filing only
python scripts/data/scan_sbir_edgar.py \
    --awards /tmp/sbir_awards_full.csv \
    --form-d-xml \
    --latest-only
```

### Flow

1. Read `data/sec_edgar_scan.jsonl` (or `--output` path)
2. Filter to companies with `has_form_d == True`
3. Load PI names and earliest award year per company from awards CSV
4. For each company, re-query EFTS Form D search to get accession numbers
   (`adsh` wasn't in the original scan output)
5. For each filing (all, or latest only with `--latest-only`):
   - Fetch `primary_doc.xml` via `client.fetch_form_d_xml()`
   - Parse into `FormDOffering` dict
6. Compute `FormDMatchConfidence` using all signals
7. Write to `data/sec_edgar_scan.form_d_detail.jsonl`
8. Supports `--resume`, `--concurrency` (default 8)
9. Progress reporting every 100 companies, with tier counts

### Output format

```json
{
  "company_name": "ASPEN AEROGELS, INC.",
  "form_d_cik": "1145986",
  "offering_count": 10,
  "total_raised": 85000000,
  "match_confidence": {
    "tier": "high",
    "score": 0.91,
    "name_score": 0.95,
    "person_score": 0.92,
    "person_match_detail": "PI 'Donald Young' ↔ Director 'Donald R. Young' (92%)",
    "state_score": 1.0,
    "temporal_score": 1.0,
    "year_of_inc_score": 1.0
  },
  "offerings": [
    {
      "accession_number": "0001145986-11-000003",
      "filing_date": "2011-12-21",
      "entity_name": "ASPEN AEROGELS INC",
      "entity_type": "Corporation",
      "year_of_inc": 2008,
      "industry_group": "Other Technology",
      "total_offering_amount": 25000000,
      "total_amount_sold": 15000000,
      "securities_types": ["debt", "options"],
      "num_investors": 17,
      "related_persons": [
        {"name": "Donald R. Young", "title": "Executive Officer, Director", "state": "MA"}
      ]
    }
  ]
}
```

### Summary output

The pass prints a summary like:
```
FORM D XML PASS COMPLETE — 3,900 companies
  High confidence:   2,800 (71.8%)
  Medium confidence:  800 (20.5%)
  Low confidence:     300 (7.7%)
  XML fetch errors:   42
```

## SBIR Data Inputs

The confidence scoring needs these fields from the awards CSV:

| Field | Coverage | Use |
|-------|----------|-----|
| PI Name | 97.8% of companies (98.1% clean format) | PI-to-related-person matching |
| State | 99.99% (full names, mapped to 2-letter codes) | State overlap signal |
| Award Year | 100% | Temporal plausibility, year_of_inc sanity |

PI name normalization: strip "Dr.", "Ph.D.", "Mr.", "Mrs.", split on
double-spaces (handles "Oleg Galkin, Ph.D.  Oleg Galkin, Ph.D."
duplication pattern), take first/last only for matching.

## Estimated Performance

- ~3,900 companies with Form D matches
- Average ~4 filings per company = ~16K XML fetches (all filings mode)
- At 10 req/s with concurrency 8: ~27 minutes
- With `--latest-only`: ~4K fetches, ~7 minutes
- Confidence scoring is pure computation, negligible time

## What This Does NOT Include

- Neo4j Person nodes or executive-company relationships (future spec)
- Funding round classification (Series A/B/C from securities types)
- Aggregated fundraising timeline views (future transformer)
- Expansion of the common-word list for mention noise scoring

## Files Modified

| File | Change |
|------|--------|
| `sbir_etl/models/sec_edgar.py` | Add `FormDOffering`, `FormDMatchConfidence` models; add fields to `CompanyEdgarProfile` |
| `sbir_etl/enrichers/sec_edgar/client.py` | Add `accession_number` to Form D search results; add `fetch_form_d_xml()` method |
| `sbir_etl/enrichers/sec_edgar/enricher.py` | Add `compute_form_d_confidence()` function; remove binary state filter from `_search_form_d_filings` |
| `scripts/data/scan_sbir_edgar.py` | Add `--form-d-xml` pass, `--latest-only` flag, `run_form_d_xml_pass()` function; add `load_pi_names()`, `load_earliest_award_years()` |

## Testing

- Unit test for XML parsing (mock XML string → `FormDOffering` dict)
- Unit test for `fetch_form_d_xml` (mock HTTP response → parsed result)
- Unit test for `compute_form_d_confidence` with known signal combinations:
  - High: person match + state match + temporal match
  - Medium: state match + temporal match, no person data
  - Low: name match only, state mismatch, temporal mismatch
  - High override: person match alone (≥85%) regardless of other signals
- Smoke test: run `--form-d-xml --limit 10` on real data
