# Procurement Data Sources Evaluation — Requirements

## Introduction

[makegov/awesome-procurement-data](https://github.com/makegov/awesome-procurement-data)
catalogs federal procurement data sources, APIs, and tools. This spec scopes a
time-boxed investigation to determine which of those sources we should integrate into
the SBIR ETL pipeline — particularly to strengthen the imputation layer proposed in
`specs/data-imputation/` and the enrichment stages in `sbir_etl/enrichers/`.

We already integrate:
- **SAM.gov** (entity enrichment): `sbir_etl/enrichers/sam_gov/`
- **USAspending** (company categorization, transactions): `sbir_etl/enrichers/usaspending/`
- **SBIR.gov API** (awards, solicitations): `sbir_etl/extractors/`
- **FPDS ATOM** (federal procurement data): `sbir_etl/enrichers/fpds_atom.py`

The investigation focuses on **net-new sources or upgrades to existing integrations**
that materially move one or more of these needles:

1. Imputation confidence / coverage for the six imputable fields in
   `specs/data-imputation/design.md` (§4).
2. Entity resolution recall for UEI/DUNS backfill.
3. Solicitation-linked imputation (per-phase max amount, period of performance,
   topic→NAICS crosswalks).
4. Build-vs-buy decisions for NAICS inference.

This is an **investigation**, not an implementation. The deliverable is a decision
document plus one or more follow-on implementation specs.

## Glossary

- **Awesome-procurement-data** — Community-maintained list at
  `github.com/makegov/awesome-procurement-data`.
- **Entity Extracts** — SAM.gov bulk-download files of the full federal UEI registry.
  Distinct from the per-UEI lookup API we already use.
- **Opportunities API** — SAM.gov's machine-readable feed of federal contract
  opportunities, including SBIR/STTR solicitations with per-phase ceilings.
- **FSCPSC** — Third-party NAICS/PSC prediction API.
- **PSC** — Product Service Code, the procurement-side sibling of NAICS.

## Scope

### In scope

Evaluate every source in the awesome-procurement-data list against our imputation and
enrichment needs. Produce a go/no-go recommendation per source with confidence,
prerequisites, and effort estimate.

### Out of scope

- Implementing any new extractor or enricher (that's a downstream spec).
- Evaluating commercial/paid data providers not in the list.
- Re-evaluating sources we already integrate deeply (SAM.gov entity API,
  USAspending v2, SBIR.gov API, FPDS ATOM) *unless* a listed tool/library would
  improve our existing integration.

## Requirements

### Requirement 1 — Complete inventory and categorization

**User Story:** As a pipeline maintainer, I want every source in the
awesome-procurement-data list evaluated against our pipeline's gaps, so that no
low-hanging fruit is missed.

#### Acceptance Criteria

1. THE System SHALL produce a matrix in `specs/procurement-data-sources-eval/matrix.md`
   with one row per listed source and columns: `name`, `category`, `auth_required`,
   `rate_limits`, `data_fields_exposed`, `relevance_to_imputation`,
   `relevance_to_enrichment`, `already_integrated`, `recommendation`.
2. THE System SHALL classify each source as one of: `adopt`, `evaluate_further`,
   `defer`, `reject`, with a one-sentence rationale.
3. THE System SHALL explicitly cross-reference sources against the six imputation
   methods in `specs/data-imputation/design.md` §4.
4. THE System SHALL flag any source that supersedes an existing integration, with a
   migration-cost estimate.

### Requirement 2 — Deep evaluation of adopt-candidates

**User Story:** As a spec reviewer, I want a detailed evaluation of sources
recommended for adoption, so that I can approve or push back with concrete
information.

#### Acceptance Criteria

1. THE System SHALL, for each `adopt` or `evaluate_further` source, produce a
   per-source evaluation section covering: purpose, auth model, rate limits,
   record cadence, incremental/delta support, sample response, and the specific
   imputation/enrichment fields it unlocks.
2. THE System SHALL, where feasible, capture a real API response (or data file
   excerpt) as a fixture under
   `tests/fixtures/procurement_sources/<source_name>.json` for future implementation
   reference.
3. THE System SHALL measure coverage for each `adopt` candidate against a sample of
   recent SBIR awards (e.g., FY24 DoD SBIR Phase II) and report the match rate.

### Requirement 3 — Prerequisites and risk assessment

**User Story:** As an operator, I want each adoption recommendation to list its
prerequisites and risks, so that we don't commit to work that's blocked by
unresolved legal/auth issues.

#### Acceptance Criteria

1. THE System SHALL list, per `adopt` recommendation: credential requirements,
   legal/data-sharing review status, terms-of-service implications, and any
   dependencies on other in-flight specs.
2. THE System SHALL flag sources that require manual agency outreach or MOUs.
3. THE System SHALL estimate implementation effort in T-shirt size (S/M/L/XL) with
   brief justification.

### Requirement 4 — Integration with existing imputation spec

**User Story:** As the author of the data-imputation spec, I want concrete proposals
for which imputation methods should adopt which sources, so that the imputation
spec can be updated in one pass.

#### Acceptance Criteria

1. THE System SHALL, for each affected imputation method in
   `specs/data-imputation/design.md` §4, recommend whether to adopt an external source
   and produce a diff-ready edit proposal.
2. THE System SHALL explicitly address the two candidate upgrades already identified:
   - **SAM.gov Entity Extracts** for `identifiers.cross_award_backfill` (§4.2).
   - **SAM.gov Opportunities API** for the solicitation-linked methods (§4.3, §4.5,
     §4.8 `naics.solicitation_topic`), replacing the agency-page scraping plan in
     Task 4.3.
3. THE System SHALL evaluate **FSCPSC** and **PSC Selection Tool** as potential
   replacements for the homegrown `naics.abstract_nn` method.
4. THE System SHALL evaluate **DIIG CSIS Lookup Tables** as input to the
   NAICS hierarchical fallback and solicitation-topic crosswalks.

### Requirement 5 — Decision record and follow-on specs

**User Story:** As a project lead, I want the investigation to produce actionable
follow-on specs, so that adoption work is unambiguous and can be scheduled.

#### Acceptance Criteria

1. THE System SHALL produce a decision record
   (`specs/procurement-data-sources-eval/decisions.md`) listing each adopted source,
   its target imputation/enrichment method, and the follow-on spec name to be
   created.
2. THE System SHALL open one follow-on spec directory per adopted source (or per
   logical group of sources) with a requirements.md skeleton, ready for
   spec-implementer handoff.
3. THE System SHALL update `specs/data-imputation/design.md` and
   `specs/data-imputation/tasks.md` to reference adopted sources, if any.
