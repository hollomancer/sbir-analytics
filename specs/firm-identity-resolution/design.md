# Firm Identity Resolution — Design

## Overview

A single Dagster asset, `resolved_sbir_awards`, is inserted between `validated_sbir_awards` and the identifier-keyed enrichment fanout. It composes the existing `enrich_awards_with_companies` + `company_canonicalizer` + `SAMGovExtractor` pipeline, walks a documented reference-table cascade, and emits `firm_id` + resolution provenance columns on every award. Nine downstream consumers rewire their input dependency from `validated_sbir_awards` to `resolved_sbir_awards` and switch their identifier-join logic to join on `firm_id`.

The design is deliberately thin: no new algorithms, no new external dependencies beyond a monthly SAM.gov historical extract fetch, no schema migration for existing awards. The value is centralization and provenance, not a new resolution technique.

## Architecture

### Pipeline position

```text
raw_sbir_awards                     (extractor: DuckDB CSV load)
        │
        ▼
validated_sbir_awards               (quality filters, type coercion)
        │
        ▼
resolved_sbir_awards         ◄─── NEW: firm identity resolution stage
        │
        ├──► sec_edgar_enrichment
        ├──► company_categorization
        ├──► sbir_usaspending_enrichment
        ├──► phase_transition/pairs
        ├──► phase_transition/phase_ii, phase_iii
        ├──► phase_iii_candidates/pairing
        ├──► usaspending_database_enrichment
        ├──► usaspending_iterative_enrichment
        ├──► cet/loading
        └──► sbir_neo4j_loading
```

The stage runs after strict validation (per Requirement 8) so that parse-failure UEIs (from `input-validation-hardening`) are distinguishable from true absences before resolution begins. Reference tables (`sam_gov_entities`, `sam_gov_historical_entities`, `usaspending_vendor_master`) are loaded as sibling Dagster assets that `resolved_sbir_awards` depends on.

### Module layout

New code lives in `sbir_etl/resolution/`. All algorithmic components are reused from existing modules; the new files are orchestration and provenance emission only.

```text
sbir_etl/resolution/
├── __init__.py
├── cascade.py           # ResolutionCascade orchestrator (walks reference sources in order)
├── firm_id.py           # Deterministic firm_id generation
├── provenance.py        # Column-emission helpers, sidecar <identifier>_source columns
├── references.py        # Reference-table loader wrappers (thin adapters)
└── reports.py           # Coverage/precision/recall report emitters

packages/sbir-analytics/sbir_analytics/assets/
├── resolved_sbir_awards.py       # Dagster asset (new)
└── sam_gov_historical.py         # Historical extract loader asset (new)

sbir_etl/extractors/sam_gov.py    # Extended: add historical-parquet load path
config/base.yaml                   # + resolution section
reports/resolution/                # coverage.json, precision_calibration.json,
                                   # recall_precision.json, identifier_conflicts.json
```

### Data flow

```text
validated_sbir_awards (pd.DataFrame)
        │
        ▼
┌─────────────────────────────────────────────┐
│ ResolutionCascade.resolve(awards, refs)     │
│ ─────────────────────────────────────────   │
│ 1. Canonicalize existing UEI/DUNS/CAGE      │
│    (uppercase, trim, zero-pad DUNS)         │
│                                             │
│ 2. Identifier cascade (per Req 4):          │
│    a. sam_gov_current   [identifier_exact]  │
│    b. sam_gov_historical [identifier_exact] │
│    c. usaspending        [identifier_exact] │
│    d. internal_dedup     [identifier_exact] │
│         (cross-award propagation via        │
│          company_canonicalizer)             │
│                                             │
│ 3. DUNS→UEI crosswalk lookup where DUNS is  │
│    present but UEI is absent                │
│                                             │
│ 4. Fuzzy-name cascade (per Req 4.6):        │
│    a. Score ≥ 90 → fuzzy_name_high          │
│    b. Score in [75, 90) → fuzzy_name_low    │
│    (via enrich_awards_with_companies)       │
│                                             │
│ 5. Emit firm_id + provenance columns        │
└─────────────────────────────────────────────┘
        │
        ├──► firm_id                    (str)
        ├──► resolution_method          (str, one of the 5 tier values)
        ├──► resolution_score           (float)
        ├──► resolution_source          (str, one of the reference sources)
        ├──► uei                        (str | None, canonicalized)
        ├──► uei_source                 (str: sbir_source | sam_gov_* | usaspending | absent)
        ├──► duns                       (str | None, canonicalized)
        ├──► duns_source                (str)
        ├──► cage                       (str | None, canonicalized)
        ├──► cage_source                (str)
        └──► firm_award_count           (int, per Req 7.3)
```

## Components

### 1. `ResolutionCascade` (`sbir_etl/resolution/cascade.py`)

The orchestrator. Composes reference lookups in a fixed order and delegates the actual matching to existing modules.

```python
@dataclass(frozen=True)
class ResolutionResult:
    firm_id: str
    method: Literal["identifier_exact", "duns_crosswalk",
                    "fuzzy_name_high", "fuzzy_name_low", "unresolved"]
    score: float                       # 1.0 for exact/crosswalk, rapidfuzz/100 for fuzzy, 0.0 for unresolved
    source: Literal["sam_gov_current", "sam_gov_historical", "usaspending",
                    "opencorporates", "internal_dedup", "none"]
    uei: str | None
    duns: str | None
    cage: str | None
    uei_source: str
    duns_source: str
    cage_source: str


class ResolutionCascade:
    def __init__(
        self,
        references: ReferenceTables,
        fuzzy_high_threshold: int = 90,
        fuzzy_low_threshold: int = 75,
    ) -> None: ...

    def resolve(self, awards: pd.DataFrame) -> pd.DataFrame:
        """Bulk resolution. Returns awards with resolution columns appended.
        Delegates to enrich_awards_with_companies for the bulk match.
        Does not re-implement rapidfuzz, phonetic matching, or the
        identifier-first cascade — those are already in company_fuzzy_matcher.
        """
```

The class is a thin composition layer. `resolve` builds a joined master DataFrame from the reference sources, calls `enrich_awards_with_companies(awards, master)`, and translates the returned `_match_score` / `_match_method` / `_matched_company_idx` columns into the spec-defined column set. There is no other logic in this file besides the translation table and provenance emission.

### 2. `firm_id` generation (`sbir_etl/resolution/firm_id.py`)

`firm_id` is a deterministic string derived from the resolution result. It satisfies Requirement 1 (identical across awards for the same firm; stable across re-runs; deterministic; not a bare UEI/DUNS).

**Scheme:**

```python
def compute_firm_id(result: ResolutionResult, award_id: str) -> str:
    if result.method == "unresolved":
        # Synthetic per-award ID — never re-used across awards (Req 1.4)
        return f"firm_unresolved_{sha256(award_id)[:12]}"

    if result.method in ("identifier_exact", "duns_crosswalk"):
        # Canonical key is the resolved UEI, or DUNS if UEI unavailable
        canonical = result.uei or result.duns
        assert canonical is not None
        return f"firm_id_{sha256(canonical)[:12]}"

    # Fuzzy tiers: canonical key is the master-list index of the matched firm
    # (guaranteed identical across all awards matching the same master row)
    canonical = result.source + "|" + str(result._matched_company_idx)
    return f"firm_fx_{sha256(canonical)[:12]}"
```

Notes:
- `sha256(...)[:12]` gives ~48 bits of hash — collision probability across ~200k awards is negligible.
- The `firm_id_` prefix (identifier-based) vs `firm_fx_` (fuzzy) vs `firm_unresolved_` gives downstream code an at-a-glance confidence signal without needing to read `resolution_method`.
- Because the fuzzy hash keys on the master-list index, all awards that match the same reference row get the same `firm_id`. This is the ~3× amplification described in the archived spec's rationale.
- The format contains no raw identifier — if UEI is superseded by another scheme in the future, existing `firm_id` values remain valid.

### 3. Reference-table loaders (`sbir_etl/resolution/references.py`)

Thin adapters. Each returns a DataFrame with a standard schema (`uei`, `duns`, `cage`, `name`, `state`, `source`) suitable for `enrich_awards_with_companies` as its `master` argument.

```python
class ReferenceTables:
    def __init__(
        self,
        sam_gov_current: pd.DataFrame,
        sam_gov_historical: pd.DataFrame | None,
        usaspending_vendors: pd.DataFrame,
    ) -> None: ...

    @property
    def joined(self) -> pd.DataFrame:
        """Union of all reference sources with a source column, deduplicated
        on (uei, duns) keeping the highest-priority source per firm."""
```

Priority order: `sam_gov_current` > `sam_gov_historical` > `usaspending`. Duplicate detection uses the canonicalized identifiers. The `joined` DataFrame is what gets passed to the fuzzy matcher.

### 4. SAM.gov historical extract (`packages/sbir-analytics/sbir_analytics/assets/sam_gov_historical.py`)

New Dagster asset that loads the SAM.gov historical entity extract. Parallel to the existing `sam_gov_entities` asset. Follows the same parquet-first, API-fallback pattern as `sam_gov_ingestion.py`.

Operational note: SAM.gov publishes historical monthly extracts as separate files. The fetch cadence and file-versioning are out of scope for this design; a follow-up runbook covers the operational workflow.

### 5. Provenance emission (`sbir_etl/resolution/provenance.py`)

Utilities for materializing the sidecar columns (`uei_source`, `duns_source`, `cage_source`) and the identifier-conflict log. Trivial.

### 6. Report emitters (`sbir_etl/resolution/reports.py`)

Three reports emitted per run, all under `reports/resolution/`:

- `coverage.json` — per-source resolution counts, `firm_id` cardinality, unresolved rate
- `precision_calibration.json` — the transition-detection precision measurement (Req 6). Recomputed against the frozen precision benchmark; fails CI if precision drops below 0.85
- `recall_precision.json` — the recall-lift + false-unification measurements (Req 7). Recall-lift set is derived at build time from the SBIR bulk download; false-unification set is a checked-in fixture at `tests/fixtures/resolution/known_distinct_firms.jsonl`

## Configuration

`config/base.yaml` gains a small resolution section:

```yaml
resolution:
  enabled: true
  fuzzy_high_threshold: 90
  fuzzy_low_threshold: 75

  references:
    sam_gov_historical:
      enabled: false                # opt-in until historical fetch is set up
      parquet_path: "data/reference/sam_gov_historical/latest.parquet"

  reports:
    parse_failure_uei_treated_as: name_fallback   # options: name_fallback | unresolved

  precision_gate:
    transition_detection_min: 0.85  # matches CLAUDE.md floor
  recall_gate:
    stranded_firm_min: 0.60         # matches Req 7.1
```

No new top-level config concepts introduced. The two gates are the load-bearing values — everything else has a sensible default.

## Dagster integration

### New assets

```python
# packages/sbir-analytics/sbir_analytics/assets/resolved_sbir_awards.py

@asset(
    description="SBIR awards with canonical firm_id and resolution provenance",
    group_name="resolution",
    compute_kind="pandas",
    deps=[validated_sbir_awards, sam_gov_entities, sam_gov_historical_entities,
          usaspending_vendor_master],
)
def resolved_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    sam_gov_entities: pd.DataFrame,
    sam_gov_historical_entities: pd.DataFrame | None,
    usaspending_vendor_master: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """See specs/firm-identity-resolution/ for behavior contract."""
```

### Asset checks

Three checks, corresponding to the three gates:

1. `firm_id_completeness_check` — every row has a `firm_id`; fail otherwise
2. `transition_precision_check` — recomputes precision against the frozen benchmark; fails if `< 0.85`
3. `stranded_firm_recall_check` — recall on the recall-lift set; fails if `< 0.60`

### Rewiring existing assets

Every downstream consumer's Dagster asset changes its input from `validated_sbir_awards` to `resolved_sbir_awards`. This is a mechanical edit — the columns of `resolved_sbir_awards` are a strict superset of `validated_sbir_awards` (no columns removed), so any consumer that reads specific columns continues to work unchanged. Consumers that ran their own identifier-join logic against upstream `uei`/`duns` can now join on `firm_id` instead.

## Rewiring plan

Split into two categories per the earlier ETL fit assessment.

### Category A — mechanical dependency swap

Consumer joins on `uei`/`duns` today; will switch to `firm_id` join with no other logic change.

| Consumer | Current identifier logic | Change |
|---|---|---|
| `phase_transition/phase_ii.py` | UEI-keyed | `firm_id`-keyed |
| `phase_iii_candidates/pairing.py` | UEI, DUNS fallback | `firm_id`-keyed |
| `cet/loading.py` | UEI/DUNS | `firm_id`-keyed |
| `usaspending_database_enrichment.py` | UEI to vendor lookup | `firm_id` to vendor lookup |
| `usaspending_iterative_enrichment.py` | UEI-keyed | `firm_id`-keyed |

Each is a few-line edit. Test coverage: existing consumer tests re-run against a fixture with `firm_id` populated.

### Category B — logic simplification

Consumer today reproduces some of the identity-resolution cascade in-line. That in-line logic can be deleted once `firm_id` is authoritative.

| Consumer | Redundant logic today | Post-rewire |
|---|---|---|
| `sec_edgar_enrichment.py:73-88` | Name-fallback branch when UEI missing | Delete branch — every row has a `firm_id` |
| `company_categorization.py:88-92` | `companies.dropna(subset=["company_uei"])` silently drops UEI-missing firms | Group by `firm_id` — captures the 40.9% previously stranded |
| `phase_transition/pairs.py` | `identifier_basis` column recording UEI vs DUNS fallback | Delete column; `firm_id` is the single join key. `resolution_method` from upstream replaces it |
| `sbir_neo4j_loading.py` | Constructs `organization_id` as `org_company_<uei>` or `org_company_DUNS:<duns>` | Use `firm_id` directly as `organization_id`; delete the identifier-based construction |

Category B is where the behavior change lives. Each rewrite deletes more code than it adds. Reviewers should focus on Category B; Category A is mechanical.

## Precision/recall calibration

### Precision gate (Requirement 6)

The transition-detection precision benchmark is defined in `packages/sbir-ml/` evaluation tests. It compares detected Phase II → Phase III pairs against a labeled ground-truth set. The gate:

1. Run the benchmark against the current DAG (baseline).
2. Enable `resolved_sbir_awards`; rerun the benchmark using `firm_id` as the join key.
3. If precision drops below 0.85, raise the `fuzzy_high_threshold` from 90 to (95, 97, 99) in sequence until precision is recovered.
4. Record the chosen threshold + measured precision in `reports/resolution/precision_calibration.json`.
5. CI fails if the resulting precision `< 0.85`.

The tuning knob is a single scalar. There is no risk of the calibration itself introducing accidental complexity.

### Recall gate (Requirement 7)

Two evaluation sets:

**Recall-lift set:** derived at build time from `data/raw/sbir/award_data.csv`. Selection query (executed once when the fixture is generated, cached to `tests/fixtures/resolution/stranded_firms.parquet`):

```sql
WITH firm_stats AS (
  SELECT company_norm,
         COUNT(*) AS total_awards,
         COUNT(*) FILTER (WHERE uei IS NULL) AS uei_missing
  FROM awards
  WHERE award_year BETWEEN 2000 AND 2020
  GROUP BY company_norm
  HAVING COUNT(*) >= 2 AND uei_missing = COUNT(*)
)
SELECT * FROM firm_stats;
```

Gate: at least 60% of awards belonging to firms in this set are assigned a shared `firm_id` (per Req 7.1).

**False-unification set:** hand-curated checked-in fixture at `tests/fixtures/resolution/known_distinct_firms.jsonl`. Format:

```json
{"firm_a": {"name": "Acme Corp",   "state": "CA", "uei": "..."},
 "firm_b": {"name": "Acme Corporation Inc", "state": "TX", "uei": "..."},
 "note": "Common-name confusion — distinct firms with different states"}
```

Initial ≥100 pairs, curated from historical false-positive incidents. Gate: zero pairs share a `firm_id`.

CI fails if either gate is not met. Both gates go into `reports/resolution/recall_precision.json`.

## Sequencing with `unify-company-into-organization`

The `unify-company-into-organization` spec (Phase 2 of graph-label unification) is scheduled to merge `:Company` nodes into `:Organization` nodes keyed on `uei`. Its own requirements.md notes this is "not the entity-resolution problem originally feared" and assumes UEI as the join key.

**Risk:** if that spec merges first, the 5,452 firms with no UEI on any award are silently excluded from the merged `:Organization` population. Firm-identity-resolution's recall lift then produces `firm_id`s that don't correspond to any node in Neo4j.

**Recommendation:** land firm-identity-resolution first, or coordinate the two so that `unify-company-into-organization` Phase 2 keys on `firm_id` instead of `uei`. Concretely:

1. Land the requirements.md and design.md for both specs.
2. Implement `resolved_sbir_awards` and its Category A rewiring (mechanical; low risk).
3. Update `unify-company-into-organization` design to key on `firm_id` (edit only; that spec's requirements language explicitly says "clean `:Company{uei}` → `MATCH :Organization{uei}` retarget", which would become "MATCH :Organization{firm_id}").
4. Implement Category B rewiring, which includes `sbir_neo4j_loading.py`'s switch to `firm_id` as `organization_id`.
5. Run the `unify-company-into-organization` graph migration on the resolved population.

This is a coordination note, not a blocking dependency. Both specs can land independently as long as step 3's edit is made before either implementation runs against the graph.

## Testing strategy

- **Unit — cascade:** fixture of 20 awards spanning identifier-exact, DUNS-crosswalk, fuzzy-high, fuzzy-low, unresolved. Assert each row's `resolution_method` and `resolution_source` match expected. Assert `firm_id` values match hand-computed hashes.
- **Unit — firm_id determinism:** run cascade twice on the same fixture, assert byte-identical output DataFrame.
- **Unit — Category B logic removal:** for each rewritten consumer, snapshot test that output matches pre-rewrite behavior on identifier-populated rows AND now includes rows that were previously dropped.
- **Integration — end-to-end DAG:** materialize `resolved_sbir_awards` on a fixture snapshot, assert downstream assets materialize and Neo4j loaders persist `firm_id` as `organization_id`.
- **CI gate — precision:** existing transition benchmark, re-run with `firm_id`. Fails on `< 0.85`.
- **CI gate — recall:** stranded-firm set. Fails on `< 0.60`.
- **CI gate — false-unification:** checked-in distinct-firm fixture. Fails on any collision.

Property tests to consider:
- `firm_id` is stable under permutation of input rows.
- `firm_id` for an identifier-exact match is identical whether the identifier is UEI or DUNS (via crosswalk).
- Every row has exactly one `firm_id`; no row has `resolution_method="unresolved"` with a non-synthetic ID prefix.

## Consumer contract

Downstream consumers may:

- **Join on `firm_id`** (recommended) — captures all awards attributable to the same firm across identifier-space regimes.
- **Filter by `resolution_method`** — precision-critical consumers may filter to `identifier_exact` or `identifier_exact | duns_crosswalk | fuzzy_name_high`, excluding `fuzzy_name_low` for safety.
- **Read raw UEI/DUNS/CAGE columns** — these remain present with canonicalization; existing UEI-keyed code paths continue to work unchanged.

Downstream consumers may NOT:

- Modify `firm_id` — it is a stable canonical key.
- Construct `firm_id`-shaped values themselves — the resolution stage is the sole producer.

## Open questions

1. **DUNS→UEI crosswalk source of truth.** SAM.gov exposes both identifiers on entities that were registered at the April 2022 transition, but firms whose DUNS expired before then were never assigned a UEI. For those firms, the crosswalk simply has no row. Do we want to also consult the SAM.gov historical extract's DUNS-era rows as a `duns_crosswalk` source, even though they'll never yield a UEI? Current design says yes (they still populate `duns_source: sam_gov_historical`), but the terminology "DUNS→UEI crosswalk" is a slight misnomer in that case. Rename to `identifier_lookup`?

2. **`opencorporates` in the cascade.** The requirements enumerate it as a reference source, but the current design does not include it in the R4 cascade explicitly. Should it be added as a step (e) after `internal_dedup` fails, or held as a follow-up? Current recommendation: follow-up — it introduces an external API dependency and the four in-scope sources already cover the empirical majority.

3. **Cross-run `firm_id` stability guarantees.** The design provides deterministic `firm_id` values within a run and across identical re-runs. But if the SAM.gov reference table changes (new entities appear, entities are purged), fuzzy-tier `firm_id` values may shift because they hash the master-list index. Do we want a persistent firms table that maintains stable `firm_id` values across reference-table refreshes? Current recommendation: no — this is speculative future-proofing that CLAUDE.md's Simplicity First principle warns against, and the downstream consumers this spec identifies do not require cross-run identity. Add if a concrete use case surfaces.

4. **CAGE as a first-class resolution input.** CAGE codes are populated in SAM.gov but not in SBIR bulk downloads. Requirement 3 has the resolution stage populate CAGE from the reference table where possible. Should there also be a `cage_exact` resolution method for the case where SBIR data starts carrying CAGE in the future? Current design: no, but the enum could be extended trivially if needed.
