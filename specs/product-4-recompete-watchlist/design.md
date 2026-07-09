# Product 4 — Recompete Watchlist — Design

> **Status:** Spec / design. Thin structural join; buildable independent of A3.

## Approach
A monthly structural query — no scorer, no model. Join expiring vehicles to SBIR-lineage evidence
already produced by Product 1 + the 10Q pull, filter to the 6–18 month recompete window, render a
brief. Deterministic and re-runnable.

## Data flow
```
FPDS vehicles (PoP end dates, IDV↔order linkage) ─┐
Product 1 status-denial flags ────────────────────┤ join on vehicle / awardee (resolve_entities)
Coded Phase IIIs (10Q) + SBIR lineage ────────────┘
        │ keep PoP_end ∈ [run+6mo, run+18mo]
        ▼
  watchlist ─► data/derived/product4_recompete_watchlist.parquet (monthly)
        │ render per-vehicle
        ▼
  one-page markdown briefs (pre-solicitation engagement)
```

## Components
1. **Vehicle selection** — PoP end-date window filter; IDV parent + order rollup (reuse
   `parent_contract_id`; ~20% linkage fill bounds coverage — report the gap).
2. **Lineage evidence join** — Product 1 flags + coded Phase III + `resolve_entities` SBIR lineage.
3. **Brief renderer** — one markdown page per vehicle for OII pre-solicitation engagement.

## Risks / notes
- IDV↔order linkage is ~20% filled → vehicle rollups undercount; state coverage explicitly.
- Forward-looking dates depend on FPDS PoP fields; missing end dates drop the vehicle (report count).
- `watchlist` language only; this list informs engagement, it does not assert wrongdoing.
