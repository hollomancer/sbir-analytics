# Dark-Majority Resolution — Tasks

Sequencing rationale in `requirements.md`. Effort tags: S (<half day), M (1–2 days), L (3+).

## Phase 1 — data on disk

- [ ] **T1 (S, WS3.2):** Add confidence scoring to any-class patent matches in
  `nano_dark_firm_liveness.py`: assignee-location state vs firm state, inventor names vs
  award PI names, name-token rarity. Output tier column; report high-confidence liveness
  rate as the new floor.
- [ ] **T2 (S, WS4):** Exclude `INSUFFICIENT_TIME` awards from indeterminate percentages;
  add Kaplan–Meier time-to-first-signal figure to the methodology doc; define annual
  re-observation job.

## Phase 2 — contract-level recovery

- [ ] **T3 (M, WS1):** Pull post-award USAspending contracts/grants for the 536 mislabeled
  awards' firms (compound award keys); classify follow-on evidence tiers with provenance.
- [ ] **T4 (S, WS1):** Precision spot-check ≥20 strong-tier reclassifications; write
  recovery summary into the findings report.

## Phase 3 — identity recovery

- [ ] **T5 (M, WS2):** Multi-key resolution of the 368 no-UEI firms against FPDS recipient
  names + SAM historical (name+state+PI, tiered confidence). Output
  `data/nano_no_uei_resolution.csv`.
- [ ] **T6 (S, WS2):** Route high-confidence resolutions through T3's contract-level
  classification.

## Phase 4 — external instruments

- [ ] **T7 (M, WS3.3):** State corporate registry status for dark firms, top ~5 states by
  cohort count (reuse UCC1 CA approach).
- [ ] **T8 (M, WS3.4):** Trademark-filing check for dark firms (normalized-name match +
  confidence, filing dates).
- [ ] **T9 (S, WS3.5):** Web/domain liveness sweep (tie-breaker signal only).

## Phase 5 — synthesis

- [ ] **T10 (M, cross-cutting):** Stratified capture-recapture bound on the true transition
  rate; document independence assumptions; replace "82.6% unknown" with the bounded interval.
- [ ] **T11 (S, WS3.6):** Stratified survey design + sample frame (50–100 firms) for the
  no-evidence residual. Design only; fielding is out of scope.
- [ ] **T12 (S):** Final findings-report pass reconciling all recovered populations;
  regenerate methodology doc.
