#!/usr/bin/env python3
"""Credential-free CDK app entry point for CI template validation."""

from app import build_app
from stacks.batch import VpcConfig

OFFLINE_VPC = VpcConfig(
    vpc_id="vpc-00000000000000000",
    availability_zones=("us-east-2a",),
    public_subnet_ids=("subnet-00000000000000000",),
    public_subnet_route_table_ids=("rtb-00000000000000000",),
)

build_app(batch_vpc_config=OFFLINE_VPC).synth()
