# Neo4j Epistemic Assertions: Minimum Viable Migration Plan

**Status:** Revised proposal; no production implementation has started. Review comments addressed
(2026-08-05): ADR renumbered to ADR-005, §3.6 marked contingent-and-deferred under ADR-004, §4.2
harmonized with spec-declaration guard.

**Repository baseline audited:** `origin/main` at `8500c0c6` on 2026-08-04

**Primary research inventory:** `docs/research-questions.md`

## Decision boundary

Approve a narrow architectural decision: inferred award-to-contract derivations should be
durable, typed candidate assertions before Neo4j publishes them.

Do not approve a general assertion platform, review system, or study rewrite as part of this
decision. Those remain an architectural north star and require a demonstrated consumer.

The three-PR milestone must prove only that:

1. candidate assertions are deterministic, with one claim per prior-source/contract-award pair and
   one shared, typed contract-award key resolution rule;
2. they retain every supporting action reference, the earliest award action, and the earliest
   positive-obligation action when one exists;
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
| Contract and action identity | `sbir_etl/utils/award_identity.py`; `sbir_etl/extractors/usaspending_award_archive.py`; `tests/unit/utils/test_award_identity.py`; `tests/unit/phase_iii_candidates/test_pairing.py` | `target_transaction_id` is already distinct from `target_contract_key`, and bare `contract_id` is excluded from `award_key_series()`. However, the resolver returns an untyped, unprefixed string, treats frame-complete generated aliases as peers rather than making `generated_unique_award_id` canonical, and fails a partially populated generated-key column instead of applying an explicit row-level fallback. The Award Data Archive extractor maps raw `contract_award_unique_key` into the generated-ID field, but direct callers can still supply the raw alias. Separately, `_prepare_contract_transactions()` populates ambiguous `target_id` through a column-presence `contract_id`, PIID, generated-ID pick. The legacy composite and generated key therefore have no auditable method marker or collision-proof namespace. |
| Other shared-pair consumers | `scripts/phase3_benchmark/build_pairs_and_score.py`; `scripts/data/build_phase_iii_control_outcomes.py`; `scripts/data/build_phase_iii_placebo.py`; `tests/unit/scripts/test_phase3_pairing.py`; `tests/unit/scripts/test_build_phase_iii_control_outcomes.py`; `tests/unit/scripts/test_build_phase_iii_placebo.py` | The benchmark calls `award_key_series()` directly, while the control and placebo paths call `build_uei_pairs(..., columns=CENSUS_PAIR_COLUMNS)` directly. A namespaced resolver or census compatibility projection must migrate these consumers in PR 1 rather than changing their schemas accidentally. |
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
- `tests/unit/transition/test_graph_queries.py` mocks result shapes rather than exercising Neo4j
  projection semantics.
- `tests/unit/transition/test_transition_scores_stability.py` removes dynamic timestamps before
  comparison; it does not prove stable record identity.
- `tests/integration/test_phase_iii_retrospective_asset.py` uses engineered fixtures. It is an
  integration test, not an external precision benchmark.
- `tests/unit/phase_iii_candidates/test_pairing.py` proves that `build_uei_pairs()` retains every
  target transaction and carries an award-level key separately. It does not yet prove typed
  generated-ID precedence, prefixed legacy fallback, PIID-collision safety, or fallback counts;
  assertion projection tests do not yet exist.
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
- `docs/steering/data-quality.md` prefers raw `contract_award_unique_key` without explaining that
  the Award Data Archive extractor normalizes that source field as a generated-USAspending-key
  alias, that direct callers may still supply the raw alias, or how typed legacy fallback is
  surfaced.
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
assertion definition, award or funding anchor, and denominator. It is not a “graph transition
rate.”

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

PR 1 also owns the canonical federal contract-award identity rule:

```text
generated_unique_award_id
    -> documented agency + parent-IDV + PIID legacy composite
    -> unresolved: count and fail strict publication
```

Resolved values are namespaced as `USAID:<generated_unique_award_id>` or
`LEGACY:<agency>|<parent_idv>|<piid>` and carry `ContractKeyMethod`. Bare PIID is retained only as a
search, display, and audit field; it never precedes either award-level key or enters
`assertion_id`. The Award Data Archive extractor normalizes raw `contract_award_unique_key` into
the canonical generated-ID field; the resolver also recognizes that raw source alias for direct
callers. Conflicting generated-ID aliases block rather than selecting one.

The assertion producer and census share the normalized UEI-only pair boundary, canonical federal
contract-award key resolver, and transaction-record identity. They apply their own downstream
gates: the assertion producer imports no census inclusion predicate, and PR 1 changes no frozen
census estimand.

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
 shared normalized UEI-only action pairs + typed key resolution
                              │
                              ▼
               retrospective candidate predicates
                              │
                              ▼
 group by prior row + contract; select award/funding anchors
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
- the federal prime contract award, identified by a namespaced generated key or explicitly typed
  legacy fallback, is the assertion object; and
- the USAspending contract actions are first-class supporting observations carrying dates, codes,
  descriptions, and signed obligations.

The first release does not retrofit a general observation schema or create graph nodes for every
action. The first graph migration reuses complete award nodes and adds a complete contract
observation loader; it must never manufacture a sparse endpoint from assertion data. Future
normalized source contracts should preserve `source_system`, `source_record_id`,
`source_snapshot_id`, `record_hash`, `retrieved_at`, and `source_locator`, but that broader retrofit
is outside this milestone.

**Assertions.** A candidate assertion refers to one prior-award source-row key, one contract-award
key and key-resolution method, every supporting action key, the earliest dated award action, the
earliest dated positive-obligation action when present, any contradicting source-record keys, and
the hashes of the exact input files in its manifest. It does not replace or aggregate away those
observations. Multiple modifications under one contract award produce one logical claim, not
multiple outcomes. Zero- and negative-obligation actions can establish and support an award even
though they cannot be the positive-obligation anchor.

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

- `enums.py`: claim status, support class, permitted use, assertion type, `ContractKeyMethod`,
  dimension status, and the minimal version-one dimension reasons;
- `models.py`: frozen `DimensionAssessment`, assertion record, and snapshot manifest contracts;
- `identifiers.py`: canonical record-key normalization and semantic hashes;
- `validation.py`: candidate-only, status/score/reason, action-to-contract membership, and
  deterministic award/funding-anchor invariants; and
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

The existing `sbir_etl/utils/award_identity.py` remains the shared home for federal contract-award
resolution logic. PR 1 adds one typed resolver there; it imports the lightweight canonical
`ContractKeyMethod` from `sbir_etl.assertions.enums`, which is re-exported by
`sbir_etl.assertions`. This keeps graph-facing contract modules free of the resolver's pandas
dependency. `sbir_etl/assertions/identifiers.py` hashes the resolver's namespaced output and never
implements a competing award-key convention. `award_key_series()` becomes a thin namespaced key-
only view over the typed resolver rather than a second pick order. PR 1 migrates its benchmark
consumer and fixtures to that canonical output; it does not retain an unnamespaced resolver
contract in parallel.

### 3.4 Dagster asset graph

The first producer should be manual and unscheduled while parity is established:

```text
validated_phase_ii_awards
normalized_usaspending_contract_actions
existing award input fingerprint
existing contract input fingerprint
                    │
                    ▼
shared normalized UEI-only action pairs
  [prior source row × target transaction; shared key resolver]
                    │
                    ▼
retrospective candidate predicates
                    │
                    ▼
transition_candidate_assertions
  [group by prior_source_record_key + target_contract_key; select two anchors]
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
adapter projection; `phase_iii_census` itself is not an upstream asset. Both consumers receive
`target_contract_key`, `target_contract_key_method`, and `target_transaction_id` from the same
resolver-backed pair builder, then apply independent gates. The assertion producer imports no
census inclusion predicate.

PR 1 replaces the ambiguous column-presence pick
`target_id = contract_id | piid | generated_unique_award_id` with explicit fields. Shared pairs
carry resolver-produced `target_contract_key` and `target_contract_key_method`, stable
`target_transaction_id`, and a separate `target_piid` audit value. Any retained `target_id` is a
declared compatibility/display field populated at the consumer boundary and is prohibited from
assertion hashing, grouping, or graph endpoint identity. The candidate path retains its exact
pre-PR1 `target_id` and derived `candidate_id` as explicitly legacy compatibility fields and adds
the resolved contract key and method beside them. One reusable
`phase_iii_census/pairing.py::build_census_uei_pairs()` projection calls the shared builder and maps
`target_piid` to the census's existing audit-facing `target_id` field. The census asset, control-
outcome script, and placebo script must all use that projection so PIID remains visible without
becoming identity or duplicating a mapping. The Phase III benchmark migrates its
`phase_iii_award_key` and pair-ID expectations to the namespaced output of
`award_key_series()`; those benchmark IDs are not the detector compatibility IDs.

The detector still scores the legacy latest selected transaction. PR 1 recovers and stores that
transaction as `detector_action_record_key`; it does not rescore or imply that the detector action
is the earliest award action. The latest-action selection gains a normalized transaction-ID
tie-break so equivalent input order cannot change the selected row. This preserves score
provenance without rescoring across actions; because a same-date tie can change the selected
attributes, any resulting detector-output change remains subject to the repository's >=85%
precision gate and must be reported separately from identity parity.

For version one, a supporting action is a shared exact-UEI pair row that (a) matches an emitted
retrospective FPDS-contract logical pair, (b) has a nonblank stable transaction ID, and (c) resolves
to the asserted namespaced contract key. The adapter retains every such action key regardless of
whether the action precedes Phase II completion or has a positive, zero, or negative signed
obligation.

For each group, the adapter sorts actions by parsed action date and normalized transaction ID. It
sets `anchor_action_record_key` to the earliest dated action establishing the award and separately
sets `first_positive_obligation_action_record_key` to the earliest dated action whose signed
obligation is greater than zero. The funding anchor is nullable when no observed action qualifies;
the award anchor is not replaced by it. If no action has a valid date, strict V1 materialization
fails and reports the affected source keys rather than inventing an order. When the bound Phase II
end date is observable, B3 default latency is its signed difference from the award anchor date and
negative latency is retained. A missing Phase II end date does not suppress the assertion or its
anchor: the temporal assessment is `NOT_MEASURABLE` with `SOURCE_FIELD_UNAVAILABLE`, and no
latency is derived. Post-completion and follow-up-window restrictions belong only to downstream
estimands.

The assertion stores no obligation aggregate. All action-grained amounts remain available to
DuckDB and the census. The adapter does not merge directed or follow-on opportunity candidates.

The adapter copies no timestamp or Dagster run ID into semantic assertion identity. The snapshot
asset reuses an existing file when the logical hash and bound physical hash match; it never
overwrites that path. PR 1 assigns the new assets to an explicitly manual-only group and changes
the broad selections in `packages/sbir-analytics/sbir_analytics/definitions.py` to exclude that
group, with a definition test. No new source-snapshot asset family is introduced, and no existing
census predicate, grain, estimand, count, or obligation total changes. Existing frozen census
artifacts are never rewritten. Future census materialization uses the same generated-first,
typed-fallback resolver and records the resolution method; this versions the shared identity
representation without changing the census predicates or quantities. The selected normalized
census source continues to satisfy its existing requirement for generated award IDs, so PR 1 adds
no new census fallback-inclusion policy and does not edit the hash-frozen census design.

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

The PR 2 contract observation loader keys the contract endpoint from the same namespaced
`object_contract_key` used in PR 1 and retains PIID only as a searchable/display property. It does
not derive the graph primary key from `contract_id`. Generated-key-distinct IDV children therefore
remain distinct, and fallback endpoints visibly retain their key method.

`Assertion` is keyed by `assertion_revision_id`. It exposes the logical `assertion_id`, candidate
status/support/use, namespaced contract key and resolution method, structured dimension
assessments, method metadata, supporting and detector action keys, award anchor key/date, optional
positive-obligation anchor key/date, contradicting source-record keys, and assertion snapshot hash.
Nested Parquet dimension structs are flattened in Neo4j into explicit `*_status`, `*_score`,
`*_reason`, and `*_error_category` properties; missing properties never imply a status.
`MethodRun` uses the originating detector run ID from the snapshot manifest. Republishing the graph
reuses that node; the graph-load run is not a new claim-generating method run. Operational run
identity is not part of the assertion revision hash.

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
- `object_contract_key_method`
- `anchor_action_record_key`
- `anchor_action_date`
- `first_positive_obligation_action_record_key`
- `first_positive_obligation_action_date`
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

**Status: contingent and deferred.** The private analytics API targeted by this section was
retired in ADR-004 (*Retire the Private Analytics API*, accepted 2026-08-04), which requires any
future interface to start from a demonstrated consumer. The endpoint shapes below are preserved as
design intent but must not be implemented until a real consumer is identified and the architecture
decision in ADR-004 is satisfied. In the interim, PocketGraph and direct Cypher users consume the
assertion topology through the file-artifact surface (content-addressed Parquet snapshots) that
the explorer stack already consumes.

The minimum claim-aware API, once a consumer exists, is:

- `GET /v1/awards/{award_record_key}/transition-assertions`
- `GET /v1/assertions/{assertion_revision_id}`

Responses expose the logical and revision IDs, claim status, support class, permitted use,
the full typed identity/technology/temporal assessments, ranking-score definition, method
ID/version/fingerprint, namespaced contract key and resolution method, supporting and detector
action keys, award anchor key/date, optional positive-obligation anchor key/date, contradicting
record keys, and assertion/source snapshot hashes. When the Phase II end date is present, a
derived latency response uses the signed award-anchor date minus that end date and never clips
negative values. When it is absent, latency is null and the response exposes the temporal
assessment as `NOT_MEASURABLE`/`SOURCE_FIELD_UNAVAILABLE`; null alone is not the epistemic state.

The API embeds source references rather than presenting them as if they were retrieved evidence.
Candidate-constant status/support/use filters are deferred. PocketGraph and direct Cypher users can
expand or contract the graph using the properties already present on assertion nodes and projected
edges, especially each dimension's status and independently measured score. A
`NOT_MEASURABLE` technology dimension can therefore be shown separately from a measured low score
instead of disappearing under a threshold. Investigators can also isolate typed legacy-key
fallbacks through `object_contract_key_method` without treating that method as claim strength. Add
API filters only when a real client needs them. No client may advertise `ranking_score` as a truth
probability.

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

Object construction applies no post-completion or positive-dollar filter. Studies may select
post-completion assertions, a follow-up window, or a positive funding anchor only through declared
inclusion rules. When the prior award end date is observable, the default B3 candidate latency is
signed award-anchor date minus Phase II end. When it is missing, the assertion remains available
but the latency is not measurable. The funding anchor supports separately named funding-latency
analyses. Dollar analyses continue to use signed action rows, not assertion properties.

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
repository artifacts beyond the spec-declaration guard already established in CI. Note: when this
plan's implementation directory is created under `specs/`, it will require a `requirements.md`
with a tier declaration from day one, per that guard.

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

The lightweight canonical contract in `sbir_etl/assertions/enums.py` defines, and the shared
identity utility consumes:

```python
class ContractKeyMethod(StrEnum):
    GENERATED_UNIQUE_AWARD_ID = "GENERATED_UNIQUE_AWARD_ID"
    LEGACY_AWARD_COMPOSITE = "LEGACY_AWARD_COMPOSITE"
```

There is no `PIID` method and no `UNRESOLVED` assertion value. A row that cannot resolve by either
award-level method does not enter an assertion snapshot.

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
object_contract_key_method: ContractKeyMethod
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
supporting_action_record_keys: tuple[str, ...]
detector_action_record_key: str
anchor_action_record_key: str
anchor_action_date: date
first_positive_obligation_action_record_key: str | None
first_positive_obligation_action_date: date | None
contradicting_source_record_keys: tuple[str, ...]
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

`object_contract_key` is produced only by the PR 1 shared resolver. It is
`USAID:<normalized-generated-id>` when a documented generated-ID alias is available, otherwise
`LEGACY:<agency-code>|<parent-idv>|<piid>` when every exact composite component is present. The
resolver does not substitute agency names, generic `award_id`, `contract_id`, or bare PIID. It
returns `object_contract_key_method` with the key. Conflicting generated aliases, incomplete legacy
components, or an exact complete normalized legacy composite whose source actions resolve to more
than one namespaced key or method fail strict materialization; they are not reconciled
heuristically.

The active normalized USAspending producer already requires generated award and transaction IDs,
so production inputs should normally resolve as `USAID:`. The fallback exists for explicitly
identified legacy inputs that retain exact agency-code, parent-IDV, and PIID components; it does not
weaken normalized-source requirements.

The resolver reports generated, fallback, and unresolved row counts in check metadata. Any
unresolved row needed by a candidate blocks publication with sampled source identifiers; PR 1 does
not build a quarantine service. Both the census and assertion path retain the resolver method and
apply their independent downstream predicates; neither invents a PIID identity or a second pick
order. Legacy fallback assertions remain class C and investigative-only, and consumers can filter
them through the method field without treating fallback method as claim strength.

The adapter groups action pairs by `subject_record_key` and the resolved namespaced contract key,
then sorts and preserves every `supporting_action_record_key`. In V1 this list means observations
associated with the candidate contract; an action that predates Phase II completion does not by
itself support a post-completion temporal claim. `detector_action_record_key` identifies the legacy
latest transaction whose attributes produced the retained ranking and dimension assessments;
same-date detector ties use normalized transaction ID and enter the method fingerprint.

`anchor_action_record_key` and `anchor_action_date` identify the earliest dated associated action,
with same-date ties broken by normalized transaction ID. The optional positive-obligation key/date
pair identifies the earliest dated action with a numeric signed obligation greater than zero under
the same tie-break. Both optional fields are present together or absent together. Zero and negative
actions remain supporting observations; there is no assertion-level obligation aggregation or
post-completion construction filter. A missing Phase II end date leaves the assertion and award
anchor intact but requires `temporal = NOT_MEASURABLE` with reason
`SOURCE_FIELD_UNAVAILABLE`; it does not produce latency. PR 1 fails closed when a required
canonical subject, contract, action, detector-action, or award-anchor key is missing and never
falls back to a random ID.

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
contract_key_resolver_version
contract_key_resolution_counts:
    generated_unique_award_id
    legacy_award_composite
    unresolved
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
`contract_key_resolution_counts` reports unique normalized source contract-action records before
UEI pair fan-out and award grouping, so fallback prevalence and unresolved failures are auditable
rather than multiplied by the Phase II cohort or hidden by deduplication. Candidate-relevant
unresolved counts are reported separately at the attempted assertion boundary.

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

The logical hash includes canonical endpoints and key methods, the complete typed dimension
assessments, normalized and sorted supporting action/evidence references, detector-action key, both
anchor selections, source bindings, detector fingerprint, key-resolver version, and schema
version. It excludes row order, input evidence-list order, materialization and method-run
timestamps, output paths, Parquet writer metadata, and other operational fields.

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
    object_contract_key_method,
    typed dimension assessments,
    ranking definition,
    method fingerprint,
    supporting action and contradicting record keys,
    detector action key,
    award and positive-obligation anchor keys and dates,
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

A later source snapshot that resolves a prior `LEGACY:` object to `USAID:` produces a different
logical `assertion_id`. V1 records a new content-addressed claim rather than rewriting or silently
coalescing the older one. A cross-namespace identity map or migration is deferred until a consumer
demonstrates the need.

Supersession and review decisions are deferred. When a consumer requires them, add a sidecar status
record or a new revision linked to its predecessor; do not mutate the historical candidate row.

## 6. Migration plan

| PR | Runtime boundary | Data migration | Rollback point |
| --- | --- | --- | --- |
| 1 — fix and freeze contract | Add the ADR, shared typed contract-key resolver, canonical candidate model with typed dimension absence, deterministic action-to-contract grouping and dual anchors, stable IDs, content-addressed snapshot, blocking checks, and one manual retrospective FPDS adapter. Change no graph/API behavior or census predicate/estimand. | None; do not translate legacy graph rows or overwrite frozen census artifacts. | Unregister the manual group and revert additive contracts. Keep snapshots for diagnosis. |
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
| Every assertion resolves its subject and contract object | Require `USAID:` or complete `LEGACY:` key plus matching `ContractKeyMethod`; bare PIID and unresolved keys never publish; `MATCH` complete graph endpoints before graph publication | Blocking |
| Generated identity has precedence | Resolve documented generated-ID aliases before the exact legacy composite, reject conflicts or award-splitting mixed methods, and count every method outcome | Blocking |
| Every assertion records method and version | Require method ID, version, fingerprint, and ranking definition | Blocking |
| Every action/evidence reference resolves to a source snapshot | Resolve every namespaced action or source key to a bound snapshot manifest entry | Blocking |
| Every assertion has action and detector provenance | Require at least one unique supporting action and require `detector_action_record_key` to resolve to one of them | Blocking |
| Supporting actions belong to the asserted contract | Re-run the shared resolver for each action and require its namespaced key and method to equal the assertion object | Blocking |
| The award anchor is deterministic | Require the anchor to be a supporting action and equal the earliest valid action date, with normalized transaction-ID tie-break and no Phase II temporal filter | Blocking |
| The funding anchor is deterministic | When any supporting action has signed obligation > 0, require the earliest dated such action under the same tie-break; otherwise require both optional funding-anchor fields to be null | Blocking |
| Signed latency or typed absence is preserved | When Phase II end is observable, compute award-anchor date minus that end without clipping or excluding negative values; when it is absent, retain the assertion and require `temporal = NOT_MEASURABLE`/`SOURCE_FIELD_UNAVAILABLE` with no derived latency | Blocking |
| Assertion collapse preserves the declared grains | Require assertion count to equal distinct prior-source-row/resolved-contract-key pairs, repeated modifications to produce no duplicate assertion, and action-pair census counts/dollars to remain unchanged | Blocking |
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
assessment is blocking. Unresolved identities and missing award anchors fail strict materialization
with counts and sampled source keys; they do not create a quarantine workflow or fallback claim.
Optional funding anchors remain visibly absent when no positive action exists.

### 7.2 Test layers

**Unit tests** prove enum restrictions, frozen Pydantic behavior, typed-absence validation,
canonical key normalization and namespaces, generated-ID precedence, explicit legacy fallback,
PIID-collision safety, fallback/unresolved counts, stable hashing, timestamp exclusion, row-order
and evidence-order independence, no-overwrite behavior, collision failure, source-reference
resolution, and score semantics. Grouping fixtures prove that multiple actions under one generated
award ID create one assertion, distinct IDV children remain separate, and neither bare PIID nor
legacy detector `target_id` enters assertion identity.

Anchor fixtures preserve every associated action, select earliest dated award and positive-
obligation actions with stable transaction-ID ties, allow the detector-selected action to differ
from the award anchor, retain negative latency, leave the funding anchor null for zero/negative-
only awards, and retain an assertion with typed temporal absence when Phase II end is unavailable.
Dimension fixtures distinguish missing source text from measured zero, reject a nullable score
without status, and require stable error categories for evaluation failures. A no-valid-award-
anchor fixture blocks strict materialization rather than creating a fallback claim.

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
contract counts, and transaction-deduplicated obligation totals for its generated-key normalized
source. Resolver and assertion tests separately exercise typed legacy fallback. Together they
prove method retention changes neither census predicates nor quantities. Shared study-manifest
tests wait for a named study consumer. A direct census-pairing test proves the wrapper preserves
the normalized source validation, maps `target_piid` only to audit-facing `target_id`, passes the
canonical key/method/transaction ID through unchanged, and is used by the census asset plus both
control scripts.

The existing >=85% transition precision benchmark applies to changes in detector scoring. Because
the deterministic same-date detector tie-break can change the selected source action, PR 1 runs
the real precision backtest when its corpus is available and must retain at least 85%. The
representation tests separately prove parity to the declared retrospective candidate input and do
not claim to validate factual precision.

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
| Census/assertion grain confusion | Name the census action-pair, assertion award-contract, and action-evidence units; preserve frozen artifacts and census quantities while versioning the shared key representation | Any future estimand must declare which grain and anchor rule it uses |
| Legacy fallback identity risk | Prefix and method-tag fallback keys, count their use, and never coalesce them silently with `USAID:` keys | Add an explicit cross-namespace identity map only when a consumer needs reconciliation |
| Anchor ambiguity | Keep detector action, earliest award action, and earliest positive-obligation action distinct; preserve signed latency | Study-specific temporal and funding restrictions remain downstream inclusion rules |
| Multiple detectors | Keep method out of logical ID and permit one current revision per logical claim in V1 | Define selection or fusion before publishing multiple detector outputs |

Anything beyond candidate award-contract derivation remains exploratory. In particular, do not add
reviews, source-record nodes, accepted snapshots, patent assertions, ownership assertions, OT
unification, or a general case-management API without a named consumer.

## 9. Implementation sequence

### PR 1 — Candidate assertion contract and content-addressed snapshot

Likely files:

- `docs/decisions/ADR-005-transition-candidates-as-assertions.md`
- `docs/steering/data-quality.md`
- `docs/steering/epistemic-tiers.md`
- `sbir_etl/utils/award_identity.py`
- `sbir_etl/models/phase_iii_candidate.py`
- `sbir_etl/assertions/__init__.py`
- `sbir_etl/assertions/enums.py`
- `sbir_etl/assertions/models.py`
- `sbir_etl/assertions/identifiers.py`
- `sbir_etl/assertions/validation.py`
- `sbir_etl/assertions/snapshots.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/assets.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/criteria.py`
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census/pairing.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/__init__.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/assets.py`
- `packages/sbir-analytics/sbir_analytics/assets/transition_assertions/checks.py`
- `packages/sbir-analytics/sbir_analytics/definitions.py`
- `scripts/phase3_benchmark/build_pairs_and_score.py`
- `scripts/data/build_phase_iii_control_outcomes.py`
- `scripts/data/build_phase_iii_placebo.py`
- `tests/unit/assertions/`
- `tests/unit/assets/test_transition_assertion_assets.py`
- `tests/unit/assets/test_dagster_definitions.py`
- `tests/unit/phase_iii_candidates/test_award_key_grain.py`
- `tests/unit/phase_iii_candidates/test_candidate_outputs.py`
- `tests/unit/phase_iii_candidates/test_pairing.py`
- `tests/unit/phase_iii_census/test_asset.py`
- `tests/unit/phase_iii_census/test_arm_blindness.py`
- `tests/unit/phase_iii_census/test_criteria.py`
- `tests/unit/phase_iii_census/test_pairing.py`
- `tests/unit/scripts/test_phase3_pairing.py`
- `tests/unit/scripts/test_phase_iii_precision_backtest.py`
- `tests/unit/scripts/test_build_phase_iii_control_outcomes.py`
- `tests/unit/scripts/test_build_phase_iii_placebo.py`
- `tests/unit/utils/test_award_identity.py`
- `tests/integration/test_phase_iii_retrospective_asset.py`
- `tests/integration/test_transition_assertion_snapshot.py`

Verification:

```bash
uv run pytest tests/unit/assertions tests/unit/phase_iii_candidates \
  tests/unit/phase_iii_census/test_asset.py tests/unit/phase_iii_census/test_criteria.py \
  tests/unit/phase_iii_census/test_arm_blindness.py \
  tests/unit/phase_iii_census/test_pairing.py \
  tests/unit/scripts/test_phase3_pairing.py \
  tests/unit/scripts/test_build_phase_iii_control_outcomes.py \
  tests/unit/scripts/test_build_phase_iii_placebo.py \
  tests/unit/scripts/test_phase_iii_precision_backtest.py \
  tests/unit/utils/test_award_identity.py \
  tests/unit/assets/test_transition_assertion_assets.py \
  tests/unit/assets/test_dagster_definitions.py -q
uv run pytest tests/integration/test_phase_iii_retrospective_asset.py \
  tests/integration/test_transition_assertion_snapshot.py -q
uv run ruff check sbir_etl/assertions sbir_etl/utils/award_identity.py \
  sbir_etl/models/phase_iii_candidate.py \
  packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates \
  packages/sbir-analytics/sbir_analytics/assets/phase_iii_census \
  packages/sbir-analytics/sbir_analytics/assets/transition_assertions \
  scripts/phase3_benchmark/build_pairs_and_score.py \
  scripts/phase_iii_precision_backtest.py \
  scripts/data/build_phase_iii_control_outcomes.py scripts/data/build_phase_iii_placebo.py \
  tests/unit/assertions tests/unit/phase_iii_candidates tests/unit/phase_iii_census \
  tests/unit/utils/test_award_identity.py tests/unit/scripts/test_phase3_pairing.py \
  tests/unit/scripts/test_phase_iii_precision_backtest.py \
  tests/unit/scripts/test_build_phase_iii_control_outcomes.py \
  tests/unit/scripts/test_build_phase_iii_placebo.py \
  tests/unit/assets/test_transition_assertion_assets.py \
  tests/integration/test_phase_iii_retrospective_asset.py \
  tests/integration/test_transition_assertion_snapshot.py
uv run mypy sbir_etl/assertions sbir_etl/utils/award_identity.py
make lint-boundaries
make docs-check
```

Data-backed merge gate where the corpus is staged at the script's declared default paths; missing
data fails rather than producing a sentinel:

```bash
uv run python scripts/phase_iii_precision_backtest.py --strict --threshold 0.85
```

PR 1 cannot merge unless its acceptance suite proves all ten owner-approved cases:

1. Generated award IDs outrank both the exact legacy composite and bare PIID.
2. All actions sharing a generated award ID resolve to one contract object.
3. Distinct IDV children remain distinct where generated IDs distinguish them.
4. Bare-PIID collisions do not collapse different awards.
5. Legacy fallback use is prefixed, method-tagged, explicit, and counted.
6. Row ordering does not change resolved keys.
7. Assertion IDs remain stable across repeated runs.
8. Award-anchor selection preserves negative latency when the Phase II end date is observable.
9. A measured zero score remains `MEASURED`, not absent.
10. Unmeasurable dimensions contain typed reasons.

The broader deterministic contract also requires identical canonical rows, revision IDs, action
selections, and logical snapshot hashes across shuffled row order, changed execution time,
repeated runs, equivalent evidence-reference ordering, and a clean process restart. No assertion
ID hashes the legacy detector `target_id`. Repeated modifications create one assertion; detector-
action provenance is retained; the funding anchor is the earliest positive-obligation action or
null; same-date ties use stable transaction ID; and a missing Phase II end retains the assertion
with typed temporal absence. Existing frozen census artifacts remain untouched, while generated-
key census fixtures retain the same pair counts, distinct-contract counts, and signed obligation
totals; resolver and assertion fixtures separately prove typed fallback behavior. The manifest
binds the actual Parquet SHA; a collision, missing required anchor, or unresolved record key blocks
materialization. If the detector tie-break changes a selected source action, the available
precision corpus must still score at least 85% before merge.

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
- `tests/unit/transition/test_graph_queries.py`
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
uv run pytest tests/unit/transition/test_graph_queries.py -q
uv run ruff check packages/sbir-graph packages/sbir-analytics/sbir_analytics/assets/transition_assertions
make lint-boundaries
make docs-check
```

Acceptance: the loader consumes canonical model objects, every endpoint already exists with
complete observation properties, contract endpoints use the same namespaced object key and retain
PIID only for audit, an identical rerun is idempotent, and every convenience edge resolves one
assertion revision in the supplied snapshot. Generated-distinct IDV children do not collapse. No
discovered Dagster asset can write legacy causal edges; the live metric returns 410 rather than a
fabricated zero; and the migration receipt proves zero remaining `TRANSITIONED_TO` or
`RESULTED_IN` relationships.

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
assessments, contract-key method, detector action, supporting actions, and both anchor selections;
derived latency remains signed; the old rate cannot be mistaken for a new estimand; DuckDB reads
the bound assertion snapshot without Neo4j; no active writer emits `ACHIEVED` or `FOLLOWS`; and
isolated legacy transition/profile state is removed only after a named backup and migration receipt.

## Required conclusion

### 1. Recommended first pull request

Open **“Define deterministic transition-candidate assertions and content-addressed snapshots.”** It
contains the ADR, one shared generated-first contract-key resolver, one canonical assertion
contract with typed dimension absence, deterministic action-to-contract grouping, detector-action
provenance, separate award/funding anchors, stable logical/revision IDs, manifest enforcement, and
blocking tests. It changes no Neo4j behavior or census predicate/estimand and never overwrites a
frozen census artifact.

### 2. Recommended ADR title and outline

**ADR-005: Represent Transition Candidates as Typed Assertions Before Neo4j Projection**

1. Context: incompatible publication contracts and causal overstatement.
2. Decision boundary: one candidate award-contract assertion family.
3. Contract identity: `USAID:` generated award key, typed `LEGACY:` fallback, bare PIID forbidden,
   unresolved identity blocks publication.
4. Shared boundary: assertion and census reuse the UEI-only pair builder, contract-key resolver,
   and action identity, then apply independent downstream gates.
5. Claim grain: Phase II source row × contract award, supported and temporally anchored by
   contract-action observations; explicitly not the census row grain.
6. Action roles: associated/supporting actions, detector-selected action, earliest award action,
   and optional earliest positive-obligation action remain distinct.
7. Temporal semantics: signed award-anchor latency is preserved; object construction has no
   post-completion or positive-dollar filter.
8. Typed absence: dimension statuses distinguish unmeasurable, unevaluated, failed, and measured
   low signals.
9. Durable authority: content-addressed Parquet snapshot; Neo4j is a read projection.
10. Package decision: narrowly allow `sbir_graph -> sbir_etl.assertions`.
11. Candidate-only semantics: CANDIDATE/C/INVESTIGATIVE_ONLY.
12. V1 cardinality: one current revision per logical assertion; detector fusion is deferred.
13. Graph projection: Assertion/MethodRun plus deterministic `POSSIBLE_DERIVATION`.
14. Study boundary: DuckDB/Parquet input, never mutable graph state; census estimand unchanged.
15. Consequences, immediate legacy-edge deletion, frozen compatibility responses, rollback, and
   explicitly deferred work.

### 3. Minimum viable schema change

One shared `ContractKeyMethod`/resolver, one frozen `AssertionRecord`, one validated
`DimensionAssessment`, one `AssertionSnapshotManifest`, one `Assertion` node label, one `MethodRun` label,
`SUBJECT_OF`/`TARGETS`/`GENERATED_BY`, and one deterministic `POSSIBLE_DERIVATION` convenience
edge. The record carries the namespaced contract key and method, all associated action keys, the
detector-selected action, earliest award action/date, and optional earliest positive-obligation
action/date. Use `assertion_id` for logical identity and `assertion_revision_id` for immutable
payload identity. Store source references as keys; create no `SourceRecord`, `ContractAction`, or
`ReviewDecision` nodes.

### 4. Decisions requiring owner input before implementation

The claim-grain decision is resolved: the logical B2/B3 assertion is Phase II source record ×
federal prime contract award. Contract actions remain first-class evidence and provide dates,
codes, descriptions, and obligations. This is a deterministic projection from the
census-compatible action universe, not an exact match to the census estimand's row grain.

The identity decision is also resolved: PR 1 establishes `generated_unique_award_id` as the
canonical federal prime-contract award key. The exact agency/parent-IDV/PIID legacy composite is a
typed, namespaced fallback only when the generated key is genuinely unavailable; bare PIID is
never preferred. The shared pair builder, census, and assertion producer use the same resolver and
retain transaction identifiers separately as action-grain evidence.

Only one owner decision still blocks the three-PR milestone: identify any external API client that
needs a versioned frozen legacy response and choose its expiry. PocketGraph/direct-Cypher users
receive the assertion topology after cutover.

The architecture decision is to delete legacy causal edges in PR 2 after the named backup and
verified assertion load. It does not require a further choice between deletion and an inactive
marker.

Acceptance authority, reviewer identity, acceptance criteria, `SourceRecord` nodes,
`SUPPORTED_DERIVATION`, review cutoffs, supersession, and additional assertion families do not
block candidate-only implementation. They require separate decisions after a consumer appears.
