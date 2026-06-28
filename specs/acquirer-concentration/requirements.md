# Requirements — Acquirer Concentration & Capital-Outcome Stratification

> **Status:** Not yet started. M&A event detection (PR #286), entity resolution, and
> Form D pipeline (PR #286) are live on `main`. CET classifier is live on `main`.
> PR #314 (Form D filer vs. non-filer outcome comparison) may partially address R2 —
> verify status before implementing.
> Anchors inventory question **F2** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F2 — acquirer-type concentration; Form D filer vs. non-filer outcome differences; SBIR-firm capital structure vs. NVCA Yearbook baseline
**Answers for:** entrepreneurial finance researchers, defense industrial base analysts, NVCA / Kauffman-style investment researchers
**Complexity tier:** Relational (Tier 2)

---

## Done when

> An entrepreneurial finance researcher can state: "Life-sciences consolidators
> (Bruker, Ligand, Thermo Fisher class) account for [X]% of SBIR-firm M&A exits;
> defense primes account for [Y]%; financial sponsors (PE/VC acquirers) account for
> [Z]%. Serial acquirers (3+ SBIR-firm targets) represent [N] firms and [K]% of
> total exit volume. Form D filers show [A]× higher transition rates and [B]× higher
> patent counts than non-filers, controlling for vintage, agency, and CET area."

---

## Introduction

M&A exit analysis for SBIR firms currently produces exit rates by funding agency (HHS
biotech ~9.3% vs. DoD defense ~5.8%, PR #286). This spec extends that analysis to
answer two F2 questions that require additional computation:

1. **Acquirer-type concentration** — who is acquiring SBIR firms, and is M&A activity
   dominated by a small number of serial acquirers or specific acquirer types?
2. **Form D filer vs. non-filer outcome stratification** — controlling for cohort
   vintage, awarding agency, and CET area, do firms that raise private capital perform
   differently on transition, patent, and exit outcomes?

These are distinct from the leverage ratio (F3) and the capital-event timeline (F1) —
they are about heterogeneity in the firm population, not the aggregate leverage number.

---

## User Stories

**As a defense industrial base analyst,** I want the acquirer-type breakdown for
SBIR-firm M&A exits, so that I can quantify how much of the SBIR-funded technology
base is being absorbed by defense primes vs. life-sciences consolidators vs. financial
sponsors — and flag whether serial acquirers are concentrating the exit market.

**As an entrepreneurial finance researcher,** I want Form D filers compared to
non-filers on transition, patent, and exit outcomes — controlling for vintage, agency,
and CET area — so that I can measure whether private capital co-investment is a signal
of firm quality or a driver of better commercialization outcomes.

---

## Requirements

### Requirement 1 — Acquirer-type classification and concentration

**User Story:** As a defense industrial base analyst, I want each SBIR-firm acquirer
classified by type (life-sciences consolidator, defense prime, financial sponsor,
strategic corporate, other) and seriality (number of prior SBIR-firm acquisitions),
so that I can quantify M&A market concentration.

#### Acceptance Criteria

1. THE System SHALL classify each acquirer in the M&A event database into one of the
   following types: **defense prime** (DoD prime contractors by revenue threshold);
   **life-sciences consolidator** (acquirers with ≥ 3 prior life-sciences SBIR targets);
   **financial sponsor** (PE/VC fund vehicle); **strategic corporate** (non-prime
   corporate acquirer); **other / unclassified**.
2. THE System SHALL identify **serial acquirers** as acquirers with ≥ 3 distinct SBIR-firm
   acquisition events in the data window, and report their cumulative target count and
   share of total SBIR exit volume.
3. THE System SHALL compute acquirer-type share of M&A exit events and exit dollar
   volume, broken out by SBIR funding agency (HHS vs. DoD) and CET area.
4. WHEN an acquirer appears under multiple names across events (name variations, parent
   subsidiary), THE System SHALL resolve to the ultimate parent entity using entity
   resolution before computing seriality.

### Requirement 2 — Form D filer vs. non-filer outcome stratification

**User Story:** As an entrepreneurial finance researcher, I want Form D filers compared
to non-filers on key outcomes, so that I can measure whether private capital participation
is associated with better commercialization outcomes after controlling for observable
firm characteristics.

#### Acceptance Criteria

1. THE System SHALL split Phase II awardees into two cohorts: **filers** (at least
   one HIGH-tier Form D match within 5 years of first Phase II award) and
   **non-filers** (no HIGH-tier Form D match in that window).
2. THE System SHALL compute the following outcomes for both cohorts, stratified by
   first-Phase-II fiscal year, awarding agency, and CET area:
   - Transition rate (Phase II → detectable Phase III, HIGH-band)
   - Patent count per firm (USPTO patents linked to the firm via entity resolution)
   - M&A exit rate within 15 years of first Phase II
3. THE System SHALL compute the filer-vs.-non-filer ratio for each outcome metric
   and report bootstrap 95% confidence intervals (1,000 iterations, firm-level).
4. WHEN a stratification cell contains fewer than 20 firms in either cohort, THE
   System SHALL suppress the comparison and note the suppression reason.
5. THE System SHALL note that this comparison is associative, not causal: Form D
   filing selection is correlated with unobserved firm quality. Causal identification
   would require an instrument (e.g., Howell [L11] DOE grant lottery approach).

### Requirement 3 — NVCA Yearbook capital-structure benchmark

**User Story:** As an entrepreneurial finance researcher, I want SBIR-firm capital
structure (deal size, round type, fill rate) compared against the NVCA Yearbook
cohort of comparable-stage VC-backed startups, so that I can characterize whether
SBIR firms raise private capital on terms comparable to non-SBIR VC-backed peers.

#### Acceptance Criteria

1. THE System SHALL compute median Form D offering size, total amount sold, fill rate
   (sold ÷ offered), and security type distribution (equity vs. debt vs. convertible)
   for the HIGH-tier SBIR-firm Form D cohort.
2. THE System SHALL produce a side-by-side table comparing these metrics against the
   published NVCA Yearbook [L25] figures for seed/early-stage startups in the same
   time window.
3. THE System SHALL note the comparison caveat: Form D includes all Reg D offerings,
   not only VC rounds — the SBIR cohort includes angel, seed, and non-VC institutional
   capital, which the NVCA Yearbook measures separately.
4. THE System SHALL stratify by funding agency (HHS / DoD / NSF / DOE) since capital
   structure differs materially across these populations (per PR #286 exit-rate findings).
