# Award Export Reader and Consumer Inventory

**Reviewed:** 2026-09-21

This inventory records the active bulk-export paths found before the first
migration. It does not authorize storage moves or bulk consumer rewrites.

## Shared reader contracts

| Path | Current contract | Active consumers | Decision in this slice |
| --- | --- | --- | --- |
| `sbir_etl/extractors/sbir_award_export.py` | Exact ordered 42-column source rows; no normalization or collapse | Phase II source materializer; SBA annual-report study | Canonical raw reader |
| `sbir_etl/extractors/sbir_public_awards.py` | Normalized analytical rows; collapses source editions | tech census, tech-area cohort, NIH RePORTER, procurement-transition reporting | Keep; semantics differ |
| `sbir_etl/extractors/sbir.py` | DuckDB import and query surface; may discover a fallback file | Dagster ingestion, weekly reporting, performance tools | Keep; migrate in a later reviewed slice |
| `sbir_etl/extractors/source_downloads/sbir.py` | Current download plus dated history and small sidecar | source-download Dagster job and local CLI | Update new captures only; do not move old bytes |
| `sbir_etl/capital_events/sources/sbir_awards.py` | Capital-event study view | capital-events builder | Keep study-owned view |
| `sbir_etl/ucc/export_cohort.py` | UCC cohort projection | UCC cohort CLI | Keep study-owned view |

The SBIR.gov API client is not a bulk-export reader and is outside this
inventory.

## Direct path consumers

These maintained scripts name `data/raw/sbir/award_data.csv` directly. They do
not migrate in this slice:

- `sbir_etl/enrichers/nih_reporter/requests.py`
- `sbir_etl/supply_chain/nsf_release.py`
- `scripts/usaspending/extract_sbir_vendors.py`
- `scripts/data/audit_one_firm.py`
- `scripts/data/bootstrap_form_d_leverage_ci.py`
- `scripts/data/build_capital_events.py`
- `scripts/data/build_form_d_control_universe.py`
- `scripts/data/build_headcount_at_award_readout.py`
- `scripts/data/build_local_dod_research_inputs.py`
- `scripts/data/build_nano_cohort.py`
- `scripts/data/build_phase3_prospect_digest.py`
- `scripts/data/build_sbir_bulk_solicitation_links.py`
- `scripts/data/build_sbir_dib_subaward_network.py`
- `scripts/data/find_same_work_awards.py`
- `scripts/data/nano_dark_firm_liveness.py`
- `scripts/data/nano_dark_firm_trademarks.py`
- `scripts/data/nano_subaward_leverage.py`
- `scripts/data/nano_ws1_contract_evidence.py`
- `scripts/data/nano_ws2_resolve_no_uei.py`
- `scripts/data/run_benchmark_analysis.py`
- `scripts/phase3_benchmark/auc_by_target_length.py`
- `scripts/phase3_benchmark/consolidate_selflabeled.py`
- `scripts/phase3_benchmark/dense_vs_sparse_2x2.py`
- `scripts/phase3_benchmark/dod_transition_inventory.py`
- `scripts/phase3_benchmark/dod_within_retrieval.py`
- `scripts/phase3_benchmark/make_join_seed.py`
- `scripts/phase3_benchmark/measure_firm_ranking.py`
- `scripts/phase3_benchmark/recover_award_grain.py`
- `scripts/phase3_benchmark/text_richness_2x2.py`
- `scripts/phase3_benchmark/transition_survival.py`
- `scripts/phase3_groundtruth/resolve_firm_awards.py`

Several scripts use input parameters instead of a literal default and may still
receive the same file. That is another reason not to move or replace existing
storage in this change.

## Provenance implementations

- `sbir_etl.utils.data.file_io.file_sha256` is the only file-digest primitive
  used by the promoted source path.
- `packages/sbir-analytics/.../phase_transition/sbir_gov_source.py` retains its
  Phase II materialization manifest. It now imports the exact raw schema,
  parser, and ordered-schema fingerprint from the canonical extractor.
- `studies/sba-annual-report-tables/award-export-2026-09-17.meta.json` is the
  first complete `AwardExportSourceMetadata` sidecar.

## Search used

The inventory used repository searches for the literal bulk path, `Award Year`,
imports of the three shared readers, and direct CSV or DuckDB reads. Archived
scripts were excluded from the active list. Re-run those searches before any
storage migration because this file is a dated review, not a permanent claim
that no consumers can be added.

## Existing-storage migration plan

This plan is not authorized for execution in this change.

1. Re-run the consumer searches and reconcile the results with live Dagster job
   configuration on the deployment host.
2. Stop source-download and ingestion jobs under the deployment runbook.
3. Copy each legacy vintage into a staging directory. Do not move or symlink the
   original.
4. Generate a complete sidecar from recorded provenance. If a required fact was
   not captured, record it as unknown instead of reconstructing it by guess.
5. Verify source SHA-256, byte count, parsed row count, and ordered schema in
   both locations.
6. Run every active reader named above against the staged path and compare its
   owned outputs.
7. Change one consumer family at a time. Keep the legacy bytes until a full
   operated cycle and rollback check pass.
8. Request separate live-storage authorization before deleting, moving, or
   replacing any legacy path.
