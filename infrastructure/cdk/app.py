#!/usr/bin/env python3
"""AWS CDK app for SBIR ETL infrastructure."""

import aws_cdk as cdk
from stacks.storage import StorageStack
from stacks.security import SecurityStack
from stacks.lambda_stack import LambdaStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.batch_stack import BatchStack

app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-2",
)

# Stack dependencies:
# Storage -> Security -> Lambda -> Step Functions
# Batch (independent, but relies on Security for GitHub Actions role updates)

storage_stack = StorageStack(app, "sbir-analytics-storage", env=env)
security_stack = SecurityStack(
    app, "sbir-analytics-security", env=env, s3_bucket=storage_stack.bucket
)
lambda_stack = LambdaStack(
    app,
    "sbir-analytics-lambda",
    env=env,
    s3_bucket=storage_stack.bucket,
    lambda_role=security_stack.lambda_role,
)
step_functions_stack = StepFunctionsStack(
    app,
    "sbir-analytics-step-functions",
    env=env,
    lambda_functions=lambda_stack.functions,
    execution_role=security_stack.step_functions_role,
)

# AWS Batch stack for ML jobs (independent)
batch_stack = BatchStack(
    app,
    "sbir-analytics-batch",
    env=env,
)

app.synth()
