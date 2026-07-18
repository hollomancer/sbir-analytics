# Evaluation validity: current protocol

Status: **corrected estimator and cohort rules implemented; empirical rerun blocked by missing inputs.**

## Field-substitution experiment

The title/abstract and title/description 2×2 changes fields, not a single
abstract construct called “richness.” Its defensible estimand is field
substitution within a selected firm-linked NASA cohort.

- Candidate IDs are fixed across cells.
- One TF-IDF vocabulary and set of IDF weights is frozen across all four cells.
- Pairwise score ties receive one-half credit.
- Metadata-negative fallback tiers are reported separately.
- Absolute AUC and cross-cell effects remain provisional until regenerated.

Dense-model results and the previously reported paired-bootstrap interval are
legacy results without a committed end-to-end generating artifact; they are not
reasserted here.

## DoD retrieval

The coded DoD benchmark retains every eligible contract row. It no longer picks
the longest description per firm, no longer combines metadata from different
rows, and uses only pre-target Phase II text. Targets lacking the advertised
hard-negative pool are excluded and counted rather than silently changed to
random negatives.

The outcome remains coded-population portfolio linkage, not performance on
uncoded Phase III.

## Survival

The bounded curve starts at first observed DoD Phase II and ends at first later
observed coded Phase III action or administrative censoring. A curve that does
not cross 0.5 has a median **not reached during follow-up**. Event-only lag is a
descriptive selected-sample statistic, not a lower bound.

This does not answer elapsed time from Phase II completion to verified Phase III
lineage; that north-star question requires period-of-performance completion and
adjudicated linkage.

## Policy interpretation

A structured parent-award field is preferable to a character-count mandate,
but it still requires validation, enforcement, multi-parent support, and
missingness audits. The detector demonstrates a linkage-data gap; it does not
prove that a field would be complete or produce perfect detection.
