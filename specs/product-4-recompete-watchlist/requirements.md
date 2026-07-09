# Product 4 — Recompete Watchlist — Requirements

> **Status:** Spec / design. **Buildable independent of the A3 gate** (structural, not
> text-derivation driven). Thin watchlist over coded Phase IIIs + Product 1 flags + resolved SBIR
> lineage; cross-reads A (DIB engagement timing).
> Supports inventory questions **B3** (Phase III / transition) with an **A2** cross-read in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 (A2 cross-read) — which expiring contract vehicles carry
SBIR-derived content and are approaching recompete, so OII can engage at solicitation formation?
**Answers for:** OII / oversight staff, SBIR program managers, defense industrial base analysts
**Complexity tier:** Relational (Tier 2)

## Done when

> An analyst can state: "As of [month], [N] contract vehicles with period-of-performance end dates
> 6–18 months out have award histories containing coded Phase IIIs, Product 1 flags, or resolved
> SBIR lineage; here is the monthly watchlist and a one-page pre-solicitation brief per vehicle."

## Background

Phase III preference is easiest to honor at **solicitation formation**, not after award. Vehicles
with SBIR-derived content approaching recompete are a forward-looking engagement list. This is a
structural join over data Products 1 and the 10Q pull already produce — no new inference.

## Requirements

### Requirement 1 — Expiring-vehicle selection
#### Acceptance Criteria
1. THE System SHALL select vehicles whose period-of-performance end date is **6–18 months** ahead
   of the run date.
2. THE System SHALL restrict to vehicles whose award history includes a coded Phase III, a
   Product 1 status-denial flag, or a resolved-entity SBIR lineage.

### Requirement 2 — Monthly watchlist + brief
#### Acceptance Criteria
1. THE System SHALL emit `data/derived/product4_recompete_watchlist.parquet` monthly.
2. THE System SHALL emit a one-page markdown brief per vehicle (vehicle id, agency/office, SBIR
   lineage evidence, PoP end, recompete window, engagement note) for pre-solicitation use.
3. Outputs are a `watchlist`; no `violation` language.

## Dependencies
- Product 1 flags — IN PROGRESS
- FPDS 10Q coding (M0b) + IDV↔order linkage — IN PROGRESS / **Partial** (IDV linkage ~20% fill —
  bounds coverage; state it)
- `resolve_entities` — EXISTS

## Out of scope
- No text-derivation inference (Product 2). No violation determination. No recompete-outcome
  prediction — this is a timing/engagement list only.
