"""Lambda functions stack for SBIR ETL."""

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_ecr as ecr,
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

        # ECR repository for container images
        # Import existing repository if it exists, otherwise create new
        import_existing_ecr = self.node.try_get_context("import_existing_ecr") == "true"
        if import_existing_ecr:
            ecr_repo = ecr.Repository.from_repository_name(
                self,
                "LambdaContainerRepo",
                repository_name="sbir-etl-lambda",
            )
        else:
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
            # USPTO download functions
            "download-uspto-patentsview",
            "download-uspto-assignments",
            "download-uspto-ai-patents",
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

            # AWS currently caps Lambda timeout at 15 minutes, so USPTO download
            # functions cannot request the 30 minutes noted in the spec.
            timeout_minutes = 15
            memory_size = 512 if not func_name.startswith("download-uspto") else 1024

            func = lambda_.Function(
                self,
                f"{func_name.replace('-', '_').title()}Function",
                function_name=f"sbir-etl-{func_name}",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="lambda_handler.lambda_handler",
                code=lambda_.Code.from_asset(lambda_code_path),
                role=lambda_role,
                timeout=Duration.minutes(timeout_minutes),
                memory_size=memory_size,
                layers=[python_layer] if python_layer else [],
                environment={
                    "S3_BUCKET": s3_bucket.bucket_name,
                    "NEO4J_SECRET_NAME": "sbir-etl/neo4j-aura",
                },
            )
            self.functions[func_name] = func

        # Lambda functions using Container images (Dagster-dependent)
        # Only create if container images are available (built via GitHub Actions)
        create_container_functions = (
            self.node.try_get_context("create_container_functions") != "false"
        )
        container_functions = [
            "ingestion-checks",
            "load-neo4j",
        ]

        if create_container_functions:
            for func_name in container_functions:
                # Container-based Lambda functions using DockerImageFunction
                # DockerImageFunction accepts EcrImageCode directly
                func = lambda_.DockerImageFunction(
                    self,
                    f"{func_name.replace('-', '_').title()}Function",
                    function_name=f"sbir-etl-{func_name}",
                    code=lambda_.DockerImageCode.from_ecr(
                        repository=ecr_repo,
                        tag_or_digest=f"{func_name}:latest",
                    ),
                    role=lambda_role,
                    timeout=Duration.minutes(15),
                    memory_size=2048,  # More memory for Dagster
                    environment={
                        "S3_BUCKET": s3_bucket.bucket_name,
                        "NEO4J_SECRET_NAME": "sbir-etl/neo4j-aura",
                    },
                )
                self.functions[func_name] = func

        # Output function ARNs
        for func_name, func in self.functions.items():
            CfnOutput(
                self,
                f"{func_name.replace('-', '_').title()}FunctionArn",
                value=func.function_arn,
            )
