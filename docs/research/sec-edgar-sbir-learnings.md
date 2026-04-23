# SEC EDGAR Enrichment for SBIR Companies — Learnings

**Date:** 2026-04-19/22
**Branch:** `claude/integrate-sec-edgar-sbir-6Krd1`
**PR:** #227

## What We Built

Two-pipeline SEC EDGAR enrichment for SBIR awardees:
1. **EFTS pipeline** — filing mention detection and CIK resolution via full-text search
2. **Form D pipeline** — bulk index download, XML extraction, and confidence-scored
   entity matching using PI-to-executive person matching

## Key Technical Learnings

### EFTS API (efts.sec.gov)

- **Response format**: Hits contain `_source.ciks[]` (array) and
  `_source.display_names[]` (array like `"QUALCOMM INC/DE (QCOM) (CIK 0000804328)"`).
  NOT `entity_id`/`entity_name` as older docs suggest.
- **`items` field**: Contains 8-K item codes (e.g., `["1.01", "2.01"]`).
  Item 1.01 = material definitive agreement, 2.01 = completion of acquisition.
  This is the strongest M&A signal from metadata alone.
- **`sics` field**: Filer's SIC code. Useful for filtering REITs (6500-6799).
- **Boolean queries work**: `"Company Name" AND "City"` is supported and effective.
- **Proximity search NOT supported**: `"Company" AND "acquired"` matches if both
  words appear anywhere in a 100-page 10-K, not just near each other. Useless
  for M&A keyword qualification.
- **Rate limit**: 10 requests/second (fair-access policy). Requires User-Agent
  with contact email.
- **Throughput**: ~6.7 companies/sec with concurrent enrichment (8 companies
  in-flight, rate limiter as throttle). Sequential was ~0.4/s.
- **Transient 500s**: EFTS returns intermittent HTTP 500s (Elasticsearch
  backend load-shedding). Same queries succeed on retry. Base client now
  retries 5xx 3x with exponential backoff. Scan flags affected companies
  with `had_server_errors` for targeted re-scan via `--rescan-errors`.

### CIK Resolution (Company Name → Public Filer)

**Problem**: Fuzzy name matching at 75% threshold produces false positives.

| Query | False Match | Score | Why |
|---|---|---|---|
| Scientific Systems Company | Scientific Games Corp | 77% | Partial word overlap |
| Fibertek | Thermo Fibertek | 100% | Substring containment |
| Impact Technologies | BK Technologies | 89% | Generic word "Technologies" |

**Solution**: Three-layer filter at 90% threshold:
1. **Score ≥ 90%** after corporate suffix stripping
2. **Containment rejection** — if query is substring of a longer entity name
3. **Distinctive word overlap** — at least one non-generic word must be shared

Result: 6/6 real matches pass, 4/4 false positives rejected.

### Filing Mentions (Company Name in Other Companies' Filings)

**"Mention" ≠ "M&A"**. A company name in a filing can mean:
- **Acquisition** (10-K subsidiary list, 8-K press release)
- **Subsidiary** (Exhibit 21 listing with ownership %)
- **Customer/supplier** (10-K revenue discussion)
- **Competitor** (market analysis table)
- **Lease tenant** (REIT 8-K mentioning office building tenant)
- **Comparable transaction** (proxy statement comp table)
- **Board member bio** (prior employer mentioned in DEF 14A)

**Noise sources**:
- REITs (Vornado, Mack-Cali) — filtered by SIC code 6500-6799
- Name collisions (Fibertek ≠ Thermo Fibertek) — filtered by containment
- Mortgage pass-throughs — filtered by SIC code 6150-6199

**Signal classification** (from filing type + item codes):
- `ma_definitive`: 8-K items 1.01/2.01, SC TO-T, SC 14D9
- `ma_proxy`: DEFM14A/PREM14A (merger proxies)
- `ownership_active`: SC 13D (>5% with intent)
- `ownership_passive`: SC 13G (>5% passive)
- `financial_mention`: 8-K item 2.02
- `disclosure`: 8-K items 7.01/8.01
- `filing_mention`: unclassified (needs document fetch for context)

**Document fetch for context**: Fetching the actual filing HTML and searching
for the company name in context works well but is expensive (1 extra HTTP
request per mention). Keyword classification in surrounding 500-char window
correctly identifies acquisitions, subsidiaries, contracts, and competitors.

### Form D (Regulation D Private Capital Raises)

- Filed *after* securities are sold (not just offered)
- SBIR companies with Form D = raised venture/angel capital
- **Bulk index approach** (replaced EFTS queries): download EDGAR quarterly
  `form.idx` files (761K total Form D entries, 72 quarters, 19 seconds) and
  match company names locally. Produces 10,405 candidate matches vs 3,992
  from EFTS — wider net, scored rather than filtered.
- **XML extraction**: `primary_doc.xml` contains structured issuer data,
  offering amounts, securities types, investor counts, and — critically —
  a `relatedPersonsList` with named officers/directors/promoters.

**Form D XML fields extracted:**

| Category | Fields |
|----------|--------|
| Issuer | entityName, entityType, yearOfInc, jurisdictionOfInc |
| Address | street1, city, state, zipCode, phone |
| Offering | totalOfferingAmount, totalAmountSold, totalRemaining |
| Securities | isDebtType, isEquityType, isOptionToAcquireType |
| Investors | totalNumberAlreadyInvested, hasNonAccreditedInvestors |
| Regulatory | federalExemptionsExclusions (506b/506c), revenueRange |
| People | relatedPersonName (first/middle/last), relationship, address |

**Rate limiting on www.sec.gov archives**: The archive server throttles more
aggressively than EFTS. 600 req/min causes widespread 429s. 300 req/min
still produces periodic 429 storms. Best settings found: 120 req/min,
concurrency=2, 15s retry backoff — reduced 429s to <2% of requests.
Full 10,405-company fetch completed in ~19 hours (including laptop sleep).
The `--latest-only` flag fetches 1 filing per company instead of all,
cutting fetch volume ~3-4x.

### Form D Confidence Scoring

**Problem**: Binary state filtering is the wrong tool for Form D entity
disambiguation. Tightening state-match kills true positives from
relocations; loosening it readmits homographs. Wrong axis of optimization.

**Solution**: Rule-based tier assignment using discrete signal combinations
instead of a weighted composite score. Exploratory clustering (GMM, k-means
on the 4-signal vector) confirmed that the signals are fundamentally discrete
— person match is bimodal (yes/no), state is binary — and natural clusters
map directly to signal combinations.

**Signals computed** (all retained in the record as metadata):

| Signal | Role | Notes |
|--------|------|-------|
| Name fuzzy ≥ 85% | Baseline gate | Required for index matching |
| PI ↔ related_person match | **Primary tier driver** | Bimodal; strongest discriminator |
| ZIP code match (SBIR ↔ Form D) | **Primary tier driver** | PI-independent; 100% coverage both sides |
| biz_states ∩ SBIR state | **Secondary tier driver** | Binary match/miss |
| Form D date vs SBIR award date | Metadata only | ≤2yr=1.0, 2-5yr=0.5, >5yr=0.0 |
| year_of_inc ≤ SBIR award year | Metadata only | Missing 29% of the time |

**Tier assignment** (rule-based, two independent confirmation signals):

| Tier | Rule | Count | Rate |
|------|------|-------|------|
| High | person_score ≥ 0.7 OR address_score = 1.0 | 3,640 | 35.0% |
| Medium | neither person nor address match, state_score ≥ 0.5 | 1,120 | 10.8% |
| Low | no confirming signal | 5,645 | 54.3% |

Person match and address (ZIP) match are independent confirmation
signals — either alone is sufficient for high tier. This is critical
for HHS/NIH companies where the SBIR PI is often an academic
collaborator (8.5% have `.edu` emails) who does not appear as an
officer on the Form D filing. Address matching promoted 1,620
companies from medium to high tier, improving HHS high-only ratio
from 0.70x to 2.66x.

The composite score is still computed (weighted sum of all 6 signals)
and stored for within-tier ranking, but it no longer drives tier
assignment. Missing signals default to 0.5 (neutral).

**Why temporal was removed as a tier driver**: 81% of records score 1.0
on temporal — it doesn't discriminate. Removing it demotes ~797 records
from medium to low that had no confirming signal beyond name + timing,
while promoting ~95 records with strong person matches that were being
held back by low composite scores.

**Signals explicitly excluded from tier assignment**:
- `jurisdiction_of_inc = DE` — near-universal for VC-track companies,
  uninformative as match or mismatch signal.
- `temporal_score` — too little variance (81% score 1.0) to drive tiers;
  kept as metadata for downstream filtering.
- `year_of_inc_score` — missing 29% of the time; kept as metadata.

**Industry group exclusions**: Offerings in groups structurally
incompatible with SBIR companies are excluded from analysis: Insurance,
Lodging/Conventions, Travel/Tourism, Pooled Investment Fund, Restaurants,
Retailing. These are 85-100% low-tier (name-collision false positives).

### PI Name Matching

**Dead end for EFTS full-text search**: Searching PI names in filing prose
returns zero hits — PIs are researchers, not mentioned in corporate filings.

**Effective for Form D person matching**: SBIR PI names (97.8% coverage,
98.1% clean "First Last" format) matched against Form D `relatedPersons`
(officers, directors, promoters) is the strongest disambiguation signal.
Two unrelated companies filing Form D almost never share a named officer
with an SBIR PI.

Name normalization: strip "Dr.", "Ph.D.", "Mr.", "Jr.", single-letter
initials ("R."), duplicated names. Match via `rapidfuzz.token_set_ratio`
at ≥85% threshold.

**Key insight**: the earlier conclusion that "PI names are useless" was
about searching filing *prose* — a different use case entirely. Comparing
structured name fields from two databases (SBIR awards vs Form D filings)
is the right shape for entity resolution.

### Address Matching

**EFTS city co-occurrence**: `"Company Name" AND "City"` reduces
noise by 73-95% for generic company names in EFTS mention search.

**Form D ZIP matching**: SBIR address (100% coverage) matched against
Form D issuer address (100% coverage) by 5-digit ZIP code. This is
the strongest PI-independent confirmation signal:

| Tier | HHS ZIP match | DoD ZIP match |
|------|--------------|--------------|
| High (person-based) | 70% | 59% |
| Medium (state-only) | 67% | 46% |
| Low (name-only) | 0% | 0% |

The 0% low-tier match rate validates that low-tier records are almost
entirely false positives. The 67% HHS medium-tier match rate confirmed
that most HHS medium-tier companies were genuine matches that failed
person matching because their PI was academic.

**biz_states** (from Form D EFTS metadata or XML) is principal place of
business, not registered agent. Used as a tier signal (state match =
medium if no person/address match), not as a binary filter.

## Results at Scale (Full Scan — 34,460 Companies)

| Signal | Count | Rate |
|--------|-------|------|
| Any SEC signal | 9,973 | 28.1% |
| Filing mentions | 7,545 | 21.3% |
| Form D (Reg D capital raises) | 3,992 | 11.3% |
| Both signals | 1,564 | 4.4% |
| Server errors (5xx, partial data) | 845 | 2.4% |

### Mention Type Distribution

| Type | Count | Description |
|------|-------|-------------|
| filing_mention | 4,625 | Unclassified (generic mention in filing text) |
| ma_definitive | 2,194 | Material agreements, completed acquisitions |
| disclosure | 1,627 | Reg FD disclosures (8-K items 7.01/8.01) |
| acquisition | 1,470 | Text-confirmed acquisition context |
| financial_mention | 844 | Earnings/results mentions (8-K item 2.02) |
| contract | 733 | Customer/supplier/teaming relationships |
| investment | 695 | VC, equity stakes, funding rounds |
| subsidiary | 695 | Exhibit 21 / wholly-owned entity listings |
| ma_proxy | 675 | Merger proxies (DEFM14A/PREM14A) |
| ownership_active | 573 | SC 13D (>5% with intent) |
| ownership_passive | 327 | SC 13G (>5% passive) |
| competitor | 141 | Market analysis / peer comparisons |

### Mention Noise Filtering

**Problem**: ~9% of mention results are false positives from generic company
names matching unrelated filing text.

**Noise patterns observed**:

| Pattern | Example | Why it's noise |
|---------|---------|----------------|
| Short acronyms (≤3 chars) | LTI, MCA, BMS, STI | Match abbreviations in any filing |
| Common English words | Sediment, Informed, Ideas | Appear as regular words in 10-K prose |
| All-generic business terms | Risk Management Systems | Matches generic phrases in filings |
| High mention:award ratio | 25 mentions / 1 award | Real acquisitions have substantial award histories |

**Solution**: Two-factor `mention_noise_score` (0 = clean, higher = noisier):
1. **Name distinctiveness** (+1 to +3): short acronyms, common English words,
   all-generic phrases
2. **Mention-to-award ratio** (+1 to +2): mention_count / award_count > 2 or > 5

**Recommended threshold**: `score >= 2` is likely noise.

| | Raw | Filtered (score < 2) | Removed |
|---|---|---|---|
| Companies with mentions | 7,548 | 6,878 | 670 (8.9%) |
| M&A definitive signals | 2,194 | 1,707 | 487 |

The noise score is stored in `CompanyEdgarProfile.mention_noise_score` and
written to JSONL as `mention_noise_score`. The Neo4j loader filters mention-only
records with score >= 2. Raw data is preserved for analysis.

## Recommended Refinements

1. **City qualification for mentions**: Re-search companies with mentions
   using `"Company" AND "City"`. Separates confirmed-location matches from
   potential name collisions. One extra API call per company with mentions.

2. **Temporal clustering**: Multiple filers mentioning a company within 6 months
   = strong event signal. Single mentions over 10 years = noise.

3. **Exhibit 21 detection**: 10-K mentions specifically in `ex21*.htm` files
   are confirmed subsidiaries. Can filter by document filename in `_id` field.

4. **Filer diversity scoring**: A company mentioned by 3+ different filers
   is much more likely to be a real acquisition target than one mentioned by
   a single filer repeatedly.

5. **Expand common-word list**: The `_COMMON_ENGLISH_WORDS` set in the enricher
   is manually curated. Could be expanded with a frequency analysis of false
   positives from the full scan data.

6. **Confidence scorer tuning**: Once the full Form D XML pass completes,
   analyze the tier distribution to calibrate signal weights. The current
   weights are a starting hypothesis, not empirically tuned.

7. **Neo4j Person nodes**: The Form D XML gives us structured executive
   names and titles. Future work: create Person nodes and
   person→company relationships to enable cross-company executive tracking.

8. **Funding round classification**: Map securities types + temporal sequence
   of Form D filings to Series A/B/C rounds.

## Architecture Decisions

### EFTS Pipeline (filing mentions, CIK resolution)

- **No document fetches in bulk scan**: 5-10x slower, burns rate limit budget.
  Save for targeted second pass on companies with mentions.
- **Filing type tiers searched concurrently**: 3 parallel EFTS calls per
  company (strong M&A types, annual reports, ownership filings).
- **Concurrent enrichment**: 8 companies in-flight (configurable via
  `--concurrency`). Rate limiter on the shared client is the real throttle;
  concurrency overlaps network latency across companies.

### Form D Pipeline (bulk index, XML extraction, confidence scoring)

- **Bulk index over EFTS**: Download EDGAR quarterly `form.idx` files
  (19 seconds) instead of querying EFTS per company (50 minutes). Local
  fuzzy matching finds more candidates (10,405 vs 3,992).
- **Score, don't filter**: Confidence tiers (High/Medium/Low) replace
  binary state filtering. Downstream consumers choose their precision/recall
  tradeoff. A critic attacks a tier threshold, not the headline number.
- **PI-to-related-person matching as primary disambiguator**: Structural
  signal that doesn't depend on location. Two unrelated same-named
  companies almost never share a named officer with an SBIR PI.
- **Conservative archive rate limiting**: www.sec.gov archives throttle
  more aggressively than EFTS. 300 req/min, concurrency=2, 5 retries
  with 5s backoff. `--latest-only` flag for faster passes.

### Shared

- **JSONL checkpoint format**: Resume-safe, streamable, greppable. Supports
  `--resume` (skip done), `--rescan-errors` (retry error-affected companies).
- **Deduplication by filer**: Report distinct mentioning companies, not
  duplicate filings from the same filer.
- **Noise scoring, not filtering**: `mention_noise_score` is computed and
  stored but the raw data is preserved. Downstream consumers (Neo4j loader)
  apply the threshold. This keeps the scan data reusable for different
  analysis thresholds.

## Pipeline Summary

```
SBIR Awards CSV (34,460 companies)
    │
    ├─► EFTS Scan (scan_sbir_edgar.py)
    │     4 queries/company: CIK + 3 filing mention tiers
    │     ~6.7 companies/sec concurrent
    │     Output: sec_edgar_scan.jsonl (mentions, noise scores)
    │
    ├─► Form D Bulk Index (fetch_form_d_index.py)
    │     72 quarterly index downloads, 19 seconds total
    │     Local fuzzy matching → 10,405 candidates
    │     Output: form_d_index.jsonl (accession numbers, PI names)
    │
    └─► Form D XML Details (fetch_form_d_details.py)
          Fetch primary_doc.xml per filing
          Parse: offering amounts, executives, addresses
          Score: PI matching + state + temporal + year_of_inc
          Output: form_d_details.jsonl (tiered confidence)
```
