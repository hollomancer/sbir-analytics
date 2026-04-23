# SBIR M&A Exit Detection — Design Spec

**Date:** 2026-04-23
**Branch:** `claude/sbir-ma-exit-analysis`
**Research questions:** A4 (M&A activity detection, foreign-acquisition risk)

## Goal

Detect which SBIR companies were acquired, by whom, and when. Measure
the exit rate by agency, sector, and time period. Output a curated M&A
events dataset (JSONL) and an analysis report (markdown).

Replaces the prior skeleton spec at `specs/merger_acquisition_detection/`.

## Context

Three M&A signal sources exist in the pipeline:

1. **Form D `is_business_combination`** — 552 companies, 800 offerings.
   Self-reported by the issuer on Form D filing. High precision.
2. **EFTS mention classification** — 4,022 companies with M&A-relevant
   mention types (`ma_definitive`, `ma_proxy`, `acquisition`,
   `subsidiary`, `ownership_active`). Medium precision, needs
   disambiguation.
3. **Patent assignment detection** — existing Dagster asset
   (`ma_detection.py`). Out of scope for this work.

Sources explicitly evaluated and rejected:
- **GDELT** — 2.5TB+ dataset, requires BigQuery, fuzzy NER at scale.
  Surfaces the same events EDGAR 8-Ks capture from press releases.
  Evaluated (old spec task 1.9), correctly not built.
- **NewsAPI** — Commercial API ($449+/month). Aggregates the same
  press releases that trigger 8-K filings. Redundant with EDGAR.
- **Wikidata** — Clean structured data but fatal coverage gap for
  small SBIR companies. Evaluated (old spec task 1.12), correctly
  not built.

## Approach: Layered Signal Architecture

### Layer 1: Form D business combinations (high confidence)

552 companies with `is_business_combination = True` on at least one
Form D offering. Extract from existing `form_d_details.jsonl`:

- Company name (target)
- Filing date (event date)
- Related persons (acquirer signal — officers/directors on the filing)
- Offering amount (deal size proxy)

Confidence: **high** — self-reported, binary flag, legally filed.

### Layer 2: EFTS mention classification (variable confidence)

4,022 companies with M&A-relevant mention types from
`sec_edgar_scan.jsonl`. Signal strength varies by type:

| Mention Type | Companies | Confidence | Notes |
|---|---|---|---|
| `subsidiary` | 695 | **High** | Listed in Exhibit 21 = already acquired |
| `acquisition` | 1,472 | **Medium-high** | Context extraction confirmed acquisition language |
| `ma_definitive` | 2,195 | **Medium** | 8-K items 1.01/2.01 — could be target, customer, or counterparty |
| `ma_proxy` | 675 | **Medium** | Merger proxy — could be comp table entry |
| `ownership_active` | 574 | **Medium-low** | >5% stake with intent — pre-acquisition signal |
| `ownership_passive` | 327 | **Excluded** | Passive stake, not an exit |

Key data: `mention_filers` identifies who mentioned the SBIR company
(the potential acquirer). For `subsidiary`, the filer is the parent.

### Deduplication

157 companies appear in both layers. Layer 1 provides the event
confirmation; Layer 2 adds the acquirer identity. Deduplication
by company name with a 12-month date window for same-event merging.

## Output

### M&A Events Dataset

File: `data/sbir_ma_events.jsonl`

Per-company record with:
- `company_name`, `event_date`, `acquirer`
- `confidence` tier (high / medium / low)
- `signals` dict (which signals fired)
- `signal_count` (number of independent signals)
- `form_d_detail` (filing date, amount, related persons)
- `efts_detail` (mention filers, types, dates)
- `sbir_context` (agency, total awards, total amount, year range)

### Confidence Tiers

| Tier | Rule |
|------|------|
| High | Form D business combination OR EFTS `subsidiary` |
| Medium | EFTS `ma_definitive` or `acquisition` text, without high-tier confirmation |
| Low | `ownership_active` or `ma_proxy` only |

`ownership_passive` excluded entirely.

### Analysis Report

File: `docs/research/sbir-ma-exit-analysis.md`

Contents:
- Exit rate by agency (% of SBIR companies with M&A event)
- Exit rate by year and confidence tier
- Top acquirers (from `mention_filers`)
- Time from first SBIR award to exit
- Exit rate by SBIR funding amount (do bigger awardees get acquired
  more?)

## Implementation

### Script: `scripts/data/detect_sbir_ma_events.py`

Standalone analysis script (not a Dagster asset). Reads:
- `data/form_d_details.jsonl` (Layer 1: business combinations)
- `data/sec_edgar_scan.jsonl` (Layer 2: EFTS mentions)
- `/tmp/sbir_awards_full.csv` (SBIR context: agency, amounts, years)

Outputs:
- `data/sbir_ma_events.jsonl`
- Summary stats to stdout

### Script: `scripts/data/analyze_sbir_ma_exits.py`

Reads `data/sbir_ma_events.jsonl` and produces the analysis report.
Generates tables for exit rates, acquirer rankings, timing analysis.

## Data Dependencies

| Source | Path | Required |
|--------|------|----------|
| Form D details | `data/form_d_details.jsonl` | Yes |
| EFTS scan | `data/sec_edgar_scan.jsonl` | Yes |
| SBIR awards | `/tmp/sbir_awards_full.csv` | Yes |

## What This Does NOT Include

- Patent assignment as an M&A signal (existing asset, separate pipeline)
- Foreign-acquisition risk scoring (future layer on top of this dataset)
- GDELT, NewsAPI, or Wikidata enrichment (evaluated, rejected)
- Neo4j loading of M&A events (future spec)
- Real-time monitoring / alerting on new M&A events

## Testing

- Unit test: signal extraction from Form D records
- Unit test: EFTS mention type → confidence tier mapping
- Unit test: deduplication logic (same company, overlapping dates)
- Smoke test: run on full dataset, validate output schema

## Files

| File | Action |
|------|--------|
| `scripts/data/detect_sbir_ma_events.py` | Create |
| `scripts/data/analyze_sbir_ma_exits.py` | Create |
| `data/sbir_ma_events.jsonl` | Output |
| `docs/research/sbir-ma-exit-analysis.md` | Output |
| `specs/merger_acquisition_detection/` | Replace requirements/design/tasks |
