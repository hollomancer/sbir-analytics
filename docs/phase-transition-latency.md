# Phase II → Phase III Transition Latency

Measures the elapsed time between a firm's Phase II period-of-performance end
and its first subsequent Phase III contract, across every SBIR-awarding
federal agency.

## Pipeline

Four Dagster assets under
`packages/sbir-analytics/sbir_analytics/assets/phase_transition/`:

| Asset | Group | Purpose |
|---|---|---|
| `validated_phase_ii_awards` | validation | Unified Phase II population (FPDS/USAspending contracts + USAspending assistance grants, reconciled against SBIR.gov). |
| `validated_phase_iii_contracts` | validation | FPDS procurement rows flagged Phase III. Emits agency coverage as a `*.checks.json` audit. |
| `transformed_phase_ii_iii_pairs` | transformation | All valid (Phase II, Phase III) pairs joined on `recipient_uei` with DUNS crosswalk fallback. Latency preserved with sign. |
| `transformed_phase_transition_survival` | transformation | Per-Phase-II time-to-event frame (event indicator + `time_days` to earliest Phase III or to the data cut). Ready for Kaplan-Meier. |

Pydantic row contracts live in
[`sbir_etl/models/phase_transition.py`](../sbir_etl/models/phase_transition.py).

After materializing the assets, run the DuckDB analysis script:

```bash
python scripts/phase_transition_analysis.py
# -> reports/phase_transition/phase_transition_report.json
```

It emits latency percentiles, a month-binned histogram, agency breakdowns,
and end-year cohort transition rates.

## Threats to validity

### 1. Phase III coding is a known undercount

Phase III status on the FPDS side relies on Element 10Q (`research` = `SR3`
or `ST3`). Coding is inconsistent outside DoD: many civilian agencies leave
the field null even on clearly Phase III follow-ons, so the reported
transition rate is a **lower bound**. `validated_phase_iii_contracts` emits a
per-agency audit in its `*.checks.json` — the `agencies_with_zero_phase_iii`
list highlights where the undercount is most severe. Cross-checking against
solicitation numbers or award descriptions could narrow the gap, but that is
out of scope for v1.

### 2. Contract / grant split on the Phase II side

`validated_phase_ii_awards` unifies three distinct populations:

- **FPDS contracts** (`source = "fpds_contract"`): procurement Phase II
  awards. Authoritative period-of-performance dates.
- **USAspending assistance grants** (`source = "usaspending_assistance"`):
  Phase II grant awards. Distinguishable from contracts via the
  `transaction_normalized.type` assistance codes and the presence of a CFDA
  number. NIH and NSF dominate this population and their
  `period_of_performance_current_end_date` semantics differ from procurement.
- **SBIR.gov reconciliation** (`source = "sbir_gov"`): rows recovered from
  the SBIR.gov master dataset when federal-system phase coding was missing.
  Marked `phase_coding_reconciled = true`. Dates come from SBIR.gov's
  `contract_end_date` field, which is less consistently populated than
  federal POP dates.

When interpreting latency, slicing by `source` is important: grant-to-Phase
III transitions have different baseline rates than contract-to-Phase III.

### 3. Negative latencies are real

The pipeline preserves negative `latency_days`. Phase III procurement can
legally precede Phase II's period-of-performance end — for example, when a
Phase III option is exercised against an on-going Phase II base. We do not
clip or filter these because treating them as zero would bias KM estimates.

### 4. Multi-award firms

A firm with multiple Phase II awards and multiple Phase III contracts emits
**every** valid pair. Downstream views then derive:

- Earliest Phase III per Phase II — via the survival frame's `event_date`.
- Any Phase III within 5 years — via the `within_5_year_rate` check.

Cartesian pair-count growth is bounded by UEI cardinality; in practice the
pair table is ~1.5× the size of the Phase III contract table.

## Method knobs (all with documented defaults)

| Env var | Default | Purpose |
|---|---|---|
| `SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH` | `data/transition/contracts_ingestion.parquet` | Raw contracts input (FPDS + assistance). |
| `SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH` | `data/processed/enriched_sbir_awards.parquet` | SBIR.gov reconciliation source. |
| `SBIR_ETL__PHASE_TRANSITION__PHASE_II_OUTPUT_PATH` | `data/processed/phase_ii_awards.parquet` | Phase II asset output. |
| `SBIR_ETL__PHASE_TRANSITION__PHASE_III_OUTPUT_PATH` | `data/processed/phase_iii_contracts.parquet` | Phase III asset output. |
| `SBIR_ETL__PHASE_TRANSITION__PAIRS_OUTPUT_PATH` | `data/processed/phase_ii_iii_pairs.parquet` | Matched-pair output. |
| `SBIR_ETL__PHASE_TRANSITION__SURVIVAL_OUTPUT_PATH` | `data/processed/phase_transition_survival.parquet` | Survival frame output. |
| `SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE` | today (UTC) | Right-censoring date for Phase IIs without a matched Phase III. |

### Explicitly out of scope (v1)

- Topic / technology matching beyond firm identity.
- Neo4j loading — DuckDB aggregates are sufficient.
- Filtering outliers or negative latencies.
