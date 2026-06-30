# Follow-on Funding Multiplier Analysis — Requirements

> **Status:** Not yet started — zero implementation code as of June 2026.
> Anchors inventory question **A3** in [docs/research-questions.md](../../docs/research-questions.md).
> Prerequisites (entity resolution, SBIR identification, USAspending enrichment) are all live on `main`.
>
> NASEM's reviews of DoD SBIR call this quantity the *leverage ratio*. This codebase
> uses *follow-on funding multiplier* for the same calculation to avoid the debt
> connotation that "leverage" carries in finance.

**Research question anchor:** A3 — DoD follow-on funding multiplier (inferential tier)
**Answers for:** policy analysts (congressional briefings, OMB), SBIR program managers
**Complexity tier:** Inferential (Tier 3)

---

## Done when

> An analyst can state: "NASEM reports 4:1. Our pipeline yields [X]:1 using [method].
> The difference is attributable to [Y]."
>
> The reconciliation matters more than matching the number. A well-characterized
> divergence (different time window, different SBIR-vs-non-SBIR coding, incomplete FPDS
> Phase III tagging) is a valid and publishable result. An unexplained match is not.

---

## Background

NASEM reports a ~4:1 ratio of non-SBIR DoD obligations to SBIR/STTR obligations for
DoD SBIR firms (2012–2020) [L1][L2], computed manually on a quadrennial review cycle.
USAspending shows that a firm received a SBIR Phase II award and later won a non-SBIR
DoD contract — but it does not flag the relationship. Our entity resolution + FPDS
pipeline automates this linkage at scale, enabling a continuously-updateable follow-on
funding multiplier computation and stratifications NASEM does not publish (by CET
area, firm experience, and time trend).

---

## Glossary

- **Follow-on funding multiplier** (a.k.a. NASEM's *leverage ratio*) — Non-SBIR DoD
  obligations ÷ SBIR/STTR obligations for the set of firms that received at least one
  SBIR/STTR award in the measurement window.
- **Cohort** — The set of SBIR/STTR awardees grouped by their first-award fiscal year.
- **Experienced firm** — A firm with more than one prior SBIR award at the time of the
  award being measured.
- **NASEM benchmark** — The 4:1 aggregate ratio reported in [L1] for DoD SBIR firms,
  2012–2020.

---

## Requirements

### Requirement 1 — Aggregate multiplier computation

**User story:** As a policy analyst preparing a congressional briefing, I want an
aggregate DoD follow-on funding multiplier computed from our pipeline, so that I can
benchmark it against NASEM's 4:1 figure and state either a confirmation or a
characterized divergence before an HASC or SASC audience.

#### Acceptance Criteria

1. WHEN the pipeline runs over the SBIR firm universe, THE System SHALL compute the
   aggregate follow-on funding multiplier as: sum(non-SBIR DoD obligations) /
   sum(SBIR/STTR obligations) across all resolved firms.
2. WHEN separating SBIR from non-SBIR obligations, THE System SHALL use FPDS
   product-or-service codes and contract-type flags (not just the SBIR.gov award list)
   to classify each obligation.
3. WHEN the aggregate ratio is computed, THE System SHALL also compute a firm-level
   distribution (median, 25th/75th percentile, share of firms with ratio > 1) so that
   the aggregate is not mistaken for the typical firm experience.
4. WHEN reporting entity-resolution coverage, THE System SHALL state the share of SBIR
   award dollars that successfully matched to FPDS vendor records, so that the ratio
   carries an explicit denominator-coverage qualifier.

---

### Requirement 2 — Cohort stratification

**User story:** As an SBIR program manager, I want the follow-on funding multiplier
broken out by award vintage, firm size, technology area, and firm experience, so that
I can identify which cohorts and technology clusters generate the highest follow-on
DoD investment and target program support accordingly.

#### Acceptance Criteria

1. WHEN stratifying by award vintage, THE System SHALL group firms by first-SBIR-award
   fiscal year and compute the ratio per cohort.
2. WHEN stratifying by firm size, THE System SHALL use SAM.gov employee or revenue
   buckets and emit a ratio per bucket.
3. WHEN stratifying by technology area, THE System SHALL use CET classifier output
   (`packages/sbir-ml/`) and emit a ratio per CET area.
4. WHEN stratifying by firm experience, THE System SHALL split firms into
   first-time awardee vs. repeat awardee (≥2 prior SBIR awards) and compute the ratio
   for each group.
5. WHEN any stratification cell contains fewer than 10 firms, THE System SHALL suppress
   the ratio and note the suppression reason, to prevent unreliable small-cell figures
   from appearing in published output.

---

### Requirement 3 — NASEM reconciliation

**User story:** As a policy analyst preparing a publishable methodology comparison, I
want the pipeline's ratio accompanied by a structured reconciliation against NASEM's
4:1, so that I can explain any divergence in terms of methodology, time window, or
data-source differences rather than leaving it unexplained.

#### Acceptance Criteria

1. WHEN the aggregate ratio is computed, THE System SHALL produce a reconciliation
   report documenting: measurement time window, SBIR identification method, FPDS
   inclusion/exclusion rules, and entity-resolution match rate.
2. WHEN the pipeline ratio diverges from NASEM's 4:1 by more than 0.5 in either
   direction, THE System SHALL identify which methodology differences (e.g., time
   window, FPDS Phase III undercount, ER coverage) account for the gap.
3. WHEN producing the reconciliation report, THE System SHALL emit both a JSON artifact
   (for programmatic consumption) and a markdown summary (for human review), to the
   `reports/follow-on-multiplier/` directory.

---

### Requirement 4 — Civilian-agency extension

**User story:** As an SBIR program manager at a civilian agency, I want the same
follow-on funding multiplier computed for DOE so that my agency can benchmark its
follow-on investment generation against DoD and against the Myers & Lanahan DOE
baseline [L9][L5].

#### Acceptance Criteria

1. WHEN running the civilian-agency computation, THE System SHALL support DOE as the
   first civilian-agency target, using both FPDS contracts and USAspending grants
   (DOE uses both instrument types).
2. WHEN emitting civilian-agency results, THE System SHALL produce a side-by-side
   comparison table (DoD vs. DOE) in the same report format as Requirement 3.
3. WHEN the DOE ratio is computed, THE System SHALL note which NASEM DOE review [L5]
   and Myers & Lanahan [L9] figures are the relevant external benchmarks.

---

### Requirement 5 — Time-series trend

**User story:** As a policy analyst tracking program-level trends, I want the
follow-on funding multiplier expressed as a time series by fiscal year, so that I can
show whether DoD's follow-on investment in SBIR firms is growing, shrinking, or
stable — a question NASEM's quadrennial reviews cannot answer.

#### Acceptance Criteria

1. WHEN computing the time series, THE System SHALL emit the aggregate ratio for each
   fiscal year in the data window, using a rolling 3-year trailing cohort to smooth
   vintage effects.
2. WHEN a fiscal year has fewer than 50 resolved firms, THE System SHALL flag that
   year's ratio as low-confidence.
3. WHEN the trend direction is determinable (monotone for ≥5 consecutive years), THE
   System SHALL note it in the markdown report.

---

## Dependencies

- FPDS contract data (`packages/sbir-analytics/sbir_analytics/tools/phase0/extract_fpds_contracts.py`) — EXISTS
- Entity resolution (`sbir_etl/enrichers/`) — EXISTS
- CET classifier (`packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py`) — EXISTS
- Company categorization (`specs/company-categorization/`) — 77% complete
