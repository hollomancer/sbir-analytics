#!/usr/bin/env python3
"""AWS CDK app for SBIR ETL infrastructure."""

import os
from pathlib import Path

import aws_cdk as cdk
from stacks.storage import StorageStack
from stacks.security import SecurityStack
from stacks.batch_stack import BatchStack

app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=app.node.try_get_context("region") or os.environ.get("CDK_DEFAULT_REGION") or "us-east-2",
)

# Stack dependencies:
# Storage -> Security -> Batch

storage_stack = StorageStack(app, "sbir-analytics-storage", env=env)
security_stack = SecurityStack(
    app, "sbir-analytics-security", env=env, s3_bucket=storage_stack.bucket
)

# AWS Batch stack for analysis jobs
batch_stack = BatchStack(
    app,
    "sbir-analytics-batch",
    env=env,
)

app.synth()
