# Running ML Jobs with GitHub Actions

For infrequent ML workloads (weekly testing, on-demand training), GitHub Actions is the simplest and most cost-effective solution.

## Architecture

```
┌──────────────────────────────────────────────┐
│        GitHub Actions Serverless              │
│        Core ETL (always available)           │
│   - SBIR ingestion                           │
│   - Enrichment                               │
│   - Neo4j loading                            │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│        GitHub Actions (on-demand)            │
│        ML Jobs (manual or scheduled)         │
│   - CET training/inference                   │
│   - Fiscal R analysis                        │
│   - PaECTER embeddings                       │
└──────────────────────────────────────────────┘
```

## Benefits

| Aspect | Value |
|--------|-------|
| **Cost** | $0 (within free tier) |
| **Setup** | 5 minutes |
| **Infrastructure** | Zero servers |
| **Scaling** | Automatic |
| **Maintenance** | None |

### Free Tier Limits

- **Public repos**: Unlimited minutes
- **Private repos**: 2,000 minutes/month
- **Weekly job example**: 1 hour/week × 4 weeks = 240 minutes/month ✅

For 10 hours/week: 2,400 min/month → $8/month for extra minutes
Still cheaper than any infrastructure!

## Usage

### Option 1: Manual Trigger (Recommended for Testing)

1. Go to GitHub → **Actions** tab
2. Select **"ML Jobs On-Demand"**
3. Click **"Run workflow"**
4. Choose job:
   - `cet_full_pipeline` - CET training and inference
   - `fiscal_returns_mvp` - Fiscal impact analysis
   - `paecter_embeddings` - Generate embeddings
   - `all_ml_jobs` - Run everything

5. Click **"Run workflow"** button
6. Monitor progress in real-time

### Option 2: Weekly Schedule

The workflow is configured to run automatically:
- **Every Monday at 3 AM UTC**
- Runs all ML jobs for weekly validation

To change schedule, edit `.github/workflows/run-ml-jobs.yml`:

```yaml
schedule:
  - cron: '0 3 * * 1'  # Monday 3 AM UTC
  # - cron: '0 0 * * 0'  # Sunday midnight UTC
  # - cron: '0 12 * * *'  # Daily noon UTC
```

### Option 3: API/CLI Trigger

```bash
# Using GitHub CLI
gh workflow run run-ml-jobs.yml \
  --ref main \
  --field job_name=cet_full_pipeline

# Using REST API
curl -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/hollomancer/sbir-analytics/actions/workflows/run-ml-jobs.yml/dispatches \
  -d '{"ref":"main","inputs":{"job_name":"cet_full_pipeline"}}'
```

## What Runs

### Available Jobs

**1. CET Full Pipeline** (`cet_full_pipeline`)
- Company Emerging Technologies classification
- Training: scikit-learn models
- Inference: Apply models to SBIR data
- Drift detection: Monitor model performance
- Duration: ~30-60 minutes

**2. Fiscal Returns MVP** (`fiscal_returns_mvp`)
- Economic impact analysis using R
- ROI calculations
- Fiscal multiplier effects
- Duration: ~20-40 minutes

**3. PaECTER Job** (`paecter_embeddings`)
- Generate embeddings using sentence-transformers
- Similarity computation for patent-award matching
- Duration: ~40-80 minutes

**4. All ML Jobs** (`all_ml_jobs`)
- Runs all above jobs sequentially
- Duration: ~90-180 minutes

## Configuration

### Environment Variables

Set in `.github/workflows/run-ml-jobs.yml`:

```yaml
env:
  AWS_REGION: us-east-2
  DAGSTER_LOAD_HEAVY_ASSETS: "true"
  DAGSTER_HOME: /tmp/dagster_home
```

### AWS Credentials

Jobs access S3 automatically using OIDC:
- Uses `AWS_ROLE_ARN` secret (already configured)
- No static credentials needed
- Secure and automatic

### Timeout

Default: 3 hours (180 minutes)

To increase:
```yaml
jobs:
  run-ml-job:
    timeout-minutes: 360  # 6 hours
```

GitHub Actions max: 6 hours (360 minutes)

## Monitoring

### Real-Time Logs

1. Go to **Actions** tab
2. Click on running workflow
3. Expand job steps to see live output

### Results

Job results are uploaded as artifacts:
- Available for 7 days
- Download via Actions tab
- Includes Dagster logs and reports

### Notifications

Get notified on job completion:

**Email**: Automatic for failed jobs

**Slack**: Add to workflow:
```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "ML job ${{ job.status }}: ${{ github.event.inputs.job_name }}"
      }
```

## Cost Analysis

### Compute Time

| Job | Duration | Minutes/Month (weekly) | Cost |
|-----|----------|------------------------|------|
| CET | 45 min | 180 | Free |
| Fiscal | 30 min | 120 | Free |
| PaECTER | 60 min | 240 | Free |
| **All** | 135 min | **540** | **Free ✅** |

**Total**: 540 min/month (well within 2,000 free minutes)

### Break-Even Analysis

| Scenario | GitHub Actions | EC2 t3.small |
|----------|----------------|--------------|
| Weekly (4 jobs/mo) | $0 | $15/mo |
| Daily (30 jobs/mo) | $0 (1,800 min) | $15/mo |
| 2× daily (60 jobs/mo) | $15/mo* | $15/mo |

*Exceeds free tier but still competitive

**Winner for infrequent jobs**: GitHub Actions

## Troubleshooting

### Job Timeout

**Symptom**: Job cancelled after 3 hours

**Solution**: Either optimize job or increase timeout:
```yaml
timeout-minutes: 360  # Max 6 hours
```

### Out of Memory

**Symptom**: Job killed with OOM error

**Solution**: GitHub provides 7GB RAM by default. If not enough:
1. Optimize job to use less memory
2. Use larger GitHub-hosted runner (paid): 16GB or 32GB RAM
3. Or switch to EC2/AWS Batch for very large jobs

### AWS Credentials Failed

**Symptom**: Unable to access S3

**Solution**: Verify OIDC configuration:
```bash
# Check role ARN is set
gh secret list

# Test AWS access
aws sts get-caller-identity
```

### Dependencies Installation Slow

**Symptom**: `pip install` takes 10+ minutes

**Solution**: Already using pip cache in workflow:
```yaml
- uses: actions/setup-python@v5
  with:
    cache: 'pip'  # Caches dependencies
```

## Advanced Usage

### Run Specific Asset

To run a single asset instead of a full job:

```yaml
- name: Run specific asset
  run: |
    dagster asset materialize \
      -m src.definitions_ml \
      --select cet_model_training
```

### Parallel Execution

Run multiple jobs in parallel (uses more minutes but faster):

```yaml
strategy:
  matrix:
    job: [cet_full_pipeline, fiscal_returns_mvp, paecter_embeddings]

steps:
  - name: Run job
    run: |
      dagster job execute -m src.definitions_ml -j ${{ matrix.job }}
```

### Integration with GitHub Actions

For visibility in GitHub Actions, report runs:

```yaml
- name: Report to GitHub Actions
  env:
  run: |
    # Report run to GitHub Actions for visibility
      --deployment prod \
      --location sbir-analytics-ml
```

## Comparison to Other Options

| Approach | Cost/Month | Setup | Best For |
|----------|-----------|-------|----------|
| **GitHub Actions** | **$0-8** | **5 min** | **Infrequent/testing** |
| EC2 t3.small | $15 | 20 min | Frequent jobs |
| AWS Batch | $11 | 2 hours | Variable workloads |
| ECS Fargate | $15-30 | 1 hour | Production |

## When to Migrate

Consider moving to EC2/Batch when:
- Jobs run >20 times per week
- Each job takes >2 hours
- Need <1 minute latency
- Require >7GB RAM regularly

Until then, GitHub Actions is perfect! 🎉

## Next Steps

1. **Test now**: Go to Actions → Run ML Jobs On-Demand
2. **Schedule it**: Workflow already configured for Monday 3 AM
3. **Monitor costs**: Check Actions usage in Settings → Billing
4. **Optimize**: If jobs take too long, reduce data samples for testing

## Support

- GitHub Actions Docs: https://docs.github.com/en/actions
- Dagster CLI: https://docs.dagster.io/guides/build/jobs
- Workflow file: `.github/workflows/run-ml-jobs.yml`
