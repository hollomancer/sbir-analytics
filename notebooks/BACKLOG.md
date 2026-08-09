# Research notebook migration backlog

This inventory applies the notebook-first workflow without turning operational scripts into
notebooks or maintaining two copies of the same calculation.

Status meanings:

- **Companion added** — an example notebook now reads the canonical artifacts and demonstrates the
  investigative workflow.
- **Candidate** — add a notebook when this question is next revisited.
- **Keep automated** — the file is operational, scheduled, mutating, or a verifier; it should not be
  ported to a notebook.

## Wave 1 — companion notebooks added

| Research thread | Existing canonical computation | Notebook |
|---|---|---|
| Technology-area cohort construction and contamination review | `build_tech_area_cohort.py`, `build_nano_cohort.py`, `verify_tech_area_figures.py` | `examples/technology_area_cohort_review.ipynb` |
| Commercialization-channel coverage and overlap | `nano_form_d_temporal.py`, `nano_ws1_contract_evidence.py`, `nano_ws2_resolve_no_uei.py`, `nano_ma_signal.py`, `nano_capture_recapture.py` | `examples/commercialization_channels_review.ipynb` |
| Dark-majority secondary evidence | `nano_dark_firm_liveness.py`, `nano_dark_firm_trademarks.py`, `nano_alias_expanded_evidence.py`, `nano_ws5a_subawards.py`, `nano_capture_recapture.py` | `examples/dark_majority_review.ipynb` |

These notebooks do not replace the scripts. They replace the ad hoc cycle of inspecting CSVs,
running one-off snippets, and manually transferring intermediate observations into prose.

## Wave 2 — convert when next active

| Candidate investigation | Starting source | Suggested notebook focus |
|---|---|---|
| Time to first commercialization signal | `nano_survival_analysis.py` | Censoring choices, channel-specific curves, cutoff sensitivity |
| Acquisition evidence and deal terms | `nano_prime_acquisitions.py`, `nano_prime_edgar_filings.py` | Firm-level evidence review, confidence tiers, outlier diagnostics |
| Subaward leverage | `nano_subaward_leverage.py` | Denominator definitions, dominant-prime sensitivity, firm distributions |
| Dark-firm registry evidence | `nano_ws5b_sam_status.py`, `nano_ws5c_sector_registries.py` | Missingness versus negative evidence, sector coverage |
| Maintenance-fee lapse evidence | `nano_dark_firm_maintenance_lapses.py` | Event timing and alternative liveness definitions |
| Survey frame design | `nano_survey_frame.py` | Stratification balance, sampling diagnostics, seed sensitivity |
| Agency/private-capital comparisons | `run_benchmark_analysis.py` and agency comparison assets | Cohort comparability, weighting, alternative benchmarks |
| Per-firm commercialization audit | `audit_one_firm.py` | Traceable evidence bundle and reviewer annotations |

Do not migrate dormant work merely to change its format. Convert a candidate when a research
question makes it active, using the closest Wave 1 notebook as the template.

## Keep automated — not notebook candidates

- Downloads and external ingestion: `download_sbir.py`, `download_sam_gov.py`,
  `download_uspto.py`, `download_uspto_browser.py`, `extract_b82_patents.py`.
- Refresh and pipeline checks: `profile_sbir_inputs.py`, `awards_refresh_validation.py`,
  `run_sbir_ingestion_checks.py`, `run_sbir_enrichment_check.py`.
- Neo4j operations: `reset_neo4j_sbir.py`, `run_neo4j_sbir_load.py`,
  `run_neo4j_smoke_checks.py`.
- Recurring products and migrations: `weekly_awards_report.py`,
  `build_phase3_prospect_digest.py`, `migrate_nano_report_artifacts.py`.
- Publication verification: `nano_verify_report_figures.py`, `verify_tech_area_figures.py`.

## Promotion queue

Large research scripts should be made library-first when revisited. The notebook is the caller and
narrative—not the destination for another 500–1,000 lines of embedded business logic. In
particular, extract reusable computations from `build_tech_area_cohort.py`,
`nano_prime_acquisitions.py`, and `run_benchmark_analysis.py` before expanding their notebook
companions. Promotion is explicit tier work under `docs/steering/epistemic-tiers.md`; a companion
notebook does not make its source artifacts citable.
