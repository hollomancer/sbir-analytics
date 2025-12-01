"""Lambda functions stack for SBIR ETL."""

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_lambda as lambda_,
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

        project_root = Path(__file__).parent.parent.parent.parent

        # ECR repository removed - container-based Lambda functions migrated to GitHub Actions

        # Lambda functions using Layers (lightweight)
        layer_functions = [
            "download-csv",
            "validate-dataset",
            "profile-inputs",
            "enrichment-checks",
            "reset-neo4j",
            "smoke-checks",
            "trigger-dagster-refresh",  # Simple Lambda to trigger GitHub Actions jobs
            # USPTO download function (unified - replaces 3 separate functions)
            "download-uspto",
            # Note: USAspending database download moved to EC2 automation
            # See: .github/workflows/usaspending-database-download.yml
        ]

        # Create Lambda layer for Python dependencies
        # Note: Layer will be created separately via build script
        layer_arn = self.node.try_get_context("lambda_layer_arn")
        python_layer = None
        if layer_arn:
            python_layer = lambda_.LayerVersion.from_layer_version_arn(
                self,
                "PythonDependenciesLayer",
                layer_version_arn=layer_arn,
            )

        for func_name in layer_functions:
            # Get absolute path to Lambda function code
            # CDK app.py is in infrastructure/cdk/, so go up 2 levels to project root
            # Directory names use underscores, function names use hyphens
            lambda_dir_name = func_name.replace("-", "_")
            lambda_code_path = str(project_root / "scripts" / "lambda" / lambda_dir_name)

            # AWS currently caps Lambda timeout at 15 minutes
            timeout_minutes = 15
            memory_size = 512
            if func_name == "download-uspto":
                # Unified USPTO function handles large files (up to 1.8 GB)
                memory_size = 1024

            func = lambda_.Function(
                self,
                f"{func_name.replace('-', '_').title()}Function",
                function_name=f"sbir-analytics-{func_name}",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="lambda_handler.lambda_handler",
                code=lambda_.Code.from_asset(lambda_code_path),
                role=lambda_role,
                timeout=Duration.minutes(timeout_minutes),
                memory_size=memory_size,
                layers=[python_layer] if python_layer else [],
                environment={
                    "S3_BUCKET": s3_bucket.bucket_name,
                    "NEO4J_SECRET_NAME": "sbir-analytics/neo4j-aura",  # pragma: allowlist secret
                },
            )
            self.functions[func_name] = func

        # Container-based Lambda functions (ingestion-checks, load-neo4j) have been removed.
        # These functions have been migrated to GitHub Actions as the sbir_weekly_refresh_job.
        # See: src/assets/jobs/sbir_weekly_refresh_job.py
        # The weekly refresh workflow should trigger GitHub Actions via API instead of Lambda.

        # Output function ARNs
        for func_name, func in self.functions.items():
            CfnOutput(
                self,
                f"{func_name.replace('-', '_').title()}FunctionArn",
                value=func.function_arn,
            )
