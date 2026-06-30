# Cross-Agency Technology Taxonomy — Requirements

> **Status:** Partially implemented as of June 2026 — analytical tools in
> `packages/sbir-analytics/sbir_analytics/tools/mission_a/` already compute HHI per CET
> area, cross-agency company count, geographic concentration, semantic clustering, gap
> detection, and topic extraction. The CET classifier is live at
> `packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py`. What remains is a Dagster
> pipeline / reporting asset wiring these tools into a scheduled, cross-agency view.
> Anchors inventory questions **C1a–c** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** C1 — federal SBIR portfolio composition across all 11 agencies (descriptive tier)
**Answers for:** SBIR program managers, OSTP analysts, agency R&D directors
**Complexity tier:** Descriptive (Tier 1) → Relational (Tier 2) for overlap and trend

---

## Done when

> An analyst can open a single report and state:
> "Across all 11 SBIR agencies, [CET area X] is the most-funded technology area
> ($Y in SBIR awards, N% of total). Agencies A and B both fund [CET area Z] — with
> [X%] portfolio overlap. No agency funds [CET area W] above the noise threshold,
> a potential coverage gap. DoD's technology mix has shifted from [area P] toward
> [area Q] over the last five fiscal years."
>
> The report must be producible by re-running a Dagster asset, not by manually
> assembling tool outputs.

---

## Background

No unified view exists of what the 11-agency federal SBIR portfolio funds technologically.
NASEM reviews are siloed by agency and committee mandate — there is no cross-agency
synthesis. The CET classifier and portfolio-metrics tools exist and already run in
isolation; this spec wires them into a single scheduled pipeline that applies the
CET spine consistently across all agencies and produces a cross-agency view that no
NASEM report provides.

---

## Requirements

### Requirement 1 — Full-corpus CET classification

**User story:** As an SBIR program manager briefing an interagency audience, I want
all SBIR awards classified against the canonical 21-area CET taxonomy in a single
pass, so that every agency's portfolio is described in a common vocabulary and
cross-agency comparisons rest on consistent labels rather than agency-specific framing.

#### Acceptance Criteria

1. WHEN running the classification pipeline, THE System SHALL apply the CET classifier
   (`packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py`) to the full SBIR.gov
   corpus, producing a per-award `cet_area` assignment and a calibrated confidence
   score.
2. WHEN storing classification results, THE System SHALL write a Parquet artifact
   with columns `award_id`, `agency`, `cet_area`, and `confidence` so that downstream
   analysis can filter by confidence threshold without re-running the classifier.
3. WHEN the classified corpus is materialized, THE System SHALL emit coverage metrics:
   % of awards classified at confidence ≥ 0.5, multi-label distribution, and
   unclassified count by agency.
4. WHEN the CET taxonomy changes (i.e., `config/cet/taxonomy.yaml` is updated from
   the canonical 21-area spine), THE System SHALL re-classify the full corpus and
   flag the taxonomy version in the artifact metadata.

---

### Requirement 2 — Cross-agency overlap and concentration

**User story:** As an OSTP analyst identifying coordination opportunities and
concentration risk across the federal SBIR portfolio, I want a cross-agency
technology-overlap matrix and an HHI-based concentration measure per CET area, so
that I can flag areas funded redundantly by multiple agencies and areas dominated
by a single-agency funder.

#### Acceptance Criteria

1. WHEN computing cross-agency overlap, THE System SHALL produce a pairwise
   Jaccard similarity matrix over each agency pair's CET-area portfolios (by award
   dollar share per CET area).
2. WHEN computing concentration per CET area, THE System SHALL use the existing
   `compute_portfolio_metrics.py` HHI computation, with HHI > 6000 flagged as
   high-concentration (single-agency dominance).
3. WHEN identifying coverage gaps, THE System SHALL use `detect_gaps.py` to surface
   CET areas with total SBIR funding below [configurable threshold] across all
   agencies, which represent whitespace relative to the CET spine.
4. WHEN emitting the overlap and concentration results, THE System SHALL include
   both award-count and award-dollar weighting so that large-dollar concentration
   is distinguishable from high-volume but low-dollar overlap.

---

### Requirement 3 — Technology-mix trend by agency

**User story:** As an SBIR program manager tracking portfolio shifts, I want each
agency's CET-area allocation expressed as a time series by fiscal year, so that
I can detect emerging priorities and fading investment areas before a NASEM review
cycle surfaces them.

#### Acceptance Criteria

1. WHEN computing technology-mix trends, THE System SHALL compute each agency's
   CET-area share (% of award dollars) per fiscal year, producing a
   `(agency, cet_area, fiscal_year, share)` table.
2. WHEN a CET area's share shifts by more than 10 percentage points within a single
   agency over a three-year window, THE System SHALL flag it as a significant trend
   in the report summary.
3. WHEN an agency has fewer than 20 awards in a given fiscal year, THE System SHALL
   suppress that year's trend point for that agency to prevent noise from sparse
   recent vintages.

---

### Requirement 4 — Scheduled Dagster asset

**User story:** As a pipeline engineer maintaining the cross-agency view, I want the
classification and reporting steps wired into a Dagster asset with a scheduled
refresh, so that the cross-agency taxonomy report stays current as new SBIR awards
are ingested without requiring manual re-runs.

#### Acceptance Criteria

1. WHEN the Dagster asset is defined, THE System SHALL declare the full-corpus
   classification Parquet, the overlap matrix, and the trend table as distinct
   asset outputs so they can be materialized and inspected independently.
2. WHEN the SBIR.gov award corpus is refreshed (weekly asset in the existing
   pipeline), THE System SHALL trigger a downstream re-classification run if the
   new corpus contains awards not present in the existing classification Parquet.
3. WHEN the reporting asset runs, THE System SHALL write output to
   `reports/cross-agency-taxonomy/` as a markdown summary and companion JSON,
   date-stamped to the corpus snapshot used.

---

## Dependencies

- CET classifier (`packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py`) — EXISTS
- Portfolio-metrics tools (`packages/sbir-analytics/sbir_analytics/tools/mission_a/`) — EXISTS
- Full SBIR.gov award corpus — EXISTS (verify freshness before scheduling)
- ModernBERT embeddings (`specs/modernbert_analysis_layer/`) — enhances clustering but not required
