# Phase-Transition Report Grain — Design

## Current flow

`phase_transition_analysis` reads both `pairs` and `survival`. Percentiles, histograms, and agency
median latency query all pair rows; transition rates query survival rows. This makes the report a
mixture of pair-weighted and award-weighted summaries.

## Proposed reporting contract

The survival/follow-up artifact becomes the only headline analysis table:

- grain: one row per canonical Phase II award;
- event fields: observed flag, selected first-event contract/action, signed time from the declared
  origin;
- censor fields: cut date and follow-up time when no event is observed;
- strata: Phase II agency and cohort attributes copied from the same award row.

Headline incidence, event-conditional latency, agency summaries, and cohort summaries query this
table. The pairs table remains an input to construction and an output for link diagnostics only.

## Multiplicity audit

Before report generation, compute and emit:

1. candidate Phase III contracts per Phase II award;
2. Phase II assignments per selected Phase III contract;
3. counts with multiplicity greater than one and each maximum;
4. row totals at pair, Phase II award, and distinct selected-contract grain.

These diagnostics explain linkage ambiguity without changing the chosen headline unit.

## Failure behavior

Duplicate Phase II identifiers, incomplete event/censor fields, or inconsistent observed flags are
blocking schema errors. Signed negative event times may be retained as diagnostics when the source
contract permits them, but the reporter must not call the resulting event-only distribution a
survival estimate.

## Migration

Version the report schema. Rename pair-based legacy fields if they must be retained temporarily;
do not silently overwrite their semantics under the same key. Update downstream fixtures and docs
to name the award-grain denominator.

## Testing strategy

- One firm with several Phase II awards and several candidate contracts.
- One selected contract reused by multiple Phase II assignments.
- Duplicate-award and incomplete event/censor failure fixtures.
- Invariance test: adding a non-selected candidate pair leaves headline metrics unchanged.
