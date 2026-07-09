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
