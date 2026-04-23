# SBIR Company M&A Exit Analysis

**Date:** 2026-04-23
**Branch:** `claude/sbir-ma-exit-analysis`
**Research question:** A4 (M&A activity detection)

## Summary

Of 34,460 SBIR companies in the awards database, **3,825 (11.1%)
show M&A signals** at high or medium confidence, and **1,197 (3.5%)
at high confidence only**. Median time from first SBIR award to
M&A event is **16 years**.

## Methodology

Two-layer signal extraction from SEC EDGAR data:

**Layer 1 — Form D business combinations** (high confidence): SBIR
companies whose Form D filing has `is_business_combination = True`.
Self-reported by the issuer. 552 companies.

**Layer 2 — EFTS mention classification** (variable confidence): SBIR
companies mentioned in other companies' SEC filings with M&A-relevant
context. Signal types ranked by confidence:

| Signal | Confidence | Meaning |
|--------|-----------|---------|
| `subsidiary` (Exhibit 21) | High | Listed as subsidiary = already acquired |
| `acquisition` (text context) | Medium | Filing text confirms acquisition language |
| `ma_definitive` (8-K 1.01/2.01) | Medium | Material agreement / completed acquisition |
| `ma_proxy` (DEFM14A/PREM14A) | Low | Merger proxy — may be comp table entry |
| `ownership_active` (SC 13D) | Low | >5% stake with intent — pre-acquisition |

Events are deduplicated by company name. When both layers have a
signal for the same company, they are merged into one event.
`ownership_passive` (SC 13G) is excluded — passive stakes are not exits.

**Acquirer identification**: For EFTS signals, the filing company
(`mention_filers[0]`) is the acquirer candidate. For Form D-only events,
acquirer is not directly identifiable from the filing.

## Confidence Tiers

| Tier | Rule | Count |
|------|------|-------|
| High | Form D business combination OR EFTS `subsidiary` | 1,197 |
| Medium | EFTS `ma_definitive` or `acquisition` text | 2,628 |
| Low | `ownership_active` or `ma_proxy` only | 481 |
| **Total** | | **4,306** |

## Exit Rate

| Filter | Companies | Rate |
|--------|-----------|------|
| Any M&A signal | 4,306 | 12.5% |
| High + Medium | 3,825 | 11.1% |
| High only | 1,197 | 3.5% |

## Exit Rate by Agency

| Agency | H+M | High | SBIR Cos | Rate (H+M) | Rate (High) |
|--------|-----|------|----------|-----------|------------|
| HHS | 1,578 | 473 | 12,373 | 12.8% | 3.8% |
| DoD | 1,141 | 369 | 14,362 | 7.9% | 2.6% |
| DOE | 208 | 68 | 3,512 | 5.9% | 1.9% |
| Education | 38 | 17 | 652 | 5.8% | 2.6% |
| NSF | 437 | 145 | 7,535 | 5.8% | 1.9% |
| USDA | 110 | 38 | 1,937 | 5.7% | 2.0% |
| NASA | 186 | 48 | 3,714 | 5.0% | 1.3% |
| Commerce | 44 | 14 | 928 | 4.7% | 1.5% |
| DHS | 24 | 5 | 531 | 4.5% | 0.9% |
| EPA | 30 | 10 | 736 | 4.1% | 1.4% |
| DOT | 24 | 8 | 616 | 3.9% | 1.3% |

HHS leads at 12.8% (H+M) — consistent with biotech/pharma being the
most M&A-active sector. DoD is second at 7.9%. The remaining agencies
cluster around 4-6%.

## Top Acquirers (H+M, where identified)

| Acquirer | Acquisitions |
|----------|-------------|
| TITAN CORP | 8 |
| SEROLOGICALS CORP | 7 |
| KRATOS DEFENSE & SECURITY SOLUTIONS | 7 |
| CACI INTERNATIONAL | 7 |
| TELEDYNE TECHNOLOGIES | 7 |
| AMETEK INC | 7 |
| BRUKER CORP | 6 |
| INTEGRA LIFESCIENCES | 6 |
| ADVENTRX PHARMACEUTICALS | 6 |
| LABORATORY CORP OF AMERICA | 6 |
| LIGAND PHARMACEUTICALS | 6 |
| HERCULES CAPITAL | 6 |
| PLUG POWER | 6 |
| MERCURY SYSTEMS | 5 |
| L3 TECHNOLOGIES | 5 |

The top acquirers split into two clear groups: **defense primes**
(Kratos, CACI, Teledyne, Mercury Systems, L3) and **life sciences
consolidators** (Serologicals, Integra LifeSciences, LabCorp, Ligand,
Bruker). This mirrors the HHS vs DoD agency split.

## Time from First SBIR Award to M&A Exit

For H+M events with valid dates (N=3,532):

| Percentile | Years |
|-----------|-------|
| P25 | 9 |
| P50 (median) | 16 |
| P75 | 24 |
| Mean | 17.0 |

The median 16-year gap suggests M&A exits are a long-tail outcome —
companies receive SBIR funding early in their lifecycle and are
acquired much later, often after building substantial value through
multiple funding rounds and product development cycles.

## Signal Co-occurrence

Most events are single-signal:

| Signal Combination | Count |
|-------------------|-------|
| `efts_ma_definitive` only | 1,157 |
| `efts_acquisition_text` only | 734 |
| `form_d_business_combination` only | 407 |
| `efts_ma_proxy` only | 282 |
| `efts_subsidiary` only | 274 |
| `efts_acquisition_text` + `efts_ma_definitive` | 239 |
| `efts_ownership_active` only | 192 |
| `efts_ma_definitive` + `efts_ma_proxy` | 148 |
| `efts_ma_definitive` + `efts_ownership_active` | 134 |
| `efts_ma_definitive` + `efts_subsidiary` | 104 |

Multi-signal events (2+ signals) are higher confidence — 239 companies
have both acquisition text and a material definitive agreement filing.

## Caveats

- **EFTS mentions are noisy.** A company mentioned in an 8-K item 1.01
  may be a counterparty to a material contract, not an acquisition
  target. The `acquisition` text-context signal is more precise but
  coverage is incomplete (only applied when document text was fetched).

- **Acquirer identification is approximate.** `mention_filers[0]` is
  the first filer that mentioned the SBIR company — usually the
  acquirer, but could be a financial advisor, competitor, or customer.

- **Form D business combinations lack acquirer data.** The 407
  Form-D-only events identify the target company but not who acquired
  them.

- **Time coverage varies by signal.** EFTS full-text search covers
  filings from ~2001 onward. Form D data covers 2009-2025. Older
  acquisitions may be missed.

- **Exit ≠ successful outcome.** Some "exits" may be distressed sales,
  acqui-hires, or asset purchases rather than successful acquisitions.
  The data does not distinguish exit quality.

## Data

- Events dataset: `data/sbir_ma_events.jsonl` (4,306 records)
- Detection script: `scripts/data/detect_sbir_ma_events.py`
- Analysis script: `scripts/data/analyze_sbir_ma_exits.py`
