# SBIR M&A Dated Signal Study — Requirements

> **Lifecycle status:** Active pre-run protocol. This is a new, dated study;
> it does not reproduce the unrecoverable April 2026 analysis.
> **Spec-file progress:** Pre-run documentation complete; source acquisition,
> materialization, and analysis are deliberately blocked.
> Anchors inventory question **F1 — M&A exit rate** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Target epistemic tier:** `exploratory`

**Research question anchor:** F1 — what dated, observed M&A signal prevalence is
available in a newly defined SBIR firm frame?
**Answers for:** SBIR program managers and entrepreneurial-finance researchers.
**RQ complexity tier:** Descriptive (not an exit-rate, causal, agency-comparison,
or survival estimand).

---

## Done when

An analyst has a pre-run protocol for one explicitly dated M&A *signal* study,
including a fixed planned cutoff of **2026-08-29 UTC**, a source-acquisition
decision gate, an identity and validation plan, and an explicit path to an
evidence-tier study if any numerical claim is proposed externally. No result,
rate, or April-result reproduction is produced by this spec.

## Background

The historic April award denominator and source snapshot cannot be recovered.
Consequently, the previously quoted aggregate result cannot be reproduced,
validated, or reused as a result of this study. F1 currently records M&A
figures only as dated research notes, not inventory Status or citable claims.
This protocol preserves a fresh starting point without implying continuity with
the historic output.

## Glossary

- **Signal:** a sourced observation suggestive of an ownership-change event; it
  is not, without validation, a distinct acquisition, deal, transaction date,
  exit, or firm outcome.
- **Planned cutoff:** 2026-08-29 23:59:59 UTC. It defines the intended source
  observation boundary after sources are acquired and frozen; it does not say
  that any source was queried on that date.

---

## Requirements

### Requirement 1 — Explicitly new dated study

**User story:** As an SBIR program manager, I want the study boundary recorded
before data work begins, so that a later observed-signal result cannot be
mistaken for a reproduction of an unrecoverable historic analysis.

#### Acceptance Criteria

1. THE protocol SHALL name 2026-08-29 UTC as its planned as-of cutoff.
2. THE protocol SHALL state that April 2026 figures, denominator, inputs, and
   historical aggregate totals are not inputs, benchmarks, or reproduction
   targets for this study.
3. THE protocol SHALL label its current work and notebook `exploratory` and
   non-citable, and SHALL keep its materialization gate closed.

### Requirement 2 — Conditional source and cohort protocol

**User story:** As an entrepreneurial-finance researcher, I want a proposed
source and cohort contract before collection, so that later results have a
reviewable denominator and observation boundary.

#### Acceptance Criteria

1. BEFORE acquisition is separately authorized, THE study SHALL perform no
   network call, source download, local-source substitution, or analysis run.
2. IF acquisition is authorized, THEN the execution amendment SHALL name the
   reviewed SBIR firm-frame source, each outcome-signal source, license/privacy
   review, retrieval timestamps, cutoff handling, and hashes before counting.
3. IF an eligible source cannot establish coverage through the planned cutoff,
   THEN the study SHALL remain unmaterialized rather than silently move the
   cutoff or mix vintages.
4. THE protocol SHALL use one prospective firm-frame identity policy and retain
   aliases, source record identifiers, and match rationale for every candidate;
   it SHALL not treat normalized names alone as validated firms.

### Requirement 3 — Validation before a numerical claim

**User story:** As a policy analyst, I want a validation plan, so that an
observed signal count is not reported as an acquisition or exit rate.

#### Acceptance Criteria

1. IF a dated descriptive count is proposed, THEN the run SHALL preserve a
   candidate-level audit table, exclusion ledger, source provenance, and
   duplicate/deal-resolution policy before aggregation.
2. IF any externally reportable numerical claim is proposed, THEN an explicit
   evidence-tier promotion SHALL first freeze the design at a content hash,
   pin all inputs with SHA-256/size/row-count manifests, add blocking
   materialization checks, and declare the estimand and falsification limits.
3. BEFORE a claim calls a signal an acquisition, exit, rate, or prevalence,
   independent blinded human adjudication and documented disagreement resolution
   SHALL validate the sampled or full claimed population as appropriate to the
   estimand.
4. THE protocol SHALL retain `citable: false` treatment until a study manifest
   reaches `citable` after the required evidence and human review.

### Requirement 4 — Scope boundary

**User story:** As a pipeline engineer, I want a bounded protocol, so that a
lost historical snapshot does not broaden into a new discovery system.

#### Acceptance Criteria

1. THE study SHALL NOT implement discovery, LLM extraction, search backends,
   vintage adjustment or survival analysis, external comparators, agency
   stratification, or causal claims.
2. THE study SHALL NOT alter historic M&A specs, reports, artifacts, or their
   stated limitations.
3. THE study SHALL NOT use a live Dagster materialization or generate a public
   dataset under this pre-run slice.

---

## Dependencies

- `specs/sbir-ma-match-rate-by-fy/` — EXISTS; historical diagnostic only and
  not a reproduction source.
- `scripts/data/sbir_ma_signal_counts_by_fy.py` — EXISTS; a fail-closed
  prospective signal-count utility, usable only after a separately reviewed
  source contract is supplied.
- Human source/privacy/license review and blinded adjudication — BLOCKED;
  required before any externally reportable numerical claim.
