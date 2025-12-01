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

        # Lambda layer for Python dependencies
        layer_arn = self.node.try_get_context("lambda_layer_arn")
        python_layer = None
        if layer_arn:
            python_layer = lambda_.LayerVersion.from_layer_version_arn(
                self,
                "PythonDependenciesLayer",
                layer_version_arn=layer_arn,
            )

        # USPTO download function - the only Lambda still in use
        # Other functions migrated to GitHub Actions workflows
        func = lambda_.Function(
            self,
            "DownloadUsptoFunction",
            function_name="sbir-analytics-download-uspto",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="lambda_handler.lambda_handler",
            code=lambda_.Code.from_asset(
                str(project_root / "scripts" / "lambda" / "download_uspto")
            ),
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=1024,  # Handles large files (up to 1.8 GB)
            layers=[python_layer] if python_layer else [],
            environment={
                "S3_BUCKET": s3_bucket.bucket_name,
            },
        )
        self.functions["download-uspto"] = func

        CfnOutput(
            self,
            "DownloadUsptoFunctionArn",
            value=func.function_arn,
        )
