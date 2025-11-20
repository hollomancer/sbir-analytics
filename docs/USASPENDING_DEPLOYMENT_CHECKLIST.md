# USAspending Database Integration - Deployment Checklist

## 🔍 Current Status

**Code Status**: ✅ Complete - All code committed and pushed
**Access Status**: ⚠️ Needs verification - Database URLs require investigation

## 📋 Pre-Deployment Steps

### 1. Verify Database Access (CRITICAL)

- [ ] **Access the USAspending database portal**
  - Portal: https://onevoicecrm.my.site.com/usaspending/s/database-download
  - May require registration or authentication

- [ ] **Identify actual download mechanism**
  - Option A: Direct URLs work (if access granted)
  - Option B: Portal provides signed/temporary URLs
  - Option C: Portal requires authentication tokens

- [ ] **Document access method**
  - Update Lambda function with correct URL/auth approach
  - Add credentials to AWS Secrets Manager if needed

### 2. Determine Database Type to Download

- [ ] **Test Database** (Recommended for initial setup)
  - Expected size: ~50-100 GB compressed
  - Contains sample data for testing
  - **Need to verify**: Does a test database exist? If so, what's the URL pattern?

- [ ] **Full Database** (Production)
  - Size: ~500-800 GB compressed (~1.5-2.5 TB uncompressed)
  - URL pattern: `usaspending-db_YYYYMMDD.zip`
  - Latest confirmed: `usaspending-db_20250106.zip`

### 3. AWS Infrastructure Setup

- [ ] **Verify AWS credentials configured**
  ```bash
  aws sts get-caller-identity
  ```

- [ ] **Check S3 bucket exists**
  ```bash
  aws s3 ls s3://sbir-etl-production-data/
  ```

- [ ] **Verify sufficient S3 storage**
  - Need: 1+ TB free space for full database
  - Check quota: AWS Console → S3 → Storage

- [ ] **Deploy CDK stacks**
  ```bash
  cd infrastructure/cdk

  # Deploy storage stack with lifecycle policies
  cdk deploy SbirEtlStorageStack

  # Deploy Lambda stack with new download function
  cdk deploy SbirEtlLambdaStack
  ```

- [ ] **Verify Lambda function deployed**
  ```bash
  aws lambda get-function \
    --function-name sbir-analytics-download-usaspending-database
  ```

### 4. Configuration Updates

- [ ] **Set S3 bucket in environment**
  ```bash
  export S3_BUCKET=sbir-etl-production-data
  ```

- [ ] **Update Lambda environment variables** (if needed)
  ```bash
  aws lambda update-function-configuration \
    --function-name sbir-analytics-download-usaspending-database \
    --environment Variables={S3_BUCKET=sbir-etl-production-data}
  ```

- [ ] **Configure Dagster Cloud environment**
  - Add `S3_BUCKET` environment variable
  - Verify AWS credentials available

## 🧪 Testing Phase

### 1. Test Lambda Function (Local)

- [ ] **Create test event**
  ```json
  {
    "s3_bucket": "sbir-etl-production-data",
    "database_type": "test",
    "source_url": "https://files.usaspending.gov/database_download/usaspending-db-test_YYYYMMDD.zip",
    "force_refresh": true
  }
  ```

- [ ] **Test locally** (if possible)
  ```bash
  cd scripts/lambda/download_usaspending_database
  python -c "
  from lambda_handler import lambda_handler
  import json

  event = {
      'database_type': 'test',
      'source_url': 'YOUR_ACTUAL_URL_HERE'
  }

  result = lambda_handler(event, None)
  print(json.dumps(result, indent=2))
  "
  ```

### 2. Test Lambda Function (AWS)

- [ ] **Invoke Lambda with test URL**
  ```bash
  aws lambda invoke \
    --function-name sbir-analytics-download-usaspending-database \
    --payload '{"database_type":"test","source_url":"ACTUAL_URL"}' \
    --cli-binary-format raw-in-base64-out \
    response.json

  cat response.json | jq
  ```

- [ ] **Check CloudWatch logs**
  ```bash
  aws logs tail /aws/lambda/sbir-analytics-download-usaspending-database \
    --follow
  ```

- [ ] **Verify S3 upload**
  ```bash
  aws s3 ls s3://sbir-etl-production-data/raw/usaspending/database/ \
    --recursive
  ```

### 3. Test DuckDB Extraction

- [ ] **Test S3 path resolution**
  ```python
  from sbir_analytics.utils.cloud_storage import resolve_data_path

  path = resolve_data_path(
      "s3://sbir-etl-production-data/raw/usaspending/database/latest/dump.zip"
  )
  print(f"Resolved to: {path}")
  ```

- [ ] **Test DuckDB import**
  ```python
  from sbir_analytics.extractors.usaspending import DuckDBUSAspendingExtractor

  extractor = DuckDBUSAspendingExtractor()
  success = extractor.import_postgres_dump(
      "s3://sbir-etl-production-data/raw/usaspending/database/latest/dump.zip",
      "transaction_normalized"
  )
  print(f"Import success: {success}")
  ```

### 4. Test Dagster Assets

- [ ] **Materialize in Dagster UI**
  - Navigate to Assets → `usaspending_database` group
  - Click "Materialize" on `sbir_relevant_usaspending_transactions`
  - Check for errors in Dagster logs

- [ ] **Verify output data**
  ```python
  # Check materialized asset
  import pandas as pd

  # Dagster will store this in configured IO manager
  # Verify the data looks correct
  ```

## 🚀 Production Deployment

### 1. Schedule Monthly Downloads

- [ ] **Create EventBridge rule**

  Option A: Via AWS Console
  - Navigate to EventBridge → Rules
  - Create rule: "USAspending Monthly Download"
  - Schedule: `cron(0 2 1 * ? *)` (1st of month, 2 AM UTC)
  - Target: Lambda function `sbir-analytics-download-usaspending-database`
  - Input: `{"database_type": "test"}`

  Option B: Via CDK (add to `step_functions_stack.py`)
  ```python
  usaspending_rule = events.Rule(
      self,
      "USAspendingMonthlyDownload",
      schedule=events.Schedule.cron(
          minute="0",
          hour="2",
          day="1",
          month="*",
          year="*"
      ),
  )

  usaspending_rule.add_target(
      targets.LambdaFunction(
          lambda_functions["download-usaspending-database"],
          event=events.RuleTargetInput.from_object({
              "database_type": "test",
              "s3_bucket": s3_bucket.bucket_name,
          }),
      )
  )
  ```

- [ ] **Deploy updated stack**
  ```bash
  cdk deploy SbirEtlStepFunctionsStack
  ```

### 2. Dagster Job Configuration

- [ ] **Create monthly refresh job** (similar to SBIR weekly)
  ```python
  # In src/assets/jobs/usaspending_monthly_job.py
  from dagster import define_asset_job, AssetSelection

  usaspending_monthly_refresh_job = define_asset_job(
      name="usaspending_monthly_refresh",
      selection=AssetSelection.groups("usaspending_database"),
      description="Monthly USAspending database enrichment",
  )
  ```

- [ ] **Add schedule in Dagster Cloud**
  - Schedule: Monthly (1st of month, after Lambda download completes)
  - Job: `usaspending_monthly_refresh`

### 3. Monitoring Setup

- [ ] **CloudWatch alarms**
  - Lambda errors > 0
  - Lambda duration > 800 seconds (13 min warning)
  - S3 storage > threshold

- [ ] **Dagster asset checks**
  - Data volume checks (transactions count)
  - Data quality checks (match rate)
  - Freshness checks (data recency)

- [ ] **Cost monitoring**
  - Set S3 storage budget alert ($50/month)
  - Lambda execution budget alert ($5/month)

## 📝 Documentation Updates

- [ ] **Update README with access instructions**
  - Document how to get database access
  - Add authentication steps if required

- [ ] **Create runbook for monthly process**
  - What to do if download fails
  - How to manually trigger
  - Troubleshooting guide

- [ ] **Document data schema**
  - Key tables and columns
  - Filtering criteria
  - Known issues/limitations

## ⚠️ Known Issues to Resolve

### Issue #1: Database Download Authentication

**Status**: 🔴 Blocked
**Description**: Direct URLs to `files.usaspending.gov` return 403 Forbidden
**Action Required**:
1. Visit https://onevoicecrm.my.site.com/usaspending/s/database-download
2. Determine if registration/authentication is needed
3. Document the actual download process
4. Update Lambda function if needed

**Options**:
- [ ] Register for database access (if required)
- [ ] Get API credentials or access token
- [ ] Use portal's download mechanism
- [ ] Contact USAspending support for access

### Issue #2: Test Database URL Unknown

**Status**: 🟡 Needs verification
**Description**: Unclear if a test/sample database exists
**Action Required**:
1. Verify if `usaspending-db-test_YYYYMMDD.zip` exists
2. Check portal for test database option
3. Determine alternative for testing (e.g., subset of full database)

**Options**:
- [ ] Use full database with aggressive DuckDB filtering
- [ ] Create own subset after first download
- [ ] Use local PostgreSQL dump subset

### Issue #3: Large File Timeout Risk

**Status**: 🟡 Potential issue
**Description**: Full database (~500GB) may exceed 15-min Lambda timeout
**Mitigation**:
- [ ] Test with smaller file first
- [ ] Monitor Lambda duration closely
- [ ] Prepare AWS Batch/Fargate alternative if needed

## 🎯 Success Criteria

- [ ] Lambda function successfully downloads database to S3
- [ ] S3 lifecycle policies working (check after 7 days)
- [ ] DuckDB successfully queries S3-stored dump
- [ ] Dagster assets materialize without errors
- [ ] Neo4j enriched with USAspending transaction data
- [ ] Monthly automation running (check after first scheduled run)
- [ ] Total monthly cost < $25

## 📞 Support Resources

- **USAspending Support**: https://www.usaspending.gov/about/contact-us
- **Database Documentation**: https://files.usaspending.gov/database_download/usaspending-db-setup.pdf (if accessible)
- **API Documentation**: https://api.usaspending.gov
- **GitHub**: https://github.com/fedspendingtransparency/usaspending-api

## 🔄 Next Steps

**Immediate (Week 1)**:
1. ✅ Code complete - Already done!
2. 🔴 Resolve database access issue
3. 🟡 Update Lambda with correct URLs
4. 🟡 Deploy infrastructure
5. 🟡 Test with smallest available database

**Short-term (Weeks 2-3)**:
1. Refine data filtering queries
2. Validate data quality
3. Integrate with Neo4j
4. Set up monitoring

**Long-term (Month 2+)**:
1. Optimize for full database
2. Implement incremental processing
3. Add analytics dashboards
4. Consider additional federal datasets
