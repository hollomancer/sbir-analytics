# Dark-Majority Resolution

**Problem:** 82.6% of the nanotech Phase II cohort (2,352 of 2,849 awards) has indeterminate
commercialization status. The findings report (`docs/nanotech_sbir_transition_findings.md`,
Finding 3) shows this "dark majority" is measurement failure more than proven failure — but
"indeterminate" is not one problem. The deficiency taxonomy splits it into four populations
that need four different treatments. This spec defines the treatments.

**Scope note:** Built and validated on the nanotech cohort; every workstream is
technology-agnostic and should reuse cleanly for other technology-area reports
(the PR #428 pipeline pattern).

**Prior art in this repo:** Phase III detection product line (contract-level analysis),
Form D multi-signal confidence scoring, EDGAR scan infrastructure,
`scripts/data/nano_dark_firm_liveness.py` (patent liveness bracket, WS3 step 1 — done),
UCC1 CA pilot (state-registry experience).

---

## WS1 — Reclassify the mislabeled (536 awards)

`NO_FPDS_CODING` (354) + `DATA_GAP_FPDS_NONDOD` (182): the firm appears in federal data;
only the FPDS Phase III flag is missing (GAO-24-106398 structural gap).

**Requirement:** For each of the 536 awards, classify post-award federal activity from
contract-level evidence rather than the Phase III flag: subsequent contracts/grants by the
same firm, agency continuity, competed-vs-sole-source, topic similarity to the Phase II
(existing transition-scoring features).

**Acceptance:**
- Every award carries a contract-level evidence tier (e.g., strong/weak/none) with
  provenance (contract IDs, join keys — compound award keys, not bare PIIDs).
- Reclassification summary states how many awards move out of "indeterminate."
- Precision spot-check on ≥20 strong-tier awards.

**Dependencies:** USAspending contract pulls for cohort firms (overlaps the Phase III
detection M0a critical path). Effort: medium.

## WS2 — Resolve identities (539 awards / 368 firms, no UEI)

`ENTITY_RESOLUTION_FAILURE`: the award-to-federal-systems join fails, not the firm.
Patent liveness already shows 51% of these firms exist in patent records under matchable
names — the identities are recoverable.

**Requirement:** Multi-key retroactive resolution: normalized name + state (+ address/PI
where present) against FPDS recipient names and SAM historical registrations; DUNS-era
crosswalks where available. Tiered confidence, same pattern as the Form D matcher.

**Acceptance:**
- `data/nano_no_uei_resolution.csv`: per firm, candidate UEI/recipient matches with
  confidence tier and matched keys.
- ≥ 30% of the 368 firms resolved at high confidence (target, not gate — report actual).
- High-confidence resolutions feed back into WS1-style contract-level classification.

**Effort:** medium.

## WS3 — Triage the procurement-dark (1,298 awards / 651 firms)

`FIRM_ACTIVITY_ABSENT`: genuinely invisible to procurement. Escalate through cheap public
instruments; reserve the expensive step (survey) for the residual.

1. **Patent liveness [DONE].** `nano_dark_firm_liveness.py` brackets provable post-award
   activity at 11% (B82-only floor) to 52% (any-class upper bound).
2. **Tighten the bracket.** Add confidence scoring to the any-class matches: state
   agreement (assignee location vs firm state), inventor-name ↔ PI-name overlap, name-token
   rarity. Acceptance: each any-class match tiered high/medium/low; report the
   high-confidence liveness rate as the new floor.
3. **State corporate registry status.** Start with the top ~5 states by cohort firm count
   (CA experience exists from the UCC1 pilot). Acceptance: active/dissolved/unknown status
   with retrieval date for ≥60% of dark firms.
4. **Trademark filings.** USPTO trademark data; a live product mark is
   commercialization-specific evidence (stronger than a patent for §638 purposes).
   Acceptance: per-firm trademark hits with filing dates, same normalized-name + confidence
   approach.
5. **Web/domain liveness.** Automated check (domain resolves, site mentions firm name).
   Weakest signal; tie-breaker only.
6. **Stratified survey design (50–100 firms)** for the residual, sampling within strata
   defined by steps 1–5 outcomes. Deliverable is the design + sample frame, not fielding.

**Acceptance (workstream):** every dark firm labeled
`{active-evidence, dissolved-evidence, no-evidence}` with source list and confidence;
the no-evidence residual counted and characterized.

## WS4 — Handle the censored (214 awards, `INSUFFICIENT_TIME`)

**Requirement:** Stop treating award-year ≥ 2023 awards as part of the dark majority.
Report time-to-first-signal as survival curves (Kaplan–Meier over the five channels) and
re-observe annually (scheduled job re-runs the signal pipeline as awards mature).

**Acceptance:** censored awards excluded from indeterminate percentages everywhere in the
report; survival curve figure generated; re-observation job defined (Dagster/cron).

**Effort:** small.

## Cross-cutting — bound what remains

With five semi-independent channels (FPDS contract-level, Form D, M&A, patents,
registries/trademarks), estimate the commercialized-but-undetected population via
stratified capture-recapture (stratify by agency/pathway; the channels' near-disjointness
violates naive independence, so document assumptions explicitly).

**Acceptance:** a bounded interval for the true transition rate with stated assumptions,
replacing "82.6% unknown" in the report's summary.

## Sequencing

1. WS3 step 2 (tighten patent bracket) + WS4 — cheap, data on disk.
2. WS1 (contract-level reclassification) — highest-certainty recovery; shares the M0a path.
3. WS2 (entity resolution) — feeds WS1.
4. WS3 steps 3–5 (registries, trademarks, web).
5. Capture-recapture bound, then WS3 step 6 (survey design) on the residual.
