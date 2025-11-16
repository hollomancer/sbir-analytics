"""Lambda functions stack for SBIR ETL."""

from aws_cdk import (
    Duration,
    Stack,
    aws_lambda as lambda_,
    aws_ecr as ecr,
)
from constructs import Construct


class LambdaStack(Stack):
    """Lambda functions for SBIR ETL workflow."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        s3_bucket,
        lambda_role,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.functions = {}

        # ECR repository for container images
        ecr_repo = ecr.Repository(
            self,
            "LambdaContainerRepo",
            repository_name="sbir-etl-lambda",
            image_scan_on_push=True,
        )

        # Lambda functions using Layers (lightweight)
        layer_functions = [
            "download-csv",
            "validate-dataset",
            "profile-inputs",
            "enrichment-checks",
            "reset-neo4j",
            "smoke-checks",
            "create-pr",
        ]

        # Create Lambda layer for Python dependencies
        # Note: Layer will be created separately via build script
        python_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "PythonDependenciesLayer",
            layer_version_arn=self.node.try_get_context("lambda_layer_arn") or "",
        )

        for func_name in layer_functions:
            func = lambda_.Function(
                self,
                f"{func_name.replace('-', '_').title()}Function",
                function_name=f"sbir-etl-{func_name}",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler=f"{func_name.replace('-', '_')}.lambda_handler",
                code=lambda_.Code.from_asset(f"scripts/lambda/{func_name}"),
                role=lambda_role,
                timeout=Duration.minutes(15),
                memory_size=512,
                layers=[python_layer] if python_layer.layer_version_arn else [],
                environment={
                    "S3_BUCKET": s3_bucket.bucket_name,
                    "NEO4J_SECRET_NAME": "sbir-etl/neo4j-aura",
                    "GITHUB_SECRET_NAME": "sbir-etl/github-token",
                },
            )
            self.functions[func_name] = func

        # Lambda functions using Container images (Dagster-dependent)
        container_functions = [
            "ingestion-checks",
            "load-neo4j",
        ]

        for func_name in container_functions:
            func = lambda_.Function(
                self,
                f"{func_name.replace('-', '_').title()}Function",
                function_name=f"sbir-etl-{func_name}",
                code=lambda_.Code.from_ecr_image(
                    repository=ecr_repo,
                    tag_or_digest=f"{func_name}:latest",
                ),
                role=lambda_role,
                timeout=Duration.minutes(30),  # Longer timeout for Dagster functions
                memory_size=2048,  # More memory for Dagster
                environment={
                    "S3_BUCKET": s3_bucket.bucket_name,
                    "NEO4J_SECRET_NAME": "sbir-etl/neo4j-aura",
                },
            )
            self.functions[func_name] = func

        # Output function ARNs
        for func_name, func in self.functions.items():
            self.add_output(f"{func_name.replace('-', '_').title()}FunctionArn", value=func.function_arn)

