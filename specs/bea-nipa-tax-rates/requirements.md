# Requirements — BEA NIPA Tax Rate Ingestion

> **Status:** Not yet started. BEA API client exists at
> `sbir_etl/transformers/bea_api_client.py`; NIPA endpoints not yet wired.
> Required by **Phase 1** of [../fiscal-tax-impact-v2.md](../fiscal-tax-impact-v2.md).
> Anchors inventory questions **D2** and **D3** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** D2 — jurisdiction-separated fiscal tax receipts from SBIR spending; D3 — NIPA-derived rate credibility vs. hardcoded effective rates
**Answers for:** pipeline engineers (data infrastructure), Treasury / OMB analysts (downstream consumers)
**Complexity tier:** Foundational data acquisition

---

## Done when

> A pipeline engineer can state: "BEA NIPA tables 3.2, 3.3, 3.4, 3.6, 1.12, and 6.2D
> are cached in `data/reference/bea/nipa_tax_rates.parquet`, refreshed quarterly via
> the existing BEA API client. `NIPATaxRateBuilder` produces derived effective rates
> (federal income 12–18%, federal payroll 14–15%, federal corporate 8–14%, state+local)
> with unit tests verifying each rate falls in its expected range."

---

## Introduction

The `FiscalTaxEstimator` in `sbir_etl/transformers/fiscal/taxes.py` currently applies
hardcoded flat effective rates (~22%). The D2 spec (`specs/fiscal-tax-impact-v2.md`)
requires replacing those with rates derived from BEA NIPA tables. This spec covers only
the data acquisition layer: fetching, caching, and computing derived rates from the six
NIPA tables. The downstream estimator replacement is in `specs/fiscal-tax-impact-v2.md`
Phase 2.

The BEA API client (`sbir_etl/transformers/bea_api_client.py`) already handles
authentication and I-O table fetch. NIPA endpoints use the same BEA Data API but
with different `TableName` parameters.

---

## User Stories

**As a pipeline engineer,** I want BEA NIPA tax-rate tables cached locally and
refreshed quarterly, so that the fiscal estimator always uses current-year rates
without requiring a code change when tax law changes.

**As a Treasury analyst,** I want the derived effective rates documented with their
NIPA source table and line, so that the methodology is auditable and I can point GAO
reviewers to the primary BEA data.

---

## Requirements

### Requirement 1 — NIPA table fetch and cache

#### Acceptance Criteria

1. THE System SHALL fetch the following BEA NIPA tables via the existing BEA Data API:
   Table 3.2 (Federal government current receipts), 3.3 (State/local current receipts),
   3.4 (Personal current taxes), 3.6 (Contributions for government social insurance),
   1.12 (National income by type), 6.2D (Compensation by industry — detail).
2. THE System SHALL cache fetched tables to `data/reference/bea/nipa_tax_rates.parquet`
   and refresh on a quarterly schedule (or on-demand via CLI flag).
3. WHEN the BEA API is unreachable, THE System SHALL serve the last cached version and
   emit a staleness warning if the cache is older than 120 days.

### Requirement 2 — Derived effective rate computation

#### Acceptance Criteria

1. THE `NIPATaxRateBuilder` class SHALL compute the following derived rates:
   - Federal income tax rate = Table 3.2 personal tax ÷ Table 1.12 compensation
   - Federal payroll tax rate = Table 3.6 contributions ÷ Table 1.12 compensation
   - Federal corporate tax rate = Table 3.2 corporate tax ÷ Table 1.12 corporate profits
   - State+local rate = Table 3.3 receipts ÷ Table 1.12 total income
2. THE System SHALL validate each derived rate against expected ranges:
   federal income 12–18%, federal payroll 14–15%, federal corporate 8–14%.
   Out-of-range rates SHALL trigger a logged warning (not a hard failure).
3. THE System SHALL attach the source table name, line number, and BEA vintage year
   to each derived rate for audit traceability.

### Requirement 3 — Unit tests with mocked BEA responses

#### Acceptance Criteria

1. THE System SHALL include unit tests in `tests/unit/test_nipa_tax_rate_builder.py`
   using mocked BEA API responses that cover: normal fetch, stale-cache fallback,
   and out-of-range rate warning.
2. Tests SHALL verify that derived rates for a sample year (e.g., 2022) fall within
   the documented expected ranges.
