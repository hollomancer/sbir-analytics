# Requirements — Form D Private Capital Pipeline

> **Status:** Implemented on `main`. PR #286 merged. Methodology commit `f65abb89`.
> Canonical analysis: [`docs/research/sbir-form-d-fundraising-analysis.md`](../../docs/research/sbir-form-d-fundraising-analysis.md).
> Supports inventory questions **F1** and **F3** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** F1 (Form D fundraising profile of SBIR awardees), F3 (private-to-SBIR leverage ratio)
**Answers for:** entrepreneurial finance researchers, defense industrial base analysts
**Complexity tier:** Descriptive (Tier 1) / Inferential (Tier 3)

---

## Done when

> An entrepreneurial finance researcher can state: "3,640 high-confidence SBIR-firm
> Form D matches (PI name score ≥ 0.7 OR ZIP match). Private-to-SBIR leverage ratio:
> $1.82x (95% bootstrap CI [1.65, 2.02]) using total SBIR program spending as the
> denominator; $9.48x [8.26, 10.85] per matched firm. Two-signal tiering documented
> in `docs/research/sbir-form-d-fundraising-analysis.md`."

---

## Introduction

This pipeline matches SBIR awardees to their SEC Form D (Regulation D) private-placement
filings and computes the private-to-SBIR leverage ratio — the private capital raised per
dollar of SBIR funding received. It is the private-capital mirror to NASEM's 4:1
DoD-contract leverage ratio.

**Matching methodology:** Company name fuzzy matching with two independent confirmation
signals — PI-to-Form-D-executive name score (≥ 0.7 = high) and ZIP code overlap. Either
signal alone qualifies a match as high-confidence. State overlap only = medium confidence.
Pooled Investment Fund vehicles and other structurally incompatible industry groups are
excluded.

**Key findings (methodology commit `f65abb89`):**
- 3,640 high-confidence matches across 219K SBIR awards
- High-tier leverage: $1.82x [1.65, 2.02] (total-program denominator)
- Per-firm leverage: $9.48x [8.26, 10.85] (matched-firm denominator)
- HHS/NIH companies use ZIP matching as the primary confirmation signal (PI often
  doesn't appear as a Form D officer)

---

## User Stories

**As an entrepreneurial finance researcher,** I want SBIR awardees matched to their
SEC Form D private-placement filings, so that I can compute private-to-SBIR leverage
ratios by agency, vintage, and firm size and benchmark them against the NVCA Yearbook
cohort.

**As a defense industrial base analyst,** I want Form D matches broken out by awarding
agency and CET area, so that I can identify which technology domains attract the highest
private co-investment alongside federal SBIR funding and flag areas where private capital
is absent.

---

## Requirements

### Requirement 1 — SBIR-to-Form-D matching

**User Story:** As an entrepreneurial finance researcher, I want SBIR awardee records
matched to Form D filings using a two-signal confidence model, so that matches are
high-precision without unnecessarily excluding companies where PI names don't appear
on SEC filings (e.g., HHS/NIH academic PIs).

#### Acceptance Criteria

1. THE System SHALL match SBIR companies to Form D filings using company name fuzzy
   matching as the primary filter.
2. THE System SHALL assign confidence tier `HIGH` when person_score ≥ 0.7 OR the
   SBIR ZIP code matches the Form D issuer ZIP code.
3. THE System SHALL assign confidence tier `MEDIUM` when neither person nor address
   matches but the SBIR state matches the Form D state.
4. THE System SHALL assign confidence tier `LOW` for all remaining name matches and
   exclude the LOW tier from leverage ratio computation.
5. THE System SHALL exclude Form D filings in structurally incompatible industry groups
   (Pooled Investment Fund, Insurance, Restaurants, Retailing, and related categories)
   before computing leverage ratios.

### Requirement 2 — Leverage ratio computation

**User Story:** As an entrepreneurial finance researcher, I want private-to-SBIR
leverage ratios computed at both the program level and the per-matched-firm level,
so that both interpretations (program-wide ROI framing and per-firm leverage framing)
are available for citation.

#### Acceptance Criteria

1. THE System SHALL compute the program-level leverage ratio as:
   sum(Form D `totalAmountSold` for HIGH-tier matches) ÷ sum(SBIR `Award Amount`)
   across the full SBIR award universe.
2. THE System SHALL compute the per-firm leverage ratio as:
   sum(Form D `totalAmountSold` for HIGH-tier matches) ÷ sum(SBIR `Award Amount`
   for firms with at least one HIGH-tier Form D match).
3. THE System SHALL compute bootstrap confidence intervals (≥ 1,000 iterations,
   firm-level percentile bootstrap) for both ratio variants.
4. THE System SHALL stratify leverage ratios by awarding agency, first-award fiscal
   year, and CET area when sample sizes permit (minimum cell size 10 firms).

### Requirement 3 — Capital-event timeline integration

**User Story:** As a defense industrial base analyst, I want Form D events on the
unified capital-event timeline alongside federal awards, M&A events, and patent grants,
so that I can read a firm's full capital history in one query.

#### Acceptance Criteria

1. THE System SHALL load each HIGH-tier Form D match as a `RAISED` or
   `PRIVATE_PLACEMENT` event node in the Neo4j graph, linked to the matched
   `Organization` node.
2. THE System SHALL include `offering_date`, `total_amount_sold`, `security_type`,
   `confidence_tier`, and `cik` on each event node.
3. THE System SHALL support incremental updates: re-running the pipeline SHALL add
   new Form D filings without duplicating existing events.
