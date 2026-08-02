# Cross-agency generalization — scope (not yet implemented)

Status: **scoping.** Extends the DoD+NASA undercount and the transition ranker to other agencies. Frames
the obstacles and the concrete tests; no code here.

## Why it matters
The FPDS Phase III undercount [L14] and the transition-thinness questions (A-CP5 / A-CP10) are
program-wide, not DoD-only. Everything measured so far is DoD (baseline) plus a NASA cross-check.

## Agency tiers (they behave differently)

1. **DoD** — baseline. Undercount 14.7%; ranker AUC 0.844. Done.
2. **NASA (contract) — ranker recovery does NOT generalize (tested, negative).** Undercount reproduces
   (16/202, 7.9%) from USAspending, so the *count* generalizes. But the archive ranker does not: NASA is
   present with 94% rich text, yet **every firm-link key is sparse and matched zero** of our NASA Phase III
   firms — `AwardNumber` ~6%, **`Awardee` ~5%**, FPDS `solicitationID` ~2.5% (10 of 1,037 PIIDs). The rich
   NASA text is **general solicitations/synopses, not the firm-specific award notices / J&As** that made
   DoD work: NASA runs SBIR through NSPIRES and its Phase III is sole-source with almost no FPDS
   solicitation trail, so it does not post firm-linkable award documents to sam.gov Contract Opportunities.
   **Conclusion:** NASA transition detection needs a **NASA-specific source (NSPIRES / NASA award data)**,
   not the GSA archive. (An earlier note called this a "wrong-join-key artifact, fixable" — the data
   corrected that: all three keys fail.) This is the d8 hypothesis confirmed — **coverage/linkage
   dominates per agency**: the archive ranker generalizes only to agencies that post J&As/award notices.

   **But NASA has its own source — TechPort (confirmed viable).** `techport.nasa.gov/api` is public and holds
   **~20,036 SBIR/STTR projects**, ~95% of a sample carrying a **performing firm org + a rich project
   description** — NASA's own portfolio, exactly where NASA "posts" its work. This replaces the sam.gov
   archive for NASA: match TechPort project `organizations` → our SBIR firm UEIs (fuzzy name), use the
   project `description` as firm-linkable rich text. Caveats for the build: (a) the API **rate-limits**
   under rapid calls → needs a paced, cached, retried pull (like the GSA archive); (b) org-name→UEI needs
   proper fuzzy matching; (c) verify whether a TechPort project represents the **transition/Phase III** vs
   the original Phase I/II (the `program`/date fields help). So NASA is **not a dead end** — it needs a
   TechPort-based recovery, not the GSA archive. Other non-sam.gov leads: NSPIRES (gated), `api.nasa.gov`
   (keyed), NASA SBIR success stories.
3. **Other contract agencies (DHS, DOT, DOE-contracts, Commerce, …)** — FPDS-coded + USAspending-described,
   same `falextracts` archive (all agencies). The undercount pulls are already **agency-parameterized**
   (`--agency`), so extension is mechanical; recovery/ranker are **untested** cross-agency.
4. **Grant-heavy agencies (NIH, NSF, DOE-Office-of-Science)** — Phase III is largely **grant/commercial,
   outside FPDS entirely** (already excluded from the undercount scope). Detecting their transitions is a
   *different problem* (Form D / SBIR.gov commercialization surveys), **out of scope** for this pipeline.

## Concrete tests (in order)
1. **NASA recovery diagnosis** — measure `falextracts` `AwardNumber`/`Sol#` coverage for NASA Phase III
   PIIDs; check format normalization; identify whether an alt source (NSPIRES) is needed. Decides whether
   NASA ranker coverage is fixable or structural.
2. **Undercount across all FPDS contract agencies** — run the manifested coded (`pull_fpds_10q`, per
   `DEPARTMENT_ID`) + described (`pull_described_phase3 --agency …`) pulls for the top contract agencies;
   report per-agency undercount rate. Cheap (pulls are parameterized) and directly feeds A-CP5.
3. **Ranker coverage + AUC per agency** — for agencies with recoverable rich notices, re-run recovery +
   `transition_ranker.evaluate` (GroupKFold by firm); report per-agency AUC and recovery coverage.
4. **Transfer test** — DoD-trained ranker applied to a held-out agency (vs per-agency retrain), to see
   whether the jargon-lexical + structural signal is agency-portable.

## Expected obstacles / hypotheses
- **Coverage, not method**, will dominate — as with DoD sole-source, the recoverable rich-text segment is
  the competed + J&A-posted slice; agencies that post less will yield thinner ranker coverage even where
  the undercount count is fine.
- **NASA** is likely an archive-coverage/format issue (fixable via a NASA-specific source or normalization),
  not a modeling one — the undercount already works there.
- **Grant agencies** stay out of scope; conflating them would misstate transition rates.

## Effort
- Test 1 (NASA diagnosis): small (measurement on data in hand + a targeted probe).
- Test 2 (all-agency undercount): small–moderate (parameterized pulls already exist; manifested).
- Tests 3–4 (ranker cross-agency): moderate–large (per-agency recovery pulls; #442 pipeline territory).

## RESULTS — first cross-agency number (Test 3, DoD↔NASA)
Substrate: the NASA TechPort non-SBIR-project pool from #456 (`nasa-techport.md`) supplies NASA-side
targets keyed by firm UEI; DoD side is the SBIR award abstracts + the SR3/ST3-coded contract pool.

**Cross-agency overlap (UEI join, data on disk):**

| Crossover | N (any) | N (strict) | Clean? |
|---|---:|---:|---|
| DoD SBIR → NASA non-SBIR project | 310 | 72 | ✅ target genuinely non-SBIR |
| NASA SBIR → DoD Phase III (SR3/ST3) | 308 | 3 | ❌ target pool *is* SBIR-coded |
| Firms w/ coded Phase III at BOTH agencies | 88 | — | — |
| Firms doing SBIR at BOTH DoD & NASA | 1,489 | — | context |

**Cross-agency retrieval (DoD SBIR abstract → its NASA non-SBIR project, 25 same-register hard negatives,
306 firms): AUC 0.828, top-1 45%, top-3 60%** [within-NASA 0.879 | within-DoD 0.844]. pos-sim median
**0.066** — absolute cosine is tiny (agencies use different jargon registers) yet the *ranking* holds, so
this is genuine cross-agency continuity, not firm co-occurrence (1,489 firms do both SBIR → co-occurrence
alone would sit at 0.5). The softer top-1 (45% vs 59% within-NASA) is the empirical case for *fusion*:
identity + temporal features (vocabulary-agnostic) recover the most exactly where cross-agency text is weakest.

**Asymmetry / data block:** NASA→DoD collapses to 3 strict **not** because it's rare but because our DoD
target pool is SR3/ST3-*coded* (SBIR by construction) — a firm in it did DoD SBIR by definition. Measuring
NASA→DoD (and DoD-internal *uncoded* Phase III) needs a **DoD non-SBIR contract pool** (recipient-UEI-filtered
USAspending/FPDS, excluding SBIR-coded), the DoD analogue of what TechPort is for NASA. That is the richest
open avenue — but it is the base-rate wall in full force if scanned whole-universe (~1% prevalence → needs
~0.95 AUC); the tractable framing is **per-firm/recipient-scoped** ranking (a firm's SBIR abstract → its own
non-SBIR DoD contracts), which is the same retrieval frame that yields 0.828/0.844/0.879 and tames the base rate.

**Gate before building the ranker:** the 72 strict DoD→NASA firms are a proxy ("DoD-SBIR firm doing a NASA
project") that needs human confirmation (genuine transition vs unrelated NASA work) — fold ~10–15 into the
precision@K manual-eval pass before investing in the DoD non-SBIR pull.
