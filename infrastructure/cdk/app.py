#!/usr/bin/env python3
"""AWS CDK app for SBIR ETL infrastructure."""

import subprocess
from pathlib import Path

import aws_cdk as cdk
from stacks.storage import StorageStack
from stacks.security import SecurityStack
from stacks.lambda_stack import LambdaStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.batch_stack import BatchStack

# Prepare Lambda functions before synthesis
project_root = Path(__file__).parent.parent.parent
prepare_script = project_root / "scripts" / "lambda" / "prepare_lambdas.sh"
print("Preparing Lambda functions...")
subprocess.run([str(prepare_script)], check=True)

app = cdk.App()

# Environment configuration
# Use explicit account/region for VPC lookups (required by Batch stack)
import os
env = cdk.Environment(
    account=app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=app.node.try_get_context("region") or os.environ.get("CDK_DEFAULT_REGION") or "us-east-2",
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

# AWS Batch stack for analysis jobs (independent)
batch_stack = BatchStack(
    app,
    "sbir-analytics-batch",
    env=env,
)

app.synth()
