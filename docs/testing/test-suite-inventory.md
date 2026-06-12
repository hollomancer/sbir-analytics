# Integration, end-to-end, and validation test inventory

This inventory records the intended execution model for `tests/integration/`, `tests/e2e/`, and
`tests/validation/`. Pytest collection runs separately from test execution in CI so a marker change
or removed principal test is visible before execution. The static suite-integrity tests also reject
concrete `Test*` classes containing only `pass` and pytest modules containing zero executable tests.

## Test categories

| Category | Definition | Normal execution |
| --- | --- | --- |
| Fixture-based integration | Exercises multiple current interfaces using deterministic local fixtures; no live service or restricted dataset is required. | Pull-request CI |
| Service-backed integration | Exercises a live dependency such as Neo4j, S3, or an external API. The test must declare the relevant prerequisite marker. | CI job with the service/credentials, or an explicit skip |
| Real-data validation | Compares behavior or results with approved reference data that is not distributed with the repository. | Explicitly skipped unless prerequisites are mounted |
| Scheduled end-to-end | Exercises a complete pipeline and may be too slow or data-dependent for pull requests. | Weekly/scheduled workflow |

## Module inventory

The counts below are executable test functions/methods, not helper classes or standalone program
assertions.

### Integration

| Module | Tests | Classification / prerequisite |
| --- | ---: | --- |
| `agency_private_capital/test_phase1_pipeline.py` | 2 | Fixture-based integration |
| `extractors/test_contract_extraction_integration.py` | 12 | Fixture-based integration |
| `neo4j/test_multi_key_merge.py` | 4 | Service-backed integration: Neo4j |
| `test_cet_training_and_classification.py` | 1 | Fixture-based integration |
| `test_cet_training_scale.py` | 1 | Fixture-based integration |
| `test_company_categorization_client_injection.py` | 5 | Fixture-based integration |
| `test_configuration_environments.py` | 17 | Fixture-based integration |
| `test_exception_handling.py` | 8 | Fixture-based integration |
| `test_fiscal_assets_integration.py` | 9 | Fixture-based integration |
| `test_fiscal_pipeline_integration.py` | 4 | Fixture-based integration |
| `test_naics_integration.py` | 1 | Fixture-based integration |
| `test_neo4j_client.py` | 16 | Service-backed integration: Neo4j |
| `test_paecter_client.py` | 15 | Fixture-based and explicitly marked service-backed cases |
| `test_patent_etl_integration.py` | 32 | Fixture-based integration |
| `test_phase_iii_retrospective_asset.py` | 2 | Fixture-based integration |
| `test_s3_operations.py` | 10 | Service-backed integration: S3/AWS credentials |
| `test_sam_gov_integration.py` | 4 | Fixture-based integration; obsolete extractor S3 suite removed |
| `test_sbir_ingestion_assets.py` | 1 | Fixture-based integration |
| `test_transition_integration.py` | 16 | Fixture-based integration |
| `test_transition_mvp_chain.py` | 2 | Fixture-based integration against current `sbir_analytics.assets.transition` exports |
| `test_usaspending_iterative_enrichment.py` | 7 | Fixture-based integration |
| `test_uspto_download.py` | 5 | Fixture-based integration |
| `test_uspto_extractor.py` | 1 | Fixture-based integration |

### End-to-end

| Module | Tests | Classification / prerequisite |
| --- | ---: | --- |
| `test_enrichment_job.py` | 1 | Scheduled end-to-end |
| `test_fiscal_stateio_pipeline.py` | 11 | Scheduled end-to-end |
| `test_multi_source_enrichment.py` | 7 | Six fixture-based scheduled tests plus one explicit real-data skip requiring approved snapshots |
| `test_pipeline_validator.py` | 12 | Scheduled end-to-end |
| `transition/test_assets.py` | 4 | Scheduled transition end-to-end |
| `transition/test_cet_effectiveness.py` | 2 | Scheduled transition end-to-end |
| `transition/test_detection_smoke.py` | 3 | Scheduled transition end-to-end |
| `transition/test_graph_queries.py` | 4 | Scheduled/service-backed end-to-end: Neo4j |
| `transition/test_quality_metrics.py` | 4 | Scheduled transition end-to-end |

### Validation

| Module | Tests | Classification / prerequisite |
| --- | ---: | --- |
| `test_fiscal_reference_validation.py` | 12 | Local numerical checks plus one explicit real-data skip requiring the external R reference implementation and approved snapshots |
| `test_categorization_quick.py` | 0 | Standalone operator quick-check program; not a pytest suite |
| `test_patentsview_enrichment.py` | 0 | Standalone service-backed validation CLI; not a pytest suite |

## Test class inventory

Modules shown as `module-level tests only` contain executable test functions without `Test*` classes.

| Module | Test classes |
| --- | --- |
| `tests/integration/agency_private_capital/test_phase1_pipeline.py` | module-level tests only |
| `tests/integration/extractors/test_contract_extraction_integration.py` | `TestContractExtractorStreaming`, `TestExtractFromDump`, `TestContractExtractorEdgeCasesIntegration` |
| `tests/integration/neo4j/test_multi_key_merge.py` | module-level tests only |
| `tests/integration/test_cet_training_and_classification.py` | module-level tests only |
| `tests/integration/test_cet_training_scale.py` | module-level tests only |
| `tests/integration/test_company_categorization_client_injection.py` | module-level tests only |
| `tests/integration/test_configuration_environments.py` | `TestConfigurationEnvironments`, `TestConfigurationValidation` |
| `tests/integration/test_exception_handling.py` | `TestConfigurationErrorHandling`, `TestExceptionRetryability`, `TestExceptionDetailsUsability` |
| `tests/integration/test_fiscal_assets_integration.py` | `TestFiscalDataPreparationAssets`, `TestTaxCalculationAssets`, `TestSensitivityAnalysisAssets`, `TestAssetChecks` |
| `tests/integration/test_fiscal_pipeline_integration.py` | `TestFiscalPipelineIntegration`, `TestPerformanceThresholds` |
| `tests/integration/test_naics_integration.py` | module-level tests only |
| `tests/integration/test_neo4j_client.py` | `TestNeo4jClientConnection`, `TestNeo4jConstraintsAndIndexes`, `TestNeo4jNodeUpsert`, `TestNeo4jRelationships`, `TestNeo4jTransactions` |
| `tests/integration/test_paecter_client.py` | `TestPaECTERClient` |
| `tests/integration/test_patent_etl_integration.py` | `TestExtractorBasicParsing`, `TestTransformerBasicNormalization`, `TestDataQualityValidation`, `TestCompanyLinkageMatcher`, `TestEdgeCasesAndErrors`, `TestBatchProcessing`, `TestEndToEndPipeline`, `TestPerformanceMetrics` |
| `tests/integration/test_phase_iii_retrospective_asset.py` | module-level tests only |
| `tests/integration/test_s3_operations.py` | `TestS3Upload`, `TestS3Download`, `TestS3Fallback`, `TestS3PathBuilding`, `TestS3Permissions` |
| `tests/integration/test_sam_gov_integration.py` | `TestSAMGovExtractorIntegration`, `TestSAMGovAssetIntegration` |
| `tests/integration/test_sbir_ingestion_assets.py` | module-level tests only |
| `tests/integration/test_transition_integration.py` | `TestScoringCorrectness`, `TestDetectorPipeline`, `TestConfigIntegration` |
| `tests/integration/test_transition_mvp_chain.py` | module-level tests only |
| `tests/integration/test_usaspending_iterative_enrichment.py` | `TestFreshnessTrackingCycle`, `TestDeltaDetection`, `TestResumeFlow`, `TestFullIterativeCycle` |
| `tests/integration/test_uspto_download.py` | module-level tests only |
| `tests/integration/test_uspto_extractor.py` | module-level tests only |
| `tests/e2e/test_enrichment_job.py` | module-level tests only |
| `tests/e2e/test_fiscal_stateio_pipeline.py` | `TestFiscalStateIOPipelineE2E`, `TestFiscalDataQualityThresholds` |
| `tests/e2e/test_multi_source_enrichment.py` | `TestMultiSourceEnrichmentPipeline`, `TestRealDataEnrichmentPipeline`, `TestDataSourceIntegrity` |
| `tests/e2e/test_pipeline_validator.py` | `TestPipelineValidator`, `TestValidationModels`, `TestIntegration` |
| `tests/e2e/transition/test_assets.py` | module-level tests only |
| `tests/e2e/transition/test_cet_effectiveness.py` | module-level tests only |
| `tests/e2e/transition/test_detection_smoke.py` | module-level tests only |
| `tests/e2e/transition/test_graph_queries.py` | module-level tests only |
| `tests/e2e/transition/test_quality_metrics.py` | module-level tests only |
| `tests/validation/test_categorization_quick.py` | module-level tests only |
| `tests/validation/test_fiscal_reference_validation.py` | `TestBoundaryConditions`, `TestReasonablenessChecks`, `TestNumericalStability`, `TestReferenceValidation`, `TestSensitivityAnalysis` |
| `tests/validation/test_patentsview_enrichment.py` | module-level tests only |

## Empty-suite decisions

| Former empty suite | Decision | Rationale |
| --- | --- | --- |
| `TestSAMGovS3Integration` | Removed | S3 behavior was removed from `SAMGovExtractor`; the separate S3 operations suite owns supported S3 behavior. |
| Transition MVP shim helper/tests | Replaced | Transition behavior remains supported and is now covered through current exported asset interfaces without a test-installed Dagster shim. |
| `TestReferenceValidation` | Explicit marked skip | The external R implementation and approved reference snapshots are intentionally unavailable in local CI. |
| `TestRealDataEnrichmentPipeline` | Explicit marked skip | Approved production-derived SBIR, USAspending, and SAM.gov snapshots are mounted only by an authorized scheduled workflow. |

## Commands

```bash
# Static suite safeguards
uv run pytest tests/unit/test_test_suite_integrity.py -v

# Collection-only visibility (run separately from execution)
uv run pytest --collect-only tests/integration/ tests/e2e/ tests/validation/ -q

# Fixture-based integration execution
uv run pytest tests/integration/ -m "integration and not slow" -v

# Scheduled end-to-end execution
uv run pytest tests/e2e/ -m "e2e" -v

# Real-data validation (still skips unless documented prerequisites are installed/mounted)
uv run pytest tests/validation/ -m "real_data" -v
```
