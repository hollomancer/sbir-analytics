"""Security stack: IAM roles and Secrets Manager."""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from stacks.config import (
    BATCH_JOB_EXECUTION_ROLE_NAME,
    BATCH_JOB_TASK_ROLE_NAME,
    EXISTING_GITHUB_ACTIONS_ROLE_NAME,
    EXISTING_LAMBDA_ROLE_NAME,
    EXISTING_STEP_FUNCTIONS_ROLE_NAME,
    GITHUB_ACTIONS_ROLE_NAME,
    LAMBDA_ROLE_NAME,
    NEO4J_SECRET_NAME,
    STEP_FUNCTIONS_ROLE_NAME,
)


class SecurityStack(Stack):
    """IAM roles and Secrets Manager for SBIR ETL."""

    def __init__(self, scope: Construct, construct_id: str, s3_bucket, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Secret always exists - always import it  # pragma: allowlist secret
        self.neo4j_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "Neo4jSecret",
            secret_name=NEO4J_SECRET_NAME,  # nosec B106  # This is a secret name/path, not a password value
        )

        create_new = self.node.try_get_context("create_new_resources") == "true"

        if create_new:
            self._create_new_roles(s3_bucket)
        else:
            self._import_existing_roles()

        # Batch registration policy (needed for both create and import paths)
        self._add_batch_registration_policy(create_new)

        # Outputs
        CfnOutput(self, "LambdaRoleArn", value=self.lambda_role.role_arn)
        CfnOutput(self, "StepFunctionsRoleArn", value=self.step_functions_role.role_arn)
        CfnOutput(self, "GitHubActionsRoleArn", value=self.github_actions_role.role_arn)
        CfnOutput(self, "Neo4jSecretArn", value=self.neo4j_secret.secret_arn)

    def _create_new_roles(self, s3_bucket) -> None:
        """Create all IAM roles from scratch."""
        # Lambda execution role
        self.lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            role_name=LAMBDA_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        s3_bucket.grant_read_write(self.lambda_role)
        self.neo4j_secret.grant_read(self.lambda_role)

        # Step Functions execution role
        self.step_functions_role = iam.Role(
            self, "StepFunctionsExecutionRole",
            role_name=STEP_FUNCTIONS_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=["*"],
            )
        )
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                resources=["*"],
            )
        )

        # GitHub Actions OIDC role
        github_repo = self.node.try_get_context("github_repo") or "YOUR_GITHUB_REPO"
        self.github_actions_role = iam.Role(
            self, "GitHubActionsRole",
            role_name=GITHUB_ACTIONS_ROLE_NAME,
            assumed_by=iam.WebIdentityPrincipal(
                f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com",
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repo}:*"
                    },
                },
            ),
        )
        self._add_github_actions_policies()

    def _import_existing_roles(self) -> None:
        """Import pre-existing IAM roles."""
        self.lambda_role = iam.Role.from_role_name(
            self, "LambdaExecutionRole", role_name=EXISTING_LAMBDA_ROLE_NAME,
        )
        self.step_functions_role = iam.Role.from_role_name(
            self, "StepFunctionsExecutionRole", role_name=EXISTING_STEP_FUNCTIONS_ROLE_NAME,
        )
        self.github_actions_role = iam.Role.from_role_name(
            self, "GitHubActionsRole", role_name=EXISTING_GITHUB_ACTIONS_ROLE_NAME,
        )

    def _add_github_actions_policies(self) -> None:
        """Add all policies to the GitHub Actions role."""
        policies = [
            # Step Functions
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["states:StartExecution"],
                resources=["*"],
            ),
            # Lambda layers
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:PublishLayerVersion", "lambda:GetLayerVersion", "lambda:DeleteLayerVersion"],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:layer:sbir-analytics-*"],
            ),
            # CloudWatch Logs (read)
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:GetLogEvents"],
                resources=["*"],
            ),
            # CloudFormation (CDK deployments)
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudformation:*"],
                resources=["*"],
            ),
            # AWS Batch
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["batch:SubmitJob", "batch:DescribeJobs", "batch:ListJobs", "batch:TerminateJob"],
                resources=[
                    f"arn:aws:batch:{self.region}:{self.account}:job-definition/sbir-analytics-analysis-*",
                    f"arn:aws:batch:{self.region}:{self.account}:job-queue/sbir-analytics-analysis-*",
                ],
            ),
            # ECR auth (no resource-level permissions)
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            ),
            # ECR repository
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage",
                    "ecr:CompleteLayerUpload", "ecr:GetDownloadUrlForLayer",
                    "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
                ],
                resources=[f"arn:aws:ecr:{self.region}:{self.account}:repository/sbir-analytics-analysis-jobs"],
            ),
        ]
        for policy in policies:
            self.github_actions_role.add_to_policy(policy)

    def _add_batch_registration_policy(self, create_new: bool) -> None:
        """Add Batch RegisterJobDefinition + PassRole policy to GitHub Actions role."""
        statements = [
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["batch:RegisterJobDefinition"],
                resources=[f"arn:aws:batch:{self.region}:{self.account}:job-definition/sbir-analytics-*"],
            ),
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[
                    f"arn:aws:iam::{self.account}:role/{BATCH_JOB_TASK_ROLE_NAME}",
                    f"arn:aws:iam::{self.account}:role/{BATCH_JOB_EXECUTION_ROLE_NAME}",
                ],
                conditions={"StringEquals": {"iam:PassedToService": "batch.amazonaws.com"}},
            ),
        ]

        if create_new:
            for stmt in statements:
                self.github_actions_role.add_to_policy(stmt)
        else:
            # For imported roles, must create a separate policy
            iam.Policy(
                self, "GitHubActionsBatchRegisterPolicy",
                statements=statements,
                roles=[self.github_actions_role],
            )
