# Leverage-ratio validation, sensitivity, and limitations

The federal-to-SBIR leverage ratio is **non-SBIR federal obligations divided by
SBIR/STTR obligations** for entity-matched companies. The primary calculation is
implemented separately from validation so that a shared defect cannot silently make
both the result and its checks agree.

## Required validation before publishing

Every refresh must run `validate_run` and `enforce_report_gate`. The gate fails when:

- independently summed source numerator or denominator differs from the headline by
  more than **$0.01**;
- an SBIR or STTR record enters the non-SBIR numerator;
- an obligation ID is duplicated after entity matching;
- de-obligations are not netted or excluded exactly as the scenario declares;
- company, agency, or cohort totals do not roll up to the headline;
- entity-match coverage at the selected threshold is below **80%**;
- company, agency, cohort, or headline output is absent; or
- a ratio is infinite, or is null despite a positive denominator.

A null ratio with a zero or negative denominator is expected and visible rather than
being converted to zero. Duplicate records are never silently removed. Producers must
fix the matching output or document an upstream correction.

## Sensitivity reporting

No single preferred configuration is sufficient for publication. A release must expose
the complete scenario table and a range summary. `run_sensitivity_analysis` crosses:

| Choice | Default sensitivity values |
| --- | --- |
| Entity-match confidence | 0.70, 0.80, 0.90 |
| Analysis window | all available years; FY2012–FY2020 |
| Dollar basis | nominal; inflation-adjusted |
| Negative obligations | included (net obligations); excluded |
| STTR | included in denominator; excluded from analysis |

`sensitivity_summary` reports the minimum and maximum headline ratio overall and for
every value of every methodological choice. This makes changes to the headline result
visible rather than presenting only the preferred configuration. Inflation-adjusted
runs require a row-level `inflation_factor` tied to a documented base year.

## Manual quality review

`build_stratified_review_sample` selects deterministic samples from both tails of the
company leverage-ratio distribution. Reviewers must inspect the source obligations and
complete these fields before publication:

- `review_status`, `reviewer`, and `review_notes`;
- `entity_match_confirmed` and `sbir_classification_confirmed`; and
- `review_evidence_reference`, which stores the source obligation IDs used as evidence.

Store the completed sample with the refresh's validation artifacts. Pending records are
not evidence of completed review; they are a reproducible review queue.

## Known limitations

- The ratio measures observed federal obligations, not private sales, economic impact,
  or causal returns to SBIR funding.
- Entity-resolution errors can move both numerator coverage and company stratification;
  the match-threshold sensitivity range does not eliminate this risk.
- Contract coding may fail to identify some SBIR/STTR-funded actions. Manual tail review
  is especially important because a single large miscoded action can dominate a ratio.
- De-obligations are economically meaningful and are included in the default net measure,
  but timing can make annual or cohort ratios negative or undefined.
- Inflation adjustment changes the weighting of years and depends on the supplied
  deflator. Nominal and real results must both remain visible.
- Companies can receive funding from multiple agencies. Agency output groups obligation
  records by funding agency; it is not an exclusive company assignment.
- The NASEM 4:1 benchmark may use different periods, entity rules, and inclusion criteria.
  A numerical match alone is not reconciliation.
