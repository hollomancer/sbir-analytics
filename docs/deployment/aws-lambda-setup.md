# Lambda Function Development Guide

This guide covers developing and deploying Lambda functions for the SBIR ETL pipeline.

## Lambda Function Structure

Each Lambda function follows this pattern:

```python
import json
import boto3
from typing import Dict, Any

s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "s3_key": "...",
        ...
    }
    """
    try:
        # Read inputs from event
        # Execute function logic
        # Upload outputs to S3
        # Return results
        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "outputs": {...}
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e)
            }
        }
```

## Packaging Options

### Option A: Lambda Layers (Recommended for Simple Functions)

**Use for**: Functions with standard dependencies (pandas, boto3, neo4j)

**Steps**:

1. Create function code in `scripts/lambda/{function-name}/lambda_handler.py`
2. Build layer:
   ```bash
   ./scripts/lambda/build_layer.sh
   ```
3. Deploy layer:
   ```bash
   aws lambda publish-layer-version \
     --layer-name sbir-etl-python-dependencies \
     --zip-file fileb:///tmp/python-dependencies-layer.zip \
     --compatible-runtimes python3.11
   ```
4. Deploy function (via CDK or manually)

**Pros**: Fast cold starts, easy updates, smaller packages
**Cons**: 250MB layer limit, dependency management complexity

### Option B: Container Images (Recommended for Dagster Functions)

**Use for**: Functions using Dagster or large dependencies

**Steps**:

1. Create Dockerfile in `lambda/containers/{function-name}/Dockerfile`
2. Create `requirements.txt` with dependencies
3. Build and push:
   ```bash
   ./scripts/lambda/build_containers.sh
   ```
4. Deploy function (via CDK)

**Pros**: No size limits, includes all dependencies, easier local testing
**Cons**: Slower cold starts (~1-2s), requires Docker

### Option C: Hybrid Approach

- Use Layers for lightweight functions
- Use Containers for Dagster-dependent functions

## Local Testing

### Mock AWS Services

```python
# Use moto for local testing
from moto import mock_s3, mock_secretsmanager

@mock_s3
@mock_secretsmanager
def test_lambda_function():
    # Set up mock S3 bucket
    s3_client.create_bucket(Bucket='test-bucket')
    
    # Set up mock secret
    secrets_client.create_secret(
        Name='test-secret',
        SecretString='{"uri": "bolt://localhost:7687"}'
    )
    
    # Test Lambda function
    event = {"s3_bucket": "test-bucket", "s3_key": "test.csv"}
    result = lambda_handler(event, None)
    assert result["statusCode"] == 200
```

### Test with SAM Local

```bash
# Install SAM CLI
pip install aws-sam-cli

# Test locally
sam local invoke DownloadCsvFunction --event test-event.json
```

## Environment Variables

Lambda functions use these environment variables:

- `S3_BUCKET`: S3 bucket name
- `NEO4J_SECRET_NAME`: Secrets Manager secret name for Neo4j

## Error Handling

Lambda functions should:

1. Return structured error responses
2. Log errors to CloudWatch
3. Use retry policies in Step Functions
4. Handle transient failures gracefully

Example:

```python
try:
    # Process data
    result = process_data()
    return {"statusCode": 200, "body": {"status": "success", "result": result}}
except ValueError as e:
    # Client error - don't retry
    return {"statusCode": 400, "body": {"status": "error", "error": str(e)}}
except Exception as e:
    # Server error - retry in Step Functions
    print(f"Error: {e}")
    return {"statusCode": 500, "body": {"status": "error", "error": str(e)}}
```

## S3 Integration

### Reading from S3

```python
def read_from_s3(bucket: str, key: str) -> str:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")
```

### Writing to S3

```python
def write_to_s3(bucket: str, key: str, content: str, content_type: str = "text/plain"):
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType=content_type
    )
```

## Secrets Manager Integration

```python
def get_secret(secret_name: str) -> dict:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])
```

## Dagster Integration

For Dagster-dependent functions:

1. Use `build_asset_context()` to create Dagster context
2. Materialize assets directly
3. Handle S3 I/O for intermediate storage
4. Use temporary directories for local processing

Example:

```python
from dagster import build_asset_context
import src.assets.sbir_ingestion as assets_module

# Configure Dagster
config = _make_config(...)
assets_module.get_config = lambda: config

# Materialize asset
context = build_asset_context()
output = assets_module.raw_sbir_awards(context=context)
result = _output_value(output)
```

## Performance Optimization

1. **Cold starts**: Use provisioned concurrency for critical functions
2. **Memory**: Increase memory for CPU-intensive functions
3. **Timeout**: Set appropriate timeouts (15 min default, up to 15 hours)
4. **Parallel processing**: Use Step Functions Parallel state

## Monitoring

### CloudWatch Logs

```bash
# View logs
aws logs tail /aws/lambda/sbir-etl-download-csv --follow
```

### CloudWatch Metrics

- Invocations
- Duration
- Errors
- Throttles

### X-Ray Tracing

Enable X-Ray tracing in CDK:

```python
function = lambda_.Function(
    ...,
    tracing=lambda_.Tracing.ACTIVE
)
```

## Deployment Checklist

- [ ] Function code tested locally
- [ ] Dependencies included in layer or container
- [ ] Environment variables configured
- [ ] IAM permissions correct
- [ ] S3 bucket permissions verified
- [ ] Secrets Manager access configured
- [ ] Timeout and memory settings appropriate
- [ ] Error handling implemented
- [ ] CloudWatch logging enabled

