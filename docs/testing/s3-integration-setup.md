# S3 Integration Testing Setup

## Overview

S3 integration tests validate real AWS S3 operations to catch issues that mocked tests can't detect (permissions, regions, IAM policies, etc.).

**Cost**: ~$0.01/month
**Duration**: 2-3 minutes per run
**Frequency**: Every PR (when AWS credentials available)

## Prerequisites

### 1. Create Test S3 Bucket

```bash
# Create test bucket (one-time setup)
aws s3 mb s3://sbir-analytics-test --region us-east-2

# Enable versioning (optional, for safety)
aws s3api put-bucket-versioning \
  --bucket sbir-analytics-test \
  --versioning-configuration Status=Enabled

# Add lifecycle policy to auto-delete test files after 7 days
cat > /tmp/lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "Id": "DeleteTestFilesAfter7Days",
      "Status": "Enabled",
      "Prefix": "test/",
      "Expiration": {
        "Days": 7
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket sbir-analytics-test \
  --lifecycle-configuration file:///tmp/lifecycle.json
```

### 2. Create IAM Role for CI

```bash
# Create trust policy for GitHub Actions OIDC
cat > /tmp/trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/sbir-analytics:*"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name GitHubActions-SBIR-Test \
  --assume-role-policy-document file:///tmp/trust-policy.json

# Create policy for test bucket access
cat > /tmp/test-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::sbir-analytics-test",
        "arn:aws:s3:::sbir-analytics-test/*"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name GitHubActions-SBIR-Test \
  --policy-name S3TestAccess \
  --policy-document file:///tmp/test-policy.json
```

### 3. Configure GitHub Secrets

Add to repository secrets (Settings → Secrets and variables → Actions):

```
AWS_TEST_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActions-SBIR-Test
```

## Local Testing

### With AWS Credentials

```bash
# Set environment variables
export TEST_S3_BUCKET=sbir-analytics-test
export AWS_PROFILE=your-profile  # or use AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY

# Run S3 integration tests
make test-s3

# Or directly with pytest
uv run pytest tests/integration/test_s3_operations.py -v -m s3
```

### Without AWS Credentials

Tests will be skipped automatically:

```bash
$ make test-s3
⚠️  AWS credentials not available, skipping S3 integration tests
```

## CI Behavior

### When Tests Run

- ✅ Every PR (when AWS credentials available)
- ✅ Every push to main
- ✅ Manual workflow dispatch
- ⏭️ Skipped on docs-only changes
- ⏭️ Skipped when `skip-cloud-tests` label present

### When Tests Are Skipped

- External PRs (no access to secrets)
- PRs with `skip-cloud-tests` label
- Docs-only changes

### Graceful Degradation

```yaml
- name: Configure AWS credentials
  continue-on-error: true  # Don't fail if credentials unavailable
  id: aws-creds
  uses: aws-actions/configure-aws-credentials@v5

- name: Run S3 integration tests
  if: steps.aws-creds.outcome == 'success'  # Only run if credentials available
```

## Troubleshooting

### Tests Fail with "Access Denied"

**Cause**: IAM role doesn't have required permissions

**Fix**:
```bash
# Verify role policy
aws iam get-role-policy \
  --role-name GitHubActions-SBIR-Test \
  --policy-name S3TestAccess

# Update policy if needed
aws iam put-role-policy \
  --role-name GitHubActions-SBIR-Test \
  --policy-name S3TestAccess \
  --policy-document file:///tmp/test-policy.json
```

### Tests Fail with "Bucket Not Found"

**Cause**: Test bucket doesn't exist or wrong region

**Fix**:
```bash
# Check bucket exists
aws s3 ls s3://sbir-analytics-test

# Create if missing
aws s3 mb s3://sbir-analytics-test --region us-east-2
```

### Tests Timeout

**Cause**: Network issues or slow S3 response

**Fix**:
- Check AWS service health: https://status.aws.amazon.com/
- Retry the workflow
- Increase timeout in CI (currently 5 min)

### Cleanup Not Working

**Cause**: Lifecycle policy not configured

**Fix**:
```bash
# Manually delete old test files
aws s3 rm s3://sbir-analytics-test/test/ --recursive

# Or configure lifecycle policy (see Prerequisites)
```

## Cost Monitoring

### Expected Costs

| Operation | Cost | Frequency | Monthly |
|-----------|------|-----------|---------|
| PUT requests | $0.005/1000 | ~40 PRs × 10 files | $0.002 |
| GET requests | $0.0004/1000 | ~40 PRs × 10 files | $0.0002 |
| Storage | $0.023/GB | ~1 MB | $0.00002 |
| **Total** | | | **~$0.01** |

### Monitor Costs

```bash
# Check S3 bucket size
aws s3 ls s3://sbir-analytics-test --recursive --summarize

# View CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value=sbir-analytics-test \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Average
```

## Best Practices

### 1. Use Unique Test Prefixes

Tests use UUID-based prefixes to avoid conflicts:

```python
@pytest.fixture
def test_key_prefix():
    import uuid
    return f"test/{uuid.uuid4()}"
```

### 2. Always Cleanup

Tests automatically cleanup after each run:

```python
@pytest.fixture(autouse=True)
def cleanup_test_files(s3_client, s3_test_bucket, test_key_prefix):
    yield
    # Cleanup after test
    response = s3_client.list_objects_v2(Bucket=s3_test_bucket, Prefix=test_key_prefix)
    if "Contents" in response:
        objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
        s3_client.delete_objects(Bucket=s3_test_bucket, Delete={"Objects": objects})
```

### 3. Skip Gracefully

Always use `skipif` for optional dependencies:

```python
@pytest.mark.skipif(
    not os.getenv("AWS_ACCESS_KEY_ID"),
    reason="AWS credentials required"
)
```

### 4. Use Lifecycle Policies

Configure S3 lifecycle to auto-delete old test files:
- Prevents cost accumulation
- Automatic cleanup of failed test runs
- No manual intervention needed

## Next Steps

After S3 integration tests are stable (2 weeks):

1. **Add infrastructure tests** (Lambda, Step Functions)
2. **Add E2E cloud tests** (full pipeline with S3)
3. **Monitor costs** and adjust as needed

See [Cloud Testing Analysis](../architecture/cloud-testing-analysis.md) for full roadmap.
