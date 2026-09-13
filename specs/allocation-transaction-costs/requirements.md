# Allocation transaction costs — Requirements

> **Lifecycle status:** Active (see `specs/status.md`)
> **Spec-file progress:** In progress
> Anchors inventory question **C4** in [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `exploratory`
(see [epistemic-tiers.md](../../docs/steering/epistemic-tiers.md))

**Research question anchor:** C4 — SBIR vs conventional-grant allocation costs
**Answers for:** OSTP / R&D-policy staff, SBIR program managers, GAO/OMB readers
**RQ complexity tier:** Inferential

---

## Done when

An analyst can state, without collapsing the three outcomes:

> For NIH SBIR Phase I versus R01-equivalent grants in year Y, under duration
> convention C, an SBIR proposal could consume h* applicant hours before its
> transaction cost per awarded dollar equals an R01. Public data do not
> observe h. The ranking depends on those assumptions. These numbers are
> non-citable.

The same packet names the remaining primary-data gaps.

---

## Background

The inventory did not previously ask whether SBIR allocates federal R&D
funding with lower transaction costs than investigator-initiated grants.
NIH Data Book / RePORT publish competing applications, awards, success
rates, and award size for both SBIR/STTR phases and R01-equivalent grants,
which is enough for a break-even analysis. Applicant hours for small
businesses are not observed.

---

## Glossary

- **Duration convention:** whether R01 award size is treated as an annual
  NIH Data Book average or as that average times assumed project years.
- **Break-even hours:** the SBIR applicant-hour count at which cost per
  awarded dollar equals the R01 comparison, holding wages equal.

---

## Requirements

### Requirement 1 — Three separate outcomes

**User story:** As a policy analyst, I want hours per award, dollars per
award, and cost per awarded dollar kept separate, so that I do not brief a
single efficiency score.

#### Acceptance Criteria

1. WHEN the calculator emits metrics, THE System SHALL report transaction
   hours per funded award, transaction dollars per funded award, and
   transaction cost per dollar awarded as distinct fields.
2. THE System SHALL NOT emit a combined efficiency score.

### Requirement 2 — NIH Phase I versus R01 comparison

**User story:** As an SBIR program manager, I want an NIH-matched
comparison, so that agency and scientific-domain differences are partly
held fixed.

#### Acceptance Criteria

1. THE System SHALL compute the comparison for NIH SBIR Phase I versus NIH
   R01-equivalent grants for every overlapping fiscal year in the committed
   tables.
2. THE System SHALL keep SBIR and STTR separate, and SHALL keep Phase I,
   Phase II Regular, Direct Phase II, Phase IIB, Fast Track, and CRP
   separate.

### Requirement 3 — Break-even hours

**User story:** As a policy analyst, I want the algebraic and empirical
break-even SBIR hour threshold, so that I can see what would have to be
true for SBIR to be cheaper per awarded dollar.

#### Acceptance Criteria

1. THE System SHALL compute
   `h_sbir* = h_r01 * (s_sbir * D_sbir) / (s_r01 * D_r01)`
   for each year and duration convention.
2. THE System SHALL report both `annual_award_size` and `project_total`
   conventions.

### Requirement 4 — Provenance and assumptions

**User story:** As a pipeline engineer, I want every derived value to
trace to a source field or a named assumption, so that unexplained
constants cannot hide in the calculator.

#### Acceptance Criteria

1. WHEN a committed CSV SHA-256 does not match `sources.yaml`, THE System
   SHALL refuse to load.
2. IF a caller supplies `pra_estimate` or `fa_rate` as the hour evidence
   class, THEN THE System SHALL refuse it as `hours_per_application`.
3. Missing agency cost SHALL remain missing, not a silent zero.

### Requirement 5 — Research note

**User story:** As an OSTP / congressional oversight reader, I want a
plain-language note that says what public data can and cannot establish.

#### Acceptance Criteria

1. THE System SHALL include a source inventory, the NIH comparison, a
   sensitivity/break-even table, a complexity-index table labeled as a
   proxy, an admin-cost lower-bound note, a primary-data gap table, and
   one of: hypothesis supported, hypothesis contradicted, result depends
   on specific observable assumptions, or currently underidentified.

---

## Out of scope

- NSF, DOE, NASA, or DoD normalized series
- Live NIH RePORTER harvest
- Dagster assets, Neo4j, or weekly-report wiring
- Evidence-tier / citable promotion
- Causal identification, research quality, or welfare
- Post-award compliance burden
- Scraping FOAs at scale

---

## Dependencies

- NIH RePORT Table #215 and NIH Data Book reports 29 and 158 — EXISTS
  (committed CSVs)
- `sbir_etl.config.yaml_io.read_yaml_mapping` — EXISTS
- Study contract schema — EXISTS
