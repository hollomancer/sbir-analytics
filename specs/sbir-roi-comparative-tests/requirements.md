# SBIR ROI Comparative Tests Requirements

> **Lifecycle status:** Active
> **Spec-file progress:** Complete for contract scaffolding; empirical runs remain gated.
> Anchors inventory questions **B3, C3, D3, and F3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `exploratory`

**Research question anchor:** D3 — taxpayer-return uncertainty and reconciliation
**Answers for:** policy analysts and SBIR program managers
**RQ complexity tier:** Inferential

## Done when

An analyst can validate four non-citable study manifests and one shared contract bundle.
The contracts separate causal evidence, descriptive evidence, and inference.
The contracts prevent patents, capital, or exits from becoming standalone taxpayer benefits.

## Background

Program-wide SBIR return cannot be identified from awardee outcomes alone.
Credible comparison requires mechanism-matched programs and explicit opportunity costs.
The repository needs frozen designs before it acquires data or selects results.

## Requirements

### Requirement 1 — Shared comparison contracts

**User story:** As a policy analyst, I want common registries, so that studies use consistent evidence rules.

#### Acceptance Criteria

1. THE System SHALL distinguish mechanism-matched comparators from context-only analogues.
2. THE System SHALL define operating, capital, licensing, exit, revenue, productivity, mission, spillover, and knowledge outcomes.
3. THE System SHALL label each attribution input as causal, descriptive, or inference.
4. THE System SHALL keep fiscal and domestic-social ledgers separate.
5. THE System SHALL reject patents as a standalone success measure.

### Requirement 2 — Four study manifests

**User story:** As an SBIR program manager, I want bounded study contracts, so that data work cannot outrun identification.

#### Acceptance Criteria

1. THE System SHALL define a marginal-award identification study.
2. THE System SHALL define NIH SBIR versus R01 Test Two.
3. THE System SHALL define NASA SBIR versus external research Test Two.
4. THE System SHALL define the Test Three social-return break-even study.
5. EACH manifest SHALL block materialization until its named inputs and design gates exist.

### Requirement 3 — Claim discipline

**User story:** As a policy analyst, I want failure rules, so that descriptive outcomes do not become causal claims.

#### Acceptance Criteria

1. THE System SHALL identify private capital and exits as validation signals.
2. THE System SHALL convert revenue into incremental value added before welfare use.
3. THE System SHALL define opportunity cost against a feasible federal alternative.
4. THE System SHALL prevent duplicate counting across fiscal and social ledgers.

## Dependencies

- Existing study-manifest validation — EXISTS
- Agency applicant scores and cutoff rules — BLOCKED
- NIH lifecycle outcomes and costs — BLOCKED
- NASA external research universe — BLOCKED
- Welfare benefit and cost ledgers — BLOCKED
