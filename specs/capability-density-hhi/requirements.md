# Requirements — Capability Density & HHI Concentration Map

> **Status:** Not yet started. Dependencies (CET classifier, entity resolution) are live on `main`.
> Anchors inventory questions **A1** (cap/vuln: A-CP1/A-CP2/A-CP3, A-CP7) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** A1 — capability density and choke-point concentration map per CET area (A-CP1 concentration, A-CP2 supplier-base thickness, A-CP3 geographic distribution, A-CP7 new-entrant vs. repeat-winner mix)
**Answers for:** DoD acquisition leadership, OSTP, congressional defense committees, CSIS-style industrial-base analysts
**Complexity tier:** Descriptive (Tier 1)

---

## Done when

> A DoD acquisition analyst can state: "For each of the 21 NSTC-2025Q1 CET areas, I
> have distinct awardee counts, total award volume, awardee HHI, and geographic
> distribution (state + congressional district). HHI ≥ 2,500 flags a concentrated
> area; HHI inverted is the choke-point concentration score. New-entrant share (first-time
> winners as a percent of total awardees in the period) is computed per area. The GAO
> program-wide HHI baseline of ~11 is the comparison floor. Outputs are in
> `reports/capability-density/` as both Parquet and markdown."

---

## Introduction

SBIR/STTR award data can answer the "capability" side of the industrial-base question
well: where are domestic suppliers active, how concentrated is each CET area, and how
thin is the supplier base? This spec computes those metrics systematically for all 21
CET areas in the canonical `config/cet/taxonomy.yaml` spine.

The core output is an **awardee HHI per CET area**: H = Σ(awardee_share²) × 10,000.
A high HHI (≥ 2,500 by DoJ merger guidelines) signals a concentrated, potentially
fragile supplier base. The HHI is the capability density metric read forward and the
choke-point concentration score read backward — the A1 HHI inverted.

Geographic narrowness (A-CP3) and new-entrant vs. repeat-winner mix (A-CP7) are
computed from the same CET-partitioned award data and share the same Dagster asset
group.

---

## User Stories

**As a DoD acquisition analyst preparing a briefing for the armed-services committees,**
I want awardee HHI and distinct supplier counts per CET area, so that I can identify
which technology domains have thin or concentrated supplier bases and flag areas where
a single-firm acquisition or exit would remove a capability with no in-program substitute.

**As an SBIR program manager at DoD,** I want the new-entrant share (first-time winners)
per CET area and year, so that I can identify technology domains where the entrant
pipeline is healthy vs. domains where repeat winners crowd out new suppliers.

---

## Requirements

### Requirement 1 — Awardee HHI per CET area

**User Story:** As a DoD acquisition analyst, I want awardee concentration measured
via HHI for each CET area, so that I can rank areas by supplier-base fragility and
identify sole- or dominant-supplier clusters.

#### Acceptance Criteria

1. THE System SHALL compute awardee HHI per CET area as Σ(each_awardee_share²) × 10,000,
   where share is computed on award dollars within the area and measurement period.
2. THE System SHALL flag areas with HHI ≥ 2,500 as **concentrated** and HHI 1,500–2,499
   as **moderately concentrated**, following DoJ merger-guideline thresholds.
3. THE System SHALL also report distinct awardee count and top-3 awardee share per area,
   as the HHI alone does not identify which firms dominate.
4. WHEN a CET area has fewer than 5 distinct awardees, THE System SHALL flag it
   **thin** regardless of HHI, and report the exact count.
5. THE System SHALL support a configurable measurement period (default: rolling 5-year
   trailing window) so that trend comparisons are reproducible.

### Requirement 2 — Geographic distribution (A-CP3)

**User Story:** As a DoD acquisition analyst, I want the geographic distribution of
awardees per CET area (state + congressional district), so that I can identify areas
where supplier-base concentration coincides with geographic concentration — the
combined fragility case.

#### Acceptance Criteria

1. THE System SHALL compute the share of awardees and award dollars per CET area that
   are located in each state and congressional district.
2. THE System SHALL flag CET areas where ≥ 50% of award dollars are concentrated in
   a single state as **geographically narrow**.
3. THE System SHALL use `sbir_etl/enrichers/congressional_district_resolver.py` for
   district assignment.
4. THE System SHALL emit results in the same report format as Requirement 1, with
   state and district breakdowns as a child table.

### Requirement 3 — New-entrant vs. repeat-winner mix (A-CP7)

**User Story:** As an SBIR program manager, I want first-time vs. repeat winner share
per CET area, so that I can identify technology domains where the entrant pipeline has
dried up — an early warning that the supplier base is aging without renewal.

#### Acceptance Criteria

1. THE System SHALL classify each awardee-year observation as **first-time** (no prior
   SBIR award in any CET area) or **repeat** (≥ 1 prior award).
2. THE System SHALL compute first-time share (first-time awardee count ÷ total awardees)
   per CET area per fiscal year.
3. THE System SHALL emit a time series of first-time share per CET area covering the
   full data window, to surface trend direction.
4. WHEN first-time share in a CET area falls below 15% for three consecutive fiscal
   years, THE System SHALL flag that area as **entrant-pipeline depleted**.

### Requirement 4 — Report output

**User Story:** As a DoD acquisition analyst, I want concentration metrics in both
machine-readable and human-readable form, so that the same data feeds downstream
Dagster assets and also appears in briefing-ready tables.

#### Acceptance Criteria

1. THE System SHALL emit per-CET-area concentration metrics to
   `reports/capability-density/capability_density_<period>.parquet`.
2. THE System SHALL emit a markdown summary to
   `reports/capability-density/capability_density_<period>.md` containing an
   HHI-ranked table, concentrated/thin flags, and geographic-narrowness flags.
3. THE System SHALL produce a Dagster asset (`capability_density_report`) in the
   `industrial_base` asset group, materialized after CET classification succeeds.
