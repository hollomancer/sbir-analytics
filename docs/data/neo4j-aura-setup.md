# Neo4j Aura Setup for Weekly Workflow

The weekly SBIR awards refresh workflow can optionally load validated data into a Neo4j Aura cloud instance for testing and analysis.

## Why Neo4j Aura?

**Cost:** Free tier available with generous limits (200k nodes + relationships, 50MB storage)

**Benefits:**
- No infrastructure management
- Automatic backups
- Cloud accessibility
- Perfect for weekly data refreshes
- Auto-pauses after 3 days of inactivity (wakes instantly on connection)

## Setup Instructions

### 1. Create a Free Neo4j Aura Instance

1. Visit [https://console.neo4j.io](https://console.neo4j.io)
2. Sign up for a free account (no credit card required)
3. Click "New Instance" → Select "AuraDB Free"
4. Choose a name (e.g., "sbir-etl-weekly")
5. **Important:** Download and save your credentials immediately (you'll only see them once)

### 2. Get Your Connection Details

After creating the instance, note these values:

- **URI**: `neo4j+s://xxxxx.databases.neo4j.io` (from the instance dashboard)
- **Username**: Usually `neo4j`
- **Password**: The password you saved during setup
- **Database**: `neo4j` (default)

### 3. Add Secrets to GitHub Repository

Add these secrets to your GitHub repository settings:

```bash
# Via GitHub CLI
gh secret set NEO4J_AURA_URI -b "neo4j+s://xxxxx.databases.neo4j.io"
gh secret set NEO4J_AURA_USER -b "neo4j"
gh secret set NEO4J_AURA_PASSWORD -b "your-secure-password"
gh secret set NEO4J_AURA_DATABASE -b "neo4j"
```

Or manually via GitHub web interface:
1. Go to your repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add each secret:
   - Name: `NEO4J_AURA_URI`, Value: `neo4j+s://xxxxx.databases.neo4j.io`
   - Name: `NEO4J_AURA_USER`, Value: `neo4j`
   - Name: `NEO4J_AURA_PASSWORD`, Value: `your-password`
   - Name: `NEO4J_AURA_DATABASE`, Value: `neo4j`

### 4. Verify Setup

The Neo4j steps in the workflow will only run if `NEO4J_AURA_URI` is set. To test:

1. Trigger the workflow manually: Actions → Weekly SBIR Awards Refresh → Run workflow
2. Check the workflow logs for "Loading data to Neo4j Aura" messages
3. Verify in Neo4j Aura console that nodes were created

## Local Testing

To test Neo4j Aura connection locally:

```bash
# Set environment variables
export NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"
export NEO4J_DATABASE="neo4j"

# Test reset script
poetry run python scripts/data/reset_neo4j_sbir.py --dry-run

# Test loading (requires validated CSV)
poetry run python scripts/data/run_neo4j_sbir_load.py \
  --validated-csv data/validated/sbir_validated.csv \
  --output-dir reports/neo4j_test \
  --summary-md reports/neo4j_test/load_summary.md
```

## Monitoring & Maintenance

### Check Database Usage

View your instance usage in the Neo4j Aura console:
- Nodes count
- Relationships count
- Storage used
- Memory usage

### Free Tier Limits

- **Nodes + Relationships:** 200,000 combined
- **Storage:** 50MB
- **Compute:** Shared CPU
- **Auto-pause:** After 3 days of inactivity (resumes on connection)

### Typical SBIR Dataset Size

For reference, a full SBIR dataset typically contains:
- ~1.5M+ awards → May exceed free tier
- ~200k+ companies
- ~1.5M+ relationships

**Recommendation for free tier:**
- Use sample/filtered datasets
- Monitor node counts regularly
- Consider upgrading to Neo4j Aura Professional ($65/month) for full datasets

### Disable Neo4j Steps

To disable Neo4j loading without removing secrets:

1. Delete the `NEO4J_AURA_URI` secret
2. The workflow will skip Neo4j steps automatically

Or comment out the Neo4j steps in `.github/workflows/weekly-award-data-refresh.yml`

## Upgrading to Neo4j Aura Professional

If you need to load the full SBIR dataset:

1. Upgrade to Aura Professional in the console
2. Choose an instance size (start with 1GB RAM, 8GB storage ~ $65/month)
3. No code changes needed - same connection works
4. Benefits:
   - No auto-pause
   - Better performance
   - Automatic backups
   - 99.95% SLA

## Alternative: Self-Hosted Options

See the main documentation for other low-cost options:
- Fly.io (free tier, scale on-demand)
- Railway ($5-20/month)
- DigitalOcean Droplet ($4-6/month)

## Troubleshooting

### Connection Timeout

**Symptom:** Workflow fails with "connection timeout"

**Solutions:**
- Verify URI is correct (should start with `neo4j+s://` for Aura)
- Check that instance is not paused (visit Aura console to wake it)
- Confirm secrets are set correctly

### Authentication Failed

**Symptom:** "Authentication failed" error

**Solutions:**
- Verify password is correct
- Check username (usually `neo4j`)
- Ensure you're using the initial password (not changed via console)

### Node Limit Exceeded

**Symptom:** Load fails or Aura console shows warning

**Solutions:**
- Reset database to free space: `poetry run python scripts/data/reset_neo4j_sbir.py`
- Use filtered/sample datasets
- Upgrade to Professional tier
- Switch to self-hosted option

### Free Tier Instance Paused

**Symptom:** First connection slow or timeout

**Solution:**
- Free tier pauses after 3 days of inactivity
- First connection wakes it (may take 30-60 seconds)
- Subsequent connections are instant
- Workflow has built-in retry logic

## Security Best Practices

1. ✅ **Never commit credentials** - Always use GitHub Secrets
2. ✅ **Rotate passwords** - Change Neo4j password periodically
3. ✅ **Limit access** - Use IP allowlists if available in your Aura plan
4. ✅ **Monitor usage** - Set up Aura console alerts for unusual activity
5. ✅ **Use SSL** - Always use `neo4j+s://` protocol (enforced by Aura)

## Support

- **Neo4j Aura Docs:** https://neo4j.com/docs/aura/
- **Community Forum:** https://community.neo4j.com/
- **Status Page:** https://status.neo4j.io/
