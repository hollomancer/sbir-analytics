# SEC EDGAR Analysis for SBIR Companies — A Plain-English Guide

*Audience: policy staff, program officers, legislative analysts, journalists, and researchers who want to understand **what** this pipeline measures and **how** it reaches its conclusions — without needing to read code.*

---

## 1. Why This Analysis Exists

Every year the federal government awards billions of dollars through the Small
Business Innovation Research (SBIR) and Small Business Technology Transfer
(STTR) programs. A core oversight question follows each award: **what happened
next?**

- Did the company survive?
- Did it grow, attract private investment, or get acquired by a larger firm?
- Did the technology reach the market — or end up in a competitor's (or a
  foreign buyer's) portfolio?

Self-reported metrics from awardees are incomplete and inconsistent. But U.S.
public companies are legally required to file detailed, audited reports with
the Securities and Exchange Commission (SEC). Those filings are public,
time-stamped, and standardized. If an SBIR awardee was acquired, merged,
raised private capital, or went public, there is a very good chance the event
shows up in the SEC's **EDGAR** filing system.

This pipeline reads EDGAR programmatically and connects the dots between SBIR
awards and SEC-documented business events — at the scale of all ~34,500
companies that have ever received an SBIR award.

## 2. What It Detects

The analysis produces three complementary signals for each SBIR company.

| Signal | Plain-English meaning | Why it matters for policy |
|---|---|---|
| **Acquisition mention** | A public company's SEC filing names this SBIR awardee in a context suggesting an acquisition, merger, or material agreement. | Tells us whether federally funded technology transitioned to a larger firm — and which firm, and when. |
| **Investment signal (Form D)** | The company itself filed a **Form D** with the SEC disclosing a private securities sale (typical of a venture-capital or angel round). | Shows whether SBIR funding attracted follow-on private capital — a core measure of program success. |
| **Public-company match** | The SBIR company is itself a public filer with the SEC (has a "CIK" identifier and typically a stock ticker). | Lets us pull audited revenue, R&D spend, and assets to measure firm scale and trajectory. |

Roughly **28%** of SBIR companies produce at least one of these signals. The
other 72% are small private firms that (legitimately) never trigger an SEC
filing; those must be tracked through other sources (patents, federal
contracts, press releases).

## 3. How a Single Company Is Analyzed — Four Stages

Think of the pipeline as a funnel with increasingly strict filters. Each stage
reduces false positives at the cost of one more look-up.

### Stage 1 — Is this company a public SEC filer?

The pipeline searches EDGAR for the SBIR awardee's name and asks: **does this
name correspond to a real SEC filer?** Matching by name alone is noisy (many
companies share generic words like "Systems" or "Technologies"), so three
layers of filters are applied:

1. The name must match at ≥90% similarity after stripping legal suffixes like
   "Inc.", "LLC", or "/DE".
2. The awardee name must **not** be a substring of a bigger filer's name —
   e.g. "Fibertek" will not be accepted as "Thermo Fibertek".
3. The names must share at least one **distinctive** word, not just generic
   ones — e.g. "Impact Technologies" will not be accepted as "BK Technologies"
   simply because both end in "Technologies".

If all three filters pass, the pipeline records the company's CIK (the SEC's
permanent company identifier), its ticker, and its industry code (SIC).

### Stage 2 — Does anyone else's filing mention this company?

Using the SEC's full-text search ("EFTS"), the pipeline looks for the company's
name across three tiers of filings:

| Tier | Filing forms | What they typically mean |
|---|---|---|
| **Tier 1 — M&A announcements** | Form 8-K (Items 1.01 & 2.01), tender offers (SC TO-T), merger proxies (DEFM14A / PREM14A), prospectuses (Form 425) | A material agreement or completed acquisition. **Strongest** signal. 8-K filings are legally required within 4 business days of the event. |
| **Tier 2 — Annual & quarterly reports** | 10-K, 10-Q | Large companies list acquired subsidiaries and material contracts. Useful for catching acquisitions made years earlier. |
| **Tier 3 — Ownership disclosures** | SC 13D, SC 13D/A (active), SC 13G, SC 13G/A (passive) | Someone acquired ≥5% of the company — pre-acquisition interest or a major investor position. |

### Stage 3 — Does the location match?

Generic names still cause false matches. Because SBIR records include the
awardee's city, the pipeline re-runs each hit as a boolean search:
`"Company Name" AND "City"`. Mentions where the awardee's actual city also
appears in the filing are treated as **location-confirmed**; the rest are
flagged as **possible-but-unconfirmed** and kept separate.

For companies with common names, this step removes roughly **73–95%** of
initial false positives.

### Stage 4 — What does the filing actually say?

For the strongest mentions, the pipeline optionally downloads the filing text
and extracts a 500-character window around the company name. A keyword
classifier then labels the context:

- "acquired", "merger", "purchased", "definitive agreement" → acquisition
- "subsidiary", "wholly-owned" → post-acquisition disclosure
- "investment", "led the round", "participated" → investment signal
- "supplier", "contract", "vendor" → commercial relationship only
- "competitor" → mentioned adversarially; discount

This step separates, for example, "Acme Corp **acquired** Beta Labs" from
"Beta Labs is a **supplier** to Acme Corp" — two very different policy stories
that look identical from the filing metadata alone.

## 4. How to Read the Output

Every SBIR awardee gets a record with fields such as:

- `cik`, `ticker`, `sic_code` — public-filer identity (may be empty)
- `mention_count_total`, `mention_count_location_confirmed`
- `mention_type` — one of:
  - `ma_definitive` — strongest acquisition signal (8-K Items 1.01/2.01, tender offers)
  - `ma_proxy` — merger proxy statement
  - `ownership_active` / `ownership_passive` — someone crossed the 5% threshold
  - `financial_mention` — earnings reference
  - `disclosure` — regulatory disclosure
  - `filing_mention` — unclassified, needs context
- `form_d_count`, `form_d_latest_date` — private capital raises
- `revenue_usd`, `rnd_expense_usd`, `total_assets_usd` — most recent 10-K financials (public filers only)

A company with `mention_type = "ma_definitive"` plus a location-confirmed 8-K
from a named public acquirer is high-confidence evidence of an acquisition.
A company with only `filing_mention` entries and no city match is
low-confidence — worth manual review but not a reliable claim.

## 5. Policy Questions This Can Answer

- **Acquisitions.** How many SBIR awardees were acquired in the last decade?
  By which acquirers (domestic vs. foreign, prime contractors vs.
  private-equity rollups)? How long after the SBIR award did the acquisition
  occur?
- **Private capital leverage.** Which SBIR companies attracted follow-on
  private investment (Form D filings), and how does that correlate with
  agency, technology area, or award phase?
- **Commercialization.** Which SBIR companies went public? What is their
  revenue and R&D spend today?
- **Program outcomes by agency.** Do DoD SBIR awardees reach acquisition or
  IPO at different rates than DOE, NIH, or NASA awardees?
- **Foreign acquisition risk.** Among acquired SBIR companies, how many were
  bought by foreign-domiciled acquirers (useful for CFIUS and supply-chain
  policy discussions)?

## 6. What It Cannot Do — Honest Caveats

This is not a complete picture of SBIR outcomes. Key limitations:

- **Most SBIR companies are private and stay private.** If a firm is never
  acquired, never raises Reg D capital, and never goes public, EDGAR says
  nothing about it — that is a **data gap**, not a negative finding.
- **Name collisions cause false positives.** Even after three filtering
  layers and city confirmation, some residual (≈5–10%) false matches persist
  for companies with very generic names.
- **SEC full-text search has no proximity operator.** A hit on `"Acme Corp"
  AND "acquired"` means both words appear *somewhere* in the filing, not
  necessarily near each other. Stage 4 (context extraction) compensates at
  additional cost.
- **Form D is filed after the fact.** It confirms a capital raise happened
  but does not identify the investors by name unless they are named
  separately.
- **Not all acquisitions trigger an 8-K.** An 8-K is required when the target
  is "material" to the acquiring public company. A large prime acquiring a
  tiny SBIR firm may disclose it only in a later 10-K, or not individually.
- **Private acquirers do not file.** If a private-equity firm or another
  private company acquires an SBIR awardee, there is no public filing at all.

## 7. Relationship to Other Pipeline Signals

SEC EDGAR is one of six independent signals the broader pipeline uses to
assess SBIR "technology transition". Others include federal follow-on
contracts (USAspending), patent assignments (USPTO), SAM.gov entity changes,
and press-release mining. No single signal is authoritative; their
**agreement** is what produces high-confidence policy findings.

## 8. Reproducibility and Data Provenance

- **Data source:** SEC EDGAR ([sec.gov](https://www.sec.gov/edgar), public
  filings database), queried through the official EFTS, Submissions, and
  Company Facts endpoints.
- **Access model:** Public, rate-limited (10 requests per second). The
  pipeline identifies itself in a User-Agent header as required by SEC fair
  access policy.
- **Freshness:** EDGAR updates within minutes of a filing. This pipeline can
  be re-run at any cadence; results are resumable via JSONL checkpoints.
- **Audit trail:** Every mention retained in the output includes the
  accession number (a unique SEC-assigned filing identifier). Any
  finding can be traced back to the original filing at
  `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession>`.

## 9. Where to Go Next

- **For a technical reader:** see `sbir_etl/enrichers/sec_edgar/` and
  `docs/research/sec-edgar-sbir-learnings.md` for implementation details and
  validation results.
- **For a data reader:** Neo4j nodes and relationships are documented in
  `docs/schemas/`.
- **For a policy reader with a specific question:** see
  `docs/research-questions.md` for the full inventory of SBIR questions this
  pipeline is designed to answer.

---

*This document summarizes pipeline behavior as of April 2026. The underlying
filing forms, API endpoints, and classification rules are subject to change
as SEC rules and the SBIR pipeline both evolve.*
