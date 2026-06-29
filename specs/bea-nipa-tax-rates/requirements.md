# Requirements — BEA NIPA Tax Rate Hardening

> **Status:** Partially implemented. `sbir_etl/transformers/fiscal/nipa_rates.py`
> (`NIPARateProvider`) already fetches BEA NIPA Tables 3.2, 3.3, and 1.5 via the
> existing BEA API client and produces the eight derived federal + state/local
> rates `FiscalTaxEstimator` consumes. This spec covers the remaining two gaps
> surfaced during a 2026-06-29 audit:
>
> 1. The NIPA cache is in-memory only; a fresh process pays the full BEA API
>    cost on every run.
> 2. Three runtime sites still use a hardcoded `0.22` (or `0.18`) effective
>    rate even though a NIPA-derived rate is available.
>
> Anchors inventory questions **D2** and **D3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** D2 — jurisdiction-separated fiscal tax receipts from SBIR spending; D3 — NIPA-derived rate credibility vs. hardcoded effective rates
**Answers for:** pipeline engineers (data infrastructure), Treasury / OMB analysts (downstream consumers)
**Complexity tier:** Targeted hardening of an existing component

---

## Done when

> A pipeline engineer can state: "`NIPARateProvider` reads / writes
> `data/reference/bea/nipa_tax_rates.parquet`, so a fresh process gets cached
> rates without re-hitting the BEA API. No runtime code path applies a hardcoded
> `0.22` effective-tax flat rate where a NIPA-derived rate is available — the
> sensitivity analyzer, the `mission_c` tax-estimation tool, and the
> `TaxParameterConfig` audit-trail default all flow through (or align with) the
> same `NIPARateProvider` baseline."

---

## Introduction

A 2026-06-29 audit of PR #400's original premise found that the bulk of the
data-acquisition work it proposed — BEA API wiring, NIPA-derived rate
computation, `FiscalTaxEstimator` integration — already shipped via
`NIPARateProvider` in `sbir_etl/transformers/fiscal/nipa_rates.py` (339 LOC,
tested in `tests/unit/transformers/fiscal/test_nipa_rates.py`).

This rewrite narrows the spec to the genuine gaps. The original ask for six
NIPA tables (3.4, 3.6, 1.12, 6.2D in addition to 3.2/3.3/1.5) is **out of
scope** — the three tables `NIPARateProvider` already fetches produce all
eight derived rates (`federal_income`, `federal_payroll`, `federal_corporate`,
`federal_excise`, `state_local_income`, `state_local_sales`,
`state_local_property`, `state_local_other`). Add the others in a follow-up if
a downstream consumer asks for the finer-grained breakdown they expose.

---

## User Stories

**As a pipeline engineer,** I want `NIPARateProvider` to persist fetched rates
to `data/reference/bea/nipa_tax_rates.parquet`, so that nightly Dagster runs
and ad-hoc CLI invocations both reuse cached rates instead of paying the BEA
API cost (and BEA quota) every time the process restarts.

**As a Treasury analyst auditing the fiscal-impact methodology,** I want every
runtime tax-rate application to flow through `NIPARateProvider` (year-stamped,
source-tagged `nipa_api` or `nipa_baseline`), so that the audit trail logs the
actual NIPA-derived rate that was applied — not a stale `0.22` flat-rate
literal sitting in a config default.

---

## Requirements

### Requirement 1 — Parquet on-disk cache for `NIPARateProvider`

#### Acceptance Criteria

1. THE System SHALL persist fetched / baseline rates to
   `data/reference/bea/nipa_tax_rates.parquet` (one row per `(year, source)`)
   with columns: `year`, `source` (`nipa_api` | `nipa_baseline`),
   `federal_income_rate`, `federal_payroll_rate`, `federal_corporate_rate`,
   `federal_excise_rate`, `state_local_income_rate`, `state_local_sales_rate`,
   `state_local_property_rate`, `state_local_other_rate`, `fetched_at`
   (UTC timestamp).
2. THE System SHALL, on `NIPARateProvider.get_rates(year)`, check the on-disk
   parquet **before** hitting the BEA API; in-memory cache short-circuits both.
3. THE System SHALL, on a successful API fetch, append (or upsert on
   `(year, source)`) the resulting row to the parquet cache atomically (write to
   temp file + rename) so concurrent processes don't corrupt the cache.
4. THE System SHALL accept a `cache_path` constructor argument
   (default `data/reference/bea/nipa_tax_rates.parquet`) — tests use a
   `tmp_path` override so they don't write to the repo cache.
5. THE System SHALL keep the existing in-memory cache and `_BASELINE_RATES`
   fallback behavior unchanged.

### Requirement 2 — Sensitivity analyzer pulls from `NIPARateProvider`

#### Acceptance Criteria

1. THE System SHALL replace the literal `base_rate = 0.22` in
   `sbir_etl/transformers/fiscal/sensitivity.py:110` (individual income tax) and
   the literal `0.18` at lines 121–122 (corporate income tax) with values pulled
   from a `NIPARateProvider` (`federal_income_rate`, `federal_corporate_rate`).
2. THE System SHALL allow the sensitivity analyzer to accept an injected
   `NIPARateProvider` (default: construct one) so tests can mock rates without
   touching the live BEA API.
3. THE Sensitivity bands SHALL still apply the configured
   `variation_percent` symmetrically around the NIPA-derived center — the
   change replaces the **center**, not the band-width logic.

### Requirement 3 — `mission_c` tax-estimation tool pulls from `NIPARateProvider`

#### Acceptance Criteria

1. THE System SHALL remove the module-level constant
   `INDIVIDUAL_INCOME_TAX_RATE = 0.22` in
   `packages/sbir-analytics/sbir_analytics/tools/mission_c/tax_estimation.py:52`
   and replace its single use site (line 168, `wages * INDIVIDUAL_INCOME_TAX_RATE`)
   with `NIPARateProvider().get_rates(assessment_year).federal_income_rate`.
2. THE System SHALL keep `DEFAULT_EFFECTIVE_TAX_RATES` (the industry-keyed dict
   at lines 38–46) and `PAYROLL_TAX_RATE` (line 50) **unchanged** — they are
   not NIPA-replaceable and live outside this spec's scope.
3. THE System SHALL update `tests/unit/tools/test_mission_c.py:181`
   accordingly — assert the NIPARateProvider-derived rate falls in a sensible
   range, not the literal `0.22`.

### Requirement 4 — `TaxParameterConfig` default reflects NIPA baseline

#### Acceptance Criteria

1. THE System SHALL update
   `sbir_etl/config/schemas/domain.py:196`
   (`TaxParameterConfig.individual_income_tax["effective_rate"]`) from `0.22`
   to `0.194` — the 2022 NIPA-baseline federal income rate already declared in
   `nipa_rates.py:103`.
2. THE System SHALL add an inline comment explaining that
   `TaxParameterConfig` is a static config default used only by
   `fiscal_audit_trail.log_configuration()`; runtime fiscal calculations resolve
   the actual rate via `NIPARateProvider` per-analysis year.
3. THE System SHALL update `tests/unit/config/test_schemas.py:511` to assert
   the new default.

---

## Out of scope

- Adding NIPA tables 3.4, 3.6, 1.12, 6.2D. `NIPARateProvider`'s current three
  tables already produce the eight derived rates downstream consumers use.
  Add them in a follow-up spec if a consumer requests the finer breakdown.
- The industry-effective-tax-rate dict in `mission_c/tax_estimation.py:38-46`.
  Those rates come from IRS Statistics of Income (SOI), not NIPA — different
  spec.
- The hardcoded `PAYROLL_TAX_RATE = 0.153` in
  `mission_c/tax_estimation.py:50`. It's the statutory FICA rate, not an
  effective rate — no NIPA equivalent.
- Wholesale audit-trail rework. `fiscal_audit_trail.log_configuration()`
  continues to log the (now-updated) `TaxParameterConfig` defaults; logging
  the per-analysis NIPA-derived rates alongside is a follow-up if needed.
