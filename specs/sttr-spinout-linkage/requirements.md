# STTR Spinout–Subcontract Linkage and Partner-Type Classification — Requirements

**Target epistemic tier:** `exploratory`

> **Status (2026-08-14):** Phase 0 design only. No implementation is authorized.
> The classification criteria are **not frozen**: freezing is blocked until the
> repository owner resolves [open-questions.md](open-questions.md). Every artifact
> this spec produces is **non-citable** (`citable: false`) until the negative-control
> and adjudication gates in [design.md](design.md) pass. Primary inventory
> questions are **B2** (STTR spinout vs. subcontract relationship) and **B1**
> (STTR research-institution partner types), with supporting dimensions **A2**
> (subaward relationship) and **C2** (patent–award linkage) for RQ1, and
> **F1 / F3 / A4 / B3** for the RQ2 outcome design, in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 / B1 — classify each STTR small-business↔research-institution
relationship as spinout vs. subcontract using public data, plus a list-based RI
partner-type readout; supporting dimensions A2 / C2; design-only matched comparison
on F1 / F3 / A4 / B3
**Answers for:** SBIR program managers, policy analysts, entrepreneurial finance researchers
**Complexity tier:** Relational → Inferential (Tier 2–3)

---

## Done when

> **RQ1 (classification):** An SBIR program manager can state: "Of the [N] STTR awards
> in the frozen universe, [a]% carry an SBC↔RI relationship classified `SPINOUT_T1`,
> [b]% `SPINOUT_T2`, [c]% `SUBCONTRACT`, and [d]% `INDETERMINATE`, using public data
> only, under the criteria frozen at commit [SHA]. Precision/recall by tier against a
> [150–200]-award blind adjudication sample is [table]. This split has not been measured
> before." — reported **only** with the non-citable label until validation gates pass.
>
> **Partner-type readout:** The same manager can state: "[k] STTR awards name a
> non-university, non-FFRDC nonprofit as the research-institution partner
> ([incidence table] by category × agency × FY)," or the negative — either result is
> reportable once gates pass.
>
> **RQ2 (design only):** A researcher can read a pre-registered analysis plan for a
> matched comparison of spinout- vs. subcontract-STTRs on Phase II→III latency, Form D
> follow-on capital, and M&A — with the analysis specified but **not run** in this spec.

---

## Requirements

### Requirement 1 — Deterministic SBC↔RI relationship classification (RQ1)

**User story:** As an SBIR program manager, I want every STTR award's small-business↔research-institution
relationship classified `SPINOUT_T1` / `SPINOUT_T2` / `SUBCONTRACT` / `INDETERMINATE`
from public data, so that I can brief on how much of the STTR program routes federal
research dollars to firms *spun out of* their academic partner versus firms *subcontracting*
to an arm's-length institution.

#### Acceptance Criteria

1. WHEN an STTR award is on the frozen award spine (D1), THE System SHALL assign exactly one
   relationship label via the ordered deterministic cascade in [design.md](design.md#classification-cascade-rq1),
   with no ML in v1.
2. WHEN a scoring dimension cannot be evaluated, THE System SHALL record a typed per-dimension
   absence (`DimensionStatus`) and SHALL NOT treat absence as negative evidence.
3. WHEN a recorded license is absent, THE System SHALL encode that as typed absence and SHALL NOT
   count it toward `SUBCONTRACT`.
4. WHEN matching person or organization names, THE System SHALL apply `generic_token_guard`
   before accepting any match.

### Requirement 2 — Deterministic research-institution partner-type classification

**User story:** As a policy analyst, I want every STTR research institution classified into a
fixed partner-type vocabulary from versioned public seed lists, so that I can report whether
any non-university, non-FFRDC nonprofit (a new-model research org, research hospital, or
independent institute) has ever served as an STTR partner, by agency and fiscal year.

#### Acceptance Criteria

1. WHEN an RI is on the award spine, THE System SHALL classify it into one of
   `UNIVERSITY` / `FFRDC` / `RESEARCH_HOSPITAL` / `NONPROFIT_INSTITUTE` / `NEW_MODEL_ORG` /
   `COMMUNITY_COLLEGE` / `OTHER_NONPROFIT` / `UNRESOLVED` deterministically from dated,
   versioned seed lists (see [seed-list-provenance.md](seed-list-provenance.md)).
2. WHEN an RI matches no seed list, THE System SHALL distinguish `NO_MATCH` from
   `POSSIBLY_MASKED_BY_SPONSOR` in the typed absence, after matching known fiscal-sponsor names.
3. WHEN seed lists overlap (e.g., a university-administered FFRDC), THE System SHALL apply the
   precedence order proposed in [design.md](design.md#partner-type-classification) (owner decision pending).

### Requirement 3 — CANDIDATE graph assertions with typed absence

**User story:** As a pipeline engineer, I want linkage and partner-type results emitted only as
`CANDIDATE` assertions with per-dimension typed absence, so that no graph-derived rate can be
mistaken for a validated finding.

#### Acceptance Criteria

1. WHEN emitting an assertion, THE System SHALL set `claim_status = CANDIDATE`,
   `support_class = C`, `permitted_use = INVESTIGATIVE_ONLY`, per
   [neo4j-epistemic-assertions-plan.md](../../docs/architecture/neo4j-epistemic-assertions-plan.md).
2. THE System SHALL keep Parquet authoritative and SHALL NOT introduce any new causal edge type.

### Requirement 4 — RQ2 matched-comparison design (design only)

**User story:** As an entrepreneurial finance researcher, I want a pre-registered analysis plan
for comparing spinout- vs. subcontract-STTR transition outcomes, so that the comparison can be
run later without post-hoc specification freedom.

#### Acceptance Criteria

1. THE spec SHALL define the matched comparison (matching keys, outcomes, honesty clauses) but
   SHALL NOT run it. See [design.md](design.md#rq2--matched-outcome-comparison-design-only).

---

## Dependencies

- `sbir_etl.identity` — company/organization-name normalization and similarity primitives
  (`normalize_company_name`, `company_name_similarity`, versioned `CompanyNameProfile`,
  `CompanyNameMetric`, `RecoveryStatus`) (EXISTS). Reused; not forked.
- Graph epistemic-assertion contract — ADR-005 (`DimensionStatus`, `CANDIDATE` assertions) (PROPOSED, no production implementation).
- The named `nih-commercialization-linkage` kernel (`resolve_identity`, `classify_linkage`,
  `generic_token_guard`, `signal_absent_reason`) — **DOES NOT EXIST** in the repo today. This
  spec proposes it as new `exploratory`-tier code built on the primitives above; see
  [open-questions.md](open-questions.md) decision O-0.
- Form D / SEC EDGAR M&A infrastructure — used by the RQ2 *design* only (EXISTS; consumed, not built).

## Out of Scope

- Any ML classifier for linkage or partner type (deterministic, lexicon/list-first in v1; ML is future work).
- Running RQ2 (design only in this spec).
- Non-public agency award files (PI-employer election, allocation-of-rights agreements) — documented
  as a data gap in [design.md](design.md#coverage-and-the-documented-gap), not a data source.
- Any new causal graph edge type; any promotion of a number to a citable tier.
