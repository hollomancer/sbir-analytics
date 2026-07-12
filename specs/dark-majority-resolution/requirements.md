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

## WS5 — New positive channels (raise the floor)

Ranked by expected recovery per unit effort. All reuse existing infrastructure
(USAspending client pattern, ODP downloader, confidence-tier conventions).

### WS5a — Subawards (FSRS)

The largest untapped federal source: every contract check so far queried *prime*
awards, but delivering technology through a prime (becoming Lockheed's or Raytheon's
subcontractor) is a canonical SBIR transition that looks exactly like disappearance
in prime-award data.

**Requirement:** For dark-bucket firms (651 disappeared + WS2-resolved no-UEI first;
full cohort if cheap), query USAspending subaward records by sub-awardee (UEI where
known, exact normalized name otherwise), temporally filtered to actions after Phase II
end, classified with the WS1 tier conventions (prime's funding agency vs award agency,
SBIR exclusion, de-minimis floor).

**Known limits (state in outputs):** FSRS reporting threshold (~$30K) and documented
under-reporting; coverage begins ~FY2011; sub-awardee names are prime-entered and
dirtier than recipient names.

**Acceptance:** per-firm subaward evidence CSV with provenance (prime, sub amount,
dates, description); count of previously-dark firms recovered; report + headline update
if material. Effort: M.

### WS5b — SAM.gov registration status

Registration renewal is affirmative liveness (annual requirement); a lapse *date*
brackets when a firm stopped seeking federal work — the closest quasi-negative signal
short of state registries.

**Requirement:** For all cohort firms with UEIs (including WS2 resolutions), pull SAM
entity status (public monthly extracts, or the Entity Management API — a SAM API key
already exists in this repo's tooling). Output per-firm: status, last-update/expiry,
purpose-of-registration codes; classify active vs lapsed-with-year.

**Acceptance:** liveness/lapse table joined into the dark-firm instrument set; lapse
years feed the survival framing (WS4) as dormancy timestamps. Effort: S–M.

### WS5c — Sector go-to-market registries (biomed slice first)

Commercialization-specific registries for the pathway federal procurement sees worst.

**Requirement:** Match dark-bucket firms against (1) ClinicalTrials.gov sponsors
(bulk/API), (2) FDA 510(k) applicants + establishment registrations (openFDA), with
name+state confidence tiers. Scope to the biomed slice (HHS-funded awards, plus
NSF/NIH-adjacent firms) before considering the electronics analog (FCC equipment
authorizations).

**Acceptance:** per-firm go-to-market hits with dates and confidence; sponsor/clearance
counts reported alongside the trademark instrument in Finding 3. Effort: M.

## WS6 — Recall multipliers (rename-aware identity graph)

Exact-name matching is every instrument's shared false-negative: renamed or quietly
acquired firms defeat all of them at once. Fixing identity once lifts recall everywhere.

### WS6a — Build the alias graph

**Sources, cheapest first:**
1. `owner_name_change` from TRCFECO2 (2.9 MB, same product already downloaded) — an
   explicit old-name → new-name mapping.
2. PatentsView `assignee_id` clusters in `g_assignee_disambiguated` (already on disk) —
   the disambiguation already groups name variants we currently treat as distinct.
3. USAspending recipient profiles for known UEIs — "doing business as" and
   parent/child recipient linkages.
4. USPTO patent assignment records — portfolio transfers reveal renames AND
   sub-SEC-threshold acquisitions. Locate the research-edition product on ODP first
   (the legacy ECORSEXC path is browser-gated); if unavailable programmatically,
   descope this source and note it.

**Acceptance:** `data/processed/firm_aliases.csv` (firm → alias, source, effective
date where known); alias coverage stats per source. Effort: M.

### WS6b — Alias-expanded re-runs

**Requirement:** Re-run the patent, trademark, and USAspending matchers with alias
expansion. Alias-mediated matches are indirect — they REQUIRE corroboration (state or
PI agreement) regardless of name specificity, and carry an `alias_source` provenance
column.

**Acceptance:** per-instrument recall delta (firms recovered only via alias), report
update if material. Effort: S–M after WS6a.

**Unscoped but noted:** patent maintenance-fee lapses (portfolio-wide lapse as a
dormancy signal), Wayback-dated web presence (T9 upgrade), and the SBA/CCR access
lever (the government already holds mandatory self-reported commercialization data;
an NSET request for tabulation needs no new collection). These stay out of scope until
prioritized.

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
6. WS5a subawards → WS5b SAM status → WS6 alias graph + re-runs → WS5c sector
   registries. Subawards first (highest expected recovery per effort); the alias graph
   before WS5c so the sector matchers run alias-expanded from the start.
