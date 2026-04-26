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
        # CloudFormation: full access for CDK deployments.
        # CDK needs broad CloudFormation permissions (create/update/delete stacks,
        # changesets, exports, etc.) so a wildcard is intentional here.
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
