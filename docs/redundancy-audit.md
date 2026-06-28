# Redundancy Audit

**Date:** 2026-06-28  
**Scope:** `sbir_etl/`, `packages/sbir-analytics/`, `packages/sbir-graph/`, `packages/sbir-ml/`

---

## HIGH Severity

### 1. Company name normalization — 3 parallel implementations

- `sbir_etl/utils/text_normalization.py:19-113` — canonical version
- `packages/sbir-analytics/sbir_analytics/assets/sbir_neo4j_loading.py:155-175` — reimplements from scratch
- `scripts/data/ucc/matcher.py` — another custom variant with hardcoded `ENHANCED_ABBREVIATIONS`

**Risk:** Inconsistent normalization behavior across enrichment, loading, and matching pipelines.  
**Fix:** Remove the duplicate in `sbir_neo4j_loading.py`; import from `sbir_etl.utils.text_normalization`.

### 2. `_company_id_series()` — duplicated across two ML modules

- `packages/sbir-ml/sbir_ml/transition/analysis/analytics.py:61-103`
- `packages/sbir-ml/sbir_ml/transition/analysis/benchmark_evaluator.py:64-86`

Identical UEI → DUNS → NAME priority logic, same null-value handling (`"None"/"nan"/"NaN"`), same row-index fallback.

**Risk:** Business logic drift when priority rules change — both files must be updated independently.  
**Fix:** Extract to `packages/sbir-ml/sbir_ml/transition/analysis/_utils.py`.

---

## MEDIUM Severity

### 3. `_first_col()` helper — copy-pasted

- `packages/sbir-ml/sbir_ml/transition/analysis/analytics.py:49-58`
- `packages/sbir-ml/sbir_ml/transition/analysis/benchmark_evaluator.py:52-61`

Identical case-insensitive column lookup. Should live alongside the consolidated `_company_id_series()`.

### 4. Nine sync wrapper classes — all identical boilerplate

`sbir_etl/enrichers/sync_wrappers.py` — 9 classes (`SyncUSAspendingClient`, `SyncSAMGovClient`, `SyncSemanticScholarClient`, `SyncFPDSAtomClient`, `SyncORCIDClient`, `SyncOpenCorporatesClient`, `SyncPressWireClient`, `SyncLensPatentClient`, and one more), all inheriting `_SyncFacade` and wrapping each method with `run_sync()`.

**Fix:** A factory function or metaclass would collapse ~300 lines to ~30.

### 5. S3-first fallback pattern — repeated 3 times

- `packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py`
- `packages/sbir-analytics/sbir_analytics/assets/usaspending_ingestion.py`
- `packages/sbir-analytics/sbir_analytics/assets/sam_gov_ingestion.py`

All implement try-S3 → try-local → try-API → fail independently.

**Fix:** Extract to a shared `_load_from_tiered_sources()` helper in `sbir_analytics/utils/`.

### 6. Type coercion utilities — scattered

`_coerce_int()`, `_safe_int()`, `_safe_float()`, `_coerce_to_list_of_str()`, `_coerce_rows()` defined locally in 5+ modules. Should live in `sbir_etl/utils/coercion.py`.

### 7. Validation logic — split across `quality/` and `validators/`

`sbir_etl/quality/checks.py` and `sbir_etl/validators/sbir_awards.py` both validate data with no documented separation of responsibility.

### 8. Abbreviations dictionary — 2–3 copies

Canonical dict in `sbir_etl/enrichers/matching.py`, re-exposed in `text_normalization.py`, hardcoded again in `scripts/data/ucc/matcher.py`.

---

## LOW Severity / Verify Usage

| Module | LOC | Concern |
|---|---|---|
| `sbir_etl/enrichers/patentsview.py` | 657 | Imported in tests; verify production asset usage |
| `sbir_etl/enrichers/fpds_atom.py` | 339 | Has sync wrapper but no confirmed asset call |
| `sbir_etl/ot_consortium/` | multiple | Verify live pipeline vs legacy |

---

## Recommended Priority

1. Remove duplicate normalizer in `sbir_neo4j_loading.py` → import from `text_normalization`
2. Extract `_company_id_series()` + `_first_col()` to shared util in `sbir-ml`
3. Extract S3-fallback ingestion pattern to shared helper
4. Audit `patentsview.py`, `fpds_atom.py`, `ot_consortium/` for production usage before touching
5. Consider sync-wrapper factory if that code changes frequently
