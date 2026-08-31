# Phase-Transition Report Grain — Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Not yet started
> Anchors inventory questions **B2–B3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `pipelines`

**Research question anchor:** B2 transition linkage and B3 Phase II→III latency/survival
**Answers for:** pipeline engineers and analysts consuming shared transition reports
**RQ complexity tier:** Relational / Inferential downstream; this spec enforces reporting grain

---

## Done when

The shared transition reporter derives rates, agency summaries, and event-conditional latency from
one documented row-per-Phase-II follow-up frame, while candidate-pair multiplicity is emitted only
as a separately labeled diagnostic.

---

## Background

The current reporter calculates latency percentiles and histograms over the raw `pairs` table but
calculates transition rates from the one-row-per-Phase-II `survival` table. Firms with several
Phase II awards or Phase III contracts therefore receive extra weight in latency summaries, and
the report combines statistics with different denominators under one transition vocabulary.

## Requirements

### Requirement 1 — One declared headline grain

**User story:** As a report consumer, I want every headline transition measure tied to a declared
unit of observation, so multiplicity cannot silently change weighting.

#### Acceptance Criteria

1. THE headline follow-up frame SHALL contain exactly one row per canonical Phase II award.
2. Transition incidence SHALL use that frame's explicit event indicator and declared follow-up cut.
3. Event-conditional latency SHALL use only observed-event rows from the same frame and SHALL state
   its denominator and signed time origin.
4. Agency and cohort summaries SHALL aggregate the same frame rather than joining back to all raw
   pairs.

### Requirement 2 — Pair diagnostics remain diagnostic

**User story:** As a pipeline engineer, I want candidate-link multiplicity visible but separated,
so it helps debug matching without being mistaken for transition incidence.

#### Acceptance Criteria

1. Raw candidate pairs SHALL NOT feed headline latency or rate fields.
2. Checks SHALL report Phase II awards with multiple candidate Phase III contracts, contracts
   reused across Phase II assignments, and maximum multiplicity.
3. Every pair-derived output SHALL be labeled `candidate_pair` or equivalent and non-citable.

### Requirement 3 — Schema and semantic guards

**User story:** As a reviewer, I want automated grain assertions, so future schema changes fail
instead of quietly reintroducing mixed denominators.

#### Acceptance Criteria

1. THE reporter SHALL fail when the follow-up frame contains duplicate Phase II award identifiers.
2. THE reporter SHALL fail when an observed event lacks its event date/time or when a censored row
   lacks its censoring time.
3. Synthetic one-to-many fixtures SHALL prove that adding candidate pairs does not change a Phase
   II award's headline weight.

## Out of scope

- Choosing or validating the Phase II↔Phase III matching rule.
- Kaplan–Meier estimation or resolving negative completion-relative event times.
- Agency-specific cohort filters or Navy-specific reporting.
- Promoting the report beyond its current non-citable tier.

## Dependencies

- Phase II↔Phase III candidate-pairs asset — EXISTS
- One-row-per-Phase-II survival/follow-up asset — EXISTS
- Shared `phase_transition_analysis` reporter — EXISTS
