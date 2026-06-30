# Requirements — SBIR Transition Detection

> **Status:** Implemented and merged (October 30, 2025). Full requirements and design in
> [`specs/archive/completed-features/transition_detection/`](../archive/completed-features/transition_detection/).
> Supports inventory questions **B2** and **B3** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 (did SBIR research result in a federal contract?), B3 (Phase II→III latency, survival probability, transition effectiveness)
**Answers for:** SBIR program managers, policy analysts
**Complexity tier:** Relational (Tier 2) / Inferential (Tier 3)

---

## Done when

> A pipeline engineer can state: "The Neo4j graph contains `RESULTED_IN` edges scored
> by a 6-signal scorer (agency continuity 0.25, timing proximity 0.20, competition type
> 0.20, patent signal 0.15, CET alignment 0.10, vendor match 0.10). Confidence bands:
> HIGH ≥ 0.85, LIKELY ≥ 0.65, POSSIBLE < 0.65. Precision ≥ 85% at HIGH band; recall
> ≥ 70% overall. Detection throughput ≥ 15,000 records/min. Algorithm documented in
> `docs/transition/detection-algorithm.md`."

---

## Introduction

This feature detects technology transitions from SBIR awards to follow-on federal
contracts, measuring program commercialization effectiveness at scale. The system uses
multi-signal scoring — vendor matching, agency continuity, timing proximity, competition
type, patent filing signals, and CET alignment — to produce calibrated confidence scores
for each award-to-contract link. Evidence bundles for all HIGH and LIKELY detections
provide full audit trails.

**Implementation location:** `packages/sbir-analytics/sbir_analytics/assets/transition/`
and `sbir_etl/transition/`. Algorithm described in `docs/transition/detection-algorithm.md`.
Archived spec: `specs/archive/completed-features/transition_detection/`.

---

## User Stories

**As an SBIR program manager,** I want to see which Phase II awards led to follow-on
federal contracts, so that I can measure transition effectiveness by agency, technology
area, and award vintage and identify which cohorts or CET areas are underperforming.

**As a pipeline engineer,** I want each transition detection to include an evidence
bundle (matched vendor, score breakdown by signal, timeline) and a confidence band
(HIGH / LIKELY / POSSIBLE), so that individual detections can be audited and the
precision benchmark (≥85% at HIGH) can be verified against holdout samples.

---

## Requirements

### Requirement 1 — Multi-signal transition scoring

**User Story:** As an SBIR program manager, I want transition likelihood scored using
six independent signals, so that HIGH-confidence detections are reliable enough to cite
in program evaluations without manual review.

#### Acceptance Criteria

1. THE System SHALL score each award-to-contract candidate pair using six signals:
   agency continuity (weight 0.25), timing proximity (0.20), competition type (0.20),
   patent signal (0.15), CET alignment (0.10), and vendor match (0.10).
2. THE System SHALL classify detections as HIGH (≥ 0.85), LIKELY (≥ 0.65), or POSSIBLE
   (< 0.65) based on the composite score.
3. THE System SHALL achieve precision ≥ 85% at the HIGH confidence band and recall
   ≥ 70% overall, validated against the precision benchmark test suite in
   `tests/unit/test_transition_scorer.py`.
4. THE System SHALL generate evidence bundles for all detections with score ≥ 0.60,
   recording per-signal contributions and matched entity identifiers.

### Requirement 2 — Vendor resolution for cross-dataset matching

**User Story:** As a data analyst, I want SBIR recipients matched to federal contract
vendors using a priority cascade (UEI → CAGE → DUNS → fuzzy name), so that transitions
are not missed due to identifier inconsistencies across SBIR.gov, FPDS, and USAspending.

#### Acceptance Criteria

1. THE System SHALL match vendors using UEI (confidence 0.99), CAGE, DUNS, and fuzzy
   name matching (minimum threshold 0.85) in priority order.
2. THE System SHALL achieve vendor match rate ≥ 90% for SBIR recipients present in
   FPDS contract data.
3. THE System SHALL record the match method and confidence for each resolution so
   downstream consumers can filter by identifier type.

### Requirement 3 — Graph integration

**User Story:** As a defense industrial base analyst, I want transition detections
stored as `RESULTED_IN` edges in Neo4j, so that I can query award-to-contract
relationships alongside CET, patent, and entity nodes in a single graph traversal.

#### Acceptance Criteria

1. THE System SHALL persist each detected transition as a `RESULTED_IN` edge between
   the `Award` node and the `Contract` node, carrying `score`, `confidence_band`,
   `signals`, and `detected_at` properties.
2. THE System SHALL use MERGE operations to avoid duplicate edges on re-runs.
3. THE System SHALL support a dry-run mode that reports match counts without committing
   graph writes.
