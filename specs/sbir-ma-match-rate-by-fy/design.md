# Design: SBIR M&A Match Rate by Fiscal Year

## Approach

Read-only analysis on top of existing enrichment outputs. No new
extraction, no schema changes. One script, one Dagster asset, and
three report files (per-FY CSV, narrative MD, firm-level detail CSV)
matching the outputs enumerated in `requirements.md`.

## Inputs (existing JSONL + Dagster asset)

The implemented enrichment pipeline emits JSONL artifacts and one
DataFrame asset, not per-filing parquet. The canonical inputs are:

- `data/sbir_ma_events.jsonl` — curated M&A events output from PR #286
  (`scripts/archive/data/detect_sbir_ma_events.py`).
- `data/sec_edgar_scan.jsonl` — resumable EFTS scan output.
- `data/form_d_details.jsonl` — Form D filings with
  `is_business_combination` flag and confidence tier.
- Dagster asset `sec_edgar_enriched_companies` (DataFrame) — per-firm
  enrichment surface including `mention_*` aggregates and CIK linkage;
  use this rather than re-deriving from raw mentions.
- SBIR awards: the canonical `enriched_sbir_awards` asset.

If any later refactor introduces parquet equivalents, those become the
preferred inputs; update this section accordingly. The acceptance
criterion (AC1) is "reproducible from existing artifacts," not
specifically parquet.

## Pipeline

```
awardees(FY2015-2024) ──┐
                        ├─→ join on company_key ─→ matches ─→ tier-rank
ma_signals(FY2015-2024)─┘                              │
                                                       ↓
                                            dedupe (one row per firm)
                                                       ↓
                                            group by match_fy → CSV + MD
```

### Step 1: Build awardee denominator

```python
awardees = (
    awards
    .filter(award_start_date >= 2014-10-01,
            award_start_date <  2024-10-01)
    .with_column(award_fy = fiscal_year(award_start_date))
    .group_by(company_key)
    .agg(primary_award_fy = min(award_fy))
)
```

Federal FY: a date in [Oct 1 of year Y-1, Sep 30 of Y] is FY Y.

### Step 2: Collect dated M&A signals

Union the dated signal sources, tag each with tier and signal type:

| Source | Filter | Tier | Date column |
|---|---|---|---|
| `ma_events` | all rows | Low (1.01/2.01) | `filing_date` |
| `mentions` | `classification = 'subsidiary'` | High | `filing_date` (upper bound) |
| `mentions` | `classification = 'acquisition'` | Medium | `filing_date` |
| `mentions` | `classification = 'ma_definitive'`, form_type in (SC TO-T, SC 14D9) | Low | `filing_date` |
| `mentions` | `classification = 'ma_proxy'` | Low | `filing_date` |
| `mentions` | `classification = 'ownership_active'` | Low | `filing_date` |
| `form_d` | `is_business_combination = True` | High | `filing_date` |

Restrict to filings dated within FY2015–2024.

### Step 3: Tier ranking and dedupe

Per firm, keep one row:
- Highest tier wins (High > Medium > Low).
- Within tier, earliest filing_date wins.
- Carry list of contributing signals for the detail CSV.
- For Exhibit-21-only matches, set `date_upper_bound = true`.

### Step 4: Compute rates

Per FY:
- Denominator: distinct firms with `primary_award_fy = FY`.
- Numerator (per requirements.md): distinct matched firms with at least
  one qualifying M&A signal dated in FY2015–2024. A match is attributed
  to the FY of its earliest qualifying signal.
- Per AC6, firms whose `match_fy` precedes their `primary_award_fy`
  are still counted in the numerator but flagged
  `match_before_first_award = true` in the firm-level detail CSV and
  surfaced as a caveat in the narrative.

Two rate columns (note the inclusive-tier semantics in the names):
- `match_rate_high_medium` = (high + medium tier matches) / denom.
- `match_rate_total` = all-tier matches / denom.

Aggregate FY2015–2024 row reports Wilson 95% CI.

### Step 5: Item 2.01 sub-rate (methodological footnote)

Filter `ma_events` to rows where `'2.01' in items_reported`. Compute
the same numerator/denominator. Report as a single number with the
caveat that single-signal Item 2.01 has ~30–40% estimated precision.

## File layout

```
scripts/analysis/sbir_ma_match_rate_by_fy.py    # script (one file)
packages/sbir-analytics/sbir_analytics/assets/sbir_ma_match_rate.py
                                                # thin Dagster wrapper
reports/sbir_ma_match_rate_by_fy.csv            # generated
reports/sbir_ma_match_rate_by_fy.md             # generated
reports/sbir_ma_matched_firms_fy2015_2024.csv   # generated
```

The Dagster asset just calls the script and writes outputs to the
`reports/` directory — no new IO managers, no new resources.

## Open questions to resolve before implementation

- **Q1: Company key.** Is `company_key` already canonical across
  awards and SEC enrichment, or do we need to join through
  `sbir_company_cik_map`? Verify before writing the join.
- **Q2: Form D party.** Form D filings can be filed by the acquirer,
  the target, or a holdco. Confirm the existing `form_d_filings`
  parquet links the filing CIK back to the SBIR firm — and that
  `is_business_combination = True` rows include both directions.
- **Q3: Mentions parquet.** Confirm the column names for
  `classification` and `form_type` in `sec_edgar_mentions.parquet`
  match the model in `sbir_etl/models/sec_edgar.py`.
- **Q4: Right-censoring.** A firm acquired in 2024 may not have its
  10-K Exhibit 21 filed yet. Should the FY2024 row footnote this, or
  exclude FY2024 from the headline aggregate?

These are confirmable in <30 min by reading the asset definitions;
not blocking the spec, but blocking implementation.

## Non-goals

- Form 15 (deregistration) extraction — separate spec if needed.
- Re-running EFTS to attribute item codes per-mention — out of scope.
- Linking to acquirer ticker / market cap — out of scope.
- ML-based deduplication of signals — current rules are sufficient.
