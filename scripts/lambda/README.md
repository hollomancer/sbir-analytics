# Lambda Functions

AWS Lambda functions for SBIR ETL data operations.

## Active Functions

### download_uspto

Downloads USPTO patent data files to S3. Invoked by the data-refresh workflow.

- **Runtime**: Python 3.11
- **Memory**: 1024 MB
- **Timeout**: 15 minutes
- **Trigger**: GitHub Actions workflow (`data-refresh.yml`)

## Shared Code

### common/

Shared utilities used by Lambda functions:
- S3 operations
- Logging configuration
- Error handling

## Build Scripts

- `build_layer.sh` - Builds the Python dependencies Lambda layer
- `build_containers.sh` - Builds container images (legacy, unused)
- `prepare_lambdas.sh` - Prepares Lambda deployment packages

## Deployment

Lambda functions are deployed via CDK:

```bash
cd infrastructure/cdk
cdk deploy sbir-analytics-lambda
```

## Migrated Functions

The following functions were migrated to GitHub Actions workflows:

- `download-csv` → `data-refresh.yml` (SBIR refresh)
- `validate-dataset` → `etl-pipeline.yml`
- `profile-inputs` → `etl-pipeline.yml`
- `enrichment-checks` → `etl-pipeline.yml`
- `reset-neo4j` → Manual operation
- `smoke-checks` → `ci.yml`
- `check-usaspending-file` → `scripts/usaspending/check_new_file.py`
