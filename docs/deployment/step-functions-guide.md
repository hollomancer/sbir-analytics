# Step Functions Orchestration Guide

This guide covers the Step Functions state machine that orchestrates the SBIR weekly refresh workflow.

## Overview

The Step Functions state machine (`sbir-etl-weekly-refresh`) orchestrates the entire weekly SBIR awards refresh workflow, replacing the previous GitHub Actions-based workflow.

## State Machine Definition

The state machine is defined in `infrastructure/step-functions/weekly-refresh-state-machine.json`.

### States

1. **DownloadCSV**: Downloads CSV from SBIR.gov and uploads to S3
2. **CheckChanges**: Choice state - checks if data changed or force refresh
3. **ProcessPipeline**: Parallel execution of validation and profiling
4. **IngestionChecks**: Runs Dagster ingestion validation
5. **EnrichmentChecks**: Runs enrichment coverage analysis
6. **ResetNeo4j**: Resets Neo4j database (optional)
7. **LoadNeo4j**: Loads validated awards into Neo4j
8. **SmokeChecks**: Validates Neo4j data integrity
9. **CreatePR**: Creates GitHub PR with results
10. **EndNoChanges**: Success state when no changes detected
11. **ErrorHandler**: Catches and handles errors

## Input Format

```json
{
  "force_refresh": false,
  "source_url": "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
  "s3_bucket": "sbir-etl-production-data"
}
```

## Output Format

```json
{
  "status": "success",
  "execution_arn": "arn:aws:states:...",
  "output": {
    "status": "success",
    "pr_url": "https://github.com/...",
    ...
  }
}
```

## Error Handling

### Retry Policies

Each state has retry policies configured:

```json
{
  "Retry": [
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2.0
    }
  ]
}
```

### Catch Blocks

Error handling via Catch blocks:

```json
{
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "Next": "ErrorHandler",
      "ResultPath": "$.error"
    }
  ]
}
```

## Conditional Logic

The `CheckChanges` state uses Choice state:

```json
{
  "Type": "Choice",
  "Choices": [
    {
      "Variable": "$.body.changed",
      "BooleanEquals": true,
      "Next": "ProcessPipeline"
    },
    {
      "Variable": "$.force_refresh",
      "BooleanEquals": true,
      "Next": "ProcessPipeline"
    }
  ],
  "Default": "EndNoChanges"
}
```

## Parallel Execution

The `ProcessPipeline` state runs validation and profiling in parallel:

```json
{
  "Type": "Parallel",
  "Branches": [
    {
      "StartAt": "ValidateDataset",
      "States": {...}
    },
    {
      "StartAt": "ProfileInputs",
      "States": {...}
    }
  ],
  "Next": "IngestionChecks"
}
```

## Invoking Step Functions

### From GitHub Actions

```yaml
- name: Start Step Functions execution
  run: |
    aws stepfunctions start-execution \
      --state-machine-arn ${{ secrets.STEP_FUNCTIONS_STATE_MACHINE_ARN }} \
      --input '{"force_refresh": false, "s3_bucket": "sbir-etl-production-data"}'
```

### From AWS CLI

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-2:123456789012:stateMachine:sbir-etl-weekly-refresh \
  --input '{"force_refresh": false}'
```

### From Python

```python
import boto3

sf_client = boto3.client('stepfunctions')

response = sf_client.start_execution(
    stateMachineArn='arn:aws:states:us-east-2:123456789012:stateMachine:sbir-etl-weekly-refresh',
    input='{"force_refresh": false}'
)

execution_arn = response['executionArn']
```

## Monitoring

### CloudWatch Logs

Step Functions execution logs are available in CloudWatch:

```
/aws/vendedlogs/states/sbir-etl-weekly-refresh
```

### CloudWatch Metrics

- Execution metrics
- State transition metrics
- Error metrics

### AWS Console

View execution in AWS Console:

```
https://console.aws.amazon.com/states/home?region=us-east-2#/executions/details/{execution-arn}
```

## Querying Execution Status

```bash
# Get execution details
aws stepfunctions describe-execution \
  --execution-arn <execution-arn>

# Get execution history
aws stepfunctions get-execution-history \
  --execution-arn <execution-arn>
```

## Debugging

### Common Issues

1. **Lambda timeout**: Increase Lambda timeout or optimize function
2. **State transition errors**: Check Lambda function logs
3. **Permission errors**: Verify IAM roles have correct permissions
4. **Input/output format**: Ensure JSON structure matches expected format

### Debugging Steps

1. Check execution status in AWS Console
2. Review CloudWatch Logs for each Lambda function
3. Check Step Functions execution history
4. Verify input/output JSON structure

## Cost Optimization

- Use appropriate retry policies (avoid infinite retries)
- Set reasonable timeouts
- Use parallel execution where possible
- Monitor execution duration

## Best Practices

1. **Idempotency**: Ensure Lambda functions are idempotent
2. **Error handling**: Use appropriate retry and catch policies
3. **Logging**: Log important state transitions
4. **Monitoring**: Set up CloudWatch alarms for failures
5. **Testing**: Test state machine with sample inputs

## Testing Locally

Use Step Functions Local for local testing:

```bash
# Install Step Functions Local
docker pull amazon/aws-stepfunctions-local

# Run locally
docker run -p 8083:8083 amazon/aws-stepfunctions-local
```

## Updating the State Machine

1. Update JSON definition file
2. Deploy via CDK:
   ```bash
   cdk deploy sbir-etl-step-functions
   ```
3. Or update manually:
   ```bash
   aws stepfunctions update-state-machine \
     --state-machine-arn <arn> \
     --definition file://weekly-refresh-state-machine.json
   ```

