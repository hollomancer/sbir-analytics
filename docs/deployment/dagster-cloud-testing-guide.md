# Dagster Cloud Testing Guide

This guide provides step-by-step instructions for testing your Dagster Cloud deployment to ensure everything is configured correctly.

---

## Quick Start: 5-Minute Test

**Fastest way to verify Dagster Cloud is working:**

1. **Check Deployment**: Go to Dagster Cloud UI → Code Location → Verify deployment is "Active"
2. **Check Assets**: Go to **Assets** tab → Verify ~117 assets are visible
3. **Check Jobs**: Go to **Jobs** tab → Verify 10 jobs are listed
4. **Test Connection**: Go to **Jobs** → `sbir_ingestion_job` → Click **Materialize** → Watch logs for Neo4j connection success
5. **Verify Results**: Check **Runs** tab → Verify job completed successfully

If all 5 steps pass, your basic setup is working! Continue with detailed tests below for comprehensive verification.

---

## Prerequisites

- Dagster Cloud account created and code location configured
- Environment variables set in Dagster Cloud UI
- Neo4j Aura instance(s) accessible

---

## Test 1: Verify Code Location Deployment

### Steps

1. **Navigate to Dagster Cloud UI**
   - Go to your code location (`sbir-etl-production`)
   - Check the **Deployment** tab

2. **Verify Deployment Status**
   - ✅ Deployment should show "Success" or "Active"
   - ✅ Build logs should show no errors
   - ✅ Dependencies should be installed successfully

3. **Check for Errors**
   - Review build logs for any import errors
   - Verify Python version matches (3.11)
   - Check that all dependencies from `pyproject.toml` installed

### Expected Result

- Deployment completes successfully
- No errors in build logs
- Code location shows as "Active"

---

## Test 2: Verify Assets and Jobs Load

### Steps

1. **Check Assets Tab**
   - Navigate to **Assets** in Dagster Cloud UI
   - Verify all assets are visible
   - Expected: ~117 assets should appear

2. **Check Jobs Tab**
   - Navigate to **Jobs** in Dagster Cloud UI
   - Verify all jobs are listed
   - Expected jobs:
     - `sbir_ingestion_job`
     - `sbir_etl_job`
     - `cet_full_pipeline_job`
     - `cet_drift_job`
     - `transition_mvp_job`
     - `transition_full_job`
     - `transition_analytics_job`
     - `usaspending_iterative_enrichment_job`
     - `fiscal_returns_mvp_job`
     - `fiscal_returns_full_job`

3. **Check Schedules Tab**
   - Navigate to **Schedules** in Dagster Cloud UI
   - Verify all 3 schedules are configured:
     - `daily_sbir_etl` (02:00 UTC daily)
     - `daily_cet_full_pipeline` (02:00 UTC daily)
     - `daily_cet_drift_detection` (06:00 UTC daily)

4. **Check Sensors Tab**
   - Navigate to **Sensors** in Dagster Cloud UI
   - Verify `usaspending_refresh_sensor` is registered

### Expected Result

- All assets, jobs, schedules, and sensors visible
- No missing dependencies or import errors

---

## Test 3: Verify Environment Variables

### Steps

1. **Check Environment Variables**
   - Navigate to Code Location → **Configuration** → **Environment Variables**
   - Verify all required variables are set:
     - `NEO4J_URI`
     - `NEO4J_USER`
     - `NEO4J_PASSWORD`
     - `NEO4J_DATABASE`

2. **Verify Variable Values**
   - Check that `NEO4J_URI` matches your Neo4j Aura instance
   - Verify URI format: `neo4j+s://xxxxx.databases.neo4j.io`
   - Confirm password is correct (not placeholder)

3. **Test Variable Access (Optional)**
   - Create a simple test asset that logs environment variables
   - Or check logs from a job run to see if variables are accessible

### Expected Result

- All required environment variables are set
- Values match your Neo4j instance configuration
- Variables are accessible to jobs

---

## Test 4: Test Neo4j Connection

### Steps

1. **Run a Small Test Job**
   - Navigate to **Jobs** → `sbir_ingestion_job`
   - Click **Materialize** to trigger a manual run
   - Or use a smaller test job if available

2. **Monitor Execution**
   - Go to **Runs** tab
   - Click on the running job
   - Watch logs in real-time

3. **Check for Neo4j Connection Messages**
   - Look for log messages like:
     - "Connected to Neo4j"
     - "Neo4j connection successful"
     - Neo4j URI in connection logs
   - Verify URI matches your configured instance

4. **Check for Connection Errors**
   - Look for errors like:
     - "Connection refused"
     - "Authentication failed"
     - "Unable to connect"
   - If errors occur, check environment variables

### Expected Result

- Job starts executing
- Neo4j connection succeeds
- No authentication or connection errors
- Logs show successful connection to Neo4j

---

## Test 5: Test Job Execution (Small Job)

### Steps

1. **Choose a Small Test Job**
   - Best option: `sbir_ingestion_job` (smaller, faster)
   - Alternative: Any job that doesn't require large datasets

2. **Trigger Manual Execution**
   - Navigate to **Jobs** → Select job
   - Click **Materialize** or **Launch Run**
   - Monitor execution

3. **Monitor Progress**
   - Watch asset materialization progress
   - Check for any errors or warnings
   - Verify assets complete successfully

4. **Check Results**
   - Review execution logs
   - Verify no critical errors
   - Check that assets were materialized

### Expected Result

- Job executes successfully
- Assets materialize without errors
- Execution completes (may take a few minutes)

---

## Test 6: Test Neo4j Data Loading

### Steps

1. **Run a Job That Writes to Neo4j**
   - Example: `sbir_ingestion_job` (if it loads to Neo4j)
   - Or any job that includes Neo4j loading assets

2. **Monitor Neo4j Loading**
   - Watch logs for Neo4j write operations
   - Look for messages like:
     - "Loading nodes to Neo4j"
     - "Creating relationships"
     - "MERGE operations"

3. **Verify Data in Neo4j**
   - Connect to your Neo4j Aura instance directly
   - Run a query to check if data was loaded:
     ```cypher
     MATCH (n)
     RETURN count(n) as node_count
     LIMIT 1
     ```
   - Or check for specific nodes:
     ```cypher
     MATCH (a:Award)
     RETURN count(a) as award_count
     ```

### Expected Result

- Neo4j loading operations succeed
- Data appears in Neo4j instance
- No write errors in logs

---

## Test 7: Test Multiple Neo4j Instance Switching

### Steps

1. **Note Current Instance**
   - Check current `NEO4J_URI` in environment variables
   - Note which instance is active (free or paid)

2. **Switch to Different Instance**
   - Update `NEO4J_URI` to different instance
   - Update `NEO4J_PASSWORD` if different
   - Update `NEO4J_INSTANCE_TYPE` to track switch
   - Save changes

3. **Verify Switch**
   - Run a small test job
   - Check logs for Neo4j connection URI
   - Verify it matches the new instance

4. **Verify Data Goes to Correct Instance**
   - Connect to the new Neo4j instance
   - Check if data appears there (not in old instance)
   - Verify data isolation

5. **Switch Back (If Needed)**
   - Update environment variables back to original instance
   - Verify connection works

### Expected Result

- Environment variables update successfully
- Jobs connect to new instance
- Data loads to correct instance
- No data leakage between instances

---

## Test 8: Test Schedules

### Steps

1. **Verify Schedule Configuration**
   - Navigate to **Schedules** tab
   - Check all 3 schedules are enabled
   - Verify cron expressions are correct

2. **Test Schedule Manually (Optional)**
   - Some Dagster Cloud plans allow manual schedule triggers
   - Trigger a schedule manually to test
   - Or wait for next scheduled run

3. **Monitor Scheduled Run**
   - Wait for next scheduled execution time
   - Check **Runs** tab for scheduled runs
   - Verify runs execute automatically

4. **Check Schedule History**
   - Review schedule execution history
   - Verify runs execute at correct times
   - Check for any failed scheduled runs

### Expected Result

- Schedules are configured correctly
- Scheduled runs execute automatically
- Runs execute at expected times
- No schedule failures

---

## Test 9: Test Sensor

### Steps

1. **Verify Sensor Status**
   - Navigate to **Sensors** tab
   - Check `usaspending_refresh_sensor` is active
   - Verify sensor configuration

2. **Monitor Sensor Activity**
   - Watch sensor logs for activity
   - Check if sensor detects changes
   - Verify sensor triggers jobs when appropriate

3. **Test Sensor Trigger (If Possible)**
   - If sensor detects file changes or API updates
   - Trigger the condition manually (if possible)
   - Verify sensor responds correctly

### Expected Result

- Sensor is registered and active
- Sensor monitors for changes
- Sensor triggers jobs when conditions are met

---

## Test 10: End-to-End Pipeline Test

### Steps

1. **Run Full ETL Job**
   - Navigate to **Jobs** → `sbir_etl_job`
   - Trigger a manual run
   - This tests the complete pipeline

2. **Monitor All Stages**
   - Watch extraction stage
   - Monitor validation stage
   - Check enrichment stage
   - Verify transformation stage
   - Confirm loading stage

3. **Verify Data Flow**
   - Check that data flows through all stages
   - Verify no stage failures
   - Check asset dependencies resolve correctly

4. **Check Final Results**
   - Verify data loads to Neo4j
   - Check reports/metrics are generated
   - Verify no critical errors

### Expected Result

- Complete pipeline executes successfully
- All stages complete without errors
- Data flows correctly through pipeline
- Final data loads to Neo4j

---

## Troubleshooting Common Issues

### Issue: Assets Not Loading

**Symptoms**: Assets don't appear in Dagster Cloud UI

**Solutions**:
1. Check deployment logs for import errors
2. Verify `src/definitions.py` exports `defs` correctly
3. Check that all asset modules are importable
4. Review build logs for missing dependencies

### Issue: Neo4j Connection Fails

**Symptoms**: Jobs fail with Neo4j connection errors

**Solutions**:
1. Verify `NEO4J_URI` is correct (check for typos)
2. Ensure URI uses `neo4j+s://` protocol for Aura
3. Check password is correct
4. Verify Neo4j instance is not paused (free tier)
5. Check network connectivity

### Issue: Environment Variables Not Working

**Symptoms**: Jobs use wrong values or default values

**Solutions**:
1. Verify variables are set at code location level (not deployment level)
2. Check variable names match exactly (`NEO4J_URI`, not `NEO4J_URL`)
3. Redeploy code location after adding variables
4. Check logs for environment variable errors

### Issue: Jobs Fail to Execute

**Symptoms**: Jobs start but fail during execution

**Solutions**:
1. Check execution logs for specific errors
2. Verify all dependencies are installed
3. Check for missing data files
4. Verify Neo4j connection is working
5. Review asset dependencies

---

## Quick Test Checklist

Use this checklist for a quick verification:

- [ ] Code location deploys successfully
- [ ] All assets visible (~117 assets)
- [ ] All jobs visible (10 jobs)
- [ ] All schedules configured (3 schedules)
- [ ] Sensor registered (1 sensor)
- [ ] Environment variables set correctly
- [ ] Neo4j connection works
- [ ] Small test job executes successfully
- [ ] Data loads to Neo4j
- [ ] Can switch between Neo4j instances
- [ ] Schedules execute automatically
- [ ] End-to-end pipeline works

---

## Next Steps After Testing

Once all tests pass:

1. **Monitor Production Runs**
   - Watch first few scheduled runs
   - Verify they execute correctly
   - Check for any issues

2. **Set Up Alerts**
   - Configure alerts for job failures
   - Set up notifications for schedule failures
   - Monitor Neo4j connection issues

3. **Document Any Issues**
   - Note any problems encountered
   - Document solutions
   - Update troubleshooting guides

4. **Optimize Configuration**
   - Adjust environment variables as needed
   - Fine-tune schedules if necessary
   - Optimize job execution

---

## Support Resources

- **Dagster Cloud Docs**: https://docs.dagster.io/dagster-cloud
- **Migration Guide**: `docs/deployment/dagster-cloud-migration.md`
- **Multiple Neo4j Instances**: `docs/deployment/dagster-cloud-multiple-neo4j-instances.md`
- **Troubleshooting**: See troubleshooting sections in migration guide

