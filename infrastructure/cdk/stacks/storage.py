"""S3 bucket stack for SBIR ETL data storage."""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct


class StorageStack(Stack):
    """S3 bucket for storing SBIR ETL data and artifacts."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for production data
        self.bucket = s3.Bucket(
            self,
            "SbirEtlProductionData",
            bucket_name="sbir-etl-production-data",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="raw-data-retention",
                    prefix="raw/",
                    expiration=Duration.days(30),
                    enabled=True,
                ),
                s3.LifecycleRule(
                    id="artifacts-retention",
                    prefix="artifacts/",
                    expiration=Duration.days(90),
                    enabled=True,
                ),
            ],
            removal_policy=RemovalPolicy.RETAIN,  # Don't delete data on stack deletion
        )

        # Output bucket name and ARN
        self.add_output("BucketName", value=self.bucket.bucket_name)
        self.add_output("BucketArn", value=self.bucket.bucket_arn)

