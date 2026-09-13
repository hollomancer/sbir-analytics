# Allocation transaction costs — implementation design

Frozen analytical method: [`studies/allocation-transaction-costs/design.md`](../../studies/allocation-transaction-costs/design.md).
Approved implementation plan (ships with the PR): [`implementation-plan.md`](implementation-plan.md).

## Layout

```text
studies/allocation-transaction-costs/
  study.yaml
  design.md
  sources.yaml
  assumptions.yaml
  data/*.csv
  complexity/nih_foa_rules.yaml
scripts/data/allocation_transaction_costs.py
docs/research/allocation-transaction-costs.md
```

No `sbir_etl/` primitives, no Dagster, no Neo4j, no modular-analysis-platform
profile. Grain is mechanism-year published statistics.

## Data flow

Committed CSVs hashed in `sources.yaml` → `load_mechanism_years` → duration
conventions from `assumptions.yaml` → metrics, break-even, sensitivity,
complexity index → `data/reports/allocation-transaction-costs/` (gitignored
generated output). The research note commits the tables a reader needs.

## Failure behavior

SHA mismatch refuses the run. PRA / F&A hour classes refuse. Missing `GC`
stays missing. FY2025 aggregate "Total Phase II" rows are dropped at CSV
construction so they cannot be double-counted.

## Evidence consequences

The study is `reproducible` and non-citable. Inventory Status may say
`Partially computable` for the NIH break-even; it may not say validated or
citable.
