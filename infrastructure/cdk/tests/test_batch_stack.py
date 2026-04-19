"""CDK assertions tests for BatchStack."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.batch import BatchStack
from stacks.foundation import FoundationStack

ENV = cdk.Environment(account="123456789012", region="us-east-2")

# Minimal default-VPC context so Vpc.from_lookup doesn't hit AWS during synthesis
VPC_CONTEXT = {
    "vpc-provider:account=123456789012:filter.isDefault=true:region=us-east-2:returnAsymmetricSubnets=true": {
        "vpcId": "vpc-12345",
        "vpcCidrBlock": "172.31.0.0/16",
        "ownerAccountId": "123456789012",
        "availabilityZones": [],
        "subnetGroups": [
            {
                "name": "Public",
                "type": "Public",
                "subnets": [
                    {
                        "subnetId": "subnet-aaa",
                        "cidr": "172.31.0.0/20",
                        "availabilityZone": "us-east-2a",
                        "routeTableId": "rtb-aaa",
                    }
                ],
            }
        ],
    }
}


def _template() -> Template:
    app = cdk.App(context=VPC_CONTEXT)
    foundation = FoundationStack(app, "TestFoundation", env=ENV)
    batch = BatchStack(
        app,
        "TestBatch",
        env=ENV,
        bucket=foundation.bucket,
        neo4j_secret=foundation.neo4j_secret,
    )
    return Template.from_stack(batch)


def test_two_compute_environments():
    template = _template()
    template.resource_count_is("AWS::Batch::ComputeEnvironment", 2)


def test_spot_compute_environment():
    template = _template()
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {
            "ComputeEnvironmentName": "sbir-analytics-batch-spot",
            "ComputeResources": {"Type": "FARGATE_SPOT"},
        },
    )


def test_on_demand_compute_environment():
    template = _template()
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {
            "ComputeEnvironmentName": "sbir-analytics-batch-on-demand",
            "ComputeResources": {"Type": "FARGATE"},
        },
    )


def test_job_queue_name_and_spot_preference():
    template = _template()
    template.has_resource_properties(
        "AWS::Batch::JobQueue",
        {
            "JobQueueName": "sbir-analytics-job-queue",
            "ComputeEnvironmentOrder": Match.array_with(
                [Match.object_like({"Order": 1}), Match.object_like({"Order": 2})]
            ),
        },
    )


def test_four_job_definitions():
    template = _template()
    template.resource_count_is("AWS::Batch::JobDefinition", 4)


def test_usaspending_job_has_ephemeral_storage():
    template = _template()
    template.has_resource_properties(
        "AWS::Batch::JobDefinition",
        {
            "JobDefinitionName": "sbir-analytics-usaspending-extract",
            "ContainerProperties": Match.object_like(
                {"EphemeralStorage": {"SizeInGiB": 200}}
            ),
        },
    )


def test_usaspending_job_memory():
    template = _template()
    template.has_resource_properties(
        "AWS::Batch::JobDefinition",
        {
            "JobDefinitionName": "sbir-analytics-usaspending-extract",
            "ContainerProperties": Match.object_like(
                {
                    "ResourceRequirements": Match.array_with(
                        [Match.object_like({"Type": "MEMORY", "Value": "30720"})]
                    )
                }
            ),
        },
    )


def test_log_group_created_with_retention():
    template = _template()
    template.has_resource_properties(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": "/aws/batch/sbir-analytics",
            "RetentionInDays": 90,
        },
    )


def test_batch_execution_role():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"RoleName": "sbir-analytics-batch-execution-role"},
    )


def test_batch_task_role():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"RoleName": "sbir-analytics-batch-task-role"},
    )


def test_sns_topic_for_notifications():
    template = _template()
    template.resource_count_is("AWS::SNS::Topic", 1)
