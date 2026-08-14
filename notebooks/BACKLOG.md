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

## Wave 2 — companion notebooks added

| Candidate investigation | Starting source | Notebook |
|---|---|---|
| Time to first commercialization signal | `nano_survival_analysis.py` | `examples/time_to_first_signal_review.ipynb` |
| Acquisition evidence and deal terms | `nano_prime_acquisitions.py`, `nano_prime_edgar_filings.py` | `examples/prime_acquisitions_review.ipynb` |
| Subaward leverage | `nano_subaward_leverage.py` | `examples/subaward_leverage_review.ipynb` |
| Dark-firm registry evidence | `nano_ws5b_sam_status.py`, `nano_ws5c_sector_registries.py` | `examples/dark_firm_registry_evidence_review.ipynb` |
| Maintenance-fee lapse evidence | `nano_dark_firm_maintenance_lapses.py` | `examples/maintenance_fee_lapse_review.ipynb` |
| Survey frame design | `nano_survey_frame.py` | `examples/survey_frame_review.ipynb` |
| Agency/private-capital comparisons | `run_benchmark_analysis.py` and agency comparison assets | `examples/agency_private_capital_review.ipynb` |
| Per-firm commercialization audit | `audit_one_firm.py` | `examples/firm_commercialization_audit_review.ipynb` |

As in Wave 1, these are companion views over the canonical artifacts — the scripts remain
the repeatable computation layer, and each notebook degrades to a "run the generator first"
message when an artifact is absent.

## Active explorations

Question-driven work under `notebooks/explorations/`. These are not companions to a
canonical generator; they stay `exploratory` and non-citable until explicitly promoted.

| Investigation | Question | Notebook | Status |
|---|---|---|---|
| STTR partner-type × commercialization channels | B1 / B3 — among STTR Phase II firms, do observed Phase III / Form D / M&A rates differ by a coarse RI partner-type heuristic? | `explorations/b1_sttr_partner_type_commercialization.ipynb` | Active. Not RQ2; not the frozen partner-type classifier. |
| STTR spinout-vs-subcontract (RQ1) data availability | B2/RQ1 (spec-local anchor, distinct from the canonical B2) — is the public data the frozen classification cascade would consume actually present locally, independent of the `open-questions.md` freeze gate? | `explorations/sttr_rq1_data_availability.ipynb` | Active. Input-availability probe only; does not implement or run the cascade. |

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
