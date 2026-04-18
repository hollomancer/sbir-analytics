# Requirements — NAICS Enricher Consolidation

## Purpose

Reduce the current NAICS enricher surface
(`sbir_etl/enrichers/naics/`, `sbir_etl/transformers/naics_to_bea.py`,
`sbir_etl/transformers/naics_bea_mapper.py`,
`sbir_etl/enrichers/fiscal_bea_mapper.py`) to a smaller, clearly layered
set of modules with no duplicate classes and no dead backward-compat
re-export shims.

## Context

Today the NAICS surface has four rough layers that have accumulated
organically:

1. **Core code lookup** — `sbir_etl/enrichers/naics/core.py` (329 lines).
   Given a NAICS code, return label/sector/hierarchy.
2. **Fiscal NAICS enricher + strategies** —
   `sbir_etl/enrichers/naics/fiscal/enricher.py` (233 lines) delegating to
   `strategies/*.py`. Several strategy files are 4-line re-export shims
   (`agency_defaults.py`, `original_data.py`, `sector_fallback.py`,
   `topic_code.py`) that point at `simple_strategies.py`.
3. **NAICS → BEA mapping (library)** —
   `sbir_etl/transformers/naics_bea_mapper.py` and
   `sbir_etl/transformers/naics_to_bea.py`. Two modules, overlapping intent.
4. **NAICS → BEA mapping (enricher)** —
   `sbir_etl/enrichers/fiscal_bea_mapper.py`. Separate class with similar
   crosswalk logic.

Tests import strategies via the 4-line shim paths (~20 callsites in
`tests/unit/enrichers/naics/test_fiscal_strategies.py` and
`tests/unit/enrichers/test_naics_strategies.py`), which is the only reason
the shims exist.

## Functional Requirements (EARS)

### R1 — Single canonical location per class

**WHEN** a class exists in both a canonical module and a re-export shim
**THEN** the shim SHALL be deleted and all imports updated to the canonical
path.

Applies to: `AgencyDefaultsStrategy`, `OriginalDataStrategy`,
`SectorFallbackStrategy`, `TopicCodeStrategy`. Canonical path:
`sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies`.

### R2 — Single NAICS → BEA mapper

**WHEN** NAICS-to-BEA mapping is needed anywhere in the codebase **THEN**
there SHALL be exactly one class / function that performs it. The
duplicate between `sbir_etl/transformers/naics_bea_mapper.py`,
`sbir_etl/transformers/naics_to_bea.py`, and
`sbir_etl/enrichers/fiscal_bea_mapper.py` SHALL be resolved by picking the
class with the most complete tests, consolidating the logic, and deleting
the others (with an announced deprecation if any are used externally).

### R3 — No silent behavior change

**WHEN** logic is consolidated **THEN** all pre-consolidation tests SHALL
continue to pass, and for the NAICS → BEA mapping case a
golden-file comparison on a representative input set SHALL show zero diff.

### R4 — Strategy registration

**WHEN** the `NAICSFiscalEnricher` composes strategies **THEN** it SHALL do
so via an ordered list registered in one place (a strategy factory), not by
direct imports scattered across call sites. This makes it trivial to add /
reorder / disable strategies in config.

## Non-functional

- Module count in `sbir_etl/enrichers/naics/fiscal/strategies/` drops from
  9 to at most 5 (base, simple, text_inference, usaspending, __init__).
- No new `type: ignore`, no new `except Exception`.

## Out of scope

- Reworking the crosswalk data files themselves.
- Adding new enrichment strategies.

## Acceptance

- `grep -r "Backward-compat re-export" sbir_etl/` returns zero hits.
- A single public class for NAICS → BEA mapping; others removed or marked
  `@deprecated` and scheduled for removal.
- All pre-existing NAICS tests pass; golden-file comparison clean.

## Sizing

Small — ~1 day for the shim cleanup, ~2 days for the NAICS→BEA
consolidation (hinges on resolving the three overlapping implementations).
