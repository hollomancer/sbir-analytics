# Requirements — OT Consortium Sub-Award Attribution (FFATA/FSRS)

> **Status:** Spec only — not implemented. Follow-on to the OT consortium verification-tiering module.
> Supports inventory question **A2** (OT consortium attribution) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** A2 — OT consortium sub-award attribution and T2→T1 recovery via FSRS
**Answers for:** DoD acquisition analysts, SBIR program managers
**Complexity tier:** Relational (Tier 2)

---

## Done when

> A DoD acquisition analyst can state: "Of [N] T2 (rollup-only) OT consortium records, [X] were upgraded to T1 via sub-award UEI match. The recovered amount is $[Y] ([Z]% of the T2 pool). `recovered_from_rollup_usd` and `recovered_from_rollup_count` are surfaced in the magnitude report alongside the existing verified total."

---

## User Stories

**As a DoD acquisition analyst measuring how much SBIR-adjacent OT consortium spending is attributable to specific firms,**
I want T2 (rollup-only) records upgraded to T1 when FSRS sub-award data provides a UEI-keyed attribution, so that obligated dollars previously hidden in CMF rollups can be linked to individual SBIR-eligible firms for transition-rate and concentration analysis.

**As an SBIR program manager reviewing firm-level federal contract history,**
I want the magnitude report to expose how much formerly unverifiable T2 spending was recovered to T1 via sub-award UEI match, so that I can understand the lower bound of OT-consortium activity that was previously invisible in firm-level obligation totals.

---

## Problem

The tiering module classifies an OT-consortium award against a CMF as **T2
(rollup-only)** when the CMF is the recorded FPDS vendor and no member UEI is
populated: the obligation is a rollup across members, not attributable to any one
firm. That is honest, but it leaves real member attribution on the table when an
*authoritative* federal source can recover it.

Prime recipients of federal awards must report sub-awards above the FFATA
threshold (currently $30k) to the FSRS, surfaced in USAspending **sub-award**
data: subawardee name + **UEI**, **sub-award amount**, action date, and the parent
prime award ID. Where a CMF files sub-awards for its consortium distributions,
this gives us exactly what the rollup destroys:

- the **member UEI** (authoritative, UEI-keyed — T1-eligible), and
- the **per-member dollar amount** (not the CMF's rollup total).

## Goals

1. Ingest USAspending sub-award data and index it by prime award ID.
2. Add an authoritative **third T1 route**: a CMF-prime sub-award whose
   subawardee UEI equals the claiming firm. Use the **sub-award amount** as the
   firm's attributed obligation, never the prime rollup total.
3. Report, in the magnitude report, how much obligated $ moved from the
   unverifiable (T2) bucket into verified (T1) because of sub-award recovery.

## Non-goals / hard constraints (preserve the module's ethos)

- **Absence of a sub-award is NOT contradiction.** OTs are "other transactions",
  not contracts/grants; FFATA coverage of OT consortium distributions is
  inconsistent and often absent. A record with no sub-award stays exactly where
  it was (T2/T3) — we never downgrade or infer non-membership from absence.
- **UEI only for T1.** Sub-award attribution reaches T1 only on an exact
  subawardee-UEI == firm-UEI match. Sub-awardee *name* matches are, at most, a
  flagged lower-confidence corroboration signal, never T1.
- **No rollup double-counting.** When a sub-award attributes a member amount, the
  firm's verified line uses the sub-award amount; the CMF prime's rollup total is
  not also counted as verified.
- Below-threshold and unreported member awards remain unverifiable and are still
  reported in the unverifiable share.

## Acceptance criteria

- Sub-award present under a CMF prime, subawardee UEI == firm → **T1**
  (`resolution_method = "subaward_uei"`), obligation = sub-award amount.
- Sub-award present but subawardee UEI ≠ firm → not this firm (unchanged tier).
- Sub-award absent → tier unchanged from the federal-record-only result.
- Magnitude report exposes `recovered_from_rollup_usd` /
  `recovered_from_rollup_count`: obligated $ and records moved T2→T1 via
  sub-awards, reported alongside (not folded into) the existing verified total.
- Unit tests for each case above; ≥85% coverage on new code; ruff/black/mypy
  clean.
