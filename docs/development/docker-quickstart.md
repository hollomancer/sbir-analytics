---
Type: Guide
Owner: devops@project
Last-Reviewed: 2025-01-XX
Status: active
---

# Docker Quick Start Guide

This guide walks you through setting up the SBIR ETL pipeline using Docker for local development. **Estimated time: 20-30 minutes** (first time).

## Prerequisites

Before starting, ensure you have:
- **Docker Desktop** or **Docker Engine 20.10+** with **Compose V2**
- **5GB+ free disk space** (for image and data)
- **Ports available:** 3000, 7474, 7687

## Step 1: Check Prerequisites (1 minute)

Run the prerequisites check to verify your environment:

```bash
make docker-check-prerequisites
```

**Expected output:**
```
➤ Checking Docker development prerequisites...
✓ Docker CLI found: 24.0
✓ Docker Compose V2 found: 2.24.0
✓ Docker daemon is running
✓ Port 3000 is available
✓ Port 7474 is available
✓ Port 7687 is available
✓ Sufficient disk space: 50GB available

✓ All prerequisites met!

You're ready to run: make docker-build
```

**If you see errors:**
- Docker not found: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Docker daemon not running: Start Docker Desktop
- Ports in use: Stop services using those ports or see [Troubleshooting Guide](docker-troubleshooting.md)

## Step 2: Configure Environment (2 minutes)

### 2.1 Copy Environment Template

```bash
cp .env.example .env
```

### 2.2 Edit `.env` File

Open `.env` in your editor. For **local development**, you only need to set these:

```bash
# Neo4j credentials (for local Docker Neo4j)
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
```

**That's it!** The defaults work fine for local development.

**Optional:** If you want to use Neo4j Aura (cloud) instead of local Docker Neo4j:
```bash
# Neo4j Aura (cloud) - get credentials from https://console.neo4j.io/
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
```

**For more environment variables**, see [Environment Setup Guide](docker-env-setup.md).

## Step 3: Build Docker Image (10-20 minutes)

**First build takes longer** - subsequent builds are faster due to caching.

```bash
make docker-build
```

**What's happening:**
- Building Python application image
- Installing Python dependencies
- Installing R packages (StateIO for fiscal analysis) - **this takes 5-10 minutes**
- Creating runtime image

**Expected output:**
```
➤ Building Docker image sbir-analytics:latest
✓ Image sbir-analytics:latest ready
```

**If build fails:**
- Check error messages - common issues in [Troubleshooting Guide](docker-troubleshooting.md)
- Ensure Docker has enough resources (Settings → Resources in Docker Desktop)
- Try: `docker system prune` to free space

## Step 4: Start Services (2-3 minutes)

Start the development stack:

```bash
make docker-up-dev
```

**What's starting:**
- **Neo4j** - Graph database (ports 7474, 7687)
- **Dagster webserver** - Pipeline UI (port 3000)
- **Dagster daemon** - Background scheduler

**Expected output:**
```
➤ Starting development stack (profile: dev)
✓ Development stack ready
```

**Services will take 1-2 minutes to become healthy.** The entrypoint scripts wait for dependencies automatically.

## Step 5: Verify Setup (30 seconds)

Verify everything is working:

```bash
make docker-verify
```

**Expected output:**
```
➤ Verifying Docker setup
➤ Checking Neo4j connectivity...
✓ Neo4j is accessible at bolt://localhost:7687
➤ Checking Dagster UI...
✓ Dagster UI is accessible at http://localhost:3000
➤ Checking service status...
✓ All services are running

✓ Docker setup verification passed!

  • Dagster UI: http://localhost:3000
  • Neo4j Browser: http://localhost:7474
  • View logs: make docker-logs SERVICE=<name>
```

**If verification fails:**
- Check service logs: `make docker-logs SERVICE=neo4j` or `make docker-logs SERVICE=dagster-webserver`
- See [Troubleshooting Guide](docker-troubleshooting.md)

## Step 6: Access Services

### Dagster UI

Open in your browser: **http://localhost:3000**

**What you'll see:**
- Asset catalog
- Job definitions
- Run history
- Schedules

**First steps:**
1. Navigate to **Assets** tab
2. Click **Materialize** on `raw_sbir_awards` to run your first pipeline
3. Monitor progress in the **Runs** tab

### Neo4j Browser

Open in your browser: **http://localhost:7474**

**Login:**
- Username: `neo4j` (or value from `.env`)
- Password: `test` (or value from `.env`)

**First query:**
```cypher
MATCH (n) RETURN count(n) as node_count;
```

This shows how many nodes are in the database (will be 0 until you materialize assets).

## Next Steps

### Run Your First Pipeline

1. **In Dagster UI:**
   - Go to **Assets** tab
   - Find `raw_sbir_awards` asset
   - Click **Materialize**
   - Watch the run in **Runs** tab

2. **Or via CLI:**
   ```bash
   docker compose --profile dev exec dagster-webserver \
     dagster asset materialize -f src.definitions -s raw_sbir_awards
   ```

### Run Tests

```bash
make docker-test
```

This runs the full test suite in containers (mirrors CI environment).

### Development Workflow

**Daily workflow:**
```bash
# Start services
make docker-up-dev

# View logs
make docker-logs SERVICE=dagster-webserver

# Run commands in container
docker compose --profile dev exec dagster-webserver sh

# Stop services
make docker-down
```

**Code changes:**
- Code is bind-mounted, so changes are live
- Dagster dev mode auto-reloads on code changes
- No need to rebuild unless Dockerfile changes

## Common Commands

| Command | Description |
|---------|-------------|
| `make docker-check-prerequisites` | Check Docker setup |
| `make docker-build` | Build Docker image |
| `make docker-up-dev` | Start development stack |
| `make docker-verify` | Verify services are working |
| `make docker-down` | Stop all services |
| `make docker-logs SERVICE=<name>` | View service logs |
| `make docker-rebuild` | Rebuild and restart |
| `make docker-test` | Run tests in containers |
| `make neo4j-check` | Check Neo4j health |

## Troubleshooting

**Services won't start:**
- Check prerequisites: `make docker-check-prerequisites`
- Check logs: `make docker-logs SERVICE=<name>`
- See [Troubleshooting Guide](docker-troubleshooting.md)

**Build fails:**
- Ensure Docker has enough resources (4GB+ RAM recommended)
- Check disk space: `docker system df`
- See [Troubleshooting Guide](docker-troubleshooting.md)

**Can't connect to services:**
- Verify services are running: `docker compose --profile dev ps`
- Check ports aren't in use: `lsof -i :3000`
- See [Troubleshooting Guide](docker-troubleshooting.md)

## What's Next?

- **[Environment Setup Guide](docker-env-setup.md)** - Configure all environment variables
- **[Troubleshooting Guide](docker-troubleshooting.md)** - Common issues and solutions
- **[Containerization Guide](../deployment/containerization.md)** - Advanced Docker usage
- **[Testing Guide](../testing/index.md)** - Running tests in Docker

## Quick Reference

**Service URLs:**
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474
- Neo4j Bolt: bolt://localhost:7687

**Default Credentials (local dev):**
- Neo4j User: `neo4j`
- Neo4j Password: `test`

**Data Locations:**
- Application code: `./src` (bind-mounted, live editing)
- Data files: `./data` (bind-mounted)
- Logs: `./logs` (bind-mounted)
- Reports: `./reports` (bind-mounted)

---

**Need help?** Check the [Troubleshooting Guide](docker-troubleshooting.md) or see [Containerization Guide](../deployment/containerization.md) for advanced usage.

