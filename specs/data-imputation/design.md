# Data Imputation — Design

## Overview

A dedicated imputation layer sits between raw validation and entity enrichment. It reads
the validated-but-gap-riddled award frame, applies a registry of named imputation
methods in a defined order, and emits a widened frame with effective values, preserved
raw columns, and a per-record provenance struct. Downstream assets choose raw or
effective columns via explicit contract.

Key design tenets:

1. **Never overwrite raw.** Raw columns are immutable after extraction.
2. **One provenance struct per record.** Not a parallel file — it travels with the data.
3. **Methods are cheap, composable, backtested.** Registry pattern; each method is a
   pure function of the input frame plus optional lookups.
4. **Imputation is enrichment's prerequisite, not its peer.** Enrichers that key on
   `company_uei` benefit from UEI backfill; the order matters.

## Architecture

### Pipeline Position

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          SBIR ETL Pipeline                              │
└─────────────────────────────────────────────────────────────────────────┘

  Extractors           Validators            [NEW] Imputation          Enrichers
  ──────────           ──────────             ──────────────           ─────────
  sbir.gov bulk   ──►  sbir_awards.py   ──►  raw → effective    ──►   company_*
  DuckDB load          (lenient)              + provenance             congressional
                                                                       naics, patents
                                                                              │
                                                                              ▼
                                                                       Neo4j loaders
                                                                       Dagster assets
                                                                              │
                                                                              ▼
                                                                       Quality checks
                                                                       (raw + effective)
```

The imputation layer is a new Dagster op/asset group in `packages/sbir-analytics/`, with
the library code living in `sbir_etl/imputation/` to keep it reusable outside Dagster.

### Module Layout

```text
sbir_etl/imputation/
├── __init__.py
├── registry.py              # ImputationMethod registry, execution order
├── provenance.py            # ImputationProvenance model + struct helpers
├── config.py                # Pydantic config loaded from base.yaml[imputation]
├── methods/
│   ├── __init__.py
│   ├── award_date.py        # Cascade + agency-lag
│   ├── identifiers.py       # UEI/DUNS cross-award backfill
│   ├── award_amount.py      # Agency-phase-program median
│   ├── geography.py         # Wraps congressional_district_resolver
│   ├── contract_dates.py    # End-date repair
│   └── naics.py             # Hierarchical + abstract-NN fallback
├── backtest.py              # Mask-and-compare harness
└── runner.py                # Orchestrates method registry over a frame

packages/sbir-analytics/sbir_analytics/assets/
└── imputation.py            # Dagster asset wrapping runner

config/base.yaml              # + imputation section
sbir_etl/quality/checks.py    # + raw-vs-effective split
sbir_etl/models/award.py      # + raw_* shadow fields + imputation struct
reports/imputation/           # Per-run coverage + backtest results
```

### Data Flow

```text
validated_sbir_awards (raw)
        │
        ▼
┌───────────────────────────┐
│  ImputationRunner         │
│  ─────────────────────    │
│  for method in registry:  │
│     if config.enabled:    │
│       frame = method(     │
│         frame,            │
│         lookups,          │
│         provenance)       │
└───────────────────────────┘
        │
        ├──► raw_<field> columns (untouched copy)
        ├──► <field> columns (effective: raw if present, else imputed)
        ├──► <field>_is_imputed columns (bool)
        └──► imputation struct column (method, confidence, sources, timestamp)
        │
        ▼
imputed_sbir_awards
        │
        ├──► reports/imputation/coverage.json
        ├──► reports/imputation/backtest.json (CI gate)
        └──► downstream enrichers + Neo4j loaders
```

## Components

### 1. ImputationMethod (registry protocol)

**Purpose:** Uniform interface so methods are discoverable, orderable, and backtestable.

**Protocol** (`sbir_etl/imputation/registry.py`):

```python
class ImputationMethod(Protocol):
    name: str                          # e.g., "award_date.cascade"
    target_field: str                  # "award_date"
    source_fields: list[str]           # ["proposal_award_date", ...]
    confidence: Literal["high", "medium", "low"]
    version: int

    def impute(
        self,
        frame: pl.DataFrame,
        lookups: ImputationLookups,
    ) -> ImputationResult: ...
```

`ImputationResult` carries the imputed Series plus a parallel Series of provenance
entries, merged into the frame by the runner.

### 2. ImputationRunner

**Purpose:** Executes methods in dependency order, builds the provenance struct,
emits coverage metrics.

**Ordering rule:** Methods that fill inputs to other methods run first. E.g., UEI
backfill runs before any method that groups by UEI. The registry validates no cycles
at load time.

**Key operations:**

1. Clone raw columns into `raw_<field>` shadow columns.
2. For each enabled method in topological order, invoke and merge results.
3. Compose per-record `imputation` struct by folding method-level results.
4. Emit `<field>_is_imputed` convenience booleans.
5. Write coverage report to `reports/imputation/coverage.json`.

### 3. Provenance Model

**Schema** (`sbir_etl/models/award.py` additions):

```python
class ImputationEntry(BaseModel):
    field: str
    method: str
    method_version: int
    confidence: Literal["high", "medium", "low"]
    source_fields: list[str]
    imputed_at: datetime  # UTC

# Added to Award model:
raw_award_date: date | None = None
raw_award_amount: float | None = None
raw_company_uei: str | None = None
# ... one per imputable field
award_date_is_imputed: bool = False
# ... one per imputable field
imputation: list[ImputationEntry] = Field(default_factory=list)
```

For DuckDB/Parquet persistence the struct serializes as a nested list; for Neo4j the
list flattens to `imputation_methods: list[str]` plus the per-field boolean flags.

### 4. Method Implementations

#### 4.1 `award_date.cascade`

Walks this ordered cascade, taking the first non-null:

| Source | Confidence | Notes |
|---|---|---|
| `proposal_award_date` | high | Tight semantic match |
| `contract_start_date` | high | Usually within weeks of award |
| `date_of_notification` | medium | Agency-dependent lag |
| `solicitation_close_date + agency_lag` | medium | Uses agency-specific median lag from awards with both fields present |
| `fiscal_year` midpoint (April 1) | low | Last resort; year-only resolution |

Per-agency lag lookup is computed once from the non-null corpus and cached as an
`ImputationLookups` asset.

#### 4.2 `identifiers.cross_award_backfill`

For each `(normalize(company_name), company_state)` key:
1. Gather all UEI/DUNS values observed across the corpus.
2. If exactly one non-null value exists, backfill to sibling rows missing it.
3. If multiple values exist, skip — flag for review via
   `reports/imputation/uei_conflicts.json`.

Name normalization reuses `sbir_etl/enrichers/company_fuzzy_matcher.py` so the join key
matches what enrichment already uses.

#### 4.3 `award_amount.agency_phase_median`

Group by `(agency, program, phase, fiscal_year)`. Impute the group median where
`award_amount` is null. Guards:

- Minimum group size: 10 non-null members (else skip).
- Imputed value must fall within $1k–$5M (existing cap).
- `confidence: medium` across the board; `low` if group falls back to
  `(agency, program, phase)` without fiscal year.

#### 4.4 `geography.congressional_district`

Thin wrapper over existing `congressional_district_resolver.py`. Populates the existing
`congressional_district` + `congressional_district_confidence` fields. Tiers:

- zip+4 match → high
- zip5 match → medium
- city/state centroid → low

#### 4.5 `contract_dates.end_date_repair`

When `contract_end_date` is null or `< contract_start_date`, impute
`contract_start_date + phase_typical_duration`:

| Phase | Typical duration |
|---|---|
| Phase I | 6 months |
| Phase II | 24 months |
| Phase III | skip (highly variable) |

Durations are medians computed from the known-good corpus per agency, cached as a
lookup.

#### 4.6 `naics.hierarchical`

Two sub-methods sharing the `naics.*` namespace:

- **`naics.hierarchical_fallback`** — If 6-digit invalid but 4/3/2-digit prefix is
  valid, emit the shortest valid prefix. Reuses `sbir_etl/enrichers/naics/`.
- **`naics.abstract_nn`** — When entirely missing, TF-IDF nearest-neighbor lookup on
  `award_abstract` against awards with known NAICS. Only runs if abstract length > 100
  chars. `confidence: low`.

### 5. Configuration

**`config/base.yaml` additions:**

```yaml
imputation:
  enabled: true
  dry_run: false

  methods:
    award_date.cascade:
      enabled: true
      agency_lag_min_group_size: 20

    identifiers.cross_award_backfill:
      enabled: true
      normalization: fuzzy_matcher_v1

    award_amount.agency_phase_median:
      enabled: true
      min_group_size: 10
      fallback_grouping: [agency, program, phase]

    geography.congressional_district:
      enabled: true

    contract_dates.end_date_repair:
      enabled: true

    naics.hierarchical_fallback:
      enabled: true

    naics.abstract_nn:
      enabled: false      # opt-in, expensive
      min_abstract_chars: 100
      k_neighbors: 5

  backtest:
    holdout_fraction: 0.1
    random_seed: 42
    regression_threshold_pp: 5

  quality:
    effective_thresholds:
      award_date: 0.95
      award_amount: 0.92
      company_uei: 0.80
```

Quality checks gain a `raw_` vs `effective_` split:

```yaml
quality:
  raw_completeness:
    award_date: 0.50        # realistic source coverage
    # ...
  effective_completeness:   # references imputation.quality.effective_thresholds
    # ...
```

### 6. Dagster Integration

**New asset** (`packages/sbir-analytics/sbir_analytics/assets/imputation.py`):

```python
@asset(
    deps=[validated_sbir_awards],
    group_name="imputation",
    compute_kind="duckdb",
)
def imputed_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pl.DataFrame,
) -> pl.DataFrame: ...
```

Existing downstream assets (enrichment, Neo4j load) rewire their dependency from
`validated_sbir_awards` to `imputed_sbir_awards`. Quality checks run on both.

### 7. Backtest Harness

`sbir_etl/imputation/backtest.py` provides:

- `mask_and_reimpute(frame, field, fraction=0.1)` — randomly nulls ground-truth values,
  reruns imputation, returns accuracy/MAE per method.
- `run_backtest_suite()` — invoked by CI, writes
  `reports/imputation/backtest.json`, fails if any method regresses ≥5pp vs baseline
  in `reports/imputation/backtest_baseline.json`.

### 8. Consumer Contract

| Consumer | Reads |
|---|---|
| `packages/sbir-ml/` (CET, transition detection) | `raw_*` by default; opt-in flag to include imputed |
| `packages/sbir-analytics/` reporting | Effective columns + `_is_imputed` flags surfaced |
| `packages/sbir-graph/` Neo4j loaders | Effective values; `is_imputed` flags as node properties |
| `sbir_etl/quality/checks.py` | Both — raw for source thresholds, effective for effective thresholds |

## Testing Strategy

- **Unit:** Each method in isolation against fixture frames with hand-crafted nulls.
- **Property tests:** Raw columns byte-identical pre/post imputation; idempotency
  (running imputation twice yields identical output).
- **Integration:** End-to-end pipeline run on a fixture bulk-download snapshot, asserting
  Dagster assets materialize and Neo4j loaders persist `is_imputed` flags.
- **Backtest gate in CI:** Fails the build if any method regresses.
- **Precision benchmark:** `packages/sbir-ml/` evaluation tests re-run with imputation
  enabled to confirm ≥85% transition-scoring precision holds when ML opts in.

## Open Questions

1. Should UEI/DUNS backfill go through the same `confidence` tiering, or is any
   unambiguous cross-award match treated as `high`?
2. Is `award_abstract` reliably present enough to make `naics.abstract_nn` worth the
   dependency on TF-IDF infrastructure?
3. Do we want a per-record `imputation_policy_version` so downstream ML can pin to a
   specific imputation contract across retrains?
