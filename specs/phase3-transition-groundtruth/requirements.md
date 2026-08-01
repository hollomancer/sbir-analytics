# Independent Phase III Transition Ground-Truth Set — Requirements

> **Status:** Draft spec. No implementation. Validation deliverable for the
> merged award-grain fusion ranker (#467).
> Supports inventory questions **B2 / E1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 (did SBIR research transition to a federal contract), E1 (Phase III identification)
**Answers for:** Whoever decides whether the fusion ranker is trustworthy enough to drive packet selection
**Complexity tier:** Relational (Tier 2)

---

## Done when

> ≥ **60** real Phase III transitions are collected from agency SBIR
> program-office success posts (NASA + DoD to start), each resolved to
> `prior SBIR award (UEI + contract#) → transition contract#`, tagged with
> **evidence provenance** (independent vs. citation-derived) and a **difficulty
> stratum** (marquee/clean vs. hard-to-trace). The frozen fusion ranker (#467) is
> scored against the recoverable subset; **precision@1/@3 and MRR are reported
> split by stratum and by provenance, with 95% CIs**, and compared to the
> proxy-label 0.68@1. The citation-independence and selection-bias caveats are
> quantified, not hand-waved.

---

## Why

The merged ranker reproduces the study's AUC (0.847), but **precision@K is scored
against proxy labels** — the "true" transition is the notice the pipeline itself
attributed by PIID citation, and the negatives are auto-constructed. That is a
consistency check, not a validation (an agent can't grade its own eval). Before
the ranker is trusted to *order* — let alone *gate* — leads in the monthly
packet, its top picks need to be checked against **externally-sourced** truth.

Agency SBIR program offices publicly market their Phase III transitions (NASA
SBIR/STTR success stories; DoD component highlights — Navy/Army/Air Force). These
are **independent of the ranker's citation signal** (they come from PR/program
records, not "the J&A cites the contract"), so they are a legitimate — arguably
stronger — gold standard than blind-adjudicating the ranker's own output.

## The two traps this spec must not fall into

1. **Selection bias (load-bearing).** Marketed transitions are the biggest,
   cleanest wins — exactly the cases a ranker does not need to help with. Scoring
   only on them yields an optimistic number that says nothing about the
   ambiguous, uncoded tail the packet actually exists to surface. **Mitigation:**
   a `stratum` tag on every case; report precision separately for
   `marquee`/`clean` vs. `hard` cases; treat a marquee-only number as a ceiling,
   not the headline. Deliberately supplement with hard cases (§ future work).
2. **Citation circularity.** If a "known" transition is known *because* the notice
   cites the prior contract — the same signal the ranker keys on — scoring against
   it confirms the ranker reproduces a join rule, not that it discovers
   transitions. **Mitigation:** a `provenance` tag (`independent` when the
   transition is established from program-office narrative / follow-on genealogy /
   M&A/SEC / news, `citation` when it traces back to the J&A citation); report an
   **independent-only** precision separately.

## Scope

### In scope

1. **SHALL** catalog NASA and DoD SBIR program-office Phase III transition
   sources (URLs, publication cadence, record shape) without scraping at volume —
   a small, curated validation set, not a crawler.
2. **SHALL** define a frozen extraction schema per case: firm, prior SBIR award
   (topic / solicitation / contract# / UEI as available), transition
   contract/program, agency, year, source URL, verbatim evidence snippet,
   `provenance`, `stratum`.
3. **SHALL** resolve identifiers: firm → UEI (`award_data.csv`), prior award →
   contract#, transition → contract# (USAspending/FPDS). Cases that cannot be
   resolved to both a prior award and a transition contract are **logged and
   dropped from the retrieval test**, never silently included.
4. **SHALL** assemble a retrieval test per resolved case: the curated transition
   is the positive; the candidate pool is the firm's notices already in the
   recovered corpus / archive (reuse #467's recovery). Cases whose transition
   predates the archive window (~FY2016) or whose firm has no candidate pool are
   logged as **coverage gaps**, not scored.
5. **SHALL** score the frozen ranker (#467 `fusion_model` + `fusion_scoring`) over
   the test set: precision@1, precision@3, MRR, with bootstrap 95% CIs, **split by
   `stratum` and by `provenance`**.
6. **SHALL** report the externally-grounded precision against the proxy-label
   0.68@1, and state plainly whether it clears the bar to let fusion *order* the
   packet (vs. deadline-primary) — a separate, higher bar than reproducing AUC.

### Out of scope

- **Forward-opportunity validation.** These are award→already-happened
  transitions; they validate the retrospective ranker, **not** the packet's use of
  the model on open SAM.gov solicitations (nothing has transitioned there yet).
  That distribution transfer is a separate effort.
- **A routing/threshold gate.** Verified positives measure *ranking*; gating a
  go/no-go decision also needs verified **non**-transitions (decoys). Deferred
  until ranking precision justifies a gate at all.
- **Agencies beyond NASA/DoD** (NIH/NSF/DOE Phase III is grant/commercial,
  outside FPDS) — a later increment once the two-agency method is proven.
- **A production scraper.** Manual/assisted curation is acceptable and preferred
  at this N.

## Prerequisites

- Web access to NASA (sbir.nasa.gov success stories, TechPort) and DoD component
  SBIR success pages.
- USAspending/FPDS access to resolve transition contract numbers.
- Merged #467: frozen coefficients, `fusion_model`, `fusion_scoring`, and the
  recovery scripts / recovered corpus (local).

## Risks

| Risk | Mitigation |
|---|---|
| Marquee selection bias inflates precision | `stratum` split; marquee number reported as a ceiling; hard cases supplemented |
| Citation circularity overstates the claim | `provenance` split; independent-only precision reported separately |
| Old transitions have no recoverable pool (~10-yr archive) | log as coverage gaps; report the testable fraction honestly |
| Narrative sources omit contract identifiers | manual resolution; drop unresolved cases with a logged reason |
| Small N → wide CIs | target ~60–80; report CIs, don't over-claim on 20 |

## Addendum — collection clarifications (2026-08-01)

Four constraints from the first collection pass; they refine the set, not the goal.

1. **Procurement, not commercial (v1 scope).** These are Phase III *procurement*
   transitions — a government follow-on **contract/purchase** — which is what the
   ranker and FPDS can validate. Commercial transitions (M&A exits, spinoffs,
   consumer-market commercialization — e.g. NASA Spinoff cases Aspen Aerogels /
   Photobit, DOE Office-of-Science exits) are **collected but tagged
   `transition_type=commercial` and out of scope for the v1 classifier**. Add a
   `transition_type` field (`procurement` | `commercial` | `mixed`); score only
   procurement. Agencies do not always draw this line, so it is classified per
   case on read.
2. **Balance the set — do not let one branch/tech skew the detector.** The first
   pass is ~70% Navy (173 of ~250), and within Navy heavily NAVSEA/NAVAIR/ONR.
   A precision number off that measures "Navy acoustic/EW/training" performance,
   not the detector's. **SHALL** tag every case with `agency`, `command`, and a
   `tech_domain`, **cap the Navy share** (down-sample, stratified across commands
   and tech domains, to rough parity with the pooled non-Navy procurement set),
   and **report precision split by agency and by tech_domain** so no single
   branch drives the headline. Deliberately collect more non-Navy procurement
   (Army/AF/NASA sources the agents flagged as unmined) to widen balance.
3. **Transition-contract resolution.** Prior-award resolution is solved
   (firm→award 140/142 = 98.6% via `resolve_firm_awards`). The *transition*
   contract# is the remaining identifier: on the Navy per-story PDFs
   (`navysbir.com/success/docs/*.pdf`, curl-accessible), and otherwise resolvable
   from FPDS/USAspending by firm UEI + Phase III window. NASA/Army/AF pages give a
   program name + dollar value, not a contract#, so those resolve via FPDS.
4. **Marquee is the dominant stratum.** Nearly all collected cases are marketed
   wins (`stratum=marquee`), often $10M–$500M. Per the selection-bias guard, the
   marquee precision is a **ceiling**; the set must be supplemented with `hard`
   cases (transitions known from non-marketing evidence) before the number is
   trusted as representative.

## Verification plan

1. Source catalog produced → verify: ≥ 2 agencies, record shapes documented.
2. Cases extracted + resolved → verify: ≥ 60 with both prior-award and
   transition contract#; each tagged `provenance` + `stratum`; unresolved logged.
3. Retrieval test assembled → verify: every scored case has a real candidate pool;
   coverage gaps logged.
4. Ranker scored → verify: precision@1/@3 + MRR with CIs, split by stratum and
   provenance; independent-only number stated.
5. Decision recorded → verify: explicit go/no-go on fusion-ordered packet
   selection vs. deadline-primary, with the number it rests on.
