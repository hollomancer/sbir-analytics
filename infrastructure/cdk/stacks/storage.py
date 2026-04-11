"""S3 bucket stack for SBIR ETL data storage."""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
)
from constructs import Construct

from stacks.config import S3_BUCKET_NAME


class StorageStack(Stack):
    """S3 bucket for storing SBIR ETL data and artifacts."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Default to importing existing bucket (bucket already exists)
        # Use context variable "create_new_bucket=true" to create a new bucket instead
        create_new = self.node.try_get_context("create_new_bucket") == "true"
        bucket_name = S3_BUCKET_NAME

        if create_new:
            # Create new bucket (will fail if bucket already exists)
            self.bucket = s3.Bucket(
                self,
                "SbirEtlProductionData",
                bucket_name=bucket_name,
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
                    s3.LifecycleRule(
                        id="usaspending-database-dumps",
                        prefix="raw/usaspending/database/",
                        enabled=True,
                        transitions=[
                            # Skip Intelligent Tiering (monitoring overhead not
                            # worth it for a single large ZIP accessed monthly).
                            # Glacier Instant Retrieval: same-day restore at
                            # ~68% lower storage cost than Standard.
                            s3.Transition(
                                storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                                transition_after=Duration.days(30),
                            ),
                        ],
                        expiration=Duration.days(365),
                    ),
                    s3.LifecycleRule(
                        id="validated-data-retention",
                        prefix="validated/",
                        expiration=Duration.days(180),
                        enabled=True,
                    ),
                    s3.LifecycleRule(
                        id="enriched-data-retention",
                        prefix="enriched/",
                        expiration=Duration.days(365),
                        enabled=True,
                    ),
                ],
                removal_policy=RemovalPolicy.RETAIN,  # Don't delete data on stack deletion
            )
        else:
            # Import existing bucket (default - bucket already exists)
            self.bucket = s3.Bucket.from_bucket_name(
                self,
                "SbirEtlProductionData",
                bucket_name=bucket_name,
            )

        # Output bucket name and ARN
        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        CfnOutput(self, "BucketArn", value=self.bucket.bucket_arn)
