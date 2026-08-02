# Transition Coverage & Self-Labeling Expansion — Tasks

> Ordered by value × feasibility. T2/T3 are testable now (USASpending); T1/T4 need an
> off-sandbox SAM.gov keyed call. Exploratory spike numbers from 2026-08-01 are in
> `requirements.md`; these tasks turn them into credibly-attributed results.

## T1 — §638-J&A self-labeling spike — BLOCKED/DEPRIORITIZED (see SPIKE_RESULTS.md)
Ran off-sandbox: notice populations tiny (award notices 1,734/yr, J&As ~5/yr, 0 §638 hits),
and a personal-key **daily quota** (~15 calls) makes body-mining infeasible. Needs a SAM
**system account** or the free bulk extract to pursue — modest expected payoff either way.

### (original) — §638-J&A self-labeling spike (HIGHEST VALUE; needs off-sandbox SAM key)
Retrieve a sample of Justification & Approval notices (Get Opportunities API, `ptype=u`)
that cite 15 U.S.C. §638 / "SBIR Phase III". Confirm the narrative is machine-retrievable
(inline vs attachment). Assess as a self-labeling Phase III positive: sample precision vs
the #481 hand-collected set; coverage window (~2018+).
→ verify: N notices retrieved; body-retrievable Y/N; precision estimate; go/no-go as a
  ground-truth label source.

## T2 — Grants/assistance channel (testable now)
UEI-match civilian SBIR firms (NIH/NSF/DOE/USDA) to USASpending assistance; filter to
non-SBIR follow-on with an SBIR-derivation gate (tech-area + Phase-II proximity). Count
transitions added; size the footprint. Spike found ~$69M/35 firms unfiltered — tighten it.
→ verify: UEI-matched, derivation-filtered count + footprint; civilian agencies represented;
  SBIR-vs-follow-on split validated on a hand-checked sample.

## T3 — Subaward channel with trap mitigations (testable now)
Re-do the subaward sizing properly: **UEI-exact** match (not name search), **firm-size
threshold** (drop grown-into-primes like MTSI/PeopleTec), **per-prime caps**, validate
**obligated-not-ceiling** amounts, and an SBIR-derivation gate. Report **breadth (# primes)**
as the primary signal; give a *bounded* volume or state "not sizeable."
→ verify: artifact firms (e.g. Control Vision $2.1B/1-prime) removed; breadth-based count;
  amount fields validated on a sample; honest volume statement.

## T4 — OT award channel (needs off-sandbox SAM key)
Query SAM Contract Awards API for Other Transaction IDVs/Orders naming SBIR firms; count OT
transitions; back-fill the Anduril/EpiSci OT numbers left pending in #481.
→ verify: OT transition count; Anduril/EpiSci OT#s resolved or logged as unavailable.

## T5 — Entity longitudinal panel (optional firm feature)
Archive a SAM monthly Public Extract; extract firm cert/size-status history for dedup and a
"graduated to large business" trajectory feature (also feeds T3's size threshold).
→ verify: one monthly extract parsed; cert entry/exit dates available for a sample of firms.

## T6 — Synthesis + wire-in decision
Channel × added-transitions × confidence × access table. Recommend which channels to wire
into the pipeline and in what order. State what stays out (grown-into-prime volume, FOUO).
→ verify: table + a clear recommendation, not a hedge.

## Deferred (documented, not this PR)
- Production ingestion for any wired-in channel.
- FOUO entity fields (revenue/size) needing a federal system account.
- FPDS→SAM.gov `/contracting` migration (2026-02-24) endpoint cutover.
