# USAspending Integration Summary

## Overview

This document captures the initial integration of USAspending data for the SBIR Transition Detection pipeline. The goal of Task 5.2 was to unlock procurement and grant activity for SBIR vendors so downstream components (vendor resolution, scoring, evidence, analytics) have reliable transaction context. The current implementation streams the `transaction_normalized` PostgreSQL dump (13.1 GB `.dat.gz`) directly from removable storage, applying vendor filters and basic contract/grant discrimination to produce a compact working dataset in Parquet format.

- **Source**: `/Volumes/X10 Pro/projects/sbir-etl-data/pruned_data_store_api_dump/5530.dat.gz`
- **Output**: `/Volumes/X10 Pro/projects/sbir-etl-data/contracts_test_sample.parquet` (test run)
- **Records extracted**: 45,577 (subset run with SBIR vendor filters)
- **Purpose**: Provide both procurement contracts (potential Phase III indicators) and SBIR/STTR grant/assistance records for enrichment and analytics.

## Key Enhancements

1. **Vendor Filtering**
   - Loads UEI, DUNS, and canonical company names from `sbir_vendor_filters.json` (16,258 UEI; 21,355 DUNS; 1,000 names).
   - Filters applied during streaming to avoid materializing unrelated transactions.

2. **Contract Identification Logic**
   - Reads both `type` (column 4) and `award_type_code` (column 6) to distinguish procurement vs. assistance.
   - Accepts transactions where type is `B` (IDV) or type `A` combined with award codes starting with `A/B/C/D/IDV`.
   - Retains SBIR/STTR grants intentionally for enrichment; procurement-only filtering can be layered later via configuration.

3. **Competition Type Mapping (Task 5.4)**
   - Added `_parse_competition_type()` translating USAspending `extent_competed` codes to `CompetitionType` enum.
   - Handles FULL, FSS, A&A, CDO (full/open), NONE/NDO (sole source), and limited/restricted patterns; defaults to `other` when data absent.

4. **Vendor Identifier Extraction (Task 5.5)**
   - UEI sourced from column 96 (preferred 12-character) with legacy fallback to column 10.
   - DUNS parsed from legacy field when 9-digit numeric.
   - CAGE code pulled from column 98.
   - Parent organization UEI (column 97) captured for future roll-ups.

5. **Parent Relationship Metadata (Task 5.6 groundwork)**
   - Stores `contract_award_type` (column 100) and `parent_idv_piid` (column 102) inside the metadata payload, enabling later parent/child linking across IDV/BPA task orders.

6. **Batching and Memory Control**
   - Streaming extraction with configurable `batch_size` (default 10 k) to support the full 13 GB dataset without exhausting main memory.
   - Intermediate batches are flushed to Parquet once thresholds are reached.

## Test Run Results (contracts_test_sample.parquet)

| Metric                                   | Value                          |
| ---------------------------------------- | ------------------------------ |
| Records extracted                        | 45,577                         |
| File size                                | 4.6 MB (subset run)            |
| UEI coverage                             | 45,544 (99.9 %)                |
| Vendor name coverage                     | 100 %                          |
| Obligation amount coverage               | 100 %                          |
| Start/action date coverage               | 34.5 % (grants often omit)     |
| SBIR/STTR mentions in description        | 2,004 (4.4 %)                  |
| Research grant patterns (R\*/K\*/DE/NSF) | 35,922 (78.8 %)                |
| Procurement (has CAGE)                   | 93 (0.2 %)                     |

### Representative Samples

- **SBIR Grant** – `R44AG035405`, BRAINSYMPHONICS, LLC (HHS)
- **Research Grant** – `R44HL096214`, Circulite Inc (HHS)
- **Procurement Contract** – `DESC0022441`, ADAMAS NANOTECHNOLOGIES INC (DOE, CAGE present)

## Known Limitations / Next Steps

1. **Procurement Coverage**: Only 93 records in the subset contained a CAGE code (proxy for true procurement). Further filtering (e.g., by `contract_award_type`, `extent_competed`, or agency/vehicle patterns) may boost procurement precision.
2. **Extent Competed Values**: Many grant transactions populate `extent_competed` with FOA IDs (e.g., `PA-22-176`). We retain these for enrichment but may need additional heuristics when computing competition metrics.
3. **Parent Contract Relationships**: Metadata now includes parent IDV PIIDs, but Task 5.6 still needs a dedicated transformer/loader to materialize these relationships.
4. **Dagster Asset (Task 5.7)**: Pending. The asset should handle extraction on removable storage, persist Parquet plus checks JSON, and emit metric metadata for pipeline observability.
5. **Large-Scale Run**: Full dump processing (200 GB) has not yet been executed; current test validates functionality on subset only.

## Usage Notes

- Run the extractor via:
  ```
  poetry run python scripts/extract_federal_contracts.py --subset \
      --output /Volumes/X10\ Pro/projects/sbir-etl-data/contracts_test_sample.parquet
  ```
  Adjust `--full` and `--output` paths as needed. Ensure removable storage remains mounted (`/Volumes/X10 Pro`).

- The generated Parquet dataset lives on external storage to conserve internal disk space. Downstream processes must read from the same volume.

- Consider adding checks JSON for record counts, coverage metrics (UEI, action date), and SBIR mention rate so Task 25.x validation gates can consume consistent quality signals.

## Impact on Downstream Tasks

- **Task 25.2 Vendor Resolver**: Receives enriched transaction set (grants + contracts) with UEI coverage >99 %, enabling wide vendor linkage.
- **Task 25.3 Scoring**: Competition type now populated where available; metadata retains raw values for future tuning.
- **Task 25.4 Evidence**: Contracts/grants supply narrative descriptions useful in evidence bundles.
- **Analytics (Task 12)**: Grants provide baseline award activity; procurement records allow dual-perspective transition rate calculations.
- **Neo4j Loading (Task 13+)**: Parent IDV metadata is ready for graph relationships once loaders are implemented.

This integration establishes the foundational feed required for the Transition Detection MVP while keeping heavy data processing on the external drive for storage efficiency.