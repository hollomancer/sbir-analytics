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

- [x] **T20 (S, addendum, 2026-07-12):** Subaward leverage analysis — post-award
  subcontract dollar volume against cumulative SBIR investment for the 103 strong-tier
  WS5a firms, same framing as Finding 2's acquisition-leverage table (methodology
  matched exactly: cumulative SBIR $ = all-phases-all-years Award Amount sum).
  → `scripts/data/nano_subaward_leverage.py`. $3.2B aggregate volume (dominated by two
  large active engineering firms, Foster-Miller and Technology Service Corp — median
  firm is $1.4M, the representative figure). Median leverage 0.18x; 19/103 (18%) firms
  show subaward $ exceeding cumulative SBIR investment. 4 firms already known from
  Finding 2's confirmed acquisitions (incl. Physical Optics) flagged and excluded from
  "newly characterized" framing. Report gets a new What-This-Says conclusion (#6, third
  commercialization track: prime-supplier absorption); conclusion #2 rewritten around
  the tiered disappearance reframe; conclusion #3 extended with the WaveBand/Sierra
  Nevada private-acquirer blind-spot confirmation (verified against sec_edgar_scan.jsonl,
  enriched_sbir_ma_events.jsonl, and the Finding 2 prime registry — invisible to all
  three). Six conclusions total (was five).

- [x] **T21 (S, addendum, 2026-07-12, branch claude/nanotech-maintenance-fee-lapses):**
  Patent maintenance-fee lapse check — the first weak-negative instrument in the plan
  (every prior WS3/5/6 channel is a positive detector that can only raise the floor).
  → `scripts/data/nano_dark_firm_maintenance_lapses.py`, USPTO PTMNFEE2 (single latest
  cumulative snapshot, 27M event records streamed, fixed-width format verified byte-exact
  against a live sample before parsing). Scoped to the 582 dark firms already matched to
  patents at high confidence. Result is genuinely humbling, reported as such: 89 firms
  show ≥80% of their fee-eligible patents lapsed, but 81% of those (72) are contradicted
  by evidence elsewhere — letting old patents lapse is routine for otherwise-active firms,
  not a dormancy signal by itself. Threshold checked at 90%/100%, doesn't materially
  change the contradiction rate. The residue — 17 firms (19%) with a fully-lapsed
  portfolio AND no other signal anywhere — is real but modest corroboration, explicitly
  NOT counted toward the illuminated/dark tally (it supplies no positive evidence); its
  use is ranking the T11 survey's priority stratum, not moving the headline percentages.
  Report: new Finding 3 paragraph, methodological note, and a sentence in the "measurement
  lesson" closing paragraph. Opened as an isolated branch/PR per user request, based on
  the tip of claude/nanotech-sbir-analysis (PR #428) so the shared liveness/alias
  infrastructure is available without re-deriving it.

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
  Report updated (Policy #6 [renumbered from #5 in the 2026-07-12 policy-point insertion], synthesis, methodological notes).
- [x] **T11 (S, WS3.6):** Stratified survey design + sample frame (50–100 firms) for the
  no-evidence residual. Design only; fielding is out of scope.
  → `survey-design.md` + `scripts/data/nano_survey_frame.py` (seed 20260712): 75 primaries
  across S1 active-evidence (20/317), S2 holder-only (20/111), S3 dark-core (35/223,
  oversampled) with 2× ranked backups. S1 doubles as validation of the patent-liveness
  instrument; confirmed dissolutions supply the first negative-evidence mass for T10.
- [x] **T19 (S, addendum, 2026-07-12):** Re-run T10's capture-recapture within the
  1,019-firm dark population using the WS5/WS6 secondary channels (patent, trademark,
  alias, subaward; sector excluded — 206-firm subset only), separately from the
  cohort-wide five-channel pass. Result: well-behaved (Chao ≈ 81% vs 59% observed),
  contrasting with the cohort-wide self-rejection — real co-occurrence (38% of detected
  firms hit by ≥2 channels) among the secondary instruments, evidence of a genuine
  still-active subpopulation distinct from the residual no instrument here reaches.
  Also added: Summary disambiguation note (the 71.9%/28.1% award-level metric and the
  66% firm-level "any evidence" metric answer different questions and are not merged —
  sized the gap at ~38 points to make the distinction concrete); new Policy point on
  subcontract-based transitions being structurally invisible by design (renumbered
  policy list 1-7 → 1-8); Policy #3 cross-referenced with the alias/rename finding.

- [x] **T12 (S):** Final findings-report pass reconciling all recovered populations;
  regenerate methodology doc.
  → Stale-number sweep clean (82.6% appears only as the flags-alone baseline, 27.5% only
  as the WS1-scoped step); methodology doc regenerates byte-stable. Cumulative outcome of
  the plan: indeterminate 82.6% → 71.9% (70.6% matured); every remaining dark firm carries
  instrument outcomes; ceiling awaits negative evidence (deferred T7 / survey fielding).

## Phase 6 — new channels and recall multipliers (scoped 2026-07-12)

- [x] **T13 (M, WS5a):** Subaward (FSRS) evidence pull for dark-bucket firms — USAspending
  subaward records by sub-awardee UEI/name, post-Phase-II temporal filter, WS1 tier
  conventions. State FSRS threshold/under-reporting and FY2011+ coverage in outputs.
  → `scripts/data/nano_ws5a_subawards.py`. 117/651 (18%) disappeared firms show a
  post-award subaward (96 strong); 22 net-new beyond patent+trademark+alias — the
  largest single marginal contribution of any WS3/5/6 instrument — including firms
  subcontracting directly to Northrop Grumman, Lockheed Martin, and SRI International.
  Two None-slicing bugs caught and fixed in the API-field formatting before reporting.
- [ ] **T14 (S–M, WS5b) — BLOCKED (2026-07-12):** SAM.gov registration status for all
  UEI'd cohort firms (public extracts or Entity Management API; a SAM key exists in repo
  tooling). Output active vs lapsed-with-year; feed lapse years into WS4 survival framing.
  → `scripts/data/nano_ws5b_sam_status.py` implemented, modeled on `download_sam_gov.py`'s
  key-resolution pattern; exits 2 with a clear message when `SAM_GOV_API_KEY` is absent
  (this analysis has no key — SAM.gov keys are tied to a login, cannot self-issue). Ready
  to run once one is supplied; no partial output was written.
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
  shared-UEI aliases only counted with independent evidence. Finding 3 + Policy #7 [renumbered from #6] updated.
- [x] **T17 (M, WS5c):** ClinicalTrials.gov + openFDA go-to-market check for the biomed
  slice (alias-expanded), name+state confidence tiers; report alongside trademarks.
  → `scripts/data/nano_ws5c_sector_registries.py`, keyless APIs. 33/206 HHS-funded dark
  firms show a lead-sponsor trial (24) or 510(k) clearance (12); 7 net-new beyond
  patent+trademark (Imbed Biosciences' Microlyte, EraGen's FLEXMAP 3D, etc.).
- [x] **T18 (S):** Integrate Phase 6 outcomes into the findings report and refresh the
  headline observable/indeterminate shares.
  → Finding 3 gains WS5a/WS5c paragraphs and a combined-instrument tally; Summary,
  synthesis conclusion 2, and Policy #6 [renumbered from #5] updated to the stacked result: **427/651 (66%)**
  of "disappeared" firms now show post-award activity evidence across patents,
  trademarks, subawards, aliases, and sector registries (up from 50% patent-only);
  no-UEI bucket 183/368 (50%). Methodological notes extended with all four new
  instruments' caveats. Stale-number sweep clean.

---

## Area parameterization (post tech-area-transition-report v1)

**Prerequisite:** enriched `data/reports/<area_id>/cohort_keyword.csv` with
`deficiency_class` and `sig_*` (from `build_tech_area_cohort.py` +
`sbir_etl.utils.transition_signals`).

**Path convention:** area artifacts under `data/reports/<area_id>/`
(`form_d_post_phase2.csv`, `ws1_contract_evidence.csv`, `dark_firm_liveness.csv`, …).
Plots under `analysis/`. Global bulk inputs and `data/api_cache/` unchanged.
Helper: `sbir_etl.utils.transition_report_paths.ReportPaths`.

**`nano_*` policy:** add `--area` / `--legacy`. Unflagged invocation keeps
`data/nano_*.csv` for nanotech regression. New areas never write `data/nano_*`.

### Phases

| Phase | Work | Status |
|---|---|---|
| 0 | Signal enrichment on area cohort | **done** (T11–T12) |
| 1 | Path helper + migrate `form_d_temporal` as reference | **done** (T13) |
| 2 | WS1, WS2, liveness (B82 optional), trademarks, survival | open |
| 3 | firm alias graph, WS5a, WS6b; WS5c gated by YAML `sector_registries` | open |
| 4 | capture-recapture, survey frame; nanotech cutover | open |

### Area-specific (not path-only)

- B82 / Method C — skip when `cpc_prefixes: []`
- WS5c biomed — skip unless YAML `sector_registries` set
- External budget reference / prime EDGAR TARGETS / Finding-2 exclusion lists — per-area config

### Quantum v1 runbook (once Phase 2+ lands)

```text
build_tech_area_cohort.py --area quantum_information_science
nano_form_d_temporal.py --area quantum_information_science
# then WS1 → WS2 → liveness (no B82) → trademarks → alias → ws5a → capture-recapture
# skip WS5c / prime EDGAR
```
