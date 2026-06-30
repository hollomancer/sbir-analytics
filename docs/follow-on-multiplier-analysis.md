# Follow-on funding multiplier analysis

> The **follow-on funding multiplier** is the dollar of non-SBIR federal obligations per dollar of SBIR/STTR investment for SBIR-recipient firms. NASEM's reviews of DoD SBIR call the same quantity the *leverage ratio*; we use *follow-on funding multiplier* in this codebase because "leverage" carries debt connotations from finance that don't apply here.

## Specification validation and requirement map

Validation was completed before implementation against `specs/follow-on-multiplier-analysis/requirements.md`. The specification's old `src/tools/mission_b` paths do not match the current package layout, so implementation follows the repository's current analytics convention under `packages/sbir-analytics/sbir_analytics/assets/`.

| Requirement | Existing data / identifier | Implementation | Test |
|---|---|---|---|
| DOD aggregate multiplier | `raw_usaspending_transactions`; UEI; `federal_action_obligation`; SBIR award ID/ALN flags | `analysis.calculate_follow_on_multipliers`, `integration.build_canonical_obligations` | company/agency unit test; integration fixture |
| Vintage, firm size, technology, experience | SBIR award year, categorization/CET outputs, award history | company/cohort tables | cohort unit test |
| NASEM reconciliation | published 4:1 comparison point | `reconcile.reconcile_nasem` and markdown report | integration test |
| Civilian agency | USAspending agency dimension (fixture includes DOE) | agency table | company/agency unit test |
| Time series | USAspending fiscal year | fiscal-year table | cohort/FY unit test |
| Technology breakdown | `technology_area` / `cet_area` | cohort dimensions | cohort unit test |
| Match sensitivity | UEI and `_usaspending_match_score` / match confidence | quality table and match columns | match-quality unit test |

### Resolved analysis semantics

- **SBIR funding denominator:** net USAspending obligations identified by an explicit SBIR flag, SBIR.gov award-ID match, confirmed/exclusive SBIR ALN, or SBIR/STTR program label.
- **Non-SBIR federal obligations numerator:** net obligations to accepted SBIR-firm entity matches that are not identified as SBIR/STTR, grouped by awarding agency.
- **STTR:** included by default and configurable with `include_sttr=false`.
- **Negative obligations:** retained as de-obligations in both numerator and denominator; no clipping.
- **Dollars:** nominal by default. Constant-dollar analysis requires a complete fiscal-year-to-adjustment-factor table and applies the factor to both sides of the multiplier.
- **Entity matching:** UEI is the join identifier; rows require a company ID and confidence of at least `0.80` by default. Excluded rows remain visible in quality metadata.
- **Cohort and fiscal-year windows:** cohort is the firm's first identified SBIR/STTR award year. Fiscal-year start/end filters are inclusive and optional.
- **Zero denominator:** multiplier is undefined/null when net SBIR funding is zero or negative. A firm with positive SBIR funding and no non-SBIR funding has multiplier `0`.

### Unresolved product decisions

These do not block the accepted implementation, but must be decided before claiming a definitive NASEM replication:

1. Confirm the exact NASEM report edition, source table, covered fiscal years, and whether its 4:1 denominator is awards or net obligations.
2. Decide whether the headline numerator should include all federal agencies' follow-on obligations to DOD firms or DOD-only obligations. Current outputs group numerator and denominator by the same awarding agency.
3. Decide whether DOE's headline comparison must include grants as well as contracts; current logic includes every supplied USAspending transaction type.
4. Select the authoritative production inflation series/base year. The calculator accepts factors but does not silently choose a series.
5. Decide whether shared-ALN, unconfirmed awards belong in a sensitivity run; current identification requires confirmation.

## Execution

The standard orchestration interface is the auto-discovered Dagster asset `follow_on_multiplier_analysis`. It consumes:

- `enriched_sbir_awards` (SBIR identification, UEI/entity match quality, cohort and optional categorization/CET fields)
- `raw_usaspending_transactions` (transaction-level obligations)

Run it from the repository's normal Dagster deployment, or exercise the deterministic path with:

```bash
uv run pytest tests/unit/follow_on_multiplier tests/integration/follow_on_multiplier
```

The asset writes Parquet tables and NASEM JSON/Markdown reports to `data/processed/follow_on_multiplier/`. Nominal dollars are the default; for an adjusted-dollar orchestration run, set `dollar_basis: adjusted` and `adjustment_factors_path` to a CSV containing `fiscal_year,adjustment_factor`.

## Output schema

All multiplier tables include traceable `sbir_funding_denominator`, `non_sbir_obligations_numerator`, `follow_on_multiplier`, `record_count`, `company_count`, `matched_record_count`, `mean_match_confidence`, and `min_match_confidence`. Dimension columns vary:

- `company`: company, agency, cohort, firm size, technology area, experience
- `agency`: agency
- `cohort`: agency, cohort, firm size, technology area, experience
- `fiscal_year`: agency, cohort, and transaction fiscal year
- `quality`: input/matched/excluded counts, match rate, threshold, dollar basis, and fiscal window

## Interpretation and reproducibility

The multiplier is descriptive, not causal. Entity-resolution exclusions, transaction coverage, negative obligations, fiscal windows, SBIR identification, and dollar basis can materially change it. The generated report states "NASEM reports 4:1; our pipeline yields X:1 using [method]" and classifies benchmark differences as methodological unless a non-finite calculation indicates an implementation error.

For the deterministic fixture, accepted DOD firms have a net SBIR denominator of `$300`, a non-SBIR numerator of `$350`, and a follow-on multiplier of `1.1667:1`. The difference from 4:1 is expected because this fixture is designed to exercise edge cases, not reproduce NASEM's population.
