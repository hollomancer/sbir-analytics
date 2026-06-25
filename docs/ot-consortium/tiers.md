# OT Consortium Phase III Verification Tiering

## Why this exists

Firms can satisfy the SBIR covered-sales benchmark by citing awards received
through **Other Transaction (OT) consortia** and characterizing them as Phase III
transitions. These are hard to verify because the authoritative federal data is
*structurally* incomplete:

1. **Rollup attribution** — when the Consortium Management Firm (CMF) is the
   recorded FPDS vendor, its obligation total aggregates all member awards. The
   CMF did not "receive" that money; it distributed it.
2. **Modification-based invisibility** — many consortium OTs are recorded as
   modifications to a base agreement: a single FPDS row that auto-populates from
   the base and *cannot* carry the performing member's name.
3. **Partial newer fields** — DoD added `Consortia` (Y/N) and `Primary Consortia
   Member UEI` fields, but completion is incomplete (~84% on the project-based
   subset in FY2023–2024; worse earlier).
4. **Out-of-band truth** — the complete record sits in the Agreements Officer's
   project files, not in any queryable system.

**We do not try to defeat this opacity. We measure it.** Each OT-consortium-linked
award is classified into exactly one honest verification tier, and a magnitude
report quantifies how much of the population (by count and obligated dollars) is
member-confirmable versus unverifiable.

## The tiers

For each OT award linked to a firm, the classifier assigns **exactly one** tier.
The cardinal rule: **never upgrade a tier on weak evidence; absence of
contradiction is not confirmation.**

| Tier | Name | Meaning |
|------|------|---------|
| **T1** | Member-confirmed | `Consortia = Yes`, the `Primary Consortia Member UEI` resolves to the claiming firm **by UEI** (never name alone), and the PIID 9th position is `3` (research) or `9` (prototype/production). Attribution is verifiable. |
| **T2** | Rollup-only | Obligation recorded against a known CMF with no usable member UEI. The firm *may* be a member, but the data cannot attribute the award or amount to it. |
| **T3** | Structurally invisible | Modification-based consortium OT (single base row; member field unfillable by construction). Member identity not derivable from federal data, period. |
| **T4** | No federal record | Claimed award not located in USAspending/FPDS at all (audit mode only). |

**T2, T3, and T4 are first-class results, not failures.** Their union is the
**unverifiable share**, reported prominently and never folded into the verified
(T1) total.

## Precedence (as implemented in `classifier.assign_tier`)

```
T4  no federal record               → return T4   (audit mode)
T1  Consortia=Yes ∧ member UEI == firm UEI ∧ PIID[9] ∈ {3,9}  → return T1
T3  is_modification                 → return T3
T2  recorded vendor is a CMF        → return T2
    residual consortium-linked      → return T2 (conservative floor)
```

**Why T1 is checked before T3:** a *populated and matching* member field is
positive confirmation that overrides the structural-invisibility heuristic. A
modification row that nonetheless carries a matching member UEI is genuinely
confirmable.

**The name-collision guard lives in T1:** a member UEI that does not equal the
claiming firm UEI never reaches T1 — no matter how closely the recorded names
resemble each other. Such near-misses are recorded with
`resolution_method = "name_collision"` so a human can spot-check them, and the
record falls through to T2/T3.

## Assumptions (documented inline in `classifier.py` and `usaspending_ot.py`)

- **`None` means "not populated", never "No".** The DoD `Consortia` and
  `Primary Consortia Member UEI` fields are `None` when the source did not fill
  them. T1 requires `Consortia` to be explicitly `Yes`; an unpopulated flag can
  never satisfy T1.
- **PIID 9th position (1-indexed)** encodes the instrument type. `3` = research,
  `9` = prototype/production qualify for T1. A PIID shorter than 9 characters
  cannot satisfy the rule (evidence absent → not T1).
- **UEI comparison is exact** after upper/strip normalization. Name similarity is
  *never* sufficient for T1. A firm cited only by name may still reach T1 **iff**
  its name resolves to a canonical SBIR-firm UEI and that UEI matches the federal
  member field — the link is still UEI-to-UEI. Provenance is recorded as
  `firm_uei_source = name_resolved` and noted in the confidence note.
- **Rollup detection prefers UEI**, falling back to a normalized-name match
  against the CMF registry until the registry's UEIs are verified against the
  authoritative USAspending `recipient_lookup` table.
- **FPDS reporting lag (~90 days):** DoD OT actions post to FPDS/USAspending with
  a lag, so recent fiscal years undercount and the `Consortia` / member-UEI
  fields are sparser the closer to the present you look. This caveat is carried
  on every magnitude report (`fpds_lag_note`).

## Run modes

- **Baseline (population proxy)** — classifies OT-consortium-linked records among
  the existing detected SBIR→federal-award transitions. The claiming firm is the
  SBIR award recipient. Answers: *of transitions flowing through OT consortia,
  what share are member-confirmable vs. unverifiable, by count and obligated
  dollars?*
- **Audit (optional input)** — when a firm-reported covered-sales claims file is
  configured (`SBIR_ETL__OT_CONSORTIUM__CLAIMS_PATH`), classifies each *claimed*
  OT award against the same tiers. Aggregated covered-sales totals that cannot be
  tied to a specific award are flagged `is_attributable = False`, reported in a
  separate **non-attributable** bucket, and never tiered.

## Per-record audit trail

Every `TierAssignment` carries an `evidence` list (`TierEvidenceItem`: which
field was inspected, its value, which rule it bears on, and a human note), the
`resolution_method`, the `firm_uei_source`, and a `confidence_note` that states
*why this tier and explicitly why not a higher one*. This is persisted to the
tier parquet so a human can spot-check any classification.

## The CMF registry

`data/reference/cmf_registry.csv` seeds the known Consortium Management Firms
(Advanced Technology International, NSTXL, Consortium Management Group, SOSSEC,
National Center for Manufacturing Sciences, MTEC). It is config-extendable via
`ot_consortium.cmf_registry_path`.

**UEIs are intentionally left blank in the seed.** Hand-typing CMF UEIs would
manufacture the exact false precision this module exists to prevent. Instead
`CMFRegistry.enrich_ueis_from_recipient_lookup` resolves them against the
authoritative `recipient_lookup` table and stamps provenance; names that resolve
ambiguously are left blank for human review.
`CMFRegistry.unknown_rollup_vendor_diagnostic` surfaces high-obligation,
consortium-like vendors absent from the registry so it grows from evidence rather
than guesswork.

## Graph model

`(CMF)-[:MANAGES]->(BaseOT)-[:HAS_ORDER]->(ProjectOT)-[:PERFORMED_BY]->(Firm)`.
The `PERFORMED_BY` edge is created **only for T1**. For T2/T3/T4 it is
deliberately absent — the graph must not imply an attribution the federal record
cannot support — while the `ProjectOT` node still carries its tier and confidence
note so the unverifiable population remains queryable.
