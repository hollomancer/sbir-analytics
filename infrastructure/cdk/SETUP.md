# CDK Setup — one-time AWS prerequisites

These are the manual, one-time resources the stacks expect to exist before you
`cdk deploy`. Day-to-day deployment and the stack overview live in
[README.md](README.md).

## 1. Configure shared names

Stack names, the S3 bucket name, IAM role names, the analysis container image,
and the GitHub repo used for the OIDC trust are constants in
[`stacks/config.py`](stacks/config.py). Edit them there for your own account —
they are not read from CDK context.

## 2. GitHub Actions OIDC provider

So CI can assume an AWS role without storing long-lived keys, create the OIDC
provider once per account (the foundation stack creates the *role* that trusts
it):

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

## 3. Neo4j credentials secret

The foundation stack references (does not create) a Neo4j credentials secret in
Secrets Manager — see `NEO4J_SECRET_NAME` in
[`stacks/config.py`](stacks/config.py). Create it before deploying:

```bash
aws secretsmanager create-secret --name <SECRET_NAME> \
  --secret-string '{"username":"neo4j","password":"..."}'
```

## 4. Analysis container image

The batch job definitions run the image referenced by `ANALYSIS_IMAGE` in
[`stacks/config.py`](stacks/config.py) (published to GHCR). Build and push it
before submitting jobs — see the container build workflow in
`.github/workflows/`.

## 5. Bootstrap and deploy

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2
cdk deploy --all   # foundation first, then batch
```

> **Note:** CDK regenerates `cdk.context.json` on every `synth`/`deploy` run with
> account- and VPC-specific lookup results. That file is listed in
> `.gitignore` — do not commit it; it contains account IDs and VPC topology that
> should not be stored in the repository.
