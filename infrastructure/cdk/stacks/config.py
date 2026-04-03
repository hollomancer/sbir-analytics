"""Shared constants for SBIR Analytics CDK infrastructure."""

# S3
S3_BUCKET_NAME = "sbir-etl-production-data"

# Secrets Manager
NEO4J_SECRET_NAME = "sbir-analytics/neo4j"  # nosec B105  # Secret path, not a password

# AWS Batch
BATCH_LOG_GROUP = "/aws/batch/sbir-analytics-analysis"
BATCH_COMPUTE_ENV_NAME = "sbir-analytics-analysis-compute-env"
BATCH_JOB_QUEUE_NAME = "sbir-analytics-analysis-job-queue"
ANALYSIS_IMAGE = "ghcr.io/hollomancer/sbir-analytics-full:latest"

# IAM role names (used when creating new roles)
LAMBDA_ROLE_NAME = "sbir-analytics-lambda-execution-role"
STEP_FUNCTIONS_ROLE_NAME = "sbir-analytics-step-functions-execution-role"
GITHUB_ACTIONS_ROLE_NAME = "sbir-analytics-github-actions-role"
BATCH_JOB_EXECUTION_ROLE_NAME = "sbir-analytics-batch-job-execution-role"
BATCH_JOB_TASK_ROLE_NAME = "sbir-analytics-batch-job-task-role"

# IAM role names (used when importing existing roles)
EXISTING_LAMBDA_ROLE_NAME = "sbir-etl-lambda-execution-role"
EXISTING_STEP_FUNCTIONS_ROLE_NAME = "sbir-etl-step-functions-execution-role"
EXISTING_GITHUB_ACTIONS_ROLE_NAME = "sbir-etl-github-actions-role"
