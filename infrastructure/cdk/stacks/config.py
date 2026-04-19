"""Shared constants for SBIR Analytics CDK infrastructure."""

# S3
S3_BUCKET_NAME = "sbir-etl-prod-data"

# Secrets Manager
NEO4J_SECRET_NAME = "sbir-analytics/neo4j"  # nosec B105

# IAM
GITHUB_ACTIONS_ROLE_NAME = "sbir-analytics-github-actions"
BATCH_JOB_EXECUTION_ROLE_NAME = "sbir-analytics-batch-execution-role"
BATCH_JOB_TASK_ROLE_NAME = "sbir-analytics-batch-task-role"

# Batch
BATCH_LOG_GROUP = "/aws/batch/sbir-analytics"
BATCH_JOB_QUEUE_NAME = "sbir-analytics-job-queue"
BATCH_COMPUTE_ENV_SPOT = "sbir-analytics-batch-spot"
BATCH_COMPUTE_ENV_ON_DEMAND = "sbir-analytics-batch-on-demand"
ANALYSIS_IMAGE = "ghcr.io/hollomancer/sbir-analytics-full:latest"

# GitHub
GITHUB_REPO = "hollomancer/sbir-analytics"
