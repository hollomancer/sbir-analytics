# Product 1 — Status-Denial Flags — Design

> **Status:** Spec / design. Tuning/labeling layer over existing assets.

## Approach
Reuse `phase_iii_retrospective_candidates` (`packages/sbir-analytics/.../phase_iii_candidates/`).
The novel work is (a) tightening the same-resolved-entity gate, (b) requiring FPDS 10Q absence as
the "status-denial" condition, (c) an undercount rollup, (d) a `disposition` column. No new scorer.

## Data flow
```
FPDS 10Q-coded contracts (M0b) ─┐
                                ├─ resolve_entities ─► same-entity join to Phase II priors
SBIR Phase II awards ───────────┘
        │  keep where _is_phase_iii_already_coded == False  (uncoded)
        ▼
  status-denial flags ─► data/derived/product1_status_denial_flags.parquet + review queue
        │  rollup by agency × FY
        ▼
  [L14] undercount estimate (coded vs uncoded, count + $)
```

## Components
1. **Entity gate** — `resolve_entities`; renamed/acquired firms still match (successor cases
   flagged where M&A signal exists; full successor resolution is a known gap).
2. **Coded/uncoded filter** — reuse `_is_phase_iii_already_coded` (`pairing.py:49`), which checks
   both the FPDS `research` field and the `sbir_phase` label.
3. **Undercount rollup** — per agency/FY counts + dollars; caveat that description-keyword recovery
   (~32% DoD) is a floor and the flag set is the residual.
4. **Model change** — add nullable `disposition` to `PhaseIIICandidate`
   (`sbir_etl/models/phase_iii_candidate.py`).

## Risks / notes
- Coverage is bounded by M0a (full contract population); until then flags cover the SBIR-keyword +
  10Q-pulled subset. State the coverage gap; it biases the undercount **down** (misses uncoded
  awards absent from the subset).
- Language discipline: `flags` only.

## Methodology corrections (join-key audit — see [audit-piid-grain.md](./audit-piid-grain.md))

Same auditability standard as the benchmark. Bug class: **silent joins/identities on non-unique FPDS
keys.** Instances found in the pre-fix Product 1 code and corrected on branch `claude/product1-piid-audit`:

1. **Bare-PIID `target_id`.** `_prepare_contracts` set `target_id` to a bare `piid` fallback, which
   fed the sha1 `_candidate_id`. FPDS order PIIDs recur ("0001" on all 600 SR3 records across 286
   firms), so distinct awards collided into one candidate identity. **Fix:** `award_key_series` — a
   precomputed unique award key, else a compound `(PIID + agency + parent-IDV PIID + parent-IDV
   agency)`; bare-PIID-only frames now **raise**.
2. **Wrong-grain coded status.** `_is_phase_iii_already_coded` ran per contract row; a coded award's
   non-coded mods survived as false flags. **Fix:** aggregate to award grain — **coded if ANY
   transaction carries SR3/ST3** — and collapse targets to one row per award key.
3. **Silent no-op exclusion.** The coded check reads a `research` column that USAspending data lacks,
   so on such frames the exclusion never fired and every coded Phase III became a flag. **Fix:** raise
   if no coding column is present.

**Quantified impact:** Product 1 currently emits nothing (contract source unmaterialized), so the
real before/after is a genuine null today and is gated post-M0a. The fixes make the first real run
correct-by-construction. Regression test: `tests/unit/phase_iii_candidates/test_award_key_grain.py`.
