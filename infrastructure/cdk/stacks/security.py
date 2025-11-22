"""Security stack: IAM roles and Secrets Manager."""

from aws_cdk import (
    CfnOutput,
    Stack,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class SecurityStack(Stack):
    """IAM roles and Secrets Manager for SBIR ETL."""

    def __init__(
        self, scope: Construct, construct_id: str, s3_bucket, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Secret always exists - always import it  # pragma: allowlist secret
        self.neo4j_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "Neo4jAuraSecret",
            secret_name="sbir-analytics/neo4j-aura",  # nosec B106  # This is a secret name/path, not a password value
        )

        # Default to importing existing roles (they may already exist)
        # Use context variable "create_new_resources=true" to create new roles
        create_new = self.node.try_get_context("create_new_resources") == "true"

        if create_new:
            # Create new Lambda execution role
            self.lambda_role = iam.Role(
                self,
                "LambdaExecutionRole",
                role_name="sbir-analytics-lambda-execution-role",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSLambdaBasicExecutionRole"
                    )
                ],
            )

            # S3 permissions for Lambda
            s3_bucket.grant_read_write(self.lambda_role)

            # Secrets Manager permissions for Lambda
            self.lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[
                        f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:sbir-analytics/neo4j-aura*"
                    ],
                )
            )

            # Create new Step Functions execution role
            self.step_functions_role = iam.Role(
                self,
                "StepFunctionsExecutionRole",
                role_name="sbir-analytics-step-functions-execution-role",
                assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            )

            # Lambda invoke permissions for Step Functions
            self.step_functions_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["lambda:InvokeFunction"],
                    resources=["*"],  # Will be restricted to specific functions in Lambda stack
                )
            )

            # CloudWatch Logs permissions for Step Functions
            self.step_functions_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    resources=["*"],
                )
            )

            # Create new GitHub Actions OIDC role
            github_repo = self.node.try_get_context("github_repo") or "YOUR_GITHUB_REPO"
            
            self.github_actions_role = iam.Role(
                self,
                "GitHubActionsRole",
                role_name="sbir-analytics-github-actions-role",
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

            # Step Functions start execution permission for GitHub Actions
            self.github_actions_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["states:StartExecution"],
                    resources=["*"],  # Will be restricted to specific state machine in Step Functions stack
                )
            )

            # CloudWatch Logs read permission for GitHub Actions
            self.github_actions_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:GetLogEvents"],
                    resources=["*"],
                )
            )

        else:
            # Import existing roles (default)
            # Import Lambda execution role
            self.lambda_role = iam.Role.from_role_name(
                self,
                "LambdaExecutionRole",
                role_name="sbir-analytics-lambda-execution-role",
            )

            # Import Step Functions execution role
            self.step_functions_role = iam.Role.from_role_name(
                self,
                "StepFunctionsExecutionRole",
                role_name="sbir-analytics-step-functions-execution-role",
            )

            # Import GitHub Actions role
            self.github_actions_role = iam.Role.from_role_name(
                self,
                "GitHubActionsRole",
                role_name="sbir-analytics-github-actions-role",
            )

        # Output role ARNs
        CfnOutput(self, "LambdaRoleArn", value=self.lambda_role.role_arn)
        CfnOutput(self, "StepFunctionsRoleArn", value=self.step_functions_role.role_arn)
        CfnOutput(self, "GitHubActionsRoleArn", value=self.github_actions_role.role_arn)
        CfnOutput(self, "Neo4jSecretArn", value=self.neo4j_secret.secret_arn)

