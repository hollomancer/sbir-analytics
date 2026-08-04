# Neo4j Epistemic Assertions: Minimum Viable Migration Plan

**Status:** Revised proposal; no production implementation has started

**Repository baseline audited:** `origin/main` at `8500c0c6` on 2026-08-04

**Primary research inventory:** `docs/research-questions.md`

## Decision boundary

Approve a narrow architectural decision: inferred award-to-contract derivations should be
durable, typed candidate assertions before Neo4j publishes them.

Do not approve a general assertion platform, review system, or study rewrite as part of this
decision. Those remain an architectural north star and require a demonstrated consumer.

The three-PR milestone must prove only that:

1. candidate assertions are deterministic, with one claim per prior-source/contract-award pair and
   one frozen action-anchor rule;
2. they retain every qualifying action reference plus source and method provenance;
3. each confidence dimension distinguishes measured values from typed absence or failure;
4. Neo4j cannot strengthen their meaning; and
5. DuckDB and study tooling can consume the same content-addressed snapshot without querying
   Neo4j.

Version one is deliberately candidate-only:

- `claim_status = CANDIDATE`
- `support_class = C`
- `permitted_use = INVESTIGATIVE_ONLY`

The schema may reserve `ACCEPTED` and `REJECTED`, the other support classes, and broader permitted
uses. No version-one producer, graph projection, API, or study may emit or infer those values.

Parquet remains authoritative. Neo4j remains a disposable investigative projection. Frozen study
inputs remain the citability boundary, and no graph-derived rate becomes a research finding.

## 1. Current-state findings

### 1.1 The immediate defect is independent of the larger architecture

The active Dagster path, transition models, and Neo4j loader do not share one contract:

- `sbir_etl/models/transition_models.py` and
  `packages/sbir-ml/sbir_ml/transition/detection/` define rich transition evidence and signals.
- `packages/sbir-analytics/sbir_analytics/assets/transition/` produces a simpler candidate score
  table plus separate NDJSON evidence.
- `packages/sbir-graph/sbir_graph/loaders/neo4j/transitions.py` expects a third DataFrame shape.

The failing boundary is
`packages/sbir-analytics/sbir_analytics/assets/transition/utils.py`.
`_prepare_transition_dataframe()` creates a random UUID, drops evidence and signal dimensions,
omits `cet_area`, and emits `detection_date` where the loader expects `detected_at`. The result can
publish only part of the intended topology: `RESULTED_IN` can create a sparse contract endpoint
even when `TRANSITIONED_TO` is suppressed, and the technology writer can fail later.

This is an established publication defect. It should not be repaired by teaching the legacy
causal topology one more DataFrame schema. The replacement path should consume one typed,
content-addressed candidate contract, and the legacy writers should stop in PR 2.

### 1.2 Relevant code and documentation

| Concern | Exact paths | Current finding |
| --- | --- | --- |
| Candidate model and scorer | `sbir_etl/models/phase_iii_candidate.py`; `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py`; `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py` | Candidate IDs are deterministic and scores are decomposed. `build_uei_pairs()` preserves the target-transaction grain shared with the census, while the legacy S1 adapter deliberately selects one latest action per contract award and its output loses the stable transaction key. The assertion adapter must start from the preserved action-pair universe, not silently inherit that legacy row selection. |
| Legacy transition producer | `packages/sbir-analytics/sbir_analytics/assets/transition/scoring.py`; `detections.py`; `evidence.py`; `utils.py`; `loading.py` | Ranking, evidence, adaptation, and graph publication are separate contracts. Evidence checks do not form a blocking publication gate. |
| Dagster selection | `packages/sbir-analytics/sbir_analytics/assets/jobs/transition_job.py`; `packages/sbir-analytics/sbir_analytics/definitions.py` | Legacy graph assets are discoverable beyond the named job. Removing keys from one job is insufficient because broad asset selections can still execute decorated assets. |
| Neo4j transition loader | `packages/sbir-graph/sbir_graph/loaders/neo4j/transitions.py` | Writes `TRANSITIONED_TO` and causal `RESULTED_IN`, and creates identifier-only contract `FinancialTransaction` nodes. It stores serialized evidence only if a caller supplies it; the active adapter does not. |
| Profiles and progression | `packages/sbir-graph/sbir_graph/loaders/neo4j/profiles.py`; `packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py` | `TransitionProfile` IDs are timestamp-based; `ACHIEVED` summarizes mutable candidates; `FOLLOWS` is a heuristic phase progression with no in-repository production reader. |
| Graph queries | `packages/sbir-graph/sbir_graph/queries/pathway_queries.py`; `docs/queries/transition-queries.md` | Candidate-derived topology is queried as settled pathways and mutable graph rates. In-repository use is limited to tests and documentation. |
| Private API | `packages/sbir-analytics/sbir_analytics/api/repository.py`; `service.py`; `app.py`; `models.py` | `transition_count` and `transition_rate` are inferred from legacy edges without claim status, support, method, use, or assertion snapshot. No in-repository runtime client was found. |
| Graph schema | `docs/schemas/neo4j.md`; `packages/sbir-graph/sbir_graph/migrations/versions/006_unify_award_into_financial_transaction.py`; `007_unify_company_into_organization.py` | Awards and contracts should remain `FinancialTransaction` nodes and companies should remain `Organization` nodes. Migration 008 is the next slot on the audited baseline. |
| Census and study boundary | `sbir_etl/quality/study_manifest.py`; `specs/phase-iii-census/design.md`; `studies/phase-iii-census/study.yaml`; `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/assets.py`; `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/criteria.py`; `scripts/ci/validate_study_manifests.py` | Frozen hashes, declared estimands, and blocking checks already exist. The census enters at prior-award source row × target contract action, reports distinct contracts separately, and deduplicates signed obligations by stable target transaction ID. It must not be reinterpreted, regrouped, or silently switched to assertion grain. |
| Epistemic tiers | `docs/steering/epistemic-tiers.md` | The four artifact tiers are an architectural target with incomplete enforcement. They do not express the strength or disposition of an individual claim. |
| Package boundary | `docs/architecture/detailed-overview.md`; `scripts/ci/check_architecture_boundaries.py`; `tests/unit/scripts/test_architecture_boundaries.py` | The design document allows workspace packages to consume shared `sbir_etl` primitives. The executable guard currently forbids every `sbir_graph -> sbir_etl` import, so the guard is stricter than the documented architecture. |

Important test gaps are:

- `tests/unit/loaders/neo4j/test_transitions.py` and `test_transitions_nodes.py` use hand-built
  frames, not the active Dagster adapter.
- `tests/e2e/transition/test_graph_queries.py` mocks result shapes rather than exercising Neo4j
  projection semantics.
- `tests/unit/transition/test_transition_scores_stability.py` removes dynamic timestamps before
  comparison; it does not prove stable record identity.
- `tests/integration/test_phase_iii_retrospective_asset.py` uses engineered fixtures. It is an
  integration test, not an external precision benchmark.
- `tests/unit/phase_iii_candidates/test_pairing.py` proves that `build_uei_pairs()` retains every
  target transaction and prefers the USAspending-generated contract key; assertion projection
  tests do not yet exist.
- `tests/unit/phase_iii_census/test_criteria.py` enforces stable action and contract identifiers,
  unique prior-award/action pairs, action-date predicates, distinct-contract reporting, and
  transaction-deduplicated signed obligations. Those invariants are census non-regression tests,
  not assertion-grain tests.
- `tests/unit/api/test_analytics_api.py` accepts a bare graph-derived `transition_rate`.
- `tests/unit/test_award_progressions.py` accepts a `FOLLOWS` confidence above one, confirming that
  the value is not a calibrated probability.
- `tests/unit/ot_consortium/test_neo4j_loader.py` correctly verifies that T2-T4 rows do not create
  `PERFORMED_BY` edges.

The existing candidate model also stores numeric zero for several unavailable or unevaluated
signals. Those values cannot be safely reverse-mapped to “measured with no support.” PR 1 must
derive dimension status from source availability and method execution, not from the scalar alone.

### 1.3 Verification of the ten stated concerns

| # | Concern | Audited disposition |
| --- | --- | --- |
| 1 | Transition nodes and `TRANSITIONED_TO` store evidence | **Misstated end to end.** The low-level loader can store supplied serialized evidence; the active adapter drops it. |
| 2 | `RESULTED_IN` is stronger than the detector | **Current.** A model-generated candidate can receive a causal edge without review or an authoritative designation. |
| 3 | Transition loading creates sparse contracts | **Current.** The loader creates identifier-only contract endpoints because no independent contract observation loader exists. |
| 4 | Rates count candidates rather than transitioned awards | **Mixed and still material.** Some pandas paths deduplicate award IDs, but still call score-qualified candidates transitions. Profiles and graph queries can count candidate rows or mutable topology. |
| 5 | `TransitionProfile` IDs are timestamp-based | **Current.** Transition IDs can also be random in the active adapter. |
| 6 | `FOLLOWS` is heuristic | **Current.** It uses firm, agency, program, timing, PI, and topic continuity rather than a source-observed succession record. |
| 7 | SEC event history is flattened | **Current for Neo4j.** The graph receives aggregate/latest properties. This is not part of the first assertion milestone. |
| 8 | OT uses separate `Firm` nodes | **Current but dormant.** The active Dagster path stops at Parquet/report outputs. |
| 9 | OT withholds unsupported `PERFORMED_BY` | **Already fixed and tested.** Preserve the T1-only behavior; do not generalize it into this assertion family. |
| 10 | Existing study and tier machinery can support snapshots | **Directionally true.** Content-addressed assertion metadata and an explicit study input binding are still required. |

### 1.4 Documentation discrepancies

The migration should correct only documentation touched by the new candidate path:

- `docs/transition/evidence-bundles.md` describes evidence properties that the active writer does
  not publish.
- `docs/transition/detection-algorithm.md` and
  `docs/data/dictionaries/transition-fields-dictionary.md` overstate a composite ranking as a
  probability.
- `docs/schemas/neo4j.md` overstates graph idempotency while random and timestamp-based IDs remain.
- `docs/queries/transition-queries.md` uses effectiveness, success, enablement, and top-performer
  language unsupported by candidate-only topology.
- `packages/sbir-analytics/sbir_analytics/api/models.py` defaults provenance `as_of` to response
  time, not a data cut or assertion snapshot.

Other inconsistencies, including SEC event flattening and dormant patent loader docstrings, are
real but explicitly deferred.

### 1.5 Research and consumer traceability

The first assertion family directly supports B2 (award-to-contract outcome coverage), B3
(latency to an observed contract action), and E2 (recipient-to-contractor identity) by making
candidate lineage inspectable and reproducible without asserting legal Phase III status. It
replaces semantics currently exposed by pathway queries and the private API.

A2, B1, E1, E3, and E6 are downstream beneficiaries, not questions this migration answers. B2 and
B3 use the contract-award assertion as their durable outcome concept, but the supporting action
remains the temporal observation. Any later candidate-coverage or latency quantity must name the
assertion definition, action-anchor rule, and denominator. It is not a “graph transition rate.”

The existing census serves a different but compatible purpose. Its observational unit is prior
award source row × target contract action so frozen predicates, modification-level dates, signed
obligations, and drop-off tables remain auditable. The assertion unit is prior award source row x
target contract award so multiple modifications do not become multiple commercialization outcomes.
The latter is a deterministic projection from the former's compatible action universe, not an
exact reproduction of the census estimand or row grain.

Patent derivation for C2, ownership for A1/F2, SEC event history for F1, and phase progression for
B2 remain exploratory or unimplemented. They should not be migrated merely to make the graph
uniform. Official agency/FPDS Phase III coding remains a distinct observed designation used by the
existing Phase III source and census paths.

## 2. Recommended decision

### 2.1 Adopt the hybrid model for one assertion family

Adopt `AWARD_CONTRACT_DERIVATION` as the first and only committed assertion type. It corrects the
highest-risk inferred topology while preserving the platform:

- the assertion snapshot, not Neo4j, is durable;
- Neo4j remains useful for investigation and visualization;
- DuckDB reads the same Parquet rows as the graph loader;
- studies retain control of denominators, estimands, and citability; and
- official source designations remain distinguishable from model-generated candidates.

The resolved unit decision is:

- assertion: Phase II source record × federal prime contract award;
- evidence: one or more federal contract actions; and
- census: Phase II source record × federal contract action.

The assertion output is a deterministic action-to-contract projection for B2 candidate coverage
and candidate-defined B3 latency. It is not the census estimand and does not establish that an
anchor action is legally Phase III. Other B3 causal, survival, and effectiveness estimands remain
outside this migration.

Directed and follow-on SAM opportunity candidates do not have contract endpoints and remain
exploratory outputs. Legacy transition rows without recoverable source and method provenance are
not backfilled as if they were equivalent assertions.

### 2.2 Resolve the package contradiction with a narrow Option A

Permit `sbir_graph` to import the canonical contract from `sbir_etl.assertions`.

This is the least artificial boundary because `docs/architecture/detailed-overview.md` already
defines `sbir_etl` as the shared inward dependency. The resulting production dependency graph is:

```text
sbir_analytics ──▶ sbir_graph ──▶ sbir_etl.assertions
       │
       └─────────▶ sbir_ml ─────▶ sbir_etl
```

`sbir_graph` and `sbir_ml` still do not depend on one another, and `sbir_etl` still imports no
workspace package. The assertion contract modules imported by graph must depend only on the
standard library and Pydantic; they must not import Dagster, Neo4j, graph loaders, DuckDB, or ML
detector code.

Semantic enforcement must accompany the dependency:

- add `sbir-etl` to `packages/sbir-graph/pyproject.toml` and update `uv.lock`;
- extend `scripts/ci/check_architecture_boundaries.py` to permit the exact module prefix
  `sbir_etl.assertions` from `sbir_graph`, not arbitrary `sbir_etl.*` imports; and
- extend `tests/unit/scripts/test_architecture_boundaries.py` to prove that assertions are
  allowed while bare `sbir_etl`, `sbir_etl.models`, `sbir_etl.identity`, `sbir_ml`, and
  `sbir_analytics` remain forbidden from graph. Test both `import` and `from ... import ...` forms.

The graph loader should accept `AssertionRecord` and `AssertionSnapshotManifest` objects directly.
It should not accept an untyped DataFrame as the semantic boundary.

Option B, a new `sbir-contracts` distribution, is disproportionate for one assertion type. Option
C, keeping graph orchestration in analytics, would split persistence responsibility and leave the
graph package unable to enforce the canonical payload it writes. Revisit a neutral contracts
distribution only if multiple independently released consumers make the `sbir-etl` distribution
weight an operational problem.

### 2.3 Relationship disposition

| Relationship | What it is now | Minimum viable disposition |
| --- | --- | --- |
| `TRANSITIONED_TO` | Algorithmic inference represented as topology | Stop new writes and delete existing edges in PR 2 after backup and verified assertion publication. |
| `RESULTED_IN` | Algorithmic inference with unjustified causal wording | Stop new writes and delete existing edges in the same PR 2 migration. |
| `POSSIBLE_DERIVATION` | Not present | Deterministic convenience projection from the supplied candidate snapshot only. |
| `ACHIEVED` | Deterministic aggregate over uncertain mutable rows, with an overstrong name | Remove with transition profiles in PR 3; do not make it an assertion. |
| `FOLLOWS` | Heuristic phase-progression inference | Stop and remove in PR 3. Add no replacement without a consumer. |
| `ENABLED_BY` | Patent contribution inference; inert in the active call | Do not activate. A future consumer would require narrower patent-support semantics. |
| OT `PERFORMED_BY` | Exact-identifier attribution only for T1 | Preserve the current withholding of T2-T4. Keep outside this migration. |
| Official Phase III designation | Source-observed designation, not current candidate topology | Keep distinct. A future edge should be named `OFFICIALLY_IDENTIFIED_AS_PHASE_III`, never inferred from candidate score. |

No `SUPPORTED_DERIVATION` edge exists in version one because there is no accepted-claim policy.

## 3. Target architecture

### 3.1 Minimal data flow

```text
existing SBIR award input + existing USAspending contract input
                              │
                              ▼
       census-compatible award × contract-action pairs
                              │
                              ▼
               retrospective candidate predicates
                              │
                              ▼
 deterministic group by prior row + contract; select anchor
                              │
                              ▼
          content-addressed AssertionSnapshot (Parquet + manifest)
                  │                                  │
                  ▼                                  ▼
       Neo4j investigative projection       DuckDB / Parquet reader
                  │                                  │
                  ▼                                  ▼
       claim-aware API and graph UI        exploratory analysis or future study
```

The detector remains outside `sbir_graph`. The graph package loads and queries assertions; it does
not infer them. Graph and ML packages do not import each other.

### 3.2 Object boundaries

**Observed records.** The first assertion snapshot fingerprints the exact existing SBIR award and
USAspending contract inputs. The relevant observations have three distinct grains:

- the prior Phase II source row is the assertion subject;
- the federal prime contract award, identified by the USAspending-generated unique award key, is
  the assertion object; and
- the USAspending contract actions are first-class supporting observations carrying dates, codes,
  descriptions, and signed obligations.

The first release does not retrofit a general observation schema or create graph nodes for every
action. The first graph migration reuses complete award nodes and adds a complete contract
observation loader; it must never manufacture a sparse endpoint from assertion data. Future
normalized source contracts should preserve `source_system`, `source_record_id`,
`source_snapshot_id`, `record_hash`, `retrieved_at`, and `source_locator`, but that broader retrofit
is outside this milestone.

**Assertions.** A candidate assertion refers to one prior-award source-row key, one contract-award
key, every qualifying supporting action key, one deterministically selected anchor action, any
contradicting source-record keys, and the hashes of the exact input files in its manifest. It does
not replace or aggregate away those observations. Multiple modifications under one contract award
produce one logical claim, not multiple outcomes.

**Research findings.** A finding binds to a content-addressed assertion snapshot and states an
estimand. It never treats mutable Neo4j topology as the final analytical input.

Version one does not create `SourceRecord` or `ReviewDecision` nodes. Source references remain
typed keys on the assertion and source-snapshot bindings in the manifest. Promote them to graph
nodes only after a user needs to traverse, compare, or review source records graphically.

### 3.3 Package and module boundaries

The canonical contract is small:

```text
sbir_etl/assertions/
    __init__.py
    enums.py
    models.py
    identifiers.py
    validation.py
    snapshots.py
```

Responsibilities are:

- `enums.py`: claim status, support class, permitted use, assertion type, dimension status, and the
  minimal version-one dimension reasons;
- `models.py`: frozen `DimensionAssessment`, assertion record, and snapshot manifest contracts;
- `identifiers.py`: canonical record-key normalization and semantic hashes;
- `validation.py`: candidate-only, status/score/reason, action-to-contract membership, and
  deterministic anchor invariants; and
- `snapshots.py`: canonical row ordering, logical hashing, physical SHA binding, no-overwrite
  behavior, and collision detection.

Dagster adapters and materialization stay in
`packages/sbir-analytics/sbir_analytics/assets/transition_assertions/`. Detector code remains in its
current analytics/ML locations. Neo4j loading stays in the existing directory with clearer modules:

```text
packages/sbir-graph/sbir_graph/loaders/neo4j/
    contracts.py
    assertions.py
    convenience_edges.py
```

No loader-directory reorganization is justified in the first milestone.

### 3.4 Dagster asset graph

The first producer should be manual and unscheduled while parity is established:

```text
validated_phase_ii_awards
normalized_usaspending_contract_actions
existing award input fingerprint
existing contract input fingerprint
                    │
                    ▼
shared census-compatible action pairs
  [prior source row × target transaction; census remains unchanged]
                    │
                    ▼
retrospective candidate predicates
                    │
                    ▼
transition_candidate_assertions
  [group by prior_source_record_key + target_contract_key]
                    │
                    ▼
transition_assertion_checks  [blocking]
                    │
                    ▼
transition_assertion_snapshot + manifest
                    ├──────────────▶ neo4j_assertion_load       [PR 2]
                    └──────────────▶ DuckDB/Parquet reader test [PR 3]
```

The assertion adapter reuses the transaction-preserving boundary in
`packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py`; it must not consume
only the current candidate Parquet/NDJSON or `_legacy_s1_target_transactions()`, which keeps the
latest action and drops its stable key. It preserves the existing retrospective detector's logical
FPDS-contract candidate selection, rejoins those prior-award/contract pairs to the shared action
boundary, and groups by `prior_source_record_key` and `target_contract_key`. This is a narrow
adapter projection; `phase_iii_census` itself is not an upstream asset. The contract key uses the
existing generated-unique-award-ID precedence and never falls back to bare PIID.

For version one, a qualifying supporting action is a shared exact-UEI pair row that (a) matches an
emitted retrospective FPDS-contract logical pair, (b) has a nonblank stable transaction ID and
generated contract key, and (c) has a valid target action date after the detector's declared
temporal boundary for the prior award. These rules are frozen in the method contract before
materialization; census-only predicates are not imported into them.

For each group, the adapter retains all qualifying `supporting_action_record_keys` and chooses the
anchor as the earliest qualifying target action after the applicable prior-award temporal boundary,
breaking date ties by stable target transaction ID. B3 latency is computed from that action under
the frozen rule. It does not aggregate action obligations into the assertion; action-grained amounts
remain available to DuckDB and the census. It does not merge directed or follow-on opportunity
candidates. If a logical candidate has no qualifying dated action, the adapter emits no assertion
and records the deterministic exclusion in its check metadata; it never chooses a pre-boundary,
undated, or input-order fallback anchor.

The adapter copies no timestamp or Dagster run ID into semantic assertion identity. The snapshot
asset reuses an existing file when the logical hash and bound physical hash match; it never
overwrites that path. PR 1 assigns the new assets to an explicitly manual-only group and changes
the broad selections in `packages/sbir-analytics/sbir_analytics/definitions.py` to exclude that
group, with a definition test. No new source-snapshot asset family is introduced, and no existing
census asset, predicate, count, or output schema changes.

Human review is not in this graph. A later review asset must be a separate input and must create a
new revision or status record rather than mutating detector output.

### 3.5 Neo4j schema

The minimum graph is:

```text
(award:FinancialTransaction {transaction_type: "AWARD"})
    -[:SUBJECT_OF]->
        (assertion:Assertion)
            -[:TARGETS]->
                (contract:FinancialTransaction {transaction_type: "CONTRACT"})

(assertion)-[:GENERATED_BY]->(method:MethodRun)

(award)-[:POSSIBLE_DERIVATION]->(contract)
```

`Assertion` is keyed by `assertion_revision_id`. It exposes the logical `assertion_id`, candidate
status/support/use, structured dimension assessments, method metadata, supporting action keys,
anchor action key/date, contradicting source-record keys, and assertion snapshot hash. Nested Parquet
dimension structs are flattened in Neo4j into explicit `*_status`, `*_score`, `*_reason`, and
`*_error_category` properties; missing properties never imply a status. `MethodRun` uses the
originating detector run ID from the snapshot manifest. Republishing the graph reuses that node;
the graph-load run is not a new claim-generating method run. Operational run identity is not part
of the assertion revision hash.

`POSSIBLE_DERIVATION` is optional for semantic correctness but included because PocketGraph and
Cypher users need a compact investigative view. It is never an independent record. Its projection
rule is exactly: one edge per assertion revision in the supplied snapshot whose values are
`CANDIDATE`, `C`, and `INVESTIGATIVE_ONLY`. It carries at least:

- `assertion_id`
- `assertion_revision_id`
- `assertion_snapshot_hash`
- `claim_status`
- `support_class`
- `permitted_use`
- `identity_status`
- `identity_score`
- `identity_reason`
- `technology_status`
- `technology_score`
- `technology_reason`
- `temporal_status`
- `temporal_score`
- `temporal_reason`
- `ranking_score`
- `method_version`
- `projection_generated_at`

The edge may omit a `*_score` only when its accompanying status explicitly explains why the
dimension is not measured. Error categories remain on the assertion node unless an active graph
filter needs them; the authoritative typed assessment remains the Parquet assertion record.

`projection_generated_at` is copied from the reused snapshot manifest's fixed `generated_at`; it
is never the graph-load time. Republishing the same snapshot therefore produces the same normalized
projection properties.

Every projection query receives the expected assertion snapshot hash and requires both the edge's
`assertion_snapshot_hash` and its referenced assertion's snapshot hash to match it. A blocking
anti-join proves that every edge resolves to its `assertion_revision_id` in that snapshot.

PR 2 adds one explicitly named award-to-contract candidate query. Legacy factual pathway and graph
rate helpers raise a typed retirement error without executing Cypher; they are not aliases for the
new candidate semantics.

The MVP graph contains one supplied snapshot for this assertion family. A deterministic replacement
operation verifies the supplied hash, replaces only nodes and edges for
`AWARD_CONTRACT_DERIVATION`, and stores the hash on every assertion and convenience edge. It does
not introduce a current-snapshot node, staging state machine, or as-of graph service. Historical
snapshots remain in Parquet, and rollback republishes the prior named snapshot.

For MVP queries, “active snapshot” means that sole supplied hash, recorded in the publication
receipt. Publication blocks unless the graph contains exactly one snapshot hash for this assertion
family and it equals the receipt.

### 3.6 API and visualization boundary

The minimum claim-aware API is:

- `GET /v1/awards/{award_record_key}/transition-assertions`
- `GET /v1/assertions/{assertion_revision_id}`

Responses expose the logical and revision IDs, claim status, support class, permitted use,
the full typed identity/technology/temporal assessments, ranking-score definition, method
ID/version/fingerprint, supporting action keys, anchor action key/date, contradicting record keys,
and assertion/source snapshot hashes.

The API embeds source references rather than presenting them as if they were retrieved evidence.
Candidate-constant status/support/use filters are deferred. PocketGraph and direct Cypher users can
expand or contract the graph using the properties already present on assertion nodes and projected
edges, especially each dimension's status and independently measured score. A
`NOT_MEASURABLE` technology dimension can therefore be shown separately from a measured low score
instead of disappearing under a threshold. Add API filters only when a real client needs them. No
client may advertise `ranking_score` as a truth probability.

Do not silently reimplement `/v1/analytics/transitions` with a new denominator. If no external
consumer exists, retire it with an explicit response and replacement link. If an owner identifies
an external client, serve a clearly labeled frozen legacy result for one release; do not retain
live causal topology solely for compatibility. Replace `transition_count` with
`candidate_assertion_count` rather than changing its meaning in place.

### 3.7 Study boundary

PR 3 adds a small DuckDB/Parquet reader plus an integration test proving that analysis code can
validate and consume the same assertion snapshot without Neo4j. It does not change the shared
`StudyManifest` schema because no named study adopts assertions in this milestone.

When a study does adopt assertions, its frozen contract must bind the logical hash, physical file
SHA, assertion schema, allowed status/support/use values, method fingerprint, source hashes, and
inclusion/exclusion rules. `review_cutoff` becomes required only when reviewed assertions exist.

The current Phase III census remains unchanged at action-pair grain. The assertion adapter is a
one-way deterministic projection from the compatible action universe; it does not feed regrouped
rows back into census predicates, drop-off counts, or obligation totals. Supporting action records
and amounts remain available for DuckDB analysis even though the graph object is a contract award.
Pair counts and transaction-deduplicated signed dollars remain census quantities; assertion counts
are distinct prior-source-row/contract-award claims and the assertion stores no aggregated
obligation.

A version-one candidate snapshot may support an exploratory, explicitly candidate-defined
quantity, for example:

> The proportion of eligible Phase II awards with at least one class-C investigative
> award-contract derivation candidate produced by detector version V within five years.

It may not be called a transition rate, accepted derivation rate, legal Phase III rate, or citable
finding. Neo4j is never the final input.

## 4. Epistemic alignment

### 4.1 Artifact tier and claim strength are independent axes

| Axis | Question | Values in scope |
| --- | --- | --- |
| Artifact tier | How rigorously was the producing artifact created and maintained? | `primitives`, `pipelines`, `exploratory`, `evidence` |
| Claim status | What disposition currently applies to this assertion? | `CANDIDATE`; `ACCEPTED` and `REJECTED` reserved |
| Support class | How strong is the underlying support? | A, B, C, D; only C emitted in version one |
| Permitted use | What may a downstream consumer do? | `INVESTIGATIVE_ONLY`; broader uses reserved |

None is inferred from another. In particular, deterministic pipeline code can faithfully publish
an exploratory candidate, and an accepted claim produced through exploratory code would still be
non-citable.

### 4.2 Tier placement for this milestone

| Component | Artifact tier | Reason |
| --- | --- | --- |
| `sbir_etl/assertions/` contracts, IDs, and validation | `primitives` | One versioned meaning shared by producers and consumers. |
| Content-addressed serialization and graph loading | `pipelines` | Deterministically materializes declared inputs without changing claim meaning. |
| Retrospective detector and its assertion contents | `exploratory` | It performs contestable scoring and has not earned evidence-tier authority. |
| Candidate coverage summaries | `exploratory` | They describe detector output, not real-world transition prevalence. |
| Existing frozen studies that satisfy their own contracts | Their existing declared status | They are not promoted, demoted, or silently switched by this migration. |
| Any future externally citable assertion finding | `evidence`, only after a separate promotion | Requires a frozen spec, hash enforcement, blocking checks, declared estimand, and approved assertion inclusion policy. |

The snapshot manifest should say `producer_epistemic_tier: exploratory`. It may validate that value
against a small canonical vocabulary, but this project must not add general tier enforcement to all
repository artifacts.

### 4.3 Required documentation amendment

Amend `docs/steering/epistemic-tiers.md` narrowly to state that:

1. artifact tier and claim status/support/permitted use are orthogonal;
2. content addressing and deterministic publication do not promote exploratory claims; and
3. the assertion snapshot manifest records the producing tier without claiming repository-wide
   tier enforcement.

Do not add directories, promotion workflows, or an `ArtifactTier` field to every model in this
change.

## 5. Schema proposal

### 5.1 Enumerations

Use `StrEnum` for:

```text
AssertionType: AWARD_CONTRACT_DERIVATION
ClaimStatus: CANDIDATE, ACCEPTED, REJECTED
SupportClass: A, B, C, D
PermittedUse: INVESTIGATIVE_ONLY, STUDY_ELIGIBLE, EXTERNALLY_CITABLE
DimensionStatus:
    MEASURED
    NOT_MEASURABLE
    NOT_APPLICABLE
    NOT_EVALUATED
    EVALUATION_FAILED
DimensionReason:
    SOURCE_FIELD_UNAVAILABLE
    SOURCE_TEXT_BELOW_RETRIEVAL_FLOOR
```

The version-one producer validator accepts only the first candidate tuple. The reserved enum values
do not authorize any code path to publish, review, or cite such claims. The adapter writes each
field explicitly under its versioned method policy; the general model does not derive one axis from
another.

For this family, the contract states that an `AWARD_CONTRACT_DERIVATION` emitted by the algorithmic
detector has support class C. No score threshold assigns or upgrades support class. Scores rank
candidates within class C only.

`DimensionStatus` is the epistemic state; `None` is not. `DimensionReason` starts with only the
reasons required by the version-one adapter and is extended only when a producer can define a new
case precisely. Detector exceptions use a separately named `error_category`, not a fabricated
reason or score.

### 5.2 Canonical assertion record

A frozen Pydantic model with `extra="forbid"` should embed each optional scoring dimension as a
structured value:

```python
class DimensionAssessment(BaseModel):
    status: DimensionStatus
    score: Decimal | None = None
    reason: DimensionReason | None = None
    method_detail: str | None = None
    error_category: str | None = None
```

The validator enforces:

- `MEASURED` requires a bounded finite score; zero means measured with no supporting signal;
- every non-measured status prohibits a score;
- `NOT_MEASURABLE` requires a reason;
- `EVALUATION_FAILED` requires an error category; and
- missing or null data never stands in for one of these states.

`error_category` is a stable method-versioned slug, never an exception message or traceback.
`method_detail` is omitted unless the V1 producer has a deterministic diagnostic to preserve; it
must not contain timestamps, run IDs, paths, or other operational text that would destabilize a
revision.

The candidate record should contain:

```text
assertion_schema_version
assertion_id
assertion_revision_id
assertion_type = AWARD_CONTRACT_DERIVATION
subject_record_key
object_contract_key
claim_status = CANDIDATE
support_class = C
permitted_use = INVESTIGATIVE_ONLY
identity: DimensionAssessment
technology: DimensionAssessment
temporal: DimensionAssessment
ranking_score
ranking_score_definition
method_id
method_version
method_fingerprint
supporting_action_record_keys
anchor_action_record_key
anchor_action_date
contradicting_source_record_keys
```

The dimensions remain separate. An exact UEI match can support identity without proving technical
derivation; semantic similarity can support technology continuity without establishing legal Phase
III status. For sparse DoD procurement text, for example, technology may be
`NOT_MEASURABLE`/`SOURCE_TEXT_BELOW_RETRIEVAL_FLOOR`; that is different from a measured score of
zero. The composite score exists only to rank candidates. Its named definition and method
fingerprint must state how non-measured dimensions are handled and must not silently impute them to
zero. Source-authority and record-completeness fields are deferred in the MVP; `ranking_score` must
not proxy for them.

The retrospective adapter must declare a versioned, field-by-field mapping from existing detector
signals to the three assessments. It must not derive a dimension from the composite score. A signal
that was not measured receives the appropriate explicit non-measured status; only an actual
evaluation with no support receives a measured zero. Existing scalar zeroes are insufficient
evidence for that distinction, so ambiguous legacy rows must be re-evaluated from their source
fields or marked with an explicit non-measured status.

PR 1 preserves the detector's existing composite value as a visibly legacy-defined
`ranking_score`; it does not change weights or renormalize scores around missing dimensions. The
`ranking_score_definition` must disclose that behavior. Correcting the ranking policy is detector
work subject to the repository's >=85% precision benchmark; until then, downstream consumers must
not use the legacy ranking to erase or override the typed dimension state.

The record grains are deliberately different:

- **census unit:** prior award source row × target contract action, preserving each modification,
  date, signed obligation, and frozen predicate result;
- **assertion unit:** prior award source row × target contract award, representing one candidate
  derivation outcome; and
- **evidence unit:** target contract action, establishing dates, codes, descriptions, and amounts.

`subject_record_key` is the namespaced stable Phase II source-row identity. On the audited input,
derive it from the canonical unique `prior_award_id`; do not assume `prior_award_key` is present.
PR 1 may introduce a different key only if it proves the key is stable, unique, and available on
every validated Phase II row and documents the migration.

`object_contract_key` is the namespaced USAspending generated unique award identifier selected by
the existing `award_key_series()` precedence, never bare PIID. The adapter groups qualifying action
pairs by those two keys, sorts and preserves every `supporting_action_record_key`, and selects
`anchor_action_record_key` by the frozen earliest-qualifying-date/stable-transaction-ID rule.
`anchor_action_date` is copied from that action; no derived obligation total belongs in the
assertion. PR 1 fails closed when any required canonical subject, contract, action, or anchor key is
missing and never falls back to a random ID.

### 5.3 Snapshot manifest

The snapshot manifest should contain:

```text
manifest_schema_version
assertion_schema_version
assertion_type
logical_snapshot_hash
parquet_path
file_sha256
row_count
producer_epistemic_tier = exploratory
method_id
method_version
method_fingerprint
method_run_id
generated_at
source_snapshots[]:
    source_system
    source_snapshot_id
    hash_algorithm
    source_hash
```

For version one, `source_snapshot_id` may identify the exact existing input file or snapshot. Do not
require a new locator, retrieval event, or normalized `SourceRecord` store merely to populate the
manifest. The bindings must include both the validated prior-award input and the exact
transaction-grain contract-action input from which supporting and anchor action keys were resolved.

Parquet is not intrinsically immutable. The enforced contract is a **content-addressed assertion
snapshot**:

1. canonicalize and sort substantive records and source bindings;
2. hash the assertion schema version, method fingerprint, ordered source bindings, and canonical
   assertion rows;
3. use the logical hash in the file name;
4. write once and record the physical Parquet SHA-256;
5. bind both hashes in the manifest; and
6. block if an existing logical path has different canonical content or a mismatched bound file
   hash.

The logical hash includes canonical endpoints, the complete typed dimension assessments,
normalized and sorted supporting action/evidence references, the anchor action key/date, source
bindings, method fingerprint, and schema version. It excludes row order, input evidence-list order,
materialization and method-run timestamps, output paths, Parquet writer metadata, and other
operational fields.

An identical rerun validates and reuses the existing snapshot. Changed source hashes produce a new
logical snapshot even if the resulting assertion rows happen to match. Operational timestamps and
`method_run_id` belong in the manifest and do not perturb assertion or logical snapshot identity.

### 5.4 Stable identifiers and revisioning

Use canonical JSON, normalized namespaced record keys, sorted evidence-key lists, an explicit schema
version, and SHA-256 domain separation.

```text
assertion_id = hash(
    assertion_type,
    subject_record_key,
    object_contract_key,
)

assertion_revision_id = hash(
    assertion_id,
    substantive claim fields,
    typed dimension assessments,
    ranking definition,
    method fingerprint,
    supporting action and contradicting record keys,
    anchor action key and date,
)
```

`assertion_id` is the logical subject-predicate-object claim. `assertion_revision_id` is the
immutable payload key used in Parquet and Neo4j. Do not add `assertion_version`,
`assertion_version_id`, or an ordinal counter. A changed detector payload produces a new revision
under the same logical ID.

The detector is intentionally absent from `assertion_id`: two methods evaluating the same
award-contract proposition are discussing one logical real-world claim, not creating two claims.
Version-one snapshots allow exactly one current candidate revision per `assertion_id`. If multiple
independent detector outputs are introduced later, publication must first define an explicit
selection or aggregation/fusion contract; it must not change the logical ID to encode the detector.
Until that decision is made, duplicate logical IDs in one snapshot are blocking.

Supersession and review decisions are deferred. When a consumer requires them, add a sidecar status
record or a new revision linked to its predecessor; do not mutate the historical candidate row.

## 6. Migration plan

| PR | Runtime boundary | Data migration | Rollback point |
| --- | --- | --- | --- |
| 1 — fix and freeze contract | Add the ADR, canonical candidate model with typed dimension absence, deterministic action-to-contract grouping, stable IDs, content-addressed snapshot, blocking checks, and one manual retrospective FPDS adapter. Change no graph/API or census behavior. | None; do not translate legacy graph rows. | Unregister the manual group and revert additive contracts. Keep snapshots for diagnosis. |
| 2 — replace topology | Load complete contracts, assertions, method runs, explicit relationships, and `POSSIBLE_DERIVATION`; switch graph reads; isolate old API semantics; stop writers; delete legacy causal edges after backup. | Reproduce from the PR 1 snapshot; do not fabricate provenance for legacy rows. | Restore the named pre-cutover backup. |
| 3 — migrate consumers and retire legacy | Add two claim API reads and a DuckDB reader test; remove orphaned transition/profile state, `ACHIEVED`, and `FOLLOWS`. | Use a migration receipt; delete only nodes proven to be legacy artifacts. Leave ambiguous contracts for a later rebuild. | Before node cleanup, preserve the PR 2 graph backup; after cleanup, restore it if required. |

PR 1 assigns its assets to a manual-only group and tests their exclusion from broad jobs. PR 2
stops every new `TRANSITIONED_TO` and `RESULTED_IN` write and requires existing complete endpoints.
It also makes `/v1/analytics/transitions` return `410 Gone`, removes award-history
`transition_count` without inserting a zero-valued replacement, removes stale organization
transition fields, and removes `Transition` from freshness before edge deletion. PR 3 adds the
distinctly named `candidate_assertion_count` and assertion freshness. It does not change the shared
study-manifest schema or migrate unrelated pandas analyses.

The repository's live transition-rate query is removed. A transport-neutral typed retirement error
is raised by the service and mapped to a stable authenticated 410 response, so non-HTTP callers also
fail loudly and no Neo4j session is opened.

The live cutover is:

1. materialize and validate the content-addressed snapshot;
2. back up Neo4j and record legacy node/edge counts;
3. load the complete endpoints and assertion projection under the supplied hash;
4. verify endpoint, count, property, and idempotency checks;
5. deploy the new graph queries and explicit API isolation;
6. disable legacy writers;
7. delete all `TRANSITIONED_TO` and `RESULTED_IN` relationships with a dry-run/apply migration;
8. record zero remaining legacy causal edges in the migration receipt; and
9. in PR 3, remove isolated legacy nodes, profiles, and `FOLLOWS` after a second receipt.

Do not use an `inactive` property. PocketGraph and ad hoc Cypher can still display such edges, so it
would preserve the original epistemic defect. If an external client needs temporary access to the
old metric, serve a versioned frozen API snapshot with an expiry date; never retain live legacy
topology for compatibility. There are never two live producers.

## 7. Testing and validation

### 7.1 Publication checks

| Required invariant | MVP enforcement | Level |
| --- | --- | --- |
| Every assertion resolves its subject and contract object | Validate stable prior source-row and generated contract-award keys before snapshot; `MATCH` complete graph endpoints before publication | Blocking |
| Every assertion records method and version | Require method ID, version, fingerprint, and ranking definition | Blocking |
| Every action/evidence reference resolves to a source snapshot | Resolve every namespaced action or source key to a bound snapshot manifest entry | Blocking |
| Every assertion has action evidence | Require at least one unique `supporting_action_record_key`; candidates without a valid dated action are deterministically excluded, never given a fallback | Blocking assertion invariant |
| Supporting actions belong to the asserted contract | Recompute the generated contract key for each action and require it to equal `object_contract_key` | Blocking |
| The anchor action is deterministic | Require the anchor to be a supporting action and equal the earliest qualifying date after the temporal boundary, with transaction-ID tie-break | Blocking |
| Assertion collapse preserves the declared grains | Require assertion count to equal distinct prior-source-row/contract-key pairs in the qualifying action set, repeated modifications to produce no duplicate assertion, and action-pair census row counts to remain unchanged | Blocking |
| Accepted assertions satisfy acceptance rules | No accepted producer exists; reject any non-`CANDIDATE` row in the MVP path | Blocking |
| Rejected assertions cannot make positive edges | Projection allowlist contains only the exact MVP tuple; fixture rows with `REJECTED` must be refused | Blocking |
| Superseded assertions are absent from current study snapshots | Supersession is absent in MVP; adding it later requires this gate before schema activation | Deferred migration gate |
| Identical inputs and methods yield stable IDs | Shuffle rows and rerun; compare assertion IDs, revision IDs, logical hash, and canonical rows | Blocking |
| A snapshot has one row per logical claim and unique revisions | Reject duplicate `assertion_id` or `assertion_revision_id` values before writing | Blocking |
| Graph projection is reproducible | Rebuild from one snapshot in empty and populated Neo4j instances and compare normalized graph state | Blocking |
| Convenience edges cannot exist without assertions | Anti-join every edge to its `assertion_revision_id`; require edge, assertion, and receipt snapshot hashes to match | Blocking |
| Strength fields are internally consistent | Require the exact candidate/C/investigative tuple, validate each `DimensionAssessment`, and require an explicit ranking definition that does not silently treat absence as zero | Blocking |

The MVP adds no detector-drift or graph-cardinality monitoring framework and no warning-level
publication gate. A required record key, source hash, endpoint, method field, or internally invalid
assessment is blocking. Deterministic no-anchor exclusions are materialization metadata, not
warnings or fallback claims; optional metadata remains visibly absent.

### 7.2 Test layers

**Unit tests** prove enum restrictions, frozen Pydantic behavior, typed-absence validation,
canonical key normalization, generated-contract-key precedence, stable hashing, timestamp
exclusion, row-order and evidence-order independence, no-overwrite behavior, collision failure,
source-reference resolution, and score semantics. Grouping fixtures prove that multiple actions
under one prior-award/contract pair create one assertion, preserve all action keys, and choose the
same anchor across input permutations and process restarts. Dimension fixtures distinguish missing
source text from a measured zero, reject a nullable score without status, and require stable error
categories for evaluation failures. A no-valid-anchor fixture produces a declared exclusion, never
a fallback claim.

**Dagster tests** prove that only retrospective FPDS-contract rows enter, checks are genuinely
blocking, graph assets cannot run after a failed check, the new manual path is excluded from broad
schedules, and legacy writer assets are undiscoverable after PR 2.

**Neo4j integration tests** run against real Neo4j and prove constraints, complete endpoint
matching, no sparse node creation, idempotent reruns, snapshot replacement, orphan rejection,
projection properties, and zero writes of the legacy causal relationships.

**API tests** prove claim fields and snapshot hashes are present, confidence dimensions remain
separate, no field is called a probability, and retired metrics cannot silently return a new
estimand. PR 2 specifically proves the authenticated legacy metric returns a stable 410 without
querying Neo4j, and that mixed-purpose award/organization reads expose neither legacy fields nor
fabricated zeros.

**Analytical-input tests** validate logical and physical hashes, open the same Parquet with DuckDB,
reject graph locations as snapshot inputs, preserve candidate-only metadata, and prove that action
amounts remain accessible without an assertion-level aggregation. Existing census tests must
produce byte-equivalent or explicitly normalized-equal action survivors, drop-off counts, distinct
contract counts, and transaction-deduplicated obligation totals. Shared study-manifest tests wait
for a named study consumer.

The existing >=85% transition precision benchmark applies to changes in detector scoring. This
milestone changes representation and publication; it must show parity to the declared retrospective
candidate input and must not claim that representation tests validate factual precision.

## 8. Risks and unresolved decisions

| Risk | MVP control | Deferred decision |
| --- | --- | --- |
| False precision | Use typed dimension assessments; distinguish unmeasurable from measured-low; label ranking as prioritization only | Calibration or truth-probability claims require a labeled benchmark and separate proposal |
| Review authority | Emit only candidates | Reviewer identity, acceptance policy, rejection, appeals, and cutoff rules |
| Source retention | Bind source record keys to the exact existing input ID and hash | SourceRecord graph nodes, normalized locators, and long-term record-level UI |
| Graph growth | Keep only the supplied assertion projection in Neo4j; retain history in Parquet | Historical/as-of graph traversal |
| Schema complexity | One assertion type, one revision ID, no supersession or review model | Additional assertion families and neutral contracts package |
| Study reproducibility | Logical + physical hashes and explicit assertion filters | An accepted-assertion estimand and citable study promotion |
| Human acceptance criteria | Not required for candidate-only publication | Who may accept a claim and what support is sufficient |
| Legacy consumers | Return 410 for the live metric and offer only a versioned frozen response when required | Owner identifies any external client and the frozen response expiry |
| Census/assertion grain confusion | Name the census action-pair, assertion award-contract, and action-evidence units; keep census outputs unchanged | Any future estimand must declare which grain and anchor rule it uses |
| Multiple detectors | Keep method out of logical ID and permit one current revision per logical claim in V1 | Define selection or fusion before publishing multiple detector outputs |

Anything beyond candidate award-contract derivation remains exploratory. In particular, do not add
reviews, source-record nodes, accepted snapshots, patent assertions, ownership assertions, OT
unification, or a general case-management API without a named consumer.

## 9. Implementation sequence

### PR 1 — Candidate assertion contract and content-addressed snapshot

Likely files:

- `docs/decisions/ADR-004-transition-candidates-as-assertions.md`
- `docs/steering/epistemic-tiers.md`
- `sbir_etl/assertions/__init__.py`
- `sbir_etl/assertions/enums.py`
- `sbir_etl/assertions/models.py`
- `sbir_etl/assertions/identifiers.py`
- `sbir_etl/assertions/validation.py`
- `sbir_etl/assertions/snapshots.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/__init__.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/assets.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/checks.py`
- `packages/sbir-analytics/sbir_analytics/definitions.py`
- `tests/unit/assertions/`
- `tests/unit/assets/test_transition_assertion_assets.py`
- `tests/unit/assets/test_dagster_definitions.py`
- `tests/unit/phase_iii_candidates/test_candidate_outputs.py`
- `tests/unit/phase_iii_candidates/test_pairing.py`
- `tests/unit/phase_iii_census/test_criteria.py`
- `tests/integration/test_transition_assertion_snapshot.py`

Verification:

```bash
uv run pytest tests/unit/assertions tests/unit/phase_iii_candidates \
  tests/unit/phase_iii_census/test_criteria.py \
  tests/unit/assets/test_transition_assertion_assets.py \
  tests/unit/assets/test_dagster_definitions.py -q
uv run pytest tests/integration/test_phase_iii_retrospective_asset.py \
  tests/integration/test_transition_assertion_snapshot.py -q
uv run ruff check sbir_etl/assertions \
  packages/sbir-analytics/sbir_analytics/assets/transition_assertions \
  tests/unit/assertions tests/unit/assets/test_transition_assertion_assets.py
uv run mypy sbir_etl/assertions
make lint-boundaries
make docs-check
```

Acceptance: identical semantic inputs produce identical canonical assertion rows, assertion IDs,
revision IDs, anchor actions, and logical snapshot hashes across shuffled row order, changed
execution time, repeated runs, equivalent evidence-reference ordering, and a clean process restart.
Each optional dimension has a validated explicit status. Distinct assertion count equals distinct
prior-source-row/contract-key count in the qualifying action set, every supporting action resolves
to that contract, same-date ties select the stable transaction ID, no-anchor exclusions are
reported, repeated modifications do not duplicate claims, and existing census action counts and
obligation totals are unchanged. The manifest binds the actual Parquet SHA; a collision or
unresolved record key blocks materialization.

### PR 2 — Neo4j assertion projection and legacy-writer stop

Likely files:

- `packages/sbir-graph/pyproject.toml`
- `uv.lock`
- `scripts/ci/check_architecture_boundaries.py`
- `tests/unit/scripts/test_architecture_boundaries.py`
- `packages/sbir-graph/sbir_graph/migrations/versions/008_assertion_read_model.py`
- `packages/sbir-graph/sbir_graph/loaders/neo4j/contracts.py`
- `packages/sbir-graph/sbir_graph/loaders/neo4j/assertions.py`
- `packages/sbir-graph/sbir_graph/loaders/neo4j/convenience_edges.py`
- `packages/sbir-graph/sbir_graph/loaders/neo4j/__init__.py`
- `packages/sbir-graph/sbir_graph/queries/pathway_queries.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/graph.py`
- `packages/sbir-analytics/sbir_analytics/assets/jobs/transition_job.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition/loading.py`
- `packages/sbir-analytics/sbir_analytics/definitions.py`
- `packages/sbir-analytics/sbir_analytics/api/repository.py`
- `packages/sbir-analytics/sbir_analytics/api/service.py`
- `packages/sbir-analytics/sbir_analytics/api/app.py`
- `scripts/data/migrate_transition_assertion_projection.py`
- `docs/schemas/neo4j.md`
- `docs/queries/transition-queries.md`
- `docs/architecture/private-analytics-api.md`
- `tests/unit/loaders/neo4j/test_assertions.py`
- `tests/unit/loaders/neo4j/test_contracts.py`
- `tests/integration/neo4j/test_assertion_projection.py`
- `tests/e2e/transition/test_graph_queries.py`
- `tests/unit/assets/test_dagster_definitions.py`
- `tests/unit/api/test_repository.py`
- `tests/unit/api/test_analytics_api.py`
- `tests/unit/scripts/test_migrate_transition_assertion_projection.py`

Verification:

```bash
uv lock --check
uv run pytest tests/unit/scripts/test_architecture_boundaries.py \
  tests/unit/loaders/neo4j/test_assertions.py \
  tests/unit/loaders/neo4j/test_contracts.py \
  tests/unit/assets/test_dagster_definitions.py \
  tests/unit/api/test_repository.py tests/unit/api/test_analytics_api.py \
  tests/unit/scripts/test_migrate_transition_assertion_projection.py -q
uv run pytest -m integration tests/integration/neo4j/test_assertion_projection.py -q
uv run pytest tests/e2e/transition/test_graph_queries.py -q
uv run ruff check packages/sbir-graph packages/sbir-analytics/sbir_analytics/assets/transition_assertions
make lint-boundaries
make docs-check
```

Acceptance: the loader consumes canonical model objects, every endpoint already exists with complete
observation properties, an identical rerun is idempotent, and every convenience edge resolves one
assertion revision in the supplied snapshot. No discovered Dagster asset can write legacy causal
edges; the live metric returns 410 rather than a fabricated zero; and the migration receipt proves
zero remaining `TRANSITIONED_TO` or `RESULTED_IN` relationships.

### PR 3 — Consumer/study binding and legacy retirement

Likely files:

- `packages/sbir-analytics/sbir_analytics/api/models.py`
- `packages/sbir-analytics/sbir_analytics/api/repository.py`
- `packages/sbir-analytics/sbir_analytics/api/service.py`
- `packages/sbir-analytics/sbir_analytics/api/app.py`
- `sbir_etl/assertions/snapshots.py`
- `packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py`
- `packages/sbir-graph/sbir_graph/loaders/neo4j/profiles.py`
- `docs/architecture/private-analytics-api.md`
- `docs/deployment/mac-mini-server.md`
- `tests/unit/api/test_repository.py`
- `tests/unit/api/test_analytics_api.py`
- `tests/integration/test_transition_assertion_duckdb.py`
- `tests/unit/assets/test_sbir_neo4j_loading.py`
- `tests/unit/test_award_progressions.py`

Verification:

```bash
uv run pytest tests/unit/api tests/unit/assets/test_sbir_neo4j_loading.py \
  tests/unit/test_award_progressions.py -q
uv run pytest tests/integration/test_transition_assertion_duckdb.py -q
uv run pytest -m integration tests/integration/neo4j/test_assertion_projection.py -q
make lint-boundaries
make docs-check
make validate
```

Acceptance: claim endpoints expose status/support/use/method/snapshot fields, nested dimension
assessments, and supporting/anchor action references; the old rate cannot be mistaken for a new
estimand; DuckDB reads the bound assertion snapshot without Neo4j; no active writer emits
`ACHIEVED` or `FOLLOWS`; and isolated legacy transition/profile state is removed only after a named
backup and migration receipt.

## Required conclusion

### 1. Recommended first pull request

Open **“Define deterministic transition-candidate assertions and content-addressed snapshots.”** It
contains the ADR, one canonical contract with typed dimension absence, deterministic action-to-
contract grouping and anchor selection, stable logical/revision IDs, the retrospective
FPDS-contract adapter, manifest enforcement, and blocking tests. It changes no Neo4j or census
behavior.

### 2. Recommended ADR title and outline

**ADR-004: Represent Transition Candidates as Typed Assertions Before Neo4j Projection**

1. Context: incompatible publication contracts and causal overstatement.
2. Decision boundary: one candidate award-contract assertion family.
3. Claim grain: Phase II source row × contract award, supported and temporally anchored by
   contract-action observations; explicitly not the census row grain.
4. Typed absence: dimension statuses distinguish unmeasurable, unevaluated, failed, and measured
   low signals.
5. Durable authority: content-addressed Parquet snapshot; Neo4j is a read projection.
6. Package decision: narrowly allow `sbir_graph -> sbir_etl.assertions`.
7. Candidate-only semantics: CANDIDATE/C/INVESTIGATIVE_ONLY.
8. V1 cardinality: one current revision per logical assertion; detector fusion is deferred.
9. Graph projection: Assertion/MethodRun plus deterministic `POSSIBLE_DERIVATION`.
10. Study boundary: DuckDB/Parquet input, never mutable graph state; census unchanged.
11. Consequences, immediate legacy-edge deletion, frozen compatibility responses, rollback, and
   explicitly deferred work.

### 3. Minimum viable schema change

One frozen `AssertionRecord`, one validated `DimensionAssessment`, one
`AssertionSnapshotManifest`, one `Assertion` node label, one `MethodRun` label,
`SUBJECT_OF`/`TARGETS`/`GENERATED_BY`, and one deterministic `POSSIBLE_DERIVATION` convenience
edge. The record targets a generated contract-award key, preserves all qualifying action keys, and
declares one deterministic anchor action/date. Use `assertion_id` for logical identity and
`assertion_revision_id` for immutable payload identity. Store source references as keys; create no
`SourceRecord` or `ReviewDecision` nodes.

### 4. Decisions requiring owner input before implementation

The claim-grain decision is resolved: the logical B2/B3 assertion is Phase II source record ×
federal prime contract award. Contract actions remain first-class evidence and provide dates,
codes, descriptions, and obligations. This is a deterministic projection from the
census-compatible action universe, not an exact match to the census estimand's row grain.

Only one owner decision still blocks the three-PR milestone: identify any external API client that
needs a versioned frozen legacy response and choose its expiry. PocketGraph/direct-Cypher users
receive the assertion topology after cutover.

The architecture decision is to delete legacy causal edges in PR 2 after the named backup and
verified assertion load. It does not require a further choice between deletion and an inactive
marker.

Acceptance authority, reviewer identity, acceptance criteria, `SourceRecord` nodes,
`SUPPORTED_DERIVATION`, review cutoffs, supersession, and additional assertion families do not
block candidate-only implementation. They require separate decisions after a consumer appears.
