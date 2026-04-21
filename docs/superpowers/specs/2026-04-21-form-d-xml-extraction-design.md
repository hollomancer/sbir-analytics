# Form D XML Extraction — Design Spec

**Date:** 2026-04-21
**Branch:** `claude/integrate-sec-edgar-sbir-6Krd1`
**PR:** #227

## Goal

Extract structured data from Form D XML filings for SBIR companies that
have confirmed Form D matches in the EFTS scan. This provides fundraising
trajectory data (amounts, rounds, securities types) and structured
issuer/executive information for entity resolution.

## Context

The existing EDGAR scan identifies ~3,900 SBIR companies with Form D
filings via EFTS full-text search. EFTS returns metadata only (CIK,
entity name, filing date, biz_states). The actual Form D XML at
`primary_doc.xml` contains significantly richer structured data:
offering amounts, securities types, investor counts, executive names,
and full addresses.

## Approach

Add a `--form-d-xml` second-pass to the existing `scan_sbir_edgar.py`,
following the established `--city-pass` pattern. This keeps the fast EFTS
scan separate from the slower XML fetch.

## Data Model

New `FormDOffering` model in `sbir_etl/models/sec_edgar.py`:

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

    # People (raw list for future entity resolution)
    related_persons: list[dict]       # [{name, title, city, state}]

    # Flags
    is_amendment: bool
    is_business_combination: bool
```

`CompanyEdgarProfile` gains a new field:
```python
form_d_offerings: list[FormDOffering] = Field(default_factory=list)
```

## Client Changes

### `search_form_d_filings` — extract accession number

Add `adsh` from the EFTS `_source` to the returned dict. This is already
in the response; we just aren't extracting it. No extra API call.

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

URL pattern: `https://www.sec.gov/Archives/edgar/data/{cik_padded}/{accession_no_dashes}/primary_doc.xml`

XML parsing extracts:
- `/edgarSubmission/primaryIssuer/*` — entity name, address, phone, type, year
- `/edgarSubmission/offeringData/*` — amounts, securities, investors, exemptions
- `/edgarSubmission/relatedPersonsList/relatedPersonInfo/*` — names, titles, addresses

Returns `None` on HTTP error or parse failure (same pattern as `fetch_filing_document`).

## Scan Script Changes

### New `--form-d-xml` pass

Invoked as:
```bash
python scripts/data/scan_sbir_edgar.py \
    --awards /tmp/sbir_awards_full.csv \
    --form-d-xml \
    --resume
```

With `--latest-only`:
```bash
python scripts/data/scan_sbir_edgar.py \
    --awards /tmp/sbir_awards_full.csv \
    --form-d-xml \
    --latest-only
```

#### Flow

1. Read `data/sec_edgar_scan.jsonl` (or `--output` path)
2. Filter to companies with `has_form_d == True`
3. For each company, re-query EFTS Form D search to get accession numbers
   (we need `adsh` which wasn't in the original scan output)
4. For each accession number (all filings, or latest only with `--latest-only`):
   - Fetch `primary_doc.xml` via `client.fetch_form_d_xml()`
   - Parse into `FormDOffering` dict
5. Write to `data/sec_edgar_scan.form_d_detail.jsonl` — one line per
   company, containing company_name and a `form_d_offerings` array
6. Supports `--resume` (skip companies already in output)
7. Uses `--concurrency` (default 8) with semaphore, same as main scan
8. Progress reporting every 100 companies

#### Output format

```json
{
  "company_name": "ASPEN AEROGELS, INC.",
  "form_d_cik": "1145986",
  "offering_count": 10,
  "total_raised": 85000000,
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
      ],
      ...
    }
  ]
}
```

## Estimated Performance

- ~3,900 companies with Form D matches
- Average ~4 filings per company = ~16K XML fetches (all filings mode)
- At 10 req/s with concurrency 8: ~27 minutes
- With `--latest-only`: ~4K fetches, ~7 minutes

## What This Does NOT Include

- Neo4j Person nodes or executive-company relationships (future spec)
- Cross-referencing Form D executives against SBIR contacts (future)
- Funding round classification (Series A/B/C from securities types — future)
- Aggregated fundraising timeline views (future, likely a transformer)

## Files Modified

| File | Change |
|------|--------|
| `sbir_etl/models/sec_edgar.py` | Add `FormDOffering` model, add `form_d_offerings` to `CompanyEdgarProfile` |
| `sbir_etl/enrichers/sec_edgar/client.py` | Add `accession_number` to Form D search results, add `fetch_form_d_xml()` method |
| `scripts/data/scan_sbir_edgar.py` | Add `--form-d-xml` pass, `--latest-only` flag, `run_form_d_xml_pass()` function |

## Testing

- Unit test for XML parsing (mock XML string → `FormDOffering` dict)
- Unit test for `fetch_form_d_xml` (mock HTTP response → parsed result)
- Smoke test: run `--form-d-xml --limit 5` on real data
