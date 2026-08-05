# Phase III Undercount Extension — Tasks

> Builds on M0a + the 3-source capture-recapture. **Reuse, don't re-inline:** import the
> canonical `normalize_name` (`sbir_etl.utils.text_normalization`), the firm resolver
> (`resolve_firm_awards`, #481), the SAM self-label extractor (#485), and #467's fusion —
> pending the consolidation PR that lands the shared pieces on `main`. Log any place a
> helper had to be inlined because its home isn't merged yet, as consolidation debt.

## T0 — Reuse audit (before writing code)
Confirm which shared modules are importable on this branch (off `main`): core
`normalize_name` and #467 fusion are on `main`; the resolver / self-label extractor / coverage
data are on unmerged branches. List what must be imported vs temporarily vendored, and file it
against the consolidation PR so it's paid down, not duplicated silently.
→ verify: a short reuse table (module → home → importable now Y/N → plan).

## T1 — Generalize capture-recapture to the full Phase III frame
Lift `scripts/data/nano_capture_recapture.py` from the nanotech cohort to the DoD Phase III
frame, using M0a's coded/grey/dark pools as the base capture lists. Keep the estimator + CI.
→ verify: reproduces the ~1,543 [915–2,745] dark / 19–28% miss baseline on the existing lists.

## T2 — Add §638 self-labeled as a new contract-universe capture list
Materialize the §638 self-labeled notices (#485 `extract_phase3_selflabeled`, full sweep),
resolve to firms/awards, add as an independent capture list. Re-run capture-recapture. Report
the **tightened contract-coding undercount by agency** vs the 19–28% baseline. **Test list
independence** (self-labeled ⊄ description-coded — different detection mechanism).
→ verify: updated dark estimate + CI; per-agency miss-rate; independence checked and stated.

## T3 — Non-contract vehicle layer (separate denominator)
Quantify **subaward** and **grant** transitions (#485), relevance-filtered (SBIR-derivation
gate: tech-area + Phase-II proximity), as a **bounded, provisional** count by vehicle and
agency. **Do NOT fold into the contract-coding %** — a distinct population, reported separately.
→ verify: subaward + grant transition counts by vehicle/agency, with the provisional caveat and
  the relevance-filter definition; explicit that it is not summed into the contract undercount.

## T4 — Classifier precision/recall against the pooled ground truth
Pool the ground truth (293 hand-collected #481 + 66 self-labeled #485 + MDA-35 + component
harvest), dedupe to firm+award identity, and measure the coded Phase III set's **precision and
recall** at the **≥85% precision** operating point. Recall = the undercount, measured directly.
→ verify: precision/recall + CI; recall stated as the direct undercount; ≥85% precision gate.

## T5 — B3 memo
One page: contract-coding undercount (updated, by agency) + the separate non-contract vehicle
layer, with what's solid vs provisional, capture-recapture independence caveats, and the
classifier recall number. A clear answer to "how much undercount exists in Phase III coding."
→ verify: memo committed; contract layer and vehicle layer never conflated.

## Deferred (documented, not this PR)
- Full civilian-contract undercount (data-limited).
- Production ingestion / scheduling of the capture lists.
- The consolidation PR itself (shared ER toolkit) — a prerequisite tracked separately.
