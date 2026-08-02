# Transition Coverage & Self-Labeling Expansion — Requirements

> **Status:** Draft spec. No implementation beyond the exploratory spikes recorded below.
> Follow-on to #481 (validation) and #484 (enrichment). Supports **B2 / E1** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 (SBIR→federal follow-on), E1 (Phase III identification)
**Answers for:** Whoever needs the *full* transition footprint, not just marked prime contracts
**Complexity tier:** Relational (Tier 2)

---

## Done when

> Each new transition **channel** below is characterized with a **credibly-attributed**
> count of transitions it adds beyond the marked prime-FPDS universe — attribution meaning
> UEI-exact firm match + SBIR-derivation evidence, **not** crude dollar sums — and the
> **§638-citing J&A** source is evaluated as a *self-labeling ground-truth upgrade* (does
> its narrative confirm a Phase III derivation, machine-retrievably?). Deliver a channel-by-
> channel coverage table with honest confidence, and a recommendation on which channels to
> wire into the pipeline. **A channel that cannot be credibly attributed is reported as
> "mechanism real, volume not sizeable" — never dressed up with an inflated number.**

---

## Why

#481 answered "can the ranker order the packet?" — no, deadline-primary — **for the marked,
prime-FPDS-contract Phase III population.** #484 + its spike showed that population's text
ceiling can't be enriched. The larger finding: **that population is one slice of a much
bigger, partly-invisible transition footprint** ([[sam-gov-data-services]]). Federal data
beyond prime FPDS contracts exposes the other slices:

- **§638-citing sole-source J&A notices** — the government's own justification document
  *names 15 U.S.C. §638 (SBIR Phase III authority)*. **Self-labeling and text-rich** — it
  attacks both the empty-description wall (#484/T6) and the labeling-circularity wall (#481)
  at once. Highest value: a potential ground-truth *upgrade*, not just more coverage.
- **Grants/assistance** — civilian agencies (NIH/NSF/DOE/USDA) run SBIR as grants; their
  follow-on lives in USASpending *assistance* data, entirely absent from FPDS contracts.
- **Subaward** — SBIR firms transition as *subs* under large primes, invisible at prime level.
- **OT awards** — DIU/production-OT transitions, absent from FPDS entirely.

## Exploratory findings already in hand (2026-08-01 spikes)

- **Subaward: mechanism + linkage CONFIRMED live** (USASpending mirror). But **volume is
  NOT credibly sizeable** with crude filters — a proximity-gated pass returned an absurd
  $10.6B, dominated by **grown-into-prime firms** (MTSI $3.5B, PeopleTec $1.4B) and **data
  artifacts** (Control Vision $2.1B from a *single* prime = likely name over-match or IDIQ
  ceiling). Better signal is **breadth** (# distinct primes: Anduril 23, STR 21) than dollars.
- **Grants: real and cleaner.** Across 35 civilian SBIR firms, **~$69M non-SBIR federal
  grants + $33M contracts** of follow-on footprint (Columbia Power $19M; NIH biotech
  follow-ons). Absent from our contract universe.
- **§638-J&A: not yet testable** — SAM.gov is sandbox-blocked; needs one keyed off-network
  call to confirm the J&A narrative is machine-retrievable (may be an attachment, ~2018+).

## The three traps this spec must not fall into

1. **Grown-into-prime confounding.** Subaward/contract dollars are dominated by SBIR firms
   that *became* large subcontractors — that's firm growth, not a specific Phase III
   transition. **Mitigation:** firm-size threshold (exclude firms above an employee/revenue
   or cumulative-award cap), per-prime caps, and report **breadth (# primes) alongside — or
   instead of — dollars.**
2. **"Follow-on ≠ transition."** A later grant or subaward may be unrelated to the firm's
   SBIR. **Mitigation:** require **SBIR-derivation evidence** — tech-area/NAICS/topic match
   between the SBIR and the follow-on, and Phase-II-proximity timing — before counting it.
3. **Data artifacts.** Name over-match and ceiling-vs-obligated confusion inflate totals.
   **Mitigation:** UEI-exact firm matching (not name search), and validate amount fields
   (obligated, not ceiling) against a hand-checked sample.

## Scope

### In scope
1. **SHALL** evaluate the **§638-citing J&A** source: retrieve a sample via the Get
   Opportunities API (`ptype=u`), confirm the narrative is machine-retrievable, and assess
   it as a self-labeling Phase III positive (precision vs the #481 hand-collected set).
2. **SHALL** characterize the **grants/assistance** channel: civilian SBIR firms' non-SBIR
   follow-on federal assistance, UEI-matched, SBIR-derivation-filtered; count transitions added.
3. **SHALL** characterize the **subaward** channel with the trap-1/2/3 mitigations; report
   breadth-based counts and a *bounded* volume, or state plainly it isn't sizeable.
4. **SHALL** characterize **OT awards** (SAM Contract Awards API, off-sandbox) for the OT
   transition population, including back-filling Anduril/EpiSci OT numbers (#481 loose ends).
5. **SHALL** produce a channel × added-transitions × confidence × access table and a
   wire-in recommendation.

### Out of scope
- Re-opening the marked-set ranker verdict (#481/#484) — this is about *coverage/labels*.
- Building the production ingestion for any channel — this spec *characterizes and decides*.
- FOUO entity fields (revenue/size) requiring a federal system account we may not have.

## Prerequisites
- USASpending API (no key; subaward + assistance reachable now).
- A SAM.gov API key exercised from a **non-sandbox** network for §638-J&A + OT (api.sam.gov
  is blocked here; key rotates ~60 days — [[project_sam_gov_api_key]]).
- SBIR award data for firm→UEI + Phase-II timing + tech area.

## Risks
| Risk | Mitigation |
|---|---|
| Subaward/contract $ dominated by grown-into-prime firms | size threshold; per-prime caps; report breadth not dollars |
| Follow-on award unrelated to the SBIR | tech-area + Phase-II-proximity SBIR-derivation gate |
| Name over-match / ceiling-vs-obligated inflation | UEI-exact matching; validate amount fields on a sample |
| §638-J&A body is an attachment, not inline, or pre-2018 gap | keyed spike before committing; treat as ~2018+ only |
| SAM.gov access blocked / key expired | run SAM-dependent tasks off-sandbox; USASpending-mirrored data first |

## Verification plan
1. §638-J&A spike → verify: N sample notices retrieved; narrative machine-readable Y/N; a
   precision estimate as a Phase III label.
2. Grants channel → verify: UEI-matched, SBIR-derivation-filtered count + footprint; civilian
   agencies represented.
3. Subaward channel → verify: trap-mitigated count (breadth-based); a bounded volume or an
   explicit "not sizeable" with reasons.
4. OT channel → verify: OT transition count; Anduril/EpiSci OT numbers resolved or logged.
5. Synthesis → verify: channel × added-transitions × confidence table + wire-in recommendation.
