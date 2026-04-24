# Phase 3 Solicitation & Award Candidate Alerts — Requirements

Research-question anchors: **B2, B3, B4, E1, E6**, and the open evaluation in
**E5** ("Does the SAM.gov Opportunities API replace agency-page scraping?").
Narrows the Phase III undercount flagged as a threat-to-validity in
`docs/phase-transition-latency.md` §1.

## Background

Phase III is defined by the SBIR/STTR Policy Directive as work that "derives
from, extends, or completes" a prior Phase I or Phase II effort. It is
sole-source authorized, uncapped, and **coded inconsistently in FPDS**.
GAO-24-107036 [L14] and NASEM [L1][L3] both call out Phase III data as the
weakest link in SBIR outcome measurement; the existing
`validated_phase_iii_contracts` asset emits a `*.checks.json` audit whose
`agencies_with_zero_phase_iii` list quantifies the gap.

A "Phase 3 candidate" is not one thing. It is three things, with different
data sources, different precision expectations, and different audiences:

| Signal | Source | What it catches | Audience |
|---|---|---|---|
| **S1 — Retrospective Phase III reclassification** | FPDS / USAspending contracts already in the pipeline | Contracts fitting Phase III criteria but not coded (Element 10Q gap) | GAO / SBA oversight, research |
| **S2 — Directed / sole-source notice alerts** | SAM.gov Opportunities API (pre-solicitations, justifications, notices of intent, notices of award) | The statutorily typical Phase III path — agency directs sole-source to a prior awardee | Agency PMs, awardees |
| **S3 — Competitive solicitation follow-on candidates** | SAM.gov Opportunities + SBIR.gov solicitations | Open competitive solicitations topically adjacent to a firm's prior Phase I/II scope — not strictly Phase III, labeled as "follow-on candidates" | Awardees, commercialization analysts |

The three signals share scoring infrastructure (the same six transition
signals already proven at ≥85% precision in
`packages/sbir-ml/sbir_ml/transition/`) but differ in ingestion corpus,
cadence, and precision targets.

## Scope

### In scope

1. **SHALL** ingest SAM.gov Opportunities records on a scheduled cadence and
   normalize them into a single `opportunities.parquet` with stable
   identifiers, notice type, set-aside and competition codes, agency,
   sub-tier and buying office, NAICS, posted and response dates, and full
   description text.
2. **SHALL** produce `phase_iii_candidates.parquet` whose rows are tuples of
   `(prior_award, target, signal_class)`. Each row carries a
   `candidate_score ∈ [0,1]`, a single HIGH-vs-rest boolean flag (v1 keeps
   one threshold per class; multi-band can come later), and an
   `evidence_ref` pointer into an NDJSON bundle.
3. **SHALL** add two new signal methods to the existing `TransitionScorer`
   rather than create a new scorer class:
   - `score_topical_similarity` — cosine between prior-award and target
     text. v1 uses cheap features (NAICS + token-overlap + agency
     sub-tier); PaECTER embedding reuse is deferred (see non-goals).
   - `score_lineage_language` — regex/phrase match over target description
     for statutory Phase III language ("Phase III", "derives from",
     "extends", "completes", "prototype transition", "follow-on
     production") plus a narrow data-rights lineage vocabulary ("technical
     data package", "interface control document", "source code",
     "government purpose rights", "unlimited rights") — these phrases are
     not violations; they indicate the notice is in the Phase III
     neighborhood and a candidate worth surfacing.
4. **SHALL** emit candidates via a single parameterized Dagster asset
   factory that produces three materializations — one per signal class —
   sharing the scorer and writing to the same parquet (distinguished by
   `signal_class`). No per-signal-class asset module tree; no
   `CandidatePairGenerator` class — each signal's pair filter is a small
   module-level function.
5. **SHALL** write an evidence bundle (NDJSON) per candidate mirroring the
   format of `transitions_evidence.ndjson`.
6. **SHALL** enforce a precision backtest at release time (not as a Dagster
   asset check): a backtest script re-runs the scorer over DoD-coded
   Phase III contracts and fails CI when **S1 HIGH precision < 0.85**.
   S2 and S3 precision are tracked via a plain CSV audit log in
   `reports/phase_iii/audit/`; no parquet-backed ledger, no asset-check
   blocker on a human-driven process.
7. **SHOULD** make agency-continuity scoring hierarchical
   (agency → sub-tier → buying-office), using the finest granularity
   present. Same buying office is a markedly stronger S1 signal than same
   department.

### Out of scope (v1)

- **Delivery channels.** No email, Slack, webhook, or push notifications.
  Output is parquet + evidence NDJSON. Delivery is a follow-on spec once
  precision is proven.
- **Weekly digest / markdown report / review cards.** Deferred with
  delivery.
- **Triage action labels** (Monitor / PCR inquiry / letter-of-concern).
  Those are an SBA workflow concern, not a research-question concern.
- **`paecter_embeddings_opportunities` asset.** S3 v1 uses NAICS +
  token-overlap + agency-sub-tier-match pre-filters. Embeddings only
  re-enter v1.x if the cheap filter cannot hit 0.60 HIGH precision.
- **Per-signal-class YAML weight presets + Pydantic config tree.** v1
  ships weight constants in the asset module. YAML presets are earned
  after someone needs to tune a weight.
- **Feedback loop into `validated_phase_iii_contracts`.** No additive
  column, no env-var gate in v1. If a downstream consumer asks, we add
  the join then.
- **Direct agency-page scraping.** E5 evaluation; only if the
  Opportunities API proves insufficient.
- **Non-federal solicitations** (state, international).
- **Predictive modeling of Phase II completion likelihood** (that belongs
  in B4's spec, not this one).

## Requirements

1. **SHALL** integrate the SAM.gov Opportunities API with the
   parquet-first, API-fallback pattern established by the existing
   SAM.gov Entity Extracts integration (`docs/SAM_GOV_INTEGRATION.md`).
   Rate-limit and retry semantics mirror `SAMGovAPIClient`.
2. **SHALL** define an `Opportunity` Pydantic model with fields:
   `notice_id`, `notice_type` (pre-solicitation / solicitation /
   sources-sought / justification / award / sole-source), `agency`,
   `sub_tier`, `office`, `set_aside_code`, `competition_code`,
   `naics_code`, `psc_code`, `posted_date`, `response_deadline`,
   `description`, `awardee_uei` (nullable), and `sol_number`.
3. **SHALL** add `PhaseIIICandidate` Pydantic model with `candidate_id`,
   `signal_class` (S1/S2/S3), `prior_award_id`, `target_type`
   (fpds_contract / opportunity), `target_id`, `candidate_score`,
   `is_high_confidence` (bool), `evidence_ref`, and per-signal subscores.
4. **SHALL** hold the precision benchmark of `≥85%` for S1 HIGH. S1
   output is the input to a reclassification audit the research plan
   depends on; its precision gate is non-negotiable.
5. **SHALL** include agency and signal-class stratification in every
   summary output; civilian-agency coverage is the whole point of S1.
6. **SHALL** treat `notice_type IN {sole_source, justification,
   notice_of_intent, award}` as S2 inputs. The system alerts on both
   "this notice might be a Phase III" and "this contract just awarded
   might have been a Phase III".
7. **SHALL** label S3 output "follow-on candidate" in every column name,
   evidence field, and downstream query. A competitive solicitation is
   not statutory Phase III and must not be described as such.

## Gate condition

The spec is done when we can state:

> For FY [N], the pipeline identified [X] HIGH-confidence S1 candidates
> (Phase III contracts not coded as such in FPDS); a hand-audited 100-row
> sample shows [P]% true-positive rate (target ≥ 85%). During the
> observation window the pipeline surfaced [Y] S2 candidates and [Z] S3
> follow-on candidates, with evidence bundles in
> `data/processed/phase_iii_candidates/`. The
> `agencies_with_zero_phase_iii` list shrank by [Δ] agencies relative to
> the pre-S1 baseline.

## Dependencies

### Existing (reuse)

- `TransitionScorer` in
  `packages/sbir-ml/sbir_ml/transition/detection/scoring.py` — already
  config-driven; this spec adds two new scoring methods on the same
  class.
- CET classifier — supplies the CET alignment signal.
- Entity resolution cascade (`vendor_resolver.py`) — maps opportunity
  awardee UEIs to prior-award recipients.
- `SolicitationExtractor` and `Solicitation` model — reused for S3 where
  SBIR.gov solicitations are the right corpus.
- `validated_phase_ii_awards` — canonical prior-Phase-II population.
- `validated_phase_iii_contracts` — read-only dependency; v1 does not
  modify this asset.
- SAM.gov Entity client (`sbir_etl/enrichers/sam_gov/client.py`) —
  template for the new Opportunities client.

### New

- `sbir_etl/extractors/sam_gov_opportunities.py` — Opportunities API
  extractor.
- `sbir_etl/models/opportunity.py` and
  `sbir_etl/models/phase_iii_candidate.py`.
- `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/`
  — one asset factory module; three materializations; no nested
  module tree.
- Two new methods on `TransitionScorer` (`score_topical_similarity`,
  `score_lineage_language`). Signal-class weights live as constants in
  the asset module.
- `scripts/phase_iii_precision_backtest.py` — runs S1 backtest against
  DoD-coded Phase III and fails on < 0.85.
- `reports/phase_iii/audit/` — plain CSVs for hand-audit precision
  tracking.

## Non-goals clarification

This is a **candidate surfacing layer**, not:

- A replacement for the existing transition detection system (that
  answers retrospective "did X commercialize?"; this answers
  forward-looking "is Y likely a Phase III?" and "was Z mis-coded?").
- A compliance / adjudication system. Labels are descriptive
  ("follow-on candidate"), never prescriptive (no "violation detected",
  no "letter of concern").
- A delivery mechanism. Output is files; notification is deferred.
