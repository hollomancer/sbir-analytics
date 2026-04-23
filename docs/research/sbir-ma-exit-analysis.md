# SBIR Company M&A Exit Analysis

**Date:** 2026-04-23
**Branch:** `claude/sbir-ma-exit-analysis`
**Research question:** A4 (M&A activity detection)

## Summary

Of 34,460 SBIR companies in the awards database, **2,249 (6.5%)
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
- **Medium tier is purely `acquisition_text`** — events where filing
  document text was fetched and acquisition language was confirmed near
  the company name.

### Medium-Tier Directional Text Refinement

The 1,178 medium-tier events were further refined by re-fetching
filing documents and applying directional regex to distinguish:

- "BigCo acquired **Company X**" → confirmed target
- "**Company X** acquired a license" → not a target (demoted to low)
- "comparable to **Company X**" → comparator (demoted to low)
- Merger agreement boilerplate naming the company as "the Company" with
  "Merger Sub" and "Acquiror" → confirmed target
- Employment/consulting agreements → not a target (demoted to low)

Results:

| Direction | Count | % | Action |
|-----------|-------|---|--------|
| Confirmed target | 662 | 56% | Keep medium |
| Ambiguous | 390 | 33% | Keep medium |
| Comparator | 56 | 5% | Demoted to low |
| Not target | 51 | 4% | Demoted to low |
| No filing found | 19 | 2% | Demoted to low |

126 false positives (11% of original medium tier) were demoted,
tightening medium from 1,178 to 1,052 events.

## Confidence Tiers (Final)

| Tier | Rule | Count |
|------|------|-------|
| High | Form D business combination OR EFTS `subsidiary` | 1,197 |
| Medium | EFTS `acquisition_text`, refined by directional analysis | 1,052 |
| Low | All other signals + demoted false positives | 2,057 |
| **Total** | | **4,306** |

Within the medium tier, 662 events (63%) are text-confirmed targets
and 390 (37%) are ambiguous (acquisition language present but direction
could not be determined).

## Exit Rate

| Filter | Companies | Rate |
|--------|-----------|------|
| Any M&A signal | 4,306 | 12.5% |
| High + Medium | 2,249 | 6.5% |
| High only | 1,197 | 3.5% |

## Exit Rate by Agency

| Agency | H+M | High | SBIR Cos | Rate (H+M) | Rate (High) |
|--------|-----|------|----------|-----------|------------|
| HHS | 936 | 473 | 12,373 | 7.6% | 3.8% |
| DoD | 675 | 369 | 14,362 | 4.7% | 2.6% |
| Education | 25 | 17 | 652 | 3.8% | 2.6% |
| NSF | 268 | 145 | 7,535 | 3.6% | 1.9% |
| USDA | 68 | 38 | 1,937 | 3.5% | 2.0% |
| DOE | 113 | 68 | 3,512 | 3.2% | 1.9% |
| DHS | 15 | 5 | 531 | 2.8% | 0.9% |
| Commerce | 25 | 14 | 928 | 2.7% | 1.5% |
| DOT | 15 | 8 | 616 | 2.4% | 1.3% |
| NASA | 90 | 48 | 3,714 | 2.4% | 1.3% |
| EPA | 17 | 10 | 736 | 2.3% | 1.4% |

HHS leads at 7.6% (H+M) — biotech/pharma is the most M&A-active
SBIR sector. DoD is second at 4.7%. Other agencies cluster around
2.3-3.8%.

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
| LIGAND PHARMACEUTICALS | 4 | Pharma |

Acquirer landscape is **highly dispersed**: ~2,600 unique acquirers.
80% buy exactly one SBIR company. No "SBIR rollup" strategy —
acquisitions are driven by individual technology fit.

## Time from First SBIR Award to M&A Exit

For H+M events with valid dates (N=2,038):

| Percentile | Years |
|-----------|-------|
| P25 | 7 |
| P50 (median) | 14 |
| P75 | 23 |
| Mean | 15.6 |

## Signal Strength

### Signal count as quality indicator

| Signals | Events | High % | Median exit gap |
|---------|--------|--------|-----------------|
| 1 | 3,046 | 22% | 14 years |
| 2 | 899 | 31% | 19 years |
| 3 | 283 | 56% | 22 years |
| 4+ | 78 | 96% | 23 years |

Multi-signal events are overwhelmingly high-confidence and correspond
to older, more established companies.

### Form D acquirer blind spot

407 Form D-only events have **0% acquirer identification** — the
filing names the target's officers but not the acquirer. Every EFTS
signal has 100% acquirer ID because the filing company is the acquirer.

### High-tier composition

| Signal | Count | % of High |
|--------|-------|-----------|
| EFTS subsidiary | 676 | 56% |
| Form D business combination | 552 | 46% |
| Overlap (both) | 31 | 3% |

Two nearly non-overlapping populations: subsidiary gives acquirer
identity; Form D gives deal size.

## Caveats

- **Medium tier precision is ~65-70%.** Directional text refinement
  removed 126 confirmed false positives (11%) and confirmed 662
  targets (56%). The remaining 390 ambiguous events (33%) could not
  be classified — acquisition language was present but direction
  could not be determined from the text window.

- **Medium tier coverage is incomplete.** Text context extraction was
  only applied when document text was fetched during the EFTS scan.
  Some genuine acquisitions may lack the `acquisition` text signal
  because their filing text was never retrieved.

- **Acquirer identification is approximate.** `mention_filers[0]` is
  the first filer that mentioned the SBIR company. Usually the
  acquirer, but could be a financial advisor or counterparty.

- **Form D business combinations lack acquirer data.** The 407
  Form-D-only events identify the target but not who acquired them.

- **Time coverage varies by signal.** EFTS covers ~2001 onward.
  Form D covers 2009-2025. The 2025-2026 event spike is likely
  an artifact of `latest_mention_date` reflecting recent filing
  activity, not actual acquisition dates.

- **Exit does not equal successful outcome.** Some events may be
  distressed sales, acqui-hires, or asset purchases.

## Data

- Events dataset: `data/sbir_ma_events.jsonl` (4,306 records)
- Medium-tier refinement: `data/sbir_ma_medium_refined.jsonl` (1,178 records)
- Detection script: `scripts/data/detect_sbir_ma_events.py`
- Refinement script: `scripts/data/refine_ma_medium_tier.py`
- Analysis script: `scripts/data/analyze_sbir_ma_exits.py`
