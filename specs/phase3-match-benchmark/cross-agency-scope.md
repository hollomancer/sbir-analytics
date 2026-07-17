# Cross-agency generalization — scope (not yet implemented)

Status: **scoping.** Extends the DoD+NASA undercount and the transition ranker to other agencies. Frames
the obstacles and the concrete tests; no code here.

## Why it matters
The FPDS Phase III undercount [L14] and the transition-thinness questions (A-CP5 / A-CP10) are
program-wide, not DoD-only. Everything measured so far is DoD (baseline) plus a NASA cross-check.

## Agency tiers (they behave differently)

1. **DoD** — baseline. Undercount 14.7%; ranker AUC 0.844. Done.
2. **NASA (contract)** — undercount **reproduces (16/202, 7.9%)**, so the *count* generalizes. But the
   ranker's archive **recovery returned ~0 NASA notices** — NASA PIIDs (`NNX…`, `80NSSC…`) did not appear
   as `AwardNumber` in the GSA `falextracts` archive. **Open diagnosis:** is this a PIID-format mismatch,
   a NASA-specific posting practice (NSPIRES / NASA SEWP vs sam.gov), or genuine non-coverage? First test.
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
