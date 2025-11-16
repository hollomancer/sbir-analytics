# Dagster Cloud Serverless CLI Deployment

This guide covers deploying to Dagster Cloud Serverless using the `dagster-cloud` CLI tool, which provides a command-line alternative to the UI-based deployment method.

---

## Overview: UI vs CLI Deployment

**UI-Based Deployment** (Current method):
- Configure code locations via Dagster Cloud web UI
- Set environment variables in web interface
- Automatic deployments on git push (if configured)

**CLI-Based Serverless Deployment**:
- Deploy directly from command line using `dagster-cloud` CLI
- Configure via `dagster_cloud.yaml` file
- More control over deployment process
- Better for CI/CD automation

---

## Prerequisites

- Dagster Cloud account created
- Organization name (from Dagster Cloud UI)
- API token (generate in Dagster Cloud UI)

---

## Step 1: Install dagster-cloud CLI

### Option A: Using pip

```bash
pip install dagster-cloud
```

### Option B: Using uv (Recommended)

```bash
uv pip install dagster-cloud
```

### Option C: Add to Project Dependencies

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "dagster-cloud>=1.7.0,<2.0.0",
]
```

Then install:

```bash
uv sync
```

---

## Step 2: Get Dagster Cloud API Token

1. **Navigate to Dagster Cloud UI**
   - Go to https://cloud.dagster.io
   - Sign in to your account

2. **Generate API Token**
   - Go to **Settings** → **API Tokens**
   - Click **Create API Token**
   - Copy the token (you'll only see it once)
   - Save it securely

3. **Set Environment Variable**
   ```bash
   export DAGSTER_CLOUD_API_TOKEN="your-api-token-here"
   ```

   Or add to your shell profile (`~/.zshrc` or `~/.bashrc`):
   ```bash
   echo 'export DAGSTER_CLOUD_API_TOKEN="your-api-token-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

---

## Step 3: Create dagster_cloud.yaml

Create a `dagster_cloud.yaml` file in your project root:

```yaml
locations:
  - location_name: sbir-etl-production
    code_source:
      python_module: src.definitions
    build:
      python_version: "3.11"
```

**Configuration Options**:

- `location_name`: Name for your code location (matches `code_location_name` in `pyproject.toml`)
- `code_source.python_module`: Module path to your Definitions object (`src.definitions`)
- `build.python_version`: Python version to use

**Advanced Configuration**:

```yaml
locations:
  - location_name: sbir-etl-production
    code_source:
      python_module: src.definitions
    build:
      python_version: "3.11"
      # Optional: specify build steps
      # build_steps:
      #   - pip install -r requirements.txt
    # Optional: specify branch
    # git:
    #   branch: main
```

---

## Step 4: Authenticate with Dagster Cloud

```bash
dagster-cloud auth login
```

This will:
1. Prompt for your API token (or use `DAGSTER_CLOUD_API_TOKEN` env var)
2. Authenticate your CLI session
3. Save credentials locally

**Verify Authentication**:

```bash
dagster-cloud auth status
```

Should show your organization and deployment info.

---

## Step 5: Deploy to Serverless

**Important**: Serverless deployment requires Docker to be running, as it builds a Docker image of your code.

### Prerequisites

1. **Docker must be running**:
   ```bash
   # Check Docker status
   docker ps
   
   # If Docker isn't running, start Docker Desktop
   ```

2. **Set Organization** (if not using default):
   ```bash
   export DAGSTER_CLOUD_ORGANIZATION="your-org-name"
   ```

### Basic Deployment

**Deploy using module name**:

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions
```

This will:
1. Build a Docker image of your code
2. Upload to Dagster Cloud
3. Deploy to Serverless infrastructure
4. Show deployment progress

### Deploy with Options

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions \
  --organization your-org-name
```

### About dagster_cloud.yaml

The `dagster_cloud.yaml` file is primarily for documentation/reference and UI-based deployments. For CLI deployment, you must use explicit flags (`--module-name` and `--location-name`). Do not use `--location-file` with `deploy-python-executable` as it can cause errors.

---

## Step 6: Configure Environment Variables

### Option A: Via CLI

```bash
dagster-cloud serverless set-env \
  --location sbir-etl-production \
  NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io \
  NEO4J_USER=neo4j \
  NEO4J_PASSWORD=your-password \
  NEO4J_DATABASE=neo4j
```

### Option B: Via UI (Recommended)

1. Go to Dagster Cloud UI
2. Navigate to Code Location → Configuration → Environment Variables
3. Add variables as documented in `docs/deployment/dagster-cloud-migration.md`

### Option C: Via YAML File

Create `dagster_cloud_env.yaml`:

```yaml
locations:
  - location_name: sbir-etl-production
    env_vars:
      NEO4J_URI: neo4j+s://xxxxx.databases.neo4j.io
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: your-password
      NEO4J_DATABASE: neo4j
      NEO4J_INSTANCE_TYPE: paid
```

Then apply:

```bash
dagster-cloud serverless set-env --from-file dagster_cloud_env.yaml
```

---

## Step 7: Verify Deployment

### Check Deployment Status

```bash
dagster-cloud serverless status
```

### List Code Locations

```bash
dagster-cloud serverless list-locations
```

### View Deployment Logs

```bash
dagster-cloud serverless logs --location-name sbir-etl-production
```

### Open in Browser

```bash
dagster-cloud serverless open
```

Opens Dagster Cloud UI in your browser.

---

## CI/CD Integration

### GitHub Actions Example

Create `.github/workflows/dagster-cloud-deploy.yml`:

```yaml
name: Deploy to Dagster Cloud Serverless

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.cargo/bin" >> $GITHUB_PATH
      
      - name: Install dependencies
        run: |
          uv pip install dagster-cloud
      
      - name: Deploy to Dagster Cloud
        env:
          DAGSTER_CLOUD_API_TOKEN: ${{ secrets.DAGSTER_CLOUD_API_TOKEN }}
        run: |
          dagster-cloud serverless deploy-python-executable \
            --deployment prod \
            --location-name sbir-etl-production \
            --module-name src.definitions \
            --organization ${{ secrets.DAGSTER_CLOUD_ORG }}
```

**Required GitHub Secrets**:
- `DAGSTER_CLOUD_API_TOKEN` - Your Dagster Cloud API token
- `DAGSTER_CLOUD_ORG` - Your organization name (optional, can be inferred)

---

## Updating Deployments

### Redeploy After Code Changes

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions
```

### Update Environment Variables

```bash
dagster-cloud serverless set-env \
  --location-name sbir-etl-production \
  NEO4J_URI=neo4j+s://new-instance.databases.neo4j.io
```

### Update Configuration

Edit `dagster_cloud.yaml` (if using) and redeploy:

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions
```

---

## Managing Multiple Neo4j Instances

### Switch to Free Instance

```bash
dagster-cloud serverless set-env \
  --location-name sbir-etl-production \
  NEO4J_URI=neo4j+s://free-xxxxx.databases.neo4j.io \
  NEO4J_PASSWORD=free-password \
  NEO4J_INSTANCE_TYPE=free
```

### Switch to Paid Instance

```bash
dagster-cloud serverless set-env \
  --location-name sbir-etl-production \
  NEO4J_URI=neo4j+s://paid-xxxxx.databases.neo4j.io \
  NEO4J_PASSWORD=paid-password \
  NEO4J_INSTANCE_TYPE=paid
```

See `docs/deployment/dagster-cloud-multiple-neo4j-instances.md` for detailed guidance.

---

## Troubleshooting

### Authentication Fails

**Issue**: `dagster-cloud auth login` fails

**Solutions**:
1. Verify API token is correct
2. Check `DAGSTER_CLOUD_API_TOKEN` environment variable
3. Try logging out and back in: `dagster-cloud auth logout && dagster-cloud auth login`

### Deployment Fails

**Issue**: `dagster-cloud serverless deploy-python-executable` fails

**Solutions**:
1. **Docker not running**: Ensure Docker Desktop is running (`docker ps` should work)
2. **Missing location name**: Use `--location-name sbir-etl-production`
3. **Missing module**: Use `--module-name src.definitions`
4. Verify `pyproject.toml` has `[tool.dg.project]` block
5. Check build logs: `dagster-cloud serverless logs --location-name sbir-etl-production`

**Common Error**: `Cannot connect to the Docker daemon`
- **Solution**: Start Docker Desktop and wait for it to fully initialize

**Common Error**: `rpy2-rinterface` compilation fails (library 'emutls_w' not found)
- **Cause**: Dagster Cloud's PEX builder is trying to compile `rpy2-rinterface` from source, which requires R and C compilation tools. The `rpy2` package is in `[project.optional-dependencies]` and is only needed for fiscal analysis features, not core ETL.
- **Solution**: 
  1. **Temporary workaround**: Comment out the `r` optional dependency in `pyproject.toml` before deploying:
     ```toml
     [project.optional-dependencies]
     # r = ["rpy2>=3.5.0,<4.0.0"]  # Temporarily disabled for Dagster Cloud deployment
     dev = [...]
     ```
     Then restore it after deployment if needed for local development.
  
  2. **Permanent solution**: If you don't need fiscal analysis features in Dagster Cloud, remove the `r` optional dependency group entirely from `pyproject.toml`.
  
  3. **Alternative**: The code handles missing `rpy2` gracefully with try/except blocks, so the deployment should work even if `rpy2` fails to compile. However, Dagster Cloud's build process may fail before deployment if compilation errors occur.
  
  **Note**: This is a known limitation - Dagster Cloud's dependency resolver may attempt to build optional dependencies even though they're not required for the core ETL pipeline.

6. Verify all dependencies are listed in `pyproject.toml`

**Common Error**: `ConnectionResetError: Connection reset by peer` during upload
- **Cause**: The PEX bundle is too large (500+ MB), causing network timeouts during upload. This happens when unnecessary files (data/, reports/, docs/, tests/, etc.) are included in the bundle.
- **Solution**: 
  1. **Create `MANIFEST.in` file** in project root to exclude unnecessary files:
     ```plaintext
     # Include only essential source code and configuration
     include src/**/*
     include config/**/*
     include pyproject.toml
     include README.md
     
     # Exclude everything else
     global-exclude *
     prune data
     prune reports
     prune logs
     prune metrics
     prune artifacts
     prune neo4j
     prune docs
     prune archive
     prune tests
     prune scripts
     prune examples
     # ... (see MANIFEST.in in project root for full list)
     ```
  
  2. **Verify `pyproject.toml` limits packages**:
     ```toml
     [tool.hatch.build.targets.wheel]
     packages = ["src"]
     ```
  
  3. **Expected bundle size**: Should reduce from ~522 MB to ~300-370 MB (only `src/`, `config/`, dependencies)
  
  4. **Retry deployment** after creating `MANIFEST.in`
  
  **Reference**: [Dagster Cloud Runtime Environment Documentation](https://docs.dagster.io/deployment/dagster-plus/serverless/runtime-environment#include-data-files)

### Environment Variables Not Working

**Issue**: Variables set via CLI don't appear in UI

**Solutions**:
1. Verify location name matches exactly
2. Check variables are set at location level (not deployment level)
3. Redeploy after setting variables:
   ```bash
   dagster-cloud serverless deploy-python-executable \
     --deployment prod \
     --location-name sbir-etl-production \
     --module-name src.definitions
   ```

### Module Not Found

**Issue**: `python_module: src.definitions` not found

**Solutions**:
1. Verify `src/definitions.py` exists
2. Check `defs` object is exported correctly
3. Verify Python path includes project root
4. Check `pyproject.toml` has correct `[tool.dg.project]` configuration

---

## CLI Commands Reference

### Authentication

```bash
dagster-cloud auth login          # Login with API token
dagster-cloud auth logout         # Logout
dagster-cloud auth status         # Check auth status
```

### Deployment

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name NAME \
  --module-name src.definitions                    # Deploy to serverless

dagster-cloud serverless status                    # Check deployment status
dagster-cloud serverless list-locations            # List all locations
```

### Environment Variables

```bash
dagster-cloud serverless set-env --location-name NAME KEY=VALUE  # Set single variable
dagster-cloud serverless set-env --location-name NAME --from-file FILE  # Set from YAML file
dagster-cloud serverless get-env --location-name NAME           # Get all variables
```

### Logs and Monitoring

```bash
dagster-cloud serverless logs                     # View deployment logs
dagster-cloud serverless logs --location NAME     # Location-specific logs
dagster-cloud serverless open                      # Open UI in browser
```

---

## Comparison: UI vs CLI Deployment

| Feature | UI Deployment | CLI Serverless |
|---------|---------------|----------------|
| Setup Complexity | Low | Medium |
| CI/CD Integration | Manual | Automated |
| Environment Variables | UI only | CLI + UI |
| Deployment Speed | Manual trigger | Command-line |
| Automation | Limited | Full |
| Best For | One-time setup | CI/CD, automation |

---

## Recommended Workflow

### Initial Setup (Use UI)

1. Create code location via Dagster Cloud UI
2. Set environment variables via UI
3. Test deployment

### Ongoing Deployments (Use CLI)

1. Make code changes
2. Commit and push to git
3. Run `dagster-cloud serverless deploy` (or use CI/CD)
4. Monitor deployment

### Hybrid Approach

- **UI**: Initial setup, environment variable management
- **CLI**: Code deployments, CI/CD automation
- **Best of both**: Easy setup + automated deployments

---

## Next Steps

1. **Install CLI**: `pip install dagster-cloud` or add to `pyproject.toml`
2. **Create Config**: Add `dagster_cloud.yaml` to project root
3. **Authenticate**: `dagster-cloud auth login`
4. **Deploy**: `dagster-cloud serverless deploy`
5. **Set Variables**: Configure Neo4j connection via CLI or UI
6. **Test**: Follow testing guide in `docs/deployment/dagster-cloud-testing-guide.md`

---

## Additional Resources

- **Dagster Cloud CLI Docs**: https://docs.dagster.io/dagster-cloud/cli
- **Serverless Deployment**: https://docs.dagster.io/dagster-cloud/deployment/serverless
- **Migration Guide**: `docs/deployment/dagster-cloud-migration.md`
- **Testing Guide**: `docs/deployment/dagster-cloud-testing-guide.md`

