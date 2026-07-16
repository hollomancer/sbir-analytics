# Phase III Topic-Lineage Recovery — Design

> **Status:** Spec / design. Gated on the Req-1 availability spike.

## Approach
A firm-scoped exact-lineage matcher. For each SBIR firm, collect its lineage keys from its Phase I/II
awards, then scan **that same firm's** later contracts (already pulled in the 95k recipient universe)
for those keys. Same-firm scoping makes matches high-precision (a firm referencing its own prior SBIR
work). No fuzzy text as a primary signal — the benchmark proved that's near-chance.

## Data flow
```
award_data.csv (Phase I/II: Topic Code, Contract PIID, Solicitation Number, UEI)
        │  per resolved firm -> lineage keys {topics, piids, solicitations}
        ▼
recipient universe (95k DoD/NASA contracts) ── minus coded (SR3/ST3) minus described ("SBIR PHASE III")
        │  = ~90k "dark/neither" pool
        ▼
Tier-1 match: contract.description | solicitationID contains a lineage key of the SAME firm
        ▼
candidate uncoded Phase III  ──spot-check vs FPDS──►  topic_lineage layer -> frozen frame
```

## Lineage-key patterns
- **Topic code:** agency regexes — Air Force `AF\d{2,3}-?\d{3,4}`, Navy `N\d{2,3}-?\d{3,4}`, Army
  `A\d{2,3}-?\d{3,4}`, DARPA `SB\d{3}-\d{3}`, etc. Normalize (strip dashes/case) before matching.
- **SBIR award PIID:** the `Contract` field of the firm's Phase I/II award (e.g. `W911NF05C0123`).
- **Solicitation number:** the `Solicitation Number` field (e.g. `2005.2`, `SB052-005`).

## Tiers
1. **Tier 1 — exact reference (primary):** description/`solicitationID` contains a same-firm lineage
   key. High precision; recall bounded to contracts that textually cite lineage.
2. **Tier 2 — topic keyword (secondary):** description matches the firm's Phase II topic *title/
   keywords* (curated category text; more discriminating than free-form abstracts).
3. **Tier 3 — abstract cosine (tiebreaker only):** ModernBERT, used to rank within Tier-1/2 hits, never
   standalone (near-chance alone).

## Go/no-go (Req 1)
Before building tiers, measure structural-reference prevalence in the ~90k dark pool. Expected outcome
is uncertain: dark contracts may cite lineage (recoverable) or genuinely reference nothing (stays
dark). The spike decides in ~1 hour, cheaply.

## Risks / bounding
- **Upside is pure gain** — a Tier-1 match *converts* a dark contract into a verified flag; can only
  grow the confirmed count, never shrink it.
- **Ceiling** — only catches Phase IIIs that cite their lineage; the truly-referenceless residual stays
  in the ~1,073 model. This shrinks the unenumerable region, doesn't close it.
- **`solicitationID` may be USAspending-null** (like the research/competition fields) — the spike checks
  FPDS ATOM for it; if null everywhere, drop the solicitation key and rely on topic/PIID.
