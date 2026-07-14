# The Phase III Undercount: Visible vs. Dark Layers

> **Status:** Analysis. Visible layer is measured and verified; dark layer is a stratified
> extrapolation pending the inferential pull. DoD, FY2016–2025.
> Companion to [audit-piid-grain.md](./audit-piid-grain.md); supports **B3** (GAO-24-106398 [L14]).

## The problem in one sentence
SBIR Phase III contracts are supposed to carry FPDS Element 10Q (`research` = SR3/ST3); many don't,
and **the ones we can *find* missing the code are a small, unrepresentative slice of the ones that
are actually missing it.**

## Two signals, four cells
Every DoD contract carries two independent Phase III signals: the **code** (SR3/ST3) and whether the
**description** says "SBIR Phase III". Crossing them partitions the population:

| | Says "SBIR Phase III" (D) | Silent (~D) |
|---|---|---|
| **Coded** (C) | 821 — tagged & self-evident | **5,530** — tagged, silent description |
| **Uncoded** (~C) | **141 — VISIBLE undercount** ✅ | **~1,000 — DARK undercount** (modeled) |

Coded universe = **6,351 distinct DoD Phase III awards** (28,264 transactions; ~78% mod/txn dups)
across **1,487 firms**. Only **13% of coded awards self-describe** — the code and the description are
nearly disjoint signals, which is the crux of the whole problem.

## The visible layer — measured, verified
Contracts that *announce* themselves as Phase III but carry no code.
- **141 flags** (exact "SBIR PHASE III") → **157** with SBIR-anchored variants ("SBIR III", "SBIR PHASE 3").
- **Undercount rate 12.5%–14.7%** of the self-describing set.
- **$244M** (exact) / $296M (grey) in obligations. Priority-sorted review queue with nullable
  `disposition` for adjudication feedback.
- **Spot-verified 12/12** against FPDS by PIID (all `research=NONE`).
- Worst coders: Navy 19%, DCMA 19%; by award type, **delivery orders (24%) far worse than definitive
  contracts (12%)**.

This is the **citable, defensible** number. It is also, by construction, only the contracts that
light up *both* a filter (to find them) and the code check (to see the gap).

## The dark layer — why it's the bigger problem
Contracts that *are* Phase III but light up **neither** signal: no code, no "Phase III" in the text.
You cannot filter for them — there is nothing to filter on.

**Estimate (post-stratified extrapolation).** Apply the visible column's uncoded:coded ratio to the
coded-but-silent population (5,530), stratified so the ratio reflects each stratum's real coding
behavior:

| Stratification | Dark estimate | Total undercount | Visible share |
|---|---|---|---|
| Flat (single ratio 0.172) | 950 | 1,091 | 13% |
| By sub-agency | 958 | 1,099 | 13% |
| By award type | 1,050 | 1,191 | 12% |
| By sub-agency × award type | 980 | 1,121 | 13% |

**All four converge on ~950–1,050 dark uncoded Phase III** — the visible 141 is **~1/8 of the true
undercount.** The estimate is robust to how we slice it, which is the strongest thing we can say
without the inferential data.

**It is a floor, not a point estimate:**
1. **Zero-ratio strata undercount.** Small agencies (USSOCOM's 300 silent awards, MDA, DHA) have too
   few self-describing contracts to observe any uncoded ones, so they contribute *zero* dark — almost
   certainly too low.
2. **Silence likely correlates with sloppiness.** A CO who bothers to write "SBIR Phase III" in the
   description is plausibly *more* likely to also code it. If so, the uncoded rate among silent
   contracts is *higher* than among self-describing ones, and the true dark layer is larger.
3. **The load-bearing assumption** — that coding-failure rates transfer from the self-describing to
   the silent population — is unverifiable without independently identifying silent Phase III.

## Why the dark layer resists measurement
- **No enumeration handle.** With neither signal, there is no way to *list* dark contracts; they can
  only be *inferred* (SBIR firm + sole-source follow-on after a Phase II + topic match to the prior
  Phase II work).
- **The one clean description-independent signal doesn't scale.** SBIR Phase III sole-source is
  awarded under FPDS `reasonNotCompeted = "AUTHORIZED BY STATUTE (FAR 6.302-5(a)(2)(i))"` — present on
  coded records — but that authority is **not SBIR-exclusive**, and per-firm FPDS ATOM pulls are
  ~1–2 min/firm → ~130 hours for 8,090 firms.

## Path forward — the inferential pull
Replacing the ~1,000 model with data requires the recipient contract universe + inference:
1. Pull DoD contracts to the **8,090 SBIR firms** (FY2016–2025) from USAspending `spending_by_award`
   by recipient UEI — see sizing below.
2. Keep sole-source / limited-competition follow-ons after a Phase II (Product 1's structural filter;
   reuse the transition scorer for topic/timing).
3. Subtract the coded (6,351) and description-obvious (962) sets → dark candidates.
4. Human review; the result is a **modeled estimate**, never a spot-verifiable count like the visible layer.

### Sizing the USAspending route
- **Not feasible:** bulk-download all DoD contracts (**36.5M** FY2016–2025).
- **Feasible:** per-firm `spending_by_award` over 8,090 UEIs (100/page). Heavy firms ~5–7 pages
  (Physical Sciences 664 contracts, Charles River 445); most firms 1–3. Estimated **~15,000–25,000
  requests, ~2–3 hours**, cached — yielding a ~200–400k-contract recipient universe.
- **Sole-source pre-filter — tested, unsafe (do not use).** A non-competed
  (`extent_competed_type_codes=[B,C,G]`) filter cuts per-firm volume ~10-40× (Physical Sciences
  664→29, Charles River 445→11), but only **43% recall** on known Phase III (911 "SBIR PHASE III"
  contracts → 395 survive): USAspending's `extent_competed` is heavily **null** (same gap as the
  `research` field), and the filter drops the nulls — i.e. it discards most real Phase III. The
  full per-firm pull (no competition pre-filter) is required; scope reduction must come from the
  recipient list, not competition.

## Bottom line
- **Visible:** 141 flags / $244M — verified, but ~1/8 of the story.
- **Dark:** ~1,000 (robust across stratifications, a floor) — the majority of the undercount, reachable
  only by inference.
- **For the report:** *"≥141 confirmed uncoded Phase III ($244M); coding-overlap analysis implies the
  true undercount is ~8× larger (~1,100 awards), concentrated in contracts that identify as Phase III
  by neither code nor description."*
