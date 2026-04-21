# SEC EDGAR Enrichment for SBIR Companies — Learnings

**Date:** 2026-04-19/21
**Branch:** `claude/integrate-sec-edgar-sbir-6Krd1`
**PR:** #227

## What We Built

SEC EDGAR enrichment that detects M&A activity, investment signals, and public
company matches for SBIR awardees using the EFTS full-text search API.

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
- ~13% of SBIR companies have Form D filings
- Clean signal — minimal noise, 85% fuzzy threshold on entity name is sufficient
- SBIR companies with Form D = raised venture/angel capital

### Address Matching

- **City co-occurrence is highly effective**: `"Company Name" AND "City"` reduces
  noise by 73-95% for generic company names
- Only 7/34,459 SBIR companies have multiple addresses in the database
- SBIR award address is stable per company — reliable for filtering

### PI Name Matching

- **Dead end for this dataset**: SBIR PIs are researchers, not executives
- The "Contact Name" field is the government program manager, not company personnel
- PI names show zero hits in SEC filings
- Would need a separate source of CEO/founder names (not available in SBIR data)
- SAM.gov entity registration might have POC names but not accessible without
  the full entity extract

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

1. **City qualification (high priority)**: Re-search companies with mentions
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

## Architecture Decisions

- **No document fetches in bulk scan**: 5-10x slower, burns rate limit budget.
  Save for targeted second pass on companies with mentions.
- **JSONL checkpoint format**: Resume-safe, streamable, greppable. Supports
  `--resume` (skip done), `--rescan-errors` (retry 5xx-affected companies).
- **Deduplication by filer**: Report distinct mentioning companies, not
  duplicate filings from the same filer.
- **Filing type tiers searched concurrently**: 3 parallel EFTS calls per
  company (strong M&A types, annual reports, ownership filings).
- **Concurrent enrichment**: 8 companies in-flight (configurable via
  `--concurrency`). Rate limiter on the shared client is the real throttle;
  concurrency overlaps network latency across companies.
- **Noise scoring, not filtering**: `mention_noise_score` is computed and
  stored but the raw data is preserved. Downstream consumers (Neo4j loader)
  apply the threshold. This keeps the scan data reusable for different
  analysis thresholds.
