# State & Local Tax Rates — Tasks

> **Status (2026-07-12):** Requirements 1–3 complete (#402 + refresh CLI PR).
> See [fiscal-tax-impact-v2.md](../fiscal-tax-impact-v2.md) for downstream validation.

## Completed

- [x] 1.1 CSV reference file with source citations (`data/reference/tax/state_effective_rates.csv`)
- [x] 1.2 `StateRateProvider(csv_path=..., year=...)` with hardcoded fallback (#402)
- [x] 1.3 `default_state_rate_provider()` wired into `FiscalTaxEstimator` (#402)
- [x] 1.4 BEA NIPA parquet cache + scrub hardcoded federal rates (#400)
- [x] 1.5 `uv run refresh-state-rates` CLI (Tax Foundation fetch + JSON bundle fallback)

## Remaining — fiscal-tax-impact-v2 Phase 4 (validation)

- [ ] 4.1 Run pipeline on NASEM (2022) SBIR cohort and compare total tax receipts
- [ ] 4.2 Document deviations in `docs/fiscal/validation-report.md`
- [ ] 4.3 Add calibration adjustment factors only if IMPLAN divergence exceeds 20%

## Remaining — maintenance

- [ ] M.1 Annual operator run: `uv run refresh-state-rates --fiscal-year <Y> --fetch`
- [ ] M.2 When `--fetch` parser breaks, transcribe Tax Foundation tables into a
      `--rates-json` bundle and open a PR updating the CSV
- [ ] M.3 Census ASGF property-rate refresh (manual; not covered by Tax Foundation fetch)

## Deferred — Phase 5

- [ ] 5.1 Tax-Calculator / TAXSIM microsimulation integration (see fiscal-tax-impact-v2.md)
