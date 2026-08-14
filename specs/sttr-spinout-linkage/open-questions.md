# STTR Spinout–Subcontract Linkage — Open Questions

Decisions reserved for the repository owner. **The classification criteria in
[`design.md`](design.md) cannot be frozen, and no implementation is authorized, until these are
resolved.** Each is stated as a decision with a proposed default; the default is a recommendation,
not a resolution. When the owner decides, record the resolution as a numbered revision in
[`amendments.md`](amendments.md) and only then freeze.

Nothing here is resolved unilaterally. This file exists precisely to keep these open.

---

## O-0 — The `nih-commercialization-linkage` kernel does not exist

**Finding.** The brief instructs reuse of a `nih-commercialization-linkage` kernel exposing
`resolve_identity`, `classify_linkage`, `generic_token_guard`, and `signal_absent_reason`, and to
"extend the cascade, do not re-implement it." **None of these functions, and no such spec or
module, exist in the repository** (verified by repo-wide search). The real reusable substrate is:
- `sbir_etl.identity` (primitives tier): `normalize_company_name`, `company_name_similarity`,
  versioned `CompanyNameProfile` / `CompanyNameMetric`, and `RecoveryStatus` (the typed-absence
  `StrEnum` template) — org-name only; **no person-name primitive exists**.
- The graph-governance `DimensionStatus` enum and `CANDIDATE` assertion contract (ADR-005).

**Decision:** (a) build the four kernel functions as **new `exploratory`-tier code in this spec**,
grounded in the primitives above (`signal_absent_reason` modeled on `RecoveryStatus`;
`generic_token_guard` built from the existing `SUFFIX_TOKENS` generic-token stripping; person-name
normalization net-new); **or** (b) split the kernel into its own upstream spec (possibly a
`primitives`-tier promotion) that this spec then consumes.
**Proposed default:** (a) — build here at exploratory tier; promote to a shared primitive later if
a second consumer appears. Do not block RQ1 on a primitive-promotion project.

## O-1 — Are founders in scope for D2, or only the PI?

The person trail (D2) can match the PI alone, or the PI plus named founders/officers. Founders
widen recall (many spinouts are founded by a non-PI academic) but raise false-positive risk and
data-sourcing cost.
**Proposed default:** PI in v1; founders as a labeled extension after the adjudication sample shows
the PI-only recall floor.

## O-2 — The ±N-year authorship window for D2

How many years around the award date may an RI-affiliated authorship record fall and still count?
**Proposed default:** ±3 years. Report ±1 / ±2 / ±3 / ±5 sensitivity in the review artifact.

## O-3 — Tier thresholds (what is "exact" vs. "fuzzy")

The `company_name_similarity` cutoff separating `SPINOUT_T1` (exact) from `SPINOUT_T2` (fuzzy), and
the corroboration rule for T2 (which dimension pairs count as "independent").
**Proposed default:** exact = normalized-equality or verified identifier match (ORCID, exact
UEI↔RI); fuzzy = `company_name_similarity ≥ [cutoff]` under `CompanyNameMetric.JARO_WINKLER` with
`generic_token_guard` passing. Cutoff to be set from the adjudication sample, not guessed.

## O-4 — The v1 phrase lexicon (D5)

The exact deterministic phrase list ("spun out of", "licensed from", "founded by Professor …", and
variants) and whether it ships in v1 at all.
**Proposed default:** ship a small, frozen, hand-curated lexicon in v1; an ML text classifier is
future work, not v1. The lexicon version is part of the freeze.

## O-5 — Partner-type precedence order

When seed lists overlap (e.g., a university-administered FFRDC), which label wins?
**Proposed default (revised by O-7):** `FFRDC > NEW_MODEL_ORG > UNIVERSITY > RESEARCH_HOSPITAL >
COMMUNITY_COLLEGE > NONPROFIT_INSTITUTE > OTHER_NONPROFIT`. The `UNIVERSITY > RESEARCH_HOSPITAL`
direction is **fixed by the O-7 resolution** (university-owned academic medical centers stay
`UNIVERSITY`; the hospital list is built to exclude them, so the two rarely overlap in practice).
FFRDC (federal master list) remains most authoritative. **Still open:** owner confirmation of the
full ordering.

## O-6 — FRO / new-model-org list curation and fiscal-sponsor coverage

The curation protocol for the new-model-org (focused research organization and similar) seed list,
and the coverage of the known-fiscal-sponsor name list used to detect `POSSIBLY_MASKED_BY_SPONSOR`.
**Proposed default:** seed from public FRO directories and known science-org fiscal sponsors, each
entry date-stamped with a source URL in [`seed-list-provenance.md`](seed-list-provenance.md);
treat the list as versioned and incomplete-by-construction.

**RESOLVED (2026-08-14):** No government master list for new-model orgs exists, so this is a
**curation protocol, not a source pick.** `NEW_MODEL_ORG` seed = Convergent Research's public FRO
portfolio plus known independents (Arc Institute, Arcadia Science, Astera Institute, Speculative
Technologies, and similar), each entry date-stamped with a source URL and **verified at capture**,
treated as incomplete-by-construction. The **fiscal-sponsor list is the load-bearing piece** (the
false-zero guard for the headline readout): seed = science-specific sponsors (Convergent Research,
Astera) plus generic 501(c)(3) fiscal sponsors used by science orgs (Players Philanthropy Fund,
Hopewell Fund, Social Finance, Research Corporation for Science Advancement — verify each at
capture). Scope note: this list only distinguishes `NEW_MODEL_ORG` from `OTHER_NONPROFIT`; the
headline "non-university, non-FFRDC nonprofit" detection does **not** depend on it. Sources recorded
in [`seed-list-provenance.md`](seed-list-provenance.md); data capture remains pending.

## O-7 — Research-hospital list source

Which authoritative list defines `RESEARCH_HOSPITAL` (e.g., a teaching-hospital / AAMC-member set,
or an NIH-grantee hospital set)?
**Proposed default:** owner to name the authoritative source; record its version and date in the
provenance file.

**RESOLVED (2026-08-14):** `RESEARCH_HOSPITAL` is defined **narrowly** as a freestanding nonprofit
research hospital that is **not** the degree-granting university. Spine source = **NIH RePORTER
hospital-class grantees** (public, downloadable, versioned, research-active by construction), scoped
to non-university institutions, with **AAMC COTH** as a coverage cross-check. Precedence is set
`UNIVERSITY > RESEARCH_HOSPITAL` (university-owned academic medical centers stay `UNIVERSITY`), and
the hospital list is **built to exclude university-owned AMCs** so no overlap needs arbitration.
This resolution fixes the precedence direction in [O-5](#o-5--partner-type-precedence-order).
Sources recorded in [`seed-list-provenance.md`](seed-list-provenance.md); data capture remains pending.

## O-8 — Bayh-Dole / licensing literature anchor

The literature map has no Bayh-Dole or licensing citation. D3 relies on Bayh-Dole
government-interest statements.
**Proposed default:** add a statutory Bayh-Dole anchor (35 U.S.C. §§ 200–212) and, if desired, a
licensing citation, as a new `[L#]` (next free slot `[L49]`, currently conditionally reserved).
Do not cite Bayh-Dole informally until the anchor is added.

## O-9 — Does RQ2 ship in this spec or its own?

The matched outcome comparison (design in [`design.md`](design.md#rq2--matched-outcome-comparison-design-only))
is design-only here. It can stay as a design section, or graduate to its own spec once RQ1 labels
exist and are validated.
**Proposed default:** keep RQ2 as a design section here; spin it into its own spec at
implementation time, so this spec stays scoped to classification.

## O-10 — Embedding choice for RQ2 topic-similarity matching

Which embedding produces the topic-similarity matching key (e.g., the repository's
ModernBERT-Embed used elsewhere, or another).
**Proposed default:** reuse the existing ModernBERT-Embed path used by the analysis layer, for
consistency with prior transition work; decide at RQ2 implementation, not now.

## O-11 — Partner-type: this spec or its own primitive?

Partner-type classification shares the D1 spine with RQ1 but is conceptually independent.
**Proposed default (from the addendum):** ship it in this spec — it shares the spine. Promote to
its own primitive only if a second consumer appears.
