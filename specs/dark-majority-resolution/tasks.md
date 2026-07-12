# Dark-Majority Resolution — Tasks

Sequencing rationale in `requirements.md`. Effort tags: S (<half day), M (1–2 days), L (3+).

## Phase 1 — data on disk

- [x] **T1 (S, WS3.2):** Add confidence scoring to any-class patent matches in
  `nano_dark_firm_liveness.py`: assignee-location state vs firm state, inventor names vs
  award PI names, name-token rarity. Output tier column; report high-confidence liveness
  rate as the new floor.
  → Bracket collapsed: FIRM_ACTIVITY_ABSENT post-award liveness 328/651 (50%) at high
  confidence — 95% of high-tier matches inventor↔PI corroborated, 5% state-corroborated;
  no-UEI bucket 131/368 (36%). (Initial run under-counted state corroboration: SBIR.gov
  full state names vs USPS codes — fixed via STATE_TO_CODE normalization, found during
  the T8 spot-check.) Report Finding 3 updated to the single defensible number.
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

- [ ] **T7 (M, WS3.3) — DEFERRED (2026-07-12):** State corporate registry status for dark
  firms, top ~5 states by cohort count (reuse UCC1 CA approach). Deferred pending a
  sourcing decision (official state APIs vs aggregator vs manual pulls); note T10 showed
  this is the highest-value remaining instrument, since dissolution records are negative
  evidence and nothing else bounds the true rate from above.
- [x] **T8 (M, WS3.4):** Trademark-filing check for dark firms (normalized-name match +
  confidence, filing dates).
  → `scripts/data/nano_dark_firm_trademarks.py` over TRCFECO2/2023 (owner + case_file via
  the new `download_uspto.py --product-file` mode): FIRM_ACTIVITY_ABSENT — 51% own marks,
  43% registered, 35% filed post-award, 19% high-confidence; no-UEI — 48%/40%/32%/13%.
  Spot-check surfaced two defects fixed before reporting: registration_no '0000000' means
  never-registered, and the SBIR-vs-USPTO state format mismatch (which also silently
  suppressed state corroboration in T1 — both scripts fixed, T1 numbers refreshed).
- [ ] **T9 (S, WS3.5):** Web/domain liveness sweep (tie-breaker signal only).

## Phase 5 — synthesis

- [x] **T10 (M, cross-cutting):** Stratified capture-recapture bound on the true transition
  rate; document independence assumptions; replace "82.6% unknown" with the bounded interval.
  → `scripts/data/nano_capture_recapture.py`. Result deviates from the acceptance criterion,
  with cause documented: capture histories are singleton-dominated (287/31/6/1 firms by
  1/2/3/4 channels), WS-recovery channels target the complement of existing detection
  (structural zero overlap), and the Chao bound exceeds the cohort size — the multi-list
  model rejects the common-population premise. Reportable: floor 24.3% of firms / 28.1% of
  awards; NO defensible data-driven ceiling exists without negative evidence (T7/T11).
  Report updated (Policy #5, synthesis, methodological notes).
- [x] **T11 (S, WS3.6):** Stratified survey design + sample frame (50–100 firms) for the
  no-evidence residual. Design only; fielding is out of scope.
  → `survey-design.md` + `scripts/data/nano_survey_frame.py` (seed 20260712): 75 primaries
  across S1 active-evidence (20/317), S2 holder-only (20/111), S3 dark-core (35/223,
  oversampled) with 2× ranked backups. S1 doubles as validation of the patent-liveness
  instrument; confirmed dissolutions supply the first negative-evidence mass for T10.
- [x] **T12 (S):** Final findings-report pass reconciling all recovered populations;
  regenerate methodology doc.
  → Stale-number sweep clean (82.6% appears only as the flags-alone baseline, 27.5% only
  as the WS1-scoped step); methodology doc regenerates byte-stable. Cumulative outcome of
  the plan: indeterminate 82.6% → 71.9% (70.6% matured); every remaining dark firm carries
  instrument outcomes; ceiling awaits negative evidence (deferred T7 / survey fielding).

## Phase 6 — new channels and recall multipliers (scoped 2026-07-12)

- [ ] **T13 (M, WS5a):** Subaward (FSRS) evidence pull for dark-bucket firms — USAspending
  subaward records by sub-awardee UEI/name, post-Phase-II temporal filter, WS1 tier
  conventions. State FSRS threshold/under-reporting and FY2011+ coverage in outputs.
- [ ] **T14 (S–M, WS5b):** SAM.gov registration status for all UEI'd cohort firms
  (public extracts or Entity Management API; a SAM key exists in repo tooling).
  Output active vs lapsed-with-year; feed lapse years into WS4 survival framing.
- [x] **T15 (M, WS6a):** Build `data/processed/firm_aliases.csv` from owner_name_change
  (on disk), PatentsView assignee_id clusters (on disk), USAspending DBA/parent
  linkages, and — if programmatically available on ODP — patent assignment records.
  → Reconnaissance revised the sources: **patent assignments** (ECORSEXC, ODP-servable)
  are the rich source — 150 edges (110 namechg + 37 merger + 3 shared-UEI) across 119
  firms (e.g. microlab→magfusion, t j technologies→a123 systems, voltaix→air liquide).
  **assignee_id clusters are DEAD** (disambiguation already collapses variants: 0/293k
  sampled ids carry >1 name); **owner_name_change is a coded annotation**, not a name
  pair — deferred. Core logic is in `sbir_etl/utils/firm_aliases.py` (pure, 22 unit tests
  in `tests/unit/utils/test_firm_aliases.py`); driver `scripts/data/build_firm_alias_graph.py`.
  Self-edge filter drops 219 suffix-only false edges (ACME→ACME CORP).
- [x] **T16 (S–M, WS6b):** Alias-expanded re-runs of patent/trademark/USAspending
  matchers; alias matches require corroboration and carry alias_source provenance;
  report per-instrument recall delta.
  → `scripts/data/nano_alias_expanded_evidence.py`. 103 dark firms have ≥1 alias; recall
  delta = 11 firms negative under own name but active under a successor (WaveBand→Sierra
  Nevada, Boulder Ionics→CoorsTek, Microchip Biotechnologies→IntegenX, …), 3 with federal
  evidence under the new identity. Patent-assignment aliases are documentary (trusted);
  shared-UEI aliases only counted with independent evidence. Finding 3 + Policy #6 updated.
- [ ] **T17 (M, WS5c):** ClinicalTrials.gov + openFDA go-to-market check for the biomed
  slice (alias-expanded), name+state confidence tiers; report alongside trademarks.
- [ ] **T18 (S):** Integrate Phase 6 outcomes into the findings report and refresh the
  headline observable/indeterminate shares.
