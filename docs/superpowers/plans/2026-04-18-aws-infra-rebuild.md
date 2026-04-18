# AWS Infrastructure Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `infrastructure/cdk/` from three legacy prototype stacks to two clean stacks (`FoundationStack` + `BatchStack`) targeting the correct AWS account (`161066624831`, us-east-2).

**Architecture:** `FoundationStack` owns S3 and the GitHub Actions OIDC role. `BatchStack` takes the bucket and Neo4j secret as constructor args from `FoundationStack` and owns all Batch infrastructure. `app.py` wires them in dependency order.

**Tech Stack:** AWS CDK v2 (Python), `aws_cdk.assertions` for stack unit tests, `uv` for dependency management.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `infrastructure/cdk/cdk.json` | Remove stale `lambda_layer_arn` context key |
| Replace | `infrastructure/cdk/cdk.context.json` | Clear wrong-account VPC cache |
| Modify | `infrastructure/cdk/pyproject.toml` | Add pytest dev dependency |
| Rewrite | `infrastructure/cdk/stacks/config.py` | Clean constants — bucket name, role names, job names |
| Create | `infrastructure/cdk/stacks/foundation.py` | S3 + OIDC role + Secrets Manager ref |
| Create | `infrastructure/cdk/stacks/batch.py` | Fargate compute, job queue, 4 job definitions, SNS |
| Rewrite | `infrastructure/cdk/app.py` | Wire FoundationStack → BatchStack |
| Delete | `infrastructure/cdk/stacks/storage.py` | Replaced by foundation.py |
| Delete | `infrastructure/cdk/stacks/security.py` | Replaced by foundation.py |
| Delete | `infrastructure/cdk/stacks/batch_stack.py` | Replaced by batch.py |
| Create | `infrastructure/cdk/tests/__init__.py` | Test package marker |
| Create | `infrastructure/cdk/tests/test_foundation_stack.py` | CDK assertions for FoundationStack |
| Create | `infrastructure/cdk/tests/test_batch_stack.py` | CDK assertions for BatchStack |

---

## Task 1: Clear stale config and context

**Files:**
- Modify: `infrastructure/cdk/cdk.json`
- Replace: `infrastructure/cdk/cdk.context.json`

- [ ] **Step 1: Remove `lambda_layer_arn` from `cdk.json` context**

Open `infrastructure/cdk/cdk.json`. Remove the `lambda_layer_arn` line from the `context` block. The `context` block should end with:

```json
"context": {
  "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
  "@aws-cdk/core:checkSecretUsage": true,
  "@aws-cdk/core:target-partitions": ["aws", "aws-cn"],
  "@aws-cdk-containers/ecs-service-extensions:enableDefaultLogDriver": true,
  "@aws-cdk/aws-ec2:uniqueImdsv2TemplateName": true,
  "@aws-cdk/aws-ecs:arnFormatIncludesClusterName": true,
  "@aws-cdk/aws-iam:minimizePolicies": true,
  "@aws-cdk/core:validateSnapshotRemovalPolicy": true,
  "@aws-cdk/aws-codepipeline:crossAccountKeyAliasStackSafeResourceName": true,
  "@aws-cdk/aws-s3:createDefaultLoggingPolicy": true,
  "@aws-cdk/aws-sns-subscriptions:restrictSqsDescryption": true,
  "@aws-cdk/aws-apigateway:disableCloudWatchRole": true,
  "@aws-cdk/core:enablePartitionLiterals": true,
  "@aws-cdk/aws-events:eventsTargetQueueSameAccount": true,
  "@aws-cdk/aws-iam:standardizedServicePrincipals": true,
  "@aws-cdk/aws-ecs:disableExplicitDeploymentControllerForCircuitBreaker": true,
  "@aws-cdk/aws-iam:importedRoleStackSafeDefaultPolicyName": true,
  "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": true,
  "@aws-cdk/aws-route53-patters:useCertificate": true,
  "@aws-cdk/customresources:installLatestAwsSdkDefault": false,
  "@aws-cdk/aws-rds:databaseProxyUniqueResourceName": true,
  "@aws-cdk/aws-codedeploy:removeAlarmsFromDeploymentGroup": true,
  "@aws-cdk/aws-apigateway:authorizerChangeDeploymentLogicalId": true,
  "@aws-cdk/aws-ec2:launchTemplateDefaultUserData": true,
  "@aws-cdk/aws-ecs:removeDefaultDeploymentAlarm": true,
  "region": "us-east-2",
  "github_repo": "hollomancer/sbir-analytics"
}
```

- [ ] **Step 2: Clear `cdk.context.json`**

Replace the entire contents of `infrastructure/cdk/cdk.context.json` with:

```json
{}
```

This clears the cached VPC data from the wrong account (`658445659195`). CDK will re-lookup the default VPC on first `cdk synth` against the correct account.

- [ ] **Step 3: Commit**

```bash
cd infrastructure/cdk
git add cdk.json cdk.context.json
git commit -m "fix(infra): clear stale wrong-account context from cdk config"
```

---

## Task 2: Add test infrastructure

**Files:**
- Modify: `infrastructure/cdk/pyproject.toml`
- Create: `infrastructure/cdk/tests/__init__.py`

- [ ] **Step 1: Add pytest to pyproject.toml**

Replace `infrastructure/cdk/pyproject.toml` with:

```toml
[project]
name = "sbir-analytics-infrastructure"
version = "0.1.0"
description = "AWS CDK infrastructure for SBIR ETL pipeline"
requires-python = ">=3.11,<3.13"
dependencies = [
    "aws-cdk-lib>=2.100.0",
    "constructs>=10.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install dev dependencies**

```bash
cd infrastructure/cdk
uv pip install pytest
```

Expected: `Successfully installed pytest-...`

- [ ] **Step 3: Create tests package**

Create `infrastructure/cdk/tests/__init__.py` as an empty file.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/__init__.py
git commit -m "chore(infra): add pytest test infrastructure"
```

---

## Task 3: Rewrite config.py

**Files:**
- Rewrite: `infrastructure/cdk/stacks/config.py`

- [ ] **Step 1: Replace config.py**

Replace the entire contents of `infrastructure/cdk/stacks/config.py` with:

```python
"""Shared constants for SBIR Analytics CDK infrastructure."""

# S3
S3_BUCKET_NAME = "sbir-etl-production-data"

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
```

- [ ] **Step 2: Commit**

```bash
git add stacks/config.py
git commit -m "refactor(infra): clean up config.py — remove dead role names"
```

---

## Task 4: TDD — FoundationStack

**Files:**
- Create: `infrastructure/cdk/tests/test_foundation_stack.py`
- Create: `infrastructure/cdk/stacks/foundation.py`

- [ ] **Step 1: Write failing tests**

Create `infrastructure/cdk/tests/test_foundation_stack.py`:

```python
"""CDK assertions tests for FoundationStack."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.foundation import FoundationStack

ENV = cdk.Environment(account="123456789012", region="us-east-2")


def _template() -> Template:
    app = cdk.App()
    stack = FoundationStack(app, "TestFoundation", env=ENV)
    return Template.from_stack(stack)


def test_s3_bucket_versioning_and_encryption():
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        },
    )


def test_s3_bucket_blocks_public_access():
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_s3_bucket_lifecycle_has_five_rules():
    template = _template()
    # raw, artifacts, usaspending, validated, enriched
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": Match.array_with(
                    [
                        Match.object_like({"Prefix": "raw/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "artifacts/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "raw/usaspending/database/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "validated/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "enriched/", "Status": "Enabled"}),
                    ]
                )
            }
        },
    )


def test_github_actions_role_name():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"RoleName": "sbir-analytics-github-actions"},
    )


def test_github_actions_role_oidc_trust():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "RoleName": "sbir-analytics-github-actions",
            "AssumeRolePolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Condition": Match.object_like(
                                    {
                                        "StringEquals": {
                                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                                        },
                                        "StringLike": {
                                            "token.actions.githubusercontent.com:sub": "repo:hollomancer/sbir-analytics:*"
                                        },
                                    }
                                )
                            }
                        )
                    ]
                )
            },
        },
    )
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd infrastructure/cdk
uv run pytest tests/test_foundation_stack.py -v
```

Expected: `ModuleNotFoundError: No module named 'stacks.foundation'`

- [ ] **Step 3: Implement FoundationStack**

Create `infrastructure/cdk/stacks/foundation.py`:

```python
"""Foundation stack: S3 bucket, GitHub Actions OIDC role, Secrets Manager reference."""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from stacks.config import (
    BATCH_JOB_EXECUTION_ROLE_NAME,
    BATCH_JOB_TASK_ROLE_NAME,
    GITHUB_ACTIONS_ROLE_NAME,
    GITHUB_REPO,
    NEO4J_SECRET_NAME,
    S3_BUCKET_NAME,
)


class FoundationStack(Stack):
    """S3 data bucket, GitHub Actions OIDC role, and Secrets Manager reference."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "SbirEtlData",
            bucket_name=S3_BUCKET_NAME,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="raw-expiry",
                    prefix="raw/",
                    expiration=Duration.days(30),
                    enabled=True,
                ),
                s3.LifecycleRule(
                    id="artifacts-expiry",
                    prefix="artifacts/",
                    expiration=Duration.days(90),
                    enabled=True,
                ),
                s3.LifecycleRule(
                    id="usaspending-glacier",
                    prefix="raw/usaspending/database/",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                            transition_after=Duration.days(30),
                        )
                    ],
                    expiration=Duration.days(365),
                ),
                s3.LifecycleRule(
                    id="validated-expiry",
                    prefix="validated/",
                    expiration=Duration.days(180),
                    enabled=True,
                ),
                s3.LifecycleRule(
                    id="enriched-expiry",
                    prefix="enriched/",
                    expiration=Duration.days(365),
                    enabled=True,
                ),
            ],
        )

        oidc_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            self,
            "GitHubOidcProvider",
            open_id_connect_provider_arn=f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com",
        )

        self.github_actions_role = iam.Role(
            self,
            "GitHubActionsRole",
            role_name=GITHUB_ACTIONS_ROLE_NAME,
            assumed_by=iam.WebIdentityPrincipal(
                oidc_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{GITHUB_REPO}:*",
                    },
                },
            ),
        )

        # S3: object-level access
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                resources=[self.bucket.bucket_arn + "/*"],
            )
        )
        # S3: bucket-level listing
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:ListBucket"],
                resources=[self.bucket.bucket_arn],
            )
        )
        # Batch: job submission and monitoring
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "batch:SubmitJob",
                    "batch:DescribeJobs",
                    "batch:ListJobs",
                    "batch:TerminateJob",
                ],
                resources=[
                    f"arn:aws:batch:{self.region}:{self.account}:job-definition/sbir-analytics-*",
                    f"arn:aws:batch:{self.region}:{self.account}:job-queue/sbir-analytics-*",
                ],
            )
        )
        # Batch: job definition registration (CDK deploys)
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["batch:RegisterJobDefinition"],
                resources=[
                    f"arn:aws:batch:{self.region}:{self.account}:job-definition/sbir-analytics-*"
                ],
            )
        )
        # IAM: PassRole to Batch for task and execution roles
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[
                    f"arn:aws:iam::{self.account}:role/{BATCH_JOB_TASK_ROLE_NAME}",
                    f"arn:aws:iam::{self.account}:role/{BATCH_JOB_EXECUTION_ROLE_NAME}",
                ],
                conditions={"StringEquals": {"iam:PassedToService": "batch.amazonaws.com"}},
            )
        )
        # CloudWatch Logs: read-only for job monitoring
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                ],
                resources=["*"],
            )
        )
        # CloudFormation: full access for CDK deployments
        self.github_actions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudformation:*"],
                resources=["*"],
            )
        )

        # Secrets Manager: reference only — BatchStack calls grant_read()
        self.neo4j_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "Neo4jSecret",
            secret_name=NEO4J_SECRET_NAME,
        )

        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        CfnOutput(self, "BucketArn", value=self.bucket.bucket_arn)
        CfnOutput(self, "GitHubActionsRoleArn", value=self.github_actions_role.role_arn)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd infrastructure/cdk
uv run pytest tests/test_foundation_stack.py -v
```

Expected:
```
PASSED tests/test_foundation_stack.py::test_s3_bucket_versioning_and_encryption
PASSED tests/test_foundation_stack.py::test_s3_bucket_blocks_public_access
PASSED tests/test_foundation_stack.py::test_s3_bucket_lifecycle_has_five_rules
PASSED tests/test_foundation_stack.py::test_github_actions_role_name
PASSED tests/test_foundation_stack.py::test_github_actions_role_oidc_trust
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add stacks/foundation.py tests/test_foundation_stack.py
git commit -m "feat(infra): add FoundationStack — S3 bucket and GitHub Actions OIDC role"
```

---

## Task 5: TDD — BatchStack

**Files:**
- Create: `infrastructure/cdk/tests/test_batch_stack.py`
- Create: `infrastructure/cdk/stacks/batch.py`

- [ ] **Step 1: Write failing tests**

Create `infrastructure/cdk/tests/test_batch_stack.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd infrastructure/cdk
uv run pytest tests/test_batch_stack.py -v
```

Expected: `ModuleNotFoundError: No module named 'stacks.batch'`

- [ ] **Step 3: Implement BatchStack**

Create `infrastructure/cdk/stacks/batch.py`:

```python
"""Batch stack: Fargate compute environments, job queue, job definitions, SNS notifications."""

from dataclasses import dataclass

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_batch as batch,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

from stacks.config import (
    ANALYSIS_IMAGE,
    BATCH_COMPUTE_ENV_ON_DEMAND,
    BATCH_COMPUTE_ENV_SPOT,
    BATCH_JOB_EXECUTION_ROLE_NAME,
    BATCH_JOB_QUEUE_NAME,
    BATCH_JOB_TASK_ROLE_NAME,
    BATCH_LOG_GROUP,
    S3_BUCKET_NAME,
)


@dataclass
class JobConfig:
    """Configuration for a single Batch job definition."""

    id: str
    name: str
    command: list[str]
    vcpus: str = "2"
    memory_mb: str = "4096"
    timeout_seconds: int = 21600
    log_prefix: str = ""
    ephemeral_storage_gib: int | None = None
    extra_env: list[dict] | None = None

    @property
    def log_stream_prefix(self) -> str:
        return self.log_prefix or self.name.split("-")[-1]


_DAGSTER_ENV = [
    {"name": "DAGSTER_LOAD_HEAVY_ASSETS", "value": "true"},
    {"name": "DAGSTER_HOME", "value": "/tmp/dagster_home"},
]

_JOB_CONFIGS = [
    JobConfig(
        id="CETJob",
        name="sbir-analytics-cet-pipeline",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "cet_full_pipeline_job",
        ],
        vcpus="2",
        memory_mb="4096",
        timeout_seconds=21600,
        log_prefix="cet",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="FiscalJob",
        name="sbir-analytics-fiscal-returns",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "fiscal_returns_mvp_job",
        ],
        vcpus="4",
        memory_mb="8192",
        timeout_seconds=14400,
        log_prefix="fiscal",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="PaecterJob",
        name="sbir-analytics-paecter-embeddings",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "paecter_job",
        ],
        vcpus="2",
        memory_mb="4096",
        timeout_seconds=21600,
        log_prefix="paecter",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="UsaspendingExtractJob",
        name="sbir-analytics-usaspending-extract",
        command=[
            "bash", "-c",
            f'cd /app && python scripts/usaspending/download_database.py'
            f' --source-url "${{USASPENDING_URL}}"'
            f" --s3-bucket {S3_BUCKET_NAME}",
        ],
        vcpus="4",
        memory_mb="30720",
        timeout_seconds=28800,
        log_prefix="usaspending-extract",
        ephemeral_storage_gib=200,
    ),
]


class BatchStack(Stack):
    """AWS Batch infrastructure for running analysis jobs on-demand."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket: s3.IBucket,
        neo4j_secret: secretsmanager.ISecret,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "BatchLogGroup",
            log_group_name=BATCH_LOG_GROUP,
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        security_group = ec2.SecurityGroup(
            self,
            "BatchSG",
            vpc=vpc,
            description="SBIR Analytics Batch job security group",
            allow_all_outbound=True,
        )

        execution_role = iam.Role(
            self,
            "BatchExecutionRole",
            role_name=BATCH_JOB_EXECUTION_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        task_role = iam.Role(
            self,
            "BatchTaskRole",
            role_name=BATCH_JOB_TASK_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[bucket.bucket_arn, bucket.bucket_arn + "/*"],
            )
        )
        neo4j_secret.grant_read(task_role)

        compute_spot = batch.CfnComputeEnvironment(
            self,
            "ComputeSpot",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE_SPOT",
                maxv_cpus=8,
                subnets=[s.subnet_id for s in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
            ),
            compute_environment_name=BATCH_COMPUTE_ENV_SPOT,
        )

        compute_on_demand = batch.CfnComputeEnvironment(
            self,
            "ComputeOnDemand",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE",
                maxv_cpus=8,
                subnets=[s.subnet_id for s in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
            ),
            compute_environment_name=BATCH_COMPUTE_ENV_ON_DEMAND,
        )

        job_queue = batch.CfnJobQueue(
            self,
            "JobQueue",
            job_queue_name=BATCH_JOB_QUEUE_NAME,
            priority=1,
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_spot.attr_compute_environment_arn,
                    order=1,
                ),
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_on_demand.attr_compute_environment_arn,
                    order=2,
                ),
            ],
        )

        for job in _JOB_CONFIGS:
            self._define_job(job, task_role, execution_role, log_group)

        notification_topic = sns.Topic(
            self,
            "BatchNotifications",
            display_name="SBIR Analytics Batch Notifications",
        )

        notification_email = self.node.try_get_context("notification_email")
        if notification_email:
            notification_topic.add_subscription(
                subscriptions.EmailSubscription(notification_email)
            )

        events.Rule(
            self,
            "BatchStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.batch"],
                detail_type=["Batch Job State Change"],
                detail={
                    "status": ["SUCCEEDED", "FAILED"],
                    "jobQueue": [job_queue.attr_job_queue_arn],
                },
            ),
            targets=[targets.SnsTopic(notification_topic)],
        )

        CfnOutput(self, "JobQueueName", value=job_queue.job_queue_name)
        CfnOutput(self, "NotificationTopicArn", value=notification_topic.topic_arn)

    def _define_job(
        self,
        config: JobConfig,
        task_role: iam.Role,
        execution_role: iam.Role,
        log_group: logs.LogGroup,
    ) -> batch.CfnJobDefinition:
        env_vars = [
            batch.CfnJobDefinition.EnvironmentProperty(
                name="AWS_DEFAULT_REGION", value=self.region,
            ),
        ]
        for entry in config.extra_env or []:
            env_vars.append(
                batch.CfnJobDefinition.EnvironmentProperty(
                    name=entry["name"], value=entry["value"],
                )
            )

        container_props = batch.CfnJobDefinition.ContainerPropertiesProperty(
            image=ANALYSIS_IMAGE,
            resource_requirements=[
                batch.CfnJobDefinition.ResourceRequirementProperty(
                    type="VCPU", value=config.vcpus,
                ),
                batch.CfnJobDefinition.ResourceRequirementProperty(
                    type="MEMORY", value=config.memory_mb,
                ),
            ],
            job_role_arn=task_role.role_arn,
            execution_role_arn=execution_role.role_arn,
            network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                assign_public_ip="ENABLED",
            ),
            command=config.command,
            environment=env_vars,
            log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                log_driver="awslogs",
                options={
                    "awslogs-group": log_group.log_group_name,
                    "awslogs-stream-prefix": config.log_stream_prefix,
                },
            ),
            **(
                {
                    "ephemeral_storage": batch.CfnJobDefinition.EphemeralStorageProperty(
                        size_in_gib=config.ephemeral_storage_gib,
                    )
                }
                if config.ephemeral_storage_gib
                else {}
            ),
        )

        return batch.CfnJobDefinition(
            self,
            config.id,
            job_definition_name=config.name,
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=container_props,
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(attempts=2),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=config.timeout_seconds,
            ),
        )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd infrastructure/cdk
uv run pytest tests/test_batch_stack.py -v
```

Expected:
```
PASSED tests/test_batch_stack.py::test_two_compute_environments
PASSED tests/test_batch_stack.py::test_spot_compute_environment
PASSED tests/test_batch_stack.py::test_on_demand_compute_environment
PASSED tests/test_batch_stack.py::test_job_queue_name_and_spot_preference
PASSED tests/test_batch_stack.py::test_four_job_definitions
PASSED tests/test_batch_stack.py::test_usaspending_job_has_ephemeral_storage
PASSED tests/test_batch_stack.py::test_usaspending_job_memory
PASSED tests/test_batch_stack.py::test_log_group_created_with_retention
PASSED tests/test_batch_stack.py::test_batch_execution_role
PASSED tests/test_batch_stack.py::test_batch_task_role
PASSED tests/test_batch_stack.py::test_sns_topic_for_notifications
11 passed
```

- [ ] **Step 5: Commit**

```bash
git add stacks/batch.py tests/test_batch_stack.py
git commit -m "feat(infra): add BatchStack — Fargate compute, 4 job definitions, SNS notifications"
```

---

## Task 6: Rewrite app.py and delete old stacks

**Files:**
- Rewrite: `infrastructure/cdk/app.py`
- Delete: `infrastructure/cdk/stacks/storage.py`
- Delete: `infrastructure/cdk/stacks/security.py`
- Delete: `infrastructure/cdk/stacks/batch_stack.py`

- [ ] **Step 1: Rewrite app.py**

Replace the entire contents of `infrastructure/cdk/app.py` with:

```python
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
```

- [ ] **Step 2: Delete old stack files**

```bash
cd infrastructure/cdk
rm stacks/storage.py stacks/security.py stacks/batch_stack.py
```

- [ ] **Step 3: Run full test suite to confirm nothing broken**

```bash
cd infrastructure/cdk
uv run pytest tests/ -v
```

Expected: `16 passed`

- [ ] **Step 4: Verify synthesis**

This requires AWS credentials and the OIDC provider to exist in the account. If you have credentials configured for account `161066624831`:

```bash
cd infrastructure/cdk
uv run cdk synth --all
```

Expected: Two CloudFormation templates printed without errors — `sbir-analytics-foundation` and `sbir-analytics-batch`.

If you don't have credentials available, skip to Step 5.

- [ ] **Step 5: Commit**

```bash
git add app.py stacks/storage.py stacks/security.py stacks/batch_stack.py
git commit -m "feat(infra): wire two-stack CDK app, delete old prototype stacks"
```

Note: `git add` on deleted files stages the deletions.

---

## Task 7: Deploy

Prerequisites: AWS credentials for account `161066624831`, `us-east-2`.

- [ ] **Step 1: Bootstrap CDK (first-time only)**

```bash
cd infrastructure/cdk
uv run cdk bootstrap aws://161066624831/us-east-2
```

Expected: `✅  Environment aws://161066624831/us-east-2 bootstrapped.`

If already bootstrapped: `Environment aws://161066624831/us-east-2 is up-to-date`

- [ ] **Step 2: Deploy FoundationStack**

```bash
cd infrastructure/cdk
uv run cdk deploy sbir-analytics-foundation
```

Expected: prompts for IAM changes confirmation. Review the OIDC role and S3 bucket, then confirm with `y`.

Outputs to note:
```
sbir-analytics-foundation.BucketName = sbir-etl-production-data
sbir-analytics-foundation.BucketArn = arn:aws:s3:::sbir-etl-production-data
sbir-analytics-foundation.GitHubActionsRoleArn = arn:aws:iam::161066624831:role/sbir-analytics-github-actions
```

- [ ] **Step 3: Deploy BatchStack**

```bash
cd infrastructure/cdk
uv run cdk deploy sbir-analytics-batch
```

Expected: prompts for IAM and compute environment confirmation. Confirm with `y`.

- [ ] **Step 4: Update GitHub secret**

Copy the `GitHubActionsRoleArn` output from Step 2.

Go to: `https://github.com/hollomancer/sbir-analytics/settings/secrets/actions`

Update `AWS_ROLE_ARN` to the new ARN: `arn:aws:iam::161066624831:role/sbir-analytics-github-actions`

- [ ] **Step 5: Smoke test — trigger ETL pipeline**

Manually trigger `.github/workflows/etl-pipeline.yml` with `job: sbir_weekly_refresh` and `environment: production`. Verify the "Configure AWS credentials" step succeeds and S3 access works.

- [ ] **Step 6: Commit context update**

After deploying, CDK updates `cdk.context.json` with the looked-up VPC data. Commit this:

```bash
cd infrastructure/cdk
git add cdk.context.json
git commit -m "chore(infra): update CDK context after first deploy"
```
