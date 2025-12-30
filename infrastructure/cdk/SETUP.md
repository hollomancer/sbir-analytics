# CDK Setup Instructions

## Quick Start

1. **Set GitHub repository in cdk.json**:

   ```json
   {
     "context": {
       "github_repo": "your-username/sbir-analytics"
     }
   }
   ```

2. **Sync dependencies**:

   ```bash
   uv sync
   ```

3. **Bootstrap CDK** (first time only):

   ```bash
   AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2
   ```

4. **Deploy**:

   ```bash
   cdk deploy --all
   ```

## Context Variables

Set these in `cdk.json` or pass via `--context`:

- `github_repo`: Your GitHub repository (format: `owner/repo`)
- `lambda_layer_arn`: ARN of the Lambda layer (set after creating the layer)
- `account`: AWS account ID (auto-detected from AWS CLI)
- `region`: AWS region (default: `us-east-2`)

Example:

```bash
cdk deploy --all --context github_repo=your-username/sbir-analytics
```

## Before Deploying

1. Create OIDC provider (if not exists):

   ```bash
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
     --region us-east-2
   ```

2. Create secrets in Secrets Manager (see main setup guide)

3. Build and publish Lambda layer

4. Build and push container images to ECR
