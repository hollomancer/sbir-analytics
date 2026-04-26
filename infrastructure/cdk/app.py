#!/usr/bin/env python3
"""AWS CDK app for SBIR ETL infrastructure."""

import os

import aws_cdk as cdk

from stacks.batch import BatchStack
from stacks.foundation import FoundationStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT", "161066624831"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-2"),
)

foundation = FoundationStack(app, "sbir-analytics-foundation", env=env)

BatchStack(
    app,
    "sbir-analytics-batch",
    env=env,
    bucket=foundation.bucket,
    neo4j_secret=foundation.neo4j_secret,
)

app.synth()
