"""Security stack: IAM roles and Secrets Manager."""

from aws_cdk import (
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

        # Lambda execution role
        self.lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
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
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:sbir-etl/neo4j-aura*"
                ],
            )
        )

        # Step Functions execution role
        self.step_functions_role = iam.Role(
            self,
            "StepFunctionsExecutionRole",
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

        # GitHub Actions OIDC role (for GitHub Actions to invoke Step Functions)
        github_oidc_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            self,
            "GitHubOIDCProvider",
            open_id_connect_provider_arn=f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com",
        )

        self.github_actions_role = iam.Role(
            self,
            "GitHubActionsRole",
            assumed_by=iam.WebIdentityPrincipal(
                github_oidc_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{self.node.try_get_context('github_repo')}:*"
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

        # Secrets Manager secret for Neo4j Aura credentials
        # Note: This creates an empty secret. You'll need to populate it manually or via CLI.
        self.neo4j_secret = secretsmanager.Secret(
            self,
            "Neo4jAuraSecret",
            secret_name="sbir-etl/neo4j-aura",
            description="Neo4j Aura connection credentials for SBIR ETL",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"uri":"","username":"","password":"","database":"neo4j"}',
                generate_string_key="password",
                exclude_characters='"\\',
            ),
        )

        # Output role ARNs
        self.add_output("LambdaRoleArn", value=self.lambda_role.role_arn)
        self.add_output("StepFunctionsRoleArn", value=self.step_functions_role.role_arn)
        self.add_output("GitHubActionsRoleArn", value=self.github_actions_role.role_arn)
        self.add_output("Neo4jSecretArn", value=self.neo4j_secret.secret_arn)

