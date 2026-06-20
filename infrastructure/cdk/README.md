# AWS CDK Infrastructure

AWS CDK code for the cloud setup behind this project. This is **my personal
deployment** — it runs the analysis containers on AWS Batch on demand. It is
optional: nothing in the core ETL pipeline requires it, and you do not need AWS
to run the project locally (see the repo root README).

## Architecture

The app (`app.py`) defines two stacks:

1. **`sbir-analytics-foundation`** (`FoundationStack`) — the durable, shared
   resources: an S3 data bucket (`RemovalPolicy.RETAIN`), a GitHub Actions OIDC
   role so CI can assume AWS credentials without long-lived keys, and a
   reference to the Neo4j credentials secret in Secrets Manager.
2. **`sbir-analytics-batch`** (`BatchStack`) — on-demand compute: Fargate
   compute environments (Spot + on-demand), a job queue, the analysis job
   definitions, and SNS notifications. It consumes the bucket and secret from
   the foundation stack, so **foundation must be deployed first.**

Shared names and the container image are constants in
[`stacks/config.py`](stacks/config.py) (S3 bucket name, IAM role names, the
`ghcr.io/...` analysis image, and the GitHub repo for the OIDC trust). Adjust
them there rather than via CDK context.

## Prerequisites

1. An AWS account and the AWS CLI configured (`aws configure`).
2. AWS CDK (`npm install -g aws-cdk`).
3. Python 3.11+ and [`uv`](https://github.com/astral-sh/uv).
4. The one-time AWS resources described in [SETUP.md](SETUP.md) (GitHub OIDC
   provider, the Neo4j secret, and the published analysis image).

## Deploy

```bash
uv sync

# First time per account/region only:
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2

cdk diff                          # review changes
cdk deploy --all                  # or deploy individually, foundation first:
cdk deploy sbir-analytics-foundation
cdk deploy sbir-analytics-batch
```

The account is taken from `CDK_DEFAULT_ACCOUNT` and the region from
`CDK_DEFAULT_REGION` (default `us-east-2`). The batch stack accepts an optional
`--context notification_email=you@example.com` to subscribe an address to its
SNS job notifications.

## Outputs

- `FoundationStack`: `BucketName`, `BucketArn`, `GitHubActionsRoleArn`
- `BatchStack`: `JobQueueName`

Use the role ARN to configure GitHub Actions, and the job-queue name to submit
jobs.

## Fixing a failed deployment

If a stack is stuck in `ROLLBACK_COMPLETE` or `CREATE_FAILED`, delete it before
redeploying:

```bash
aws cloudformation delete-stack --stack-name sbir-analytics-batch --region us-east-2
# wait for deletion, then redeploy
```

## Destroy

```bash
cdk destroy --all
```

The S3 bucket uses `RemovalPolicy.RETAIN`, so it (and your data) survives a
stack destroy and must be removed manually if you really want it gone.
