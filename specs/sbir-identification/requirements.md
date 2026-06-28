# Requirements — SBIR/STTR Award Identification

> **Status:** Implemented on `main`. Classifier: `sbir_etl/extractors/sbir_classifier.py`.
> Methodology: [`docs/sbir-identification-methodology.md`](../../docs/sbir-identification-methodology.md).
> Supports inventory question **E1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E1 — which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence?
**Answers for:** pipeline engineers, SBA oversight analysts
**Complexity tier:** Foundational infrastructure (Tier 1–2)

---

## Done when

> A pipeline engineer can state: "Every award record in the pipeline carries a
> `sbir_confidence` score (0.5–1.0) and `sbir_method` tag
> (`fpds_research_field` / `aln_match` / `description_parse`). FPDS-research-field
> identifications score 1.0; ALN matches 0.8–1.0; description-parse matches 0.5–0.7.
> False-positive rates for shared-ALN programs (e.g., NIH ~20% non-SBIR via ALN 47.084)
> are documented and tested. The methodology is in `docs/sbir-identification-methodology.md`."

---

## Introduction

The SBIR/STTR identification classifier is the foundational layer for all downstream
analytics. It determines which records in USAspending / FPDS / FABS are SBIR or STTR
awards, assigning confidence scores based on the strength of the identifying signal.

Three independent signals are used in priority order:

1. **FPDS `research` field** — FAR 35.106 research type codes; when present, score 1.0.
2. **Assistance Listing Number (ALN)** — OMB Circular A-133 ALNs designated for SBIR/STTR; score 0.8–1.0 depending on ALN exclusivity (some ALNs, like NIH's 47.084, are shared with non-SBIR grants, reducing confidence).
3. **Description parsing** — abstract / title keyword extraction when neither FPDS nor ALN signals are available; score 0.5–0.7.

All confidence scores and method tags are persisted to the graph and available for
downstream filtering.

---

## User Stories

**As a pipeline engineer,** I want every federal award record tagged with an
`sbir_confidence` score and `sbir_method` tag, so that downstream analytics (transition
detection, fiscal impact, leverage ratios) can filter to high-confidence SBIR awards
without manual review.

**As an SBA oversight analyst,** I want the identification methodology's false-positive
rate documented by data source (FPDS vs. ALN vs. description), so that I can characterize
the accuracy of SBIR program metrics derived from this pipeline in reports to Congress.

---

## Requirements

### Requirement 1 — Three-tier confidence classification

**User Story:** As a pipeline engineer, I want each award classified by the strongest
available SBIR identification signal, so that high-confidence records can be separated
from uncertain ones without discarding borderline awards entirely.

#### Acceptance Criteria

1. THE System SHALL classify awards using three tiers in priority order:
   (a) FPDS `research` field present and set to SBIR/STTR → `fpds_research_field`,
   confidence 1.0;
   (b) ALN matches a designated SBIR/STTR ALN → `aln_match`, confidence 0.8–1.0
   depending on ALN exclusivity;
   (c) Abstract or title contains SBIR/STTR keywords → `description_parse`,
   confidence 0.5–0.7.
2. THE System SHALL attach `sbir_confidence` (float 0.0–1.0) and `sbir_method`
   (enum string) to every processed award record.
3. WHEN an award matches multiple tiers, THE System SHALL use the highest-confidence
   signal and record only that method tag.

### Requirement 2 — Shared-ALN false-positive handling

**User Story:** As a pipeline engineer, I want shared-ALN programs (where one ALN
covers both SBIR and non-SBIR grants) handled with reduced confidence, so that
false-positive SBIR identifications do not inflate program metrics.

#### Acceptance Criteria

1. THE System SHALL maintain a configured list of shared ALNs (e.g., NIH ALN 47.084)
   with their estimated SBIR share and associated confidence penalty.
2. WHEN an award's ALN is on the shared list, THE System SHALL assign a reduced
   confidence score (below 1.0) and flag the record as `shared_aln`.
3. THE System SHALL expose the shared-ALN false-positive rate by ALN in the
   methodology documentation (`docs/sbir-identification-methodology.md`).

### Requirement 3 — SBIR.gov reconciliation

**User Story:** As an SBA oversight analyst, I want the pipeline's SBIR award count
reconciled against SBIR.gov, so that discrepancies between USAspending FPDS data and
the authoritative SBA program database are characterized and documented.

#### Acceptance Criteria

1. THE System SHALL compare pipeline-identified SBIR award counts against SBIR.gov
   bulk award records by agency and fiscal year.
2. THE System SHALL report the reconciliation match rate (share of SBIR.gov records
   also found in the pipeline) and the unmatched count per agency.
3. WHEN the reconciliation match rate falls below 95% for any agency-year cell,
   THE System SHALL log a warning identifying the gap.
