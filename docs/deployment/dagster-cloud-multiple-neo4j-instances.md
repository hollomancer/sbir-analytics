# Managing Multiple Neo4j Instances with Dagster Cloud

**Challenge**: You have one Dagster Cloud instance (Solo Plan) but need to switch between multiple Neo4j instances (free and paid).

**Solution**: Update environment variables in Dagster Cloud UI to switch between Neo4j instances.

---

## Overview

Since Dagster Cloud Solo Plan allows only **1 code location** and **1 deployment**, you cannot create separate deployments for different Neo4j instances. Instead, you'll manage multiple Neo4j instances by updating environment variables in the Dagster Cloud UI.

---

## Setup: Multiple Neo4j Instances

### Instance Configuration

Keep track of your Neo4j instances:

**Free Instance (Development/Testing)**:
- URI: `neo4j+s://free-xxxxx.databases.neo4j.io`
- User: `neo4j`
- Password: `your-free-password`
- Database: `neo4j`
- Use case: Testing, development, small datasets

**Paid Instance (Production)**:
- URI: `neo4j+s://paid-xxxxx.databases.neo4j.io`
- User: `neo4j`
- Password: `your-paid-password`
- Database: `neo4j`
- Use case: Production workloads, full datasets

---

## Switching Between Instances

### Method 1: Update Environment Variables (Recommended)

1. **Navigate to Dagster Cloud UI**:
   - Go to your code location (`sbir-etl-production`)
   - Click **Configuration** → **Environment Variables**

2. **Update Neo4j Connection Variables**:
   - `NEO4J_URI` - Change to target instance URI
   - `NEO4J_USER` - Usually `neo4j` (same for both)
   - `NEO4J_PASSWORD` - Change to target instance password
   - `NEO4J_DATABASE` - Usually `neo4j` (same for both)

3. **Add Instance Identifier (Optional)**:
   - `NEO4J_INSTANCE_TYPE` - Set to `free` or `paid` for tracking
   - This helps identify which instance is active in logs

4. **Save Changes**:
   - Changes take effect immediately (no redeployment needed)
   - Next job run will use the new instance

### Method 2: Use Environment Variable Sets (If Available)

Some Dagster Cloud plans support environment variable sets. If available:
1. Create separate variable sets: `neo4j-free` and `neo4j-paid`
2. Switch between sets as needed
3. This keeps configurations organized

---

## Recommended Workflow

### For Development/Testing

1. **Set Free Instance Variables**:
   ```
   NEO4J_URI=neo4j+s://free-xxxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-free-password
   NEO4J_DATABASE=neo4j
   NEO4J_INSTANCE_TYPE=free
   ```

2. **Run Tests/Development Jobs**:
   - Use free instance for testing new features
   - Verify jobs work correctly
   - Check data loads properly

3. **Switch to Paid Instance**:
   - Update environment variables to paid instance
   - Run production jobs

### For Production

1. **Set Paid Instance Variables**:
   ```
   NEO4J_URI=neo4j+s://paid-xxxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-paid-password
   NEO4J_DATABASE=neo4j
   NEO4J_INSTANCE_TYPE=paid
   ```

2. **Run Production Jobs**:
   - Execute scheduled jobs
   - Monitor execution logs
   - Verify data loads to correct instance

---

## Verification Steps

After switching instances, verify the connection:

1. **Check Logs**:
   - Navigate to **Runs** tab in Dagster Cloud UI
   - View latest run logs
   - Look for Neo4j connection messages
   - Verify URI matches target instance

2. **Test Connection**:
   - Manually trigger a small job (e.g., `sbir_ingestion_job`)
   - Check logs for successful Neo4j connection
   - Verify data appears in correct Neo4j instance

3. **Query Neo4j**:
   - Connect to target Neo4j instance directly
   - Run a query to verify data was loaded
   - Check node/relationship counts

---

## Best Practices

### 1. Document Instance Details

Keep a secure document (password manager) with:
- Instance URIs
- Usernames
- Passwords
- Use cases for each instance
- Last switched date/time

### 2. Use Naming Conventions

- Name instances clearly: `sbir-etl-free`, `sbir-etl-paid`
- Use consistent naming in Dagster Cloud environment variables
- Add comments/notes in Dagster Cloud UI if supported

### 3. Verify Before Production Runs

- Always verify environment variables before scheduled production runs
- Double-check `NEO4J_URI` matches intended instance
- Test connection with a small job first

### 4. Monitor Instance Usage

- Check Neo4j Aura console for both instances
- Monitor node/relationship counts
- Track which instance was used for each Dagster run

### 5. Use Instance Identifier Variable

Add `NEO4J_INSTANCE_TYPE` to help track which instance is active:
- Set to `free` or `paid`
- Check in logs to confirm active instance
- Helps prevent accidental data loads to wrong instance

---

## Troubleshooting

### Wrong Instance Connected

**Issue**: Data loads to wrong Neo4j instance

**Solution**:
1. Check environment variables in Dagster Cloud UI
2. Verify `NEO4J_URI` matches intended instance
3. Update variables if incorrect
4. Re-run job to correct instance

### Connection Fails After Switching

**Issue**: Cannot connect to Neo4j after switching instances

**Solutions**:
1. Verify URI format is correct (`neo4j+s://` for Aura)
2. Check password is correct (copy-paste to avoid typos)
3. Ensure instance is not paused (free tier auto-pauses)
4. Check network connectivity from Dagster Cloud

### Forgot Which Instance is Active

**Issue**: Not sure which Neo4j instance is currently configured

**Solution**:
1. Check environment variables in Dagster Cloud UI
2. Look at `NEO4J_URI` to identify instance
3. Check `NEO4J_INSTANCE_TYPE` if set
4. Review recent run logs for connection URI

---

## Alternative: Upgrade to Starter Plan

If you frequently switch between instances, consider upgrading to **Starter Plan** ($100/month):
- **5 code locations** - Create separate code locations for free/paid instances
- **Separate deployments** - Each instance gets its own deployment
- **Better organization** - No need to manually switch environment variables

**Trade-off**: Higher cost ($100/month vs $10/month) but better isolation and organization.

---

## Quick Reference

### Environment Variables to Update

When switching instances, update these variables:

```
NEO4J_URI              # Instance URI (neo4j+s://...)
NEO4J_USER            # Username (usually neo4j)
NEO4J_PASSWORD        # Instance password
NEO4J_DATABASE        # Database name (usually neo4j)
NEO4J_INSTANCE_TYPE   # Optional: free or paid
```

### Where to Update

1. Dagster Cloud UI
2. Code Location → Configuration → Environment Variables
3. Update values → Save
4. Changes take effect immediately

### Verification Command

After switching, verify in Dagster Cloud UI:
- **Runs** → Latest run → **Logs**
- Search for "Neo4j" or "Connected to"
- Verify URI matches target instance

---

## Summary

With Dagster Cloud Solo Plan, you can manage multiple Neo4j instances by:
1. ✅ Updating environment variables in Dagster Cloud UI
2. ✅ Switching between instances as needed
3. ✅ Verifying connections before production runs
4. ✅ Using instance identifier variable for tracking

**No code changes required** - your application already reads from environment variables, so switching instances is just a matter of updating the UI configuration.

