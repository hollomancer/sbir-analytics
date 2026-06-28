# Requirements — Agency Continuity & Phase II→III Transition Rate Analysis

> **Status:** Not yet started. Transition detection (RESULTED_IN edges) and entity
> resolution are live on `main`. FPDS contract data available via
> `packages/sbir-analytics/sbir_analytics/tools/phase0/extract_fpds_contracts.py`.
> Anchors inventory question **A2** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** A2 — do firms show higher transition rates within the same awarding agency (agency continuity signal)? Phase II→III transition rate per CET area via FPDS.
**Answers for:** SBIR program managers, DoD acquisition leadership, policy analysts
**Complexity tier:** Relational (Tier 2)

---

## Done when

> An SBIR program manager can state: "The aggregate Phase II→III transition rate for
> DoD SBIR firms is [X]%, broken down by CET area and awarding DoD component (Army,
> Navy, AF, DARPA, DLA). Within-agency transitions occur at [Y]× the rate of
> cross-agency transitions, controlling for firm and award vintage. A firm receiving
> its first Phase II from Agency A has [Z]% probability of its first Phase III contract
> being from Agency A vs. any other federal customer."

---

## Introduction

The transition detection system produces `RESULTED_IN` edges between SBIR awards and
follow-on federal contracts. This spec derives population-level statistics from those
edges: the **agency continuity signal** (does the Phase III contract come from the
same agency that funded Phase II?), the **Phase II→III transition rate by CET area**
(what share of Phase II awards produce a detectable Phase III), and a
**within-vs.-cross-agency transition decomposition**.

These are the A2 relational questions distinct from the A3 leverage ratio. The leverage
ratio asks "how much non-SBIR DoD funding follows?" — this asks "does a federal
contract result at all, and does it come from the same agency?"

The agency continuity signal (weight 0.25) is already used by the transition scorer
as one of six evidence signals. This spec uses the same signal at the population level
to answer the policy question: is there a statistically meaningful agency loyalty effect?

---

## User Stories

**As an SBIR program manager at DoD,** I want the Phase II→III transition rate broken
out by awarding DoD component and CET area, so that I can identify which technology
domains and program offices have the strongest follow-on contract pull-through and
benchmark underperforming offices against the best.

**As a policy analyst preparing a NASEM-style program review,** I want the within-agency
vs. cross-agency transition decomposition, so that I can measure whether SBIR-funded
research mainly serves the funding agency (agency continuity) or diffuses to other
federal customers (knowledge spillover to other agencies).

---

## Requirements

### Requirement 1 — Phase II→III transition rate by CET area and agency

**User Story:** As an SBIR program manager, I want the share of Phase II awards that
produced a detectable Phase III contract, broken out by CET area and awarding agency,
so that I can identify underperforming areas and compare against the DoD-wide baseline.

#### Acceptance Criteria

1. THE System SHALL compute transition rate as: (Phase II awards with at least one
   HIGH or LIKELY `RESULTED_IN` edge) ÷ (total Phase II awards), per CET area per
   awarding agency per fiscal-year cohort.
2. THE System SHALL report transition rates separately by confidence band (HIGH-only
   vs. HIGH+LIKELY) so that consumers can choose their precision threshold.
3. THE System SHALL compute a DoD-wide aggregate transition rate as the baseline
   for component-level comparison.
4. WHEN a CET-area × agency cell contains fewer than 20 Phase II awards, THE System
   SHALL suppress the rate and note the suppression reason.
5. THE System SHALL compare the computed rates against published NASEM baselines [L1]
   and Link & Scott [L12] and emit the comparison delta in the output report.

### Requirement 2 — Agency continuity decomposition

**User Story:** As a policy analyst, I want within-agency and cross-agency transitions
quantified separately, so that I can measure whether SBIR funding creates knowledge
that stays within the funding program or diffuses to other federal customers.

#### Acceptance Criteria

1. THE System SHALL classify each `RESULTED_IN` transition as **within-agency** (Phase
   III customer = Phase II funder) or **cross-agency** (Phase III customer ≠ Phase II
   funder), using the `agency_code` on both sides of the edge.
2. THE System SHALL compute the within-agency rate per awarding agency, and the
   within-DoD-component rate (e.g., Army Phase II → any Army Phase III contract).
3. THE System SHALL compute the relative rate: within-agency transitions ÷ cross-agency
   transitions, by CET area, to surface whether continuity is technology-domain-specific.
4. THE System SHALL control for firm vintage (first-time vs. repeat awardee) in the
   agency continuity rate, since repeat awardees may have stronger agency relationships.

### Requirement 3 — Time trend

**User Story:** As a DoD acquisition analyst, I want the transition rate and agency
continuity signal expressed as a time series by fiscal year, so that I can assess
whether Phase III pull-through is improving or declining across the SBIR program.

#### Acceptance Criteria

1. THE System SHALL emit aggregate DoD transition rate, within-agency rate, and
   cross-agency rate by fiscal year for the full data window.
2. WHEN the transition rate changes by more than 5 percentage points between any two
   consecutive fiscal years, THE System SHALL flag the change and note any
   methodology or data-coverage changes that could explain it.
3. THE System SHALL use a rolling 3-year trailing cohort for vintage smoothing, consistent
   with the leverage ratio time series in `specs/leverage-ratio-analysis/`.
