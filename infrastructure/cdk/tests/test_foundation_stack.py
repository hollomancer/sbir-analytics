"""CDK assertions tests for FoundationStack."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.foundation import FoundationStack

ENV = cdk.Environment(account="123456789012", region="us-east-2")


def _template() -> Template:
    app = cdk.App()
    stack = FoundationStack(app, "TestFoundation", env=ENV)
    return Template.from_stack(stack)


def test_s3_bucket_versioning_and_encryption():
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
        },
    )


def test_s3_bucket_blocks_public_access():
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_s3_bucket_lifecycle_has_five_rules():
    template = _template()
    # raw, artifacts, usaspending, validated, enriched
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": Match.array_with(
                    [
                        Match.object_like({"Prefix": "raw/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "artifacts/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "raw/usaspending/database/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "validated/", "Status": "Enabled"}),
                        Match.object_like({"Prefix": "enriched/", "Status": "Enabled"}),
                    ]
                )
            }
        },
    )


def test_github_actions_role_name():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {"RoleName": "sbir-analytics-github-actions"},
    )


def test_github_actions_role_oidc_trust():
    template = _template()
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "RoleName": "sbir-analytics-github-actions",
            "AssumeRolePolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Condition": Match.object_like(
                                    {
                                        "StringEquals": {
                                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                                        },
                                        "StringLike": {
                                            "token.actions.githubusercontent.com:sub": "repo:hollomancer/sbir-analytics:*"
                                        },
                                    }
                                )
                            }
                        )
                    ]
                )
            },
        },
    )
