# Quick Start Guide

## Deployment Options

The SBIR ETL pipeline supports two deployment modes:

### Production (Cloud) - Recommended

**Architecture**: Dagster Cloud + AWS Lambda + Neo4j Aura + S3

**Deployment Guides**:
- **[Dagster Cloud Overview](docs/deployment/dagster-cloud-overview.md)** - Primary orchestration prerequisites & env vars
- **[AWS Infrastructure](docs/deployment/aws-infrastructure.md)** - Lambda + S3 + Step Functions
- **[Neo4j Aura Setup](docs/data/neo4j-aura-setup.md)** - Cloud graph database
- **[S3 Data Migration](docs/deployment/s3-data-migration.md)** - S3 data lake setup

**Benefits**:
- Fully managed infrastructure
- Serverless scaling
- Cost-effective ($10/month Dagster Solo + AWS free tier)
- Production-ready observability

### Local Development - For Testing

**Architecture**: Local Dagster + Docker Neo4j + Local Filesystem

---

## Running Dagster Locally (Development)

### Prerequisites

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure Neo4j Aura** (recommended) or **start local Neo4j**:
   ```bash
   # Option A: Neo4j Aura (cloud)
   # Create free instance at https://neo4j.com/cloud/aura
   # Set environment variables:
   export NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
   export NEO4J_USER=neo4j
   export NEO4J_PASSWORD=your-password

   # Option B: Local Docker Neo4j
   docker-compose --profile dev up neo4j -d
   export NEO4J_URI=bolt://localhost:7687
   export NEO4J_USER=neo4j
   export NEO4J_PASSWORD=neo4j
   ```

3. **Configure data storage**:
   ```bash
   # Option A: Use S3 (requires AWS credentials)
   export SBIR_ETL_USE_S3=true
   export SBIR_ETL_S3_BUCKET=your-bucket-name

   # Option B: Use local filesystem (development)
   export SBIR_ETL_USE_S3=false
   # Data will be stored in data/ directory
   ```

## Running Dagster UI

### ⚠️ IMPORTANT: Use Module Import Flag

**You MUST use the `-m` flag** because `definitions.py` uses relative imports:

```bash
uv run dagster dev -m src.definitions
```

**DO NOT use `-f src/definitions.py`** - this will cause import errors.

### Alternative: Using workspace.yaml

If you prefer, you can use:

```bash
uv run dagster dev
```

This should automatically read `workspace.yaml` which uses `python_module: src.definitions`.

**If you still see import errors**, explicitly use `-m src.definitions` as shown above.

### Option 3: Explicit File Path (For debugging)

If you need to use file path directly:

```bash

## First ensure PYTHONPATH includes project root

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
uv run dagster dev -f src/definitions.py
```

After starting, access the UI at: **http://localhost:3000**

## Viewing Assets

Once Dagster is running:

1. Open http://localhost:3000 in your browser
2. Navigate to the **Assets** tab in the left sidebar
3. You should see all your assets listed there
4. Click on any asset to see its details and materialize it

## Materializing Assets

### Via UI:

1. Go to the **Assets** tab
2. Select one or more assets
3. Click the **Materialize** button
4. Monitor progress in the **Runs** tab

### Via Command Line:

```bash

## Materialize a specific job

uv run dagster job execute -m src.definitions -j sbir_etl_job

## Materialize a specific asset

uv run dagster asset materialize -m src.definitions -s raw_sbir_awards
```

## Configuration Files

- **`workspace.yaml`**: Uses `python_module: src.definitions` (module-based import)
- **`pyproject.toml`**: Contains `[tool.dagster]` section with `python_module = "src.definitions"`

## Troubleshooting

If you see import errors about relative imports:

- Make sure you're using `-m src.definitions` instead of `-f src/definitions.py`
- The module-based approach is required because `definitions.py` uses relative imports (`. import assets`)

Some assets may have dependency issues that need to be fixed individually, but the UI should still start and show available assets.
