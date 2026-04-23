# SBIR Company M&A Exit Analysis

**Date:** 2026-04-23
**Branch:** `claude/sbir-ma-exit-analysis`
**Research question:** A4 (M&A activity detection)

## Summary

Of 34,460 SBIR companies in the awards database, **2,375 (6.9%)
show M&A signals** at high or medium confidence, and **1,197 (3.5%)
at high confidence only**. Median time from first SBIR award to
M&A event is **14 years** (H+M).

## Methodology

Two-layer signal extraction from SEC EDGAR data:

**Layer 1 — Form D business combinations** (high confidence): SBIR
companies whose Form D filing has `is_business_combination = True`.
Self-reported by the issuer. 552 companies.

**Layer 2 — EFTS mention classification** (variable confidence): SBIR
companies mentioned in other companies' SEC filings with M&A-relevant
context. Signal types ranked by confidence:

| Signal | Tier | Meaning |
|--------|------|---------|
| `subsidiary` (Exhibit 21) | High | Listed as subsidiary = already acquired |
| `acquisition` (text context) | Medium | Filing text confirms acquisition language |
| `ma_definitive` (8-K 1.01/2.01) | Low | Material agreement — could be contract, not acquisition |
| `ma_proxy` (DEFM14A/PREM14A) | Low | Merger proxy — may be comp table entry |
| `ownership_active` (SC 13D) | Low | >5% stake with intent — pre-acquisition |

`ownership_passive` (SC 13G) is excluded — passive stakes are not exits.

### Tier Refinement

The initial tier boundaries were refined through signal quality analysis:

- **`ma_definitive` alone was demoted from medium to low.** 8-K item
  1.01 fires for any material contract, not just acquisitions. Estimated
  precision for single-signal `ma_definitive` is ~30-40% for actual M&A.
- **`ma_definitive` multi-signal (without `acquisition_text`) was also
  demoted.** Corroborating filing-type signals don't confirm acquisition
  intent — they corroborate "mentioned in M&A-related filing types."
- **Medium tier is now purely `acquisition_text`** — events where filing
  document text was fetched and acquisition language was confirmed near
  the company name.

## Confidence Tiers

| Tier | Rule | Count |
|------|------|-------|
| High | Form D business combination OR EFTS `subsidiary` | 1,197 |
| Medium | EFTS `acquisition_text` present | 1,178 |
| Low | All other M&A signals | 1,931 |
| **Total** | | **4,306** |

## Exit Rate

| Filter | Companies | Rate |
|--------|-----------|------|
| Any M&A signal | 4,306 | 12.5% |
| High + Medium | 2,375 | 6.9% |
| High only | 1,197 | 3.5% |

## Exit Rate by Agency

| Agency | H+M | High | SBIR Cos | Rate (H+M) | Rate (High) |
|--------|-----|------|----------|-----------|------------|
| HHS | 996 | 473 | 12,373 | 8.0% | 3.8% |
| DoD | 715 | 369 | 14,362 | 5.0% | 2.6% |
| Education | 25 | 17 | 652 | 3.8% | 2.6% |
| NSF | 277 | 145 | 7,535 | 3.7% | 1.9% |
| USDA | 72 | 38 | 1,937 | 3.7% | 2.0% |
| DOE | 119 | 68 | 3,512 | 3.4% | 1.9% |
| DHS | 16 | 5 | 531 | 3.0% | 0.9% |
| DOT | 17 | 8 | 616 | 2.8% | 1.3% |
| Commerce | 25 | 14 | 928 | 2.7% | 1.5% |
| NASA | 93 | 48 | 3,714 | 2.5% | 1.3% |
| EPA | 18 | 10 | 736 | 2.4% | 1.4% |

HHS leads at 8.0% (H+M) — biotech/pharma is the most M&A-active
SBIR sector. DoD is second at 5.0%. Other agencies cluster around
2.5-3.8%.

## Top Acquirers (H+M, where identified)

| Acquirer | Acquisitions | Sector |
|----------|-------------|--------|
| AMETEK INC | 7 | Defense/industrial |
| SEROLOGICALS CORP | 5 | Life sciences |
| TELEDYNE TECHNOLOGIES | 5 | Defense |
| HERCULES CAPITAL | 5 | Financial |
| JANEL CORP | 5 | Logistics |
| IPG PHOTONICS | 4 | Photonics |
| AGILENT TECHNOLOGIES | 4 | Life sciences instruments |
| LIFE TECHNOLOGIES | 4 | Biotech |
| LIGAND PHARMACEUTICALS | 4 | Pharma |

Acquirer landscape is **highly dispersed**: 2,643 unique acquirers
for 3,418 identified acquisitions. 80% buy exactly one SBIR company.
Top 10 acquirers account for only 2% of exits. No "SBIR rollup"
strategy — acquisitions are driven by individual technology fit.

## Time from First SBIR Award to M&A Exit

For H+M events with valid dates (N=2,156):

| Percentile | Years |
|-----------|-------|
| P25 | 7 |
| P50 (median) | 14 |
| P75 | 23 |
| Mean | 15.6 |

## Signal Strength Analysis

### Signal count as quality indicator

| Signals | Events | High % | Median exit gap |
|---------|--------|--------|-----------------|
| 1 | 3,046 | 22% | 14 years |
| 2 | 899 | 31% | 19 years |
| 3 | 283 | 56% | 22 years |
| 4+ | 78 | 96% | 23 years |

Multi-signal events are overwhelmingly high-confidence and correspond
to older, more established companies. More SEC paper trail accumulates
over time, so older exits are better-documented.

### Form D acquirer blind spot

407 Form D-only events have **0% acquirer identification** — the
filing names the target's officers but not the acquirer. Every EFTS
signal has 100% acquirer ID because the filing company is the acquirer.
For Form D-only high-tier events, the `related_persons` field could
potentially identify the acquirer by detecting new officers/directors
who appeared on the business combination filing — future enrichment.

### Form D corroboration rate

Only 145 of 552 Form D business combinations (26%) have EFTS
corroboration. The other 74% are Form D-only. Possible reasons:
the acquirer is private (no SEC filings), the acquisition was too
small for an 8-K, or the business combination flag was checked
incorrectly.

### High-tier composition

| Signal | Count | % of High |
|--------|-------|-----------|
| EFTS subsidiary | 676 | 56% |
| Form D business combination | 552 | 46% |
| Overlap (both) | 31 | 3% |

Two nearly non-overlapping populations with different strengths:
subsidiary gives acquirer identity; Form D gives deal size.

## Exit Rate by SBIR Funding Amount

| Funding Bucket | SBIR Cos | Exits (H+M) | Exit Rate |
|---------------|----------|-------------|-----------|
| < $250K | 12,376 | 1,665 | 13.5% |
| $250K - $1M | 9,199 | 1,000 | 10.9% |
| $1M - $5M | 9,587 | 842 | 8.8% |
| $5M - $20M | 2,695 | 258 | 9.6% |
| > $20M | 600 | 60 | 10.0% |

Smaller SBIR awardees are acquired at a higher rate — likely
reflecting acqui-hires and early-stage technology purchases before
companies grow large enough to remain independent.

## Caveats

- **Medium tier precision is ~50-60%.** The `acquisition_text` signal
  confirms acquisition language near the company name but does not
  distinguish whether the SBIR company was the target ("acquired
  Company X"), a licensor ("Company X acquired a license"), or a
  comparator ("comparable to Company X"). A future refinement pass
  could re-fetch filing text and apply directional regex to improve
  precision to an estimated ~70-80%.

- **Medium tier coverage is incomplete.** Text context extraction was
  only applied when document text was fetched during the EFTS scan.
  Some genuine acquisitions may lack the `acquisition` text signal
  because their filing text was never retrieved.

- **Acquirer identification is approximate.** `mention_filers[0]` is
  the first filer that mentioned the SBIR company. Usually the
  acquirer, but could be a financial advisor or counterparty.

- **Form D business combinations lack acquirer data.** The 407
  Form-D-only events identify the target but not the acquirer.

- **Time coverage varies by signal.** EFTS covers ~2001 onward.
  Form D covers 2009-2025. The 2025-2026 event spike is likely
  an artifact of `latest_mention_date` reflecting recent filing
  activity, not actual acquisition dates.

- **Exit does not equal successful outcome.** Some events may be
  distressed sales, acqui-hires, or asset purchases.

## Data

- Events dataset: `data/sbir_ma_events.jsonl` (4,306 records)
- Detection script: `scripts/data/detect_sbir_ma_events.py`
- Analysis script: `scripts/data/analyze_sbir_ma_exits.py`
