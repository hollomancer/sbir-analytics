# Dark-Majority Resolution — Tasks

Sequencing rationale in `requirements.md`. Effort tags: S (<half day), M (1–2 days), L (3+).

## Phase 1 — data on disk

- [x] **T1 (S, WS3.2):** Add confidence scoring to any-class patent matches in
  `nano_dark_firm_liveness.py`: assignee-location state vs firm state, inventor names vs
  award PI names, name-token rarity. Output tier column; report high-confidence liveness
  rate as the new floor.
  → Bracket collapsed: FIRM_ACTIVITY_ABSENT post-award liveness 317/651 (49%) at high
  confidence — 100% of high-tier matches are inventor↔PI corroborated; no-UEI bucket
  126/368 (34%). Report Finding 3 updated to the single defensible number.
- [x] **T2 (S, WS4):** Exclude `INSUFFICIENT_TIME` awards from indeterminate percentages;
  add Kaplan–Meier time-to-first-signal figure to the methodology doc; define annual
  re-observation job.
  → `scripts/data/nano_survival_analysis.py` → `data/analysis/nano_time_to_signal_km.png`
  (dateable channels; 71% of first signals within 2y of Phase II end; ~30% after year 2).
  Matured-basis indeterminate (71.2%) added to report Summary; INSUFFICIENT_TIME threshold
  in `build_nano_cohort.py` is now dynamic (`date.today().year - 3`).
  **Re-observation runbook (annual):**
  1. `python scripts/data/build_nano_cohort.py` (threshold advances automatically)
  2. `python scripts/data/nano_form_d_temporal.py`
  3. `python scripts/data/nano_ws1_contract_evidence.py --refresh`
  4. `python scripts/data/nano_dark_firm_liveness.py` (after refreshing PatentsView tables
     via `download_uspto.py --local`)
  5. `python scripts/data/nano_survival_analysis.py` (bump CUTOFF)

## Phase 2 — contract-level recovery

- [x] **T3 (M, WS1):** Pull post-award USAspending contracts/grants for the 536 mislabeled
  awards' firms (compound award keys); classify follow-on evidence tiers with provenance.
  → `scripts/data/nano_ws1_contract_evidence.py` / `data/nano_ws1_contract_evidence.csv`:
  strong 301 (56%), moderate 159 (30%), weak 72 (13%), none 4 (all 2024+ P2 ends).
- [x] **T4 (S, WS1):** Precision spot-check ≥20 strong-tier reclassifications; write
  recovery summary into the findings report.
  → First spot-check caught 3 classification defects (Phase-III-mention false positives,
  unmarked later-SBIR inflation, $500 de-minimis); fixed via P1/P2-text precedence,
  SBIR.gov ID-join exclusion, $25K floor. Re-check clean. Report updated (Finding 4):
  combined observable 17.4% → 27.5%, indeterminate 82.6% → 72.5%.

## Phase 3 — identity recovery

- [x] **T5 (M, WS2):** Multi-key resolution of the 368 no-UEI firms against FPDS recipient
  names + SAM historical (name+state+PI, tiered confidence). Output
  `data/nano_no_uei_resolution.csv`.
  → `scripts/data/nano_ws2_resolve_no_uei.py`: name search against USAspending recipients
  with exact normalized-name equality resolves 157/368 firms (43%; 156 single-UEI high
  confidence). The 57% unresolved have no post-FY2008 footprint under any matching name.
  (SAM historical and state/PI keys not needed at this precision; revisit if fuzzy
  matching is ever added.)
- [x] **T6 (S, WS2):** Route high-confidence resolutions through T3's contract-level
  classification.
  → Done inside the WS2 script (reuses the WS1 classifier): 247 awards of resolved firms →
  strong 21, moderate 79, weak 40, none 107. Report updated: observable 27.5% → 28.1%,
  indeterminate 71.9% (70.6% matured); Finding 3's "permanently opaque" claim corrected;
  Policy #3 now cites the 43% recovery as the floor for SBA UEI backfill.

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
