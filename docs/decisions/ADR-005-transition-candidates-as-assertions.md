---
Type: Decision
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-19
Status: accepted
---

# ADR-005: Represent Transition Candidates as Typed Assertions Before Neo4j Projection

## Context

Inferred Phase II→III award-to-contract derivations are currently published without a
shared contract. Four surfaces disagree on the shape of the same concept:

- `sbir_etl/models/transition_models.py` and
  `packages/sbir-ml/sbir_ml/transition/detection/` define rich transition evidence and
  signal dimensions.
- `packages/sbir-analytics/sbir_analytics/assets/transition/` produces a simpler candidate
  score table plus separate NDJSON evidence.
- `packages/sbir-graph/sbir_graph/loaders/neo4j/transitions.py` expects a third DataFrame
  shape.

The failing boundary is
`packages/sbir-analytics/sbir_analytics/assets/transition/utils.py`.
`_prepare_transition_dataframe()` mints a random UUID, drops evidence and signal
dimensions, omits `cet_area`, and emits `detection_date` where the loader expects
`detected_at`. Consequences: only part of the intended topology can publish
(`RESULTED_IN` can create a sparse contract endpoint even when `TRANSITIONED_TO` is
suppressed), and non-deterministic identity makes a published derivation
non-content-addressable, non-diffable across runs, and unpinnable by a study.

Separately, the existing graph edges overstate what the evidence supports: an inferred
derivation is published as a causal-sounding relationship with no claim status, no typed
absence, and no provenance for the detector run that produced it.

This decision records the architecture proposed and reviewed in
[Neo4j epistemic assertions plan](../architecture/neo4j-epistemic-assertions-plan.md)
(revised 2026-08-05, audited against `origin/main` at `8500c0c6`). The plan reserved this
ADR's filename and outlined its content in §2; the record was never written, while
downstream code and specs began citing "ADR-005" as a dependency
(`scripts/sttr_spinout_linkage/kernel.py`, `specs/sttr-spinout-linkage/`). This ADR closes
that gap and makes the cited contract real.

The plan's final open owner decision — identify any external API client needing a
versioned frozen legacy response, and set its expiry — is discharged by
[ADR-004](ADR-004-retire-private-analytics-api.md) (accepted 2026-08-04), which retired
the private analytics API precisely because it had no consumer tied to an active research
question. No such client exists. §3.6 of the plan is already marked contingent and
deferred on that basis.

## Decision

Inferred award-to-contract derivations become **durable, typed candidate assertions in a
content-addressed Parquet snapshot before Neo4j publishes anything.** Parquet is
authoritative; Neo4j is a disposable read projection.

1. **Decision boundary.** One candidate award-contract assertion family. Not a general
   assertion platform, review system, or study rewrite.
2. **Contract identity.** `generated_unique_award_id` is the canonical federal
   prime-contract award key, namespaced `USASPENDING:`. The agency/parent-IDV/PIID composite is a
   typed, namespaced `LEGACY:` fallback used only when the generated key is genuinely
   unavailable. Bare PIID is forbidden. Unresolved identity blocks publication.
   `LEGACY:` keys are method-tagged, their use is counted, and they are never silently
   coalesced with `USASPENDING:` keys. The prefix names the source system, USAspending.
   The earlier plan text used `USAID:`, which collides with the U.S. Agency for
   International Development, an SBIR/STTR participating agency. Because the namespaced
   key is an input to `assertion_id`, the prefix is fixed here before the first snapshot
   exists. `USAID:` must never appear as a contract-key namespace.
3. **Shared boundary.** Assertions and the Phase III census reuse one UEI-only pair
   builder, one contract-key resolver, and one action identity, then apply independent
   downstream gates.
4. **Claim grain.** Phase II source row × federal prime contract award, supported and
   temporally anchored by contract-action observations. This is explicitly **not** the
   census row grain; the census estimand is unchanged.
5. **Action roles stay distinct.** Associated/supporting actions, the detector-selected
   action, the earliest award action, and the optional earliest positive-obligation action
   are separate fields, never collapsed.
6. **Temporal semantics.** Signed award-anchor latency is preserved. Object construction
   applies no post-completion filter and no positive-dollar filter; those remain
   study-specific downstream inclusion rules.
7. **Typed absence.** `DimensionStatus` distinguishes `measured`, `not_measurable`,
   `not_applicable`, `not_evaluated`, and `evaluation_failed`. A `measured` value requires
   a bounded, finite score; zero is a measured no-signal, not an absence. Missing or null
   data never stands in for a status.
8. **Durable authority.** A content-addressed Parquet snapshot with a manifest is the
   record of truth. Studies read Parquet, never mutable graph state. The manifest records
   the as-of data cut the producer observed. That cut is a required input and is never
   defaulted from the wall clock: only the producer knows which cut it observed, so a clock
   read at write time stamps a cut nobody observed onto the record of truth.

   *Clarified 2026-09-19, before PR 1 merged.* Snapshot identity covers the member
   revision set, the content digests of the pinned inputs, and the rule versions. It does
   **not** cover the as-of cut. Revisions alone are insufficient: two runs over different
   source vintages can produce an identical record set, so a revisions-only identity
   collides and the second vintage cannot be published or pinned at all. The input digests
   are what vintages actually differ on, so they are the discriminator. The cut is excluded
   because a timestamp in the identity would fork it on every rerun of byte-identical
   inputs, which destroys the idempotence that makes a rerun verifiable. An earlier draft
   of this clause said a wall-clock default "defeats content addressing"; that was wrong on
   the mechanism — the identity never included the cut. The defect was a manifest asserting
   an unobserved cut, and a vintage that could not be distinguished.
9. **Candidate-only semantics for V1.** `claim_status = CANDIDATE`,
   `support_class = C`, `permitted_use = INVESTIGATIVE_ONLY`. The schema may reserve
   `ACCEPTED`/`REJECTED`, other support classes, and broader permitted uses; no V1
   producer, graph projection, or study may emit or infer them.
10. **V1 cardinality.** One current revision per logical assertion. Detector method stays
    out of the logical ID. Multi-detector selection or fusion is deferred until a
    selection rule is defined.
11. **Graph projection.** `Assertion` and `MethodRun` node labels, `SUBJECT_OF` /
    `TARGETS` / `GENERATED_BY`, and one deterministic `POSSIBLE_DERIVATION` convenience
    edge. Neo4j cannot strengthen an assertion's meaning.
12. **Package boundary.** Narrowly allow `sbir_graph -> sbir_etl.assertions`, enforced by
    the architecture-boundary check.
13. **Legacy edges.** The existing causal-sounding transition edges are deleted after a
    named backup and a verified assertion load. No inactive-marker alternative.
14. **Study boundary.** Frozen study inputs remain the citability boundary. No
    graph-derived rate becomes a research finding.

### Minimum viable schema

One shared `ContractKeyMethod` and resolver; one frozen `AssertionRecord`; one validated
`DimensionAssessment`; one `AssertionSnapshotManifest`. `assertion_id` carries logical
identity, `assertion_revision_id` carries immutable payload identity. The record holds the
namespaced contract key and method, all associated action keys, the detector-selected
action, the earliest award action and date, and the optional earliest positive-obligation
action and date. Source references are stored as keys. No `SourceRecord`,
`ContractAction`, or `ReviewDecision` nodes are created.

## Alternatives considered

- **Fix the DataFrame mismatch only.** Rejected. Reconciling
  `_prepare_transition_dataframe()` with the loader restores the topology but leaves
  non-deterministic identity, untyped absence, and causal overstatement in place. The
  defect is independent of the larger architecture, but fixing it alone does not make a
  derivation pinnable by a study.
- **Make Neo4j the authoritative store for derivations.** Rejected. A live graph has no
  natural snapshot, so studies pinned to graph state are pinned to nothing, and Tier 1
  descriptive aggregation is worse there than in DuckDB. Neo4j also cannot add evidential
  weight to an inference it merely stores.
- **A general assertion platform with reviews and acceptance.** Rejected for V1 as
  premature. Acceptance authority, reviewer identity, acceptance criteria,
  `SourceRecord` nodes, `SUPPORTED_DERIVATION`, review cutoffs, supersession, and
  additional assertion families require separate decisions after a named consumer appears.
- **Keep publishing legacy edges behind an inactive marker.** Rejected. Unused topology
  carries the same interpretive risk as live topology and invites accidental citation.

## Consequences

**Positive**

- Derivations gain deterministic, content-addressed identity, so runs are diffable and
  studies can pin a snapshot revision.
- One contract replaces four incompatible shapes; the `detected_at` / `detection_date`
  and dropped-`cet_area` classes of defect become schema violations rather than silent
  data loss.
- Typed absence makes "we did not measure this" distinguishable from "we measured zero,"
  which several Tier 2 relational questions depend on.
- Neo4j becomes droppable and rebuildable, so it stops gating work that does not need it.
- The explorer stack and DuckDB study tooling consume the same snapshot, so the
  visualization and the research outputs cannot diverge in meaning.

**Negative**

- Producers, the graph loader, and dependent tests must migrate to one contract at once.
- Legacy causal edges are deleted; anyone reading them directly loses them at cutover.
- `LEGACY:` fallback keys add a namespace that consumers must handle explicitly rather
  than coalesce.

**Neutral**

- The Phase III census predicate and estimand are unchanged, and no frozen census
  artifact is overwritten.
- Candidate-only semantics mean nothing published under this ADR is citable; that is the
  intended V1 state, not a limitation to be fixed later.

## Implementation notes

Sequenced as three PRs per §9 of the plan.

- **PR 1 — Candidate assertion contract and content-addressed snapshot.** Adds
  `sbir_etl/assertions/` (`enums.py`, `models.py`, `identifiers.py`, `validation.py`,
  `snapshots.py`), updates `sbir_etl/utils/award_identity.py` and
  `sbir_etl/models/phase_iii_candidate.py`, and moves the Phase III candidate and census
  assets onto the shared resolver. Deterministic identity in `identifiers.py` is what
  replaces the random UUID.
- **PR 2 — Neo4j assertion projection and legacy-writer stop.** Adds
  `loaders/neo4j/assertions.py` and `convenience_edges.py`, migration
  `008_assertion_read_model.py`, the `sbir_graph -> sbir_etl.assertions` allowance in
  `scripts/ci/check_architecture_boundaries.py`, and stops the legacy writer.
- **PR 3 — Consumer/study binding and legacy retirement.** Binds studies and the
  explorer surface to the snapshot and retires legacy topology.

Two discrepancies to resolve during execution, not blockers on this decision:

1. The plan's PR 3 file list includes `packages/sbir-analytics/sbir_analytics/api/*` and
   `docs/architecture/private-analytics-api.md`. ADR-004 retired that service. Treat
   those entries as superseded; the consumer binding is the file-artifact surface, per
   §3.6.
2. `packages/sbir-analytics/sbir_analytics/assets/transition/utils.py` was modified on
   2026-09-16, after the plan's audit baseline. Re-verify the current state of
   `_prepare_transition_dataframe()` before writing PR 1.

`DimensionStatus` is already implemented in `scripts/sttr_spinout_linkage/kernel.py`
against this contract; PR 1 should make `sbir_etl/assertions/enums.py` the single
definition and have the kernel import it rather than mirror it.

## References

- [Neo4j epistemic assertions plan](../architecture/neo4j-epistemic-assertions-plan.md) —
  full design, risk table, and file-level sequence
- [ADR-004: Retire the Private Analytics API](ADR-004-retire-private-analytics-api.md) —
  discharges the external-client decision and gates §3.6
- [ADR-001: Allow Negative Obligation Amounts in Federal Contracts](ADR-001-negative-obligations.md)
- [Research questions](../research-questions.md) — A2, B2/B3, and C2 consumers
- `specs/sttr-spinout-linkage/` — first downstream consumer of `DimensionStatus` and
  `CANDIDATE` assertions
