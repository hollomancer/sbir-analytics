# Dagster Cloud Setup Checklist

This checklist tracks the manual steps required to complete the Dagster Cloud migration. All code and documentation changes have been completed.

## Completed (Code/Documentation)

- [x] Created migration guide: `docs/deployment/dagster-cloud-migration.md`
- [x] Updated README.md with Dagster Cloud as primary deployment method
- [x] Updated `docs/deployment/cloud-migration-opportunities.md` with migration status
- [x] Updated `docs/deployment/containerization.md` to note Docker as failover
- [x] Updated `docs/index.md` with Dagster Cloud references
- [x] Decided to keep Docker Compose as failover option
- [x] Created branch: `dagster-cloud-migration`

## Manual Steps Required (Dagster Cloud UI)

These steps must be completed in the Dagster Cloud web interface:

### Step 1: Account Setup
- [ ] Create Dagster Cloud account at https://cloud.dagster.io
- [ ] Start 30-day free trial
- [ ] Select Solo Plan ($10/month after trial)

### Step 2: GitHub Integration
- [ ] Connect GitHub account in Dagster Cloud UI
- [ ] Grant access to `sbir-etl` repository
- [ ] Authorize necessary permissions

### Step 3: Code Location Configuration
- [ ] Create code location named `sbir-etl-production`
- [ ] Set module to `src.definitions`
- [ ] Set branch to `main` (or preferred branch)
- [ ] Set Python version to 3.11

### Step 4: Environment Variables
Configure in Dagster Cloud UI → Code Location → Configuration → Environment Variables:

- [ ] `NEO4J_URI` - Neo4j Aura connection URI
- [ ] `NEO4J_USER` - Neo4j username (usually `neo4j`)
- [ ] `NEO4J_PASSWORD` - Neo4j Aura password
- [ ] `NEO4J_DATABASE` - Database name (usually `neo4j`)
- [ ] `SBIR_ETL__PIPELINE__ENVIRONMENT` - Set to `production` (optional)
- [ ] `PYTHONUNBUFFERED` - Set to `1` (optional)

### Step 5: Initial Deployment
- [ ] Trigger initial deployment (or wait for auto-deploy)
- [ ] Monitor build logs for any issues
- [ ] Verify deployment completes successfully

### Step 6: Verification
- [ ] Verify all 117 assets are visible in Dagster Cloud UI
- [ ] Verify all 10 jobs are listed and accessible
- [ ] Verify all 3 schedules are configured correctly
- [ ] Verify sensor (`usaspending_refresh_sensor`) is registered
- [ ] Test job execution by manually triggering `sbir_ingestion_job`
- [ ] Verify Neo4j connection works (check logs for successful writes)

### Step 7: Schedule Verification
- [ ] Verify `daily_sbir_etl` schedule (02:00 UTC daily)
- [ ] Verify `daily_cet_full_pipeline` schedule (02:00 UTC daily)
- [ ] Verify `daily_cet_drift_detection` schedule (06:00 UTC daily)
- [ ] Monitor first scheduled run to ensure it executes correctly

### Step 8: Optional Configuration
- [ ] Enable auto-deploy on git push (optional)
- [ ] Set up alerts for job failures (optional)
- [ ] Configure team access if needed (requires upgrade to Starter Plan)

## Reference Documentation

- **Complete setup guide**: `docs/deployment/dagster-cloud-migration.md`
- **Migration overview**: `docs/deployment/cloud-migration-opportunities.md`
- **Docker failover**: `docs/deployment/containerization.md`

## Support

If you encounter issues during setup:
1. Check the troubleshooting section in `docs/deployment/dagster-cloud-migration.md`
2. Review Dagster Cloud documentation: https://docs.dagster.io/dagster-cloud
3. Check Dagster Cloud status: https://status.dagster.io

## Next Steps After Setup

Once Dagster Cloud is configured and verified:
1. Monitor first few scheduled runs
2. Set up monitoring and alerts
3. Update team documentation
4. Consider upgrading to Starter Plan if you need multiple users or code locations

