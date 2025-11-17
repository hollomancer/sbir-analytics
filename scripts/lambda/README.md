# Lambda Functions

This directory contains Lambda functions for the SBIR ETL pipeline.

## Function Structure

Each function is in its own directory:
- `scripts/lambda/{function-name}/lambda_handler.py`

## Functions

### Layer-based Functions (Lightweight)

- **download-csv**: Downloads CSV from SBIR.gov and uploads to S3
- **validate-dataset**: Validates CSV schema and computes hash
- **profile-inputs**: Profiles awards and company CSVs
- **enrichment-checks**: Runs enrichment coverage analysis
- **reset-neo4j**: Resets Neo4j database
- **smoke-checks**: Runs Neo4j smoke checks

### Container-based Functions (Dagster-dependent)

- **ingestion-checks**: Runs SBIR ingestion validation using Dagster assets
- **load-neo4j**: Loads validated awards into Neo4j using Dagster assets

## Building

### Lambda Layer

```bash
./build_layer.sh
```

### Container Images

```bash
export AWS_ACCOUNT_ID=123456789012
./build_containers.sh
```

## Testing

See [`docs/deployment/aws-lambda-setup.md`](../../docs/deployment/aws-lambda-setup.md) for testing guidelines.

## Deployment

Functions are deployed automatically via CDK. To update manually:

```bash
# Package function
cd scripts/lambda/download_csv
zip -r function.zip lambda_handler.py

# Update function code
aws lambda update-function-code \
  --function-name sbir-etl-download-csv \
  --zip-file fileb://function.zip \
  --region us-east-2
```

