#!/usr/bin/env python3
"""AWS CDK app for SBIR ETL infrastructure."""

import os

import aws_cdk as cdk

from stacks.batch import BatchStack, VpcConfig
from stacks.foundation import FoundationStack


def build_app(*, batch_vpc_config: VpcConfig | None = None) -> cdk.App:
    """Build the CDK app, optionally importing explicit VPC attributes."""
    app = cdk.App()

    env = cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-2"),
    )

    foundation = FoundationStack(app, "sbir-analytics-foundation", env=env)

    BatchStack(
        app,
        "sbir-analytics-batch",
        env=env,
        bucket=foundation.bucket,
        neo4j_secret=foundation.neo4j_secret,
        vpc_config=batch_vpc_config,
    )
    return app


if __name__ == "__main__":
    build_app().synth()
