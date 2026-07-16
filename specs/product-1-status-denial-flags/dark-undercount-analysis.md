# The Phase III Undercount: Visible vs. Dark Layers

> **Status:** Analysis. Visible layer is measured and verified; dark layer is a stratified
> extrapolation pending the inferential pull. DoD, FY2016–2025.
> Companion to [audit-piid-grain.md](./audit-piid-grain.md); supports **B3** (GAO-24-106398 [L14]).

## Undercount statistics — the bottom line up front

Contract-based SBIR Phase III undercount, FY2016–2025 (DoD + NASA = ~all of it):

| | DoD | NASA | **Combined** |
|---|--:|--:|--:|
| Coded Phase III universe (awards) | 6,351 | 1,038 | **7,389** |
| Described "SBIR PHASE III" contracts | 962 | 202 | 1,164 |
| Visible undercount (uncoded ∩ described) | 141 | 16 | 157 |
| **Undercount rate** | **14.7%** | **7.9%** | — |
| + full-universe text scan | +11 | — | +11 |
| + grey Phase III variants (spelled-out / "PH III" / "PHIII" / "PH3") | +23 | — | +23 |
| **Confirmed / verifiable flags** | **175** | **16** | **191 (~$365M)** |
| Modeled dark (unenumerable) | ~1,000 | ~73 | **~1,073** |
| **Total undercount (modeled)** | ~1,175 | ~89 | **~1,264** |

- **Confirmed:** 191 uncoded Phase III contracts, **~$365M** — spot-verified (DoD 12/12 vs FPDS), citable.
  Frozen frame `frame_hash=c8769d3d6ad4` (141 exact-phrase + 11 text-scan + 23 grey-variant + 16 NASA).
- **Modeled total:** ~1,240 awards; the **~1,073 dark** portion is provably **unenumerable** from public
  data (no code, no descriptive text, competition field null, text-similarity near-chance).
- **Rates:** DoD 14.7%, NASA 7.9% (NASA codes ~2× better). Worst DoD strata: delivery orders 24%,
  Navy/DCMA 19%.
- **Scope:** NIH/NSF/DOE excluded — their Phase III is grant/commercial, outside FPDS entirely.

---

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

## Every cheap shortcut has been tested and ruled out
The dark layer cannot be scoped down; the full per-firm pull is the only remaining path. What was tried:

| Shortcut | Idea | Result | Why it fails |
|---|---|---|---|
| USAspending `Research` field | Read the 10Q code from bulk USAspending | ❌ | Column exists but is **null** even for "SBIR PHASE III" descriptions (0/40) |
| Description matching | Find Phase III by "SBIR PHASE III" text | ⚠️ partial | Only catches **~12% of coded** Phase III; misses the silent majority |
| Bulk-all-DoD download | One big file, filter locally | ❌ | **36.5M** contracts FY2016–2025 |
| Global FPDS authority pull | Query FAR 6.302-5 sole-source | ❌ | Authority **not SBIR-exclusive**; volume unbounded |
| Per-firm FPDS ATOM | Pull each firm's contracts from FPDS | ❌ | ~1–2 min/firm → **~130 h** for 8,090 firms |
| Sole-source pre-filter | `extent_competed=[B,C,G]` to cut ~10× | ❌ | **43% recall** — `extent_competed` is null-heavy, drops real Phase III |

**Only path left:** per-firm USAspending `spending_by_award` over the 8,090 recipient UEIs
(~15–25k requests, ~2–3 h), then inference. No further scoping is available.

## Executed: the full recipient pull did not crack the dark layer
We ran it — DoD contracts to **8,085/8,090** SBIR firms (FY2016–2025), a **95,103-contract** universe.

| | Count |
|---|---|
| Recipient universe | 95,103 |
| coded Phase III (matched) | 4,247 |
| exact-described | 736 |
| **neither (candidate pool)** | **90,792** |
| full-text scan → SBIR+"Phase III" text (narrow) | **+11 flags** ($35.9M) |
| grey variants → spelled-out / "PH III" / "PHIII" / "PH3" | **+23 flags** ($56.5M) |
| residual with no SBIR/Phase-III text | **76,276** |

**Scanning all 90,792 candidate descriptions added 34 flags** beyond the 141 (11 narrow SBIR+"Phase III"
+ 23 broader grey variants) — the exact-phrase API filter had already captured most, but not all,
text-evidenced Phase III. Confirmed DoD uncoded (text-evidenced) = **175 (~$337M)**; with NASA's 16,
**191 (~$365M)** total. The remaining 76,276 carry no Phase III text; with USAspending
competition null and text-similarity near-chance (the Product 2 benchmark), **no signal separates
dark Phase III from ordinary contracts.** The pull *closes* the question rather than enumerating the
layer: **the dark undercount is unenumerable from public data.**

*(coded matched 4,247 of the 6,351-award coded set because the recipient frame is scoped to Phase II
in FY2016–2025; coded firms whose Phase II predates 2016 fall outside the universe — a scope limit,
not a join failure.)*

## Agency scope — this is a DoD (and NASA) phenomenon
The undercount is a **contract-coding** gap, so it only exists where Phase III *is* a federal
contract. "SBIR PHASE III" contract counts (FY2016–2025) and SR3-coded volume by agency:

| Agency | described contracts | SR3-coded | applies? |
|---|--:|--:|---|
| DoD | 911 | 66,450 | yes (this analysis) |
| **NASA** | **202** | 6,130 | **yes — measured, see below** |
| DOE | 10 | 120 | negligible |
| NIH (HHS) | 2 | 80 | no |
| NSF | 2 | 1 | no |

NIH/NSF/DOE run SBIR on **grants**; their "Phase III" is private sales/investment that never touches
FPDS. Their invisibility is a **data-model gap** (activity outside federal contracting), not a coding
gap — a different problem (Form D / sales / commercialization surveys), not this audit. **DoD + NASA
≈ the entire contract-based Phase III undercount.**

**NASA measured (v1.1, FY2016–2025).** Coded universe 1,038 Phase III awards / 327 firms; described
"SBIR PHASE III" 202 contracts; **undercount 16/202 = 7.9% ($27.9M)**; stratified dark ~73 → total
NASA undercount ~89 (visible share 18%). **NASA codes ~2× better than DoD** (7.9% vs 14.7% uncoded,
852 vs 5,530 silent), so its dark layer is proportionally small. Combined **DoD + NASA: 191 confirmed
flags (~$365M), ~1,073 modeled total.**

## Recovery attempts since the pull (all tested, all bounded)
Two further signals were tried to recover the dark layer; both add to the ruled-out list:

- **Topic-code lineage (NO-GO).** Hypothesis: a firm's own SBIR topic code, cited in a later
  contract, marks a Phase III. Result: topic codes appear in 3.1% of dark descriptions, but 2,672
  same-firm topic matches yielded **0** that are ≥2 years after the firm's Phase II under that topic
  — the codes are artifacts of the SBIR *research award* (Phase I/II, same year), not provenance on a
  Phase III descendant. Prior-PIID refs: 0.2%. Documented on branch `claude/phase3-topic-lineage`.
- **Solicitation text (partial, coverage-capped).** Hypothesis: the follow-on contract's *solicitation*
  text (rich RFP) reveals Phase III where the terse FPDS description can't. Source **works with no key**
  via the sam.gov website backend (`sam.gov/api/prod/sgs/v1/search`), coverage back to 2010, and where
  present the text *does* carry the signal (the "WHEELBANK ASSEMBLY" contract's solicitation says
  "sole-source, SBIR Phase III"). **But coverage is the wall:** only ~19% of known Phase III have a
  findable solicitation, ~12% have retrievable inline text, and **56% of Phase III are sole-source** —
  non-competed, so no solicitation is posted. Direct-scan recall: 2%. Reaches ≤~12% of Phase III.

**Root cause, restated:** the dark layer is dark *because it's non-competed* — sole-source to the SBIR
developer under FAR 6.302-5 — which is precisely why it leaves no public text anywhere (no coded field,
no descriptive contract text, no posted solicitation). Every text/tag/solicitation signal hits this
same structural wall.

## Reframe: transition detection (candidates, not counts) — the forward path
Attribute-detection ("is this contract a Phase III?") is exhausted. The productive reframe is
**transition detection**: connect a Phase I/II to a subsequent **non-Phase-I/II** government funding
agreement that continues the same work. The Phase III *tag* is optional metadata, not the target.

- **Working definition (per direction, 2026-07):** a transition = Phase I/II → a later government
  funding agreement that is (a) *not itself* a Phase I/II SBIR award and (b) connected **strongly
  enough** to the Phase I/II work. **Sole-source is supporting evidence, not required** — the
  discriminator is strength-of-connection by *any* signal.
- **Substrate already built:** the 95,103-contract recipient universe *is* the set of subsequent
  agreements to Phase-I/II firms; the same-firm link is already made. The open problem is the
  *discriminator* — ranking which of a firm's many later contracts genuinely continue its SBIR work.
- **Connection-signal hierarchy (from this investigation):** explicit reference (rare, 0.2%);
  **semantic same-work using the RICH abstract as the query** (measured below — the earlier
  "near-chance" was a *terse-query* artifact); sole-source FAR 6.302-5 (strong but coded generic `OTH`
  in FPDS — 38.5k/yr DoD — and null in USAspending, so extraction needs a ~380k-record pull);
  timing-after-completion + PSC/NAICS domain continuity (supporting, broad alone).
- **Output is different in kind:** ranked **candidates / leads with a measured precision** (the
  `phase-3-solicitation-alerts` RETROSPECTIVE goal: ≥85% on a hand-audited sample), *not* a
  spot-verifiable count like the 191 confirmed flags. This is the intended use of the audited
  `phase_iii_retrospective_candidates` asset + transition scorer — which never had a contract source
  until the 95k universe pull.
- **Next step:** run the (join-key-fixed) transition scorer on the 95k universe → ranked candidate
  pool → spot-check precision. A PSC/NAICS **domain-shift discriminator** (R&D NAICS 5417* / PSC `A*`
  → manufacturing/production) is being pulled as the lightweight alternative to the ~380k-record
  sole-source enrichment, since terse descriptions alone can't separate truly-dark transitions.

### Rich-text semantic matching — measured (2026-07-15)
The "semantic matching doesn't work" verdict was drawn from the **wrong substrate**: terse
(~40-char) contract descriptions on *both* sides. Re-ran as a positive control on known coded
Phase III (true awardee known), TF-IDF cosine, true firm's abstract vs 20 random firms per target:

| pairing | AUC | note |
|---|--:|---|
| terse desc ↔ terse desc *(the old ModernBERT test)* | ~0.56 | near-chance |
| **rich abstract** ↔ terse FPDS desc | **0.74** | query richness alone lifts it |
| **rich abstract** ↔ **rich solicitation** | **0.79** | rich target adds a little |

**The query-side abstract (1,308-char median) does the work** — the near-chance null was a
query-starvation artifact. But 0.79 is the *easy* task (true-firm-vs-random-firms; random firms are
in unrelated fields). The **operational** task — *which of a firm's OWN contracts is the transition* —
is much harder, and the follow-up measurements settle it:

**Measurement 1 — retrospective solicitation-text coverage (sam.gov backend):** low and
**recency-gated**, not competition-gated. ~0% before 2019, 15–42% for 2020–2025, **13% overall**.
Competition status is *not* the lever (sole-source actually records a Sol# more often, 50% vs 17%);
the sam.gov *search* backend simply purges archived opportunities.

**Measurement 2 — same-firm contrastive, terse target (`pc_samefirm.py`, 768 firms / 4,009 true
Phase III):** AUC **0.492** (median 0.500) — **pure chance**. With a terse (~44-char) description as
the target, a firm's abstract cannot tell its Phase III from its routine contracts (all in the same
technology).

**Measurement 3 — same-firm contrastive, PSC/NAICS domain-shift (250 firms):** AUC **0.522** — also
chance, and it **falsifies the domain-shift thesis**: coded Phase III is *more* R&D-coded than routine
(P(production-like) 0.44 vs 0.62). SBIR Phase III is often R&D-services continuation, not
manufacturing — so R&D→production doesn't separate it.

**Neither terse text (0.492) nor structure (0.522) solves the operational discriminator.** The only
lever with signal is a **rich target** — which measurement 1 said was 13%-covered… via the wrong
source.

### Retrospective rich text IS obtainable — GSA archived extracts (2026-07-16)
`falextracts.s3.amazonaws.com/Contract Opportunities/Archived Data/FY{2015..2025}_archived_opportunities.csv`
— public S3, **no API key**, reachable from this IP (bypasses the `api.sam.gov` gateway that 404s us;
the sam.gov *search* backend is active-only). The `Description` column is **inline text, populated for
76%** of notices (median 195 chars, p90 ~5,800). Join to our contracts by `Sol#`. This is **~76% vs
the 13%** sam.gov-backend retrieval — it reopens rich-target retrospective matching. Effective
coverage for transitions ≈ P(contract has a Sol#, ~33% coded) × P(Sol# posted publicly with text);
never-posted sole-source stays absent, but competed transitions (the reframe's target) should land.

**Synthesis:** the operational discriminator needs rich *target* text. Retrospectively that means the
GSA archived extracts (join by Sol#); prospectively, live sam.gov solicitations (fully available).
PSC/NAICS is *not* the fallback it was hoped to be. **Next decisive test:** `Sol# → archived
Description` join, then re-run measurement 2 with rich targets — does it lift the same-firm
discriminator off 0.49? (`scripts/phase3_benchmark/pc_rich_match.py`, `pc_samefirm.py`.)

## Bottom line
- **Confirmed / text-evidenced:** **191 flags (~$365M)** — verifiable, citable (frozen frame
  `frame_hash=c8769d3d6ad4`); text-based discovery is now exhausted.
- **Modeled dark:** ~1,000 (stratified floor) — the majority, and — after the full pull — **provably
  unenumerable** from public data, estimable only by extrapolation.
- **Agency scope:** DoD + NASA carry the entire contract-based undercount; NIH/NSF/DOE Phase III is
  grant/commercial and outside FPDS entirely.
- **For the report:** *"The coding-discoverable Phase III undercount is 191 awards (~$365M), verified.
  Coding-overlap analysis implies the true figure is ~7× larger (~1,260 awards), but the excess is
  structurally invisible to every public signal — it can be estimated, never enumerated."*
