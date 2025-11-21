# SBIR Analytics - Cloud Infrastructure Summary

## Executive Overview

The SBIR Analytics platform is built on a **hybrid cloud architecture** that combines:
- **AWS** for data storage, compute, and orchestration
- **Neo4j Aura** (cloud-hosted graph database) for entity relationships
- **Dagster Cloud** for data pipeline orchestration (primary production)
- **Docker Compose** for local development and failover

The architecture supports multiple deployment strategies optimized for different use cases (production, weekly refresh, development).

---

## 1. Cloud Provider Configuration

### Primary Cloud Provider: AWS

**Key AWS Services:**
- **S3 (Simple Storage Service)**: Primary data storage (`sbir-etl-production-data` bucket)
- **Lambda**: Serverless compute for data downloads and validation
- **Step Functions**: Orchestrates Lambda workflows for weekly data refresh
- **Secrets Manager**: Secure credential storage (Neo4j credentials)
- **IAM**: Role-based access control and permissions

**AWS Region:** `us-east-2` (default)

**Configuration File:** `/infrastructure/cdk/app.py` (AWS CDK Infrastructure as Code)

**Infrastructure Stacks:**
1. **StorageStack** - S3 bucket with versioning, encryption, and lifecycle policies
   - S3 bucket: `sbir-etl-production-data`
   - Encryption: S3-managed
   - Lifecycle: Raw data retained 30 days, artifacts 90 days
   - Public access: Blocked

2. **SecurityStack** - IAM roles and Secrets Manager
   - Lambda execution role with S3 and Secrets Manager access
   - Step Functions execution role

3. **LambdaStack** - Lightweight Lambda functions with Python 3.11
   - 10 functions deployed via Lambda Layers
   - Note: Container-based functions migrated to Dagster Cloud

4. **StepFunctionsStack** - State machine orchestration
   - Weekly refresh workflow
   - Parallel execution branches
   - Error handling and retry logic

---

## 2. Data Storage Solutions

### Primary Storage: S3
**Bucket Name:** `sbir-etl-production-data`

**S3 Directory Structure:**
```
s3://sbir-etl-production-data/
├── raw/
│   ├── awards/{date}/award_data.csv          # SBIR awards from sbir.gov
│   ├── uspto/patentsview/                    # Patent data
│   ├── uspto/assignments/                    # Patent assignments
│   └── uspto/ai_patents/                     # AI-related patents
├── artifacts/
│   └── {processed outputs}                   # Processed results (90-day retention)
└── transformed/
    └── {transformed data}                    # Normalized data
```

**Access Pattern:**
- **S3-First Strategy**: Code uses `cloudpathlib` library
  - Tries S3 first when bucket is configured
  - Falls back to local files if S3 unavailable
  - Environment variable: `SBIR_ANALYTICS_S3_BUCKET` or `S3_BUCKET`

**Implementation:** `/src/utils/cloud_storage.py`
- `resolve_data_path()`: Resolves S3 URLs with local fallback
- `build_s3_path()`: Constructs S3 URLs from relative paths
- `_download_s3_to_temp()`: Caches downloaded files locally

### Secondary Storage: DuckDB
**Purpose:** In-memory/local database for data processing

**Configuration:**
- Database path: `data/processed/sbir.duckdb` (can be in-memory)
- Memory limit: 4 GB
- Threads: 4

**Usage:**
- Extract CSV/COPY dumps into DuckDB tables
- Perform transformations and joins
- Query intermediate results

### Graph Database: Neo4j Aura (Cloud)
**Purpose:** Store entity relationships (companies, awards, patents)

**Configuration:**
- URI: `NEO4J_URI` environment variable
- Credentials: `NEO4J_USER`, `NEO4J_PASSWORD` (from Secrets Manager)
- Database: `neo4j` (default)
- Batch size: 5000 for UNWIND operations
- Auto-migration: Enabled

**Local Development:** Neo4j 5.20.0 in Docker Compose
- Bolt port: 7687
- HTTP port: 7474
- Volume mounts for data persistence

---

## 3. Data Ingestion Pipelines (ETL)

### Pipeline Orchestrator: Dagster Cloud (Primary)
**Configuration:** `/dagster_cloud.yaml`

**Code Location:**
```yaml
locations:
  - location_name: sbir-analytics-production
    code_source:
      python_module: src.definitions
    build:
      python_version: "3.11"
```

**Key Dagster Assets (Data Pipeline):**

#### Extraction Assets
1. **`raw_sbir_awards`**
   - Source: SBIR CSV from `sbir.gov`
   - Method: DuckDB CSV import
   - Path: S3-first (`data/raw/sbir/award_data.csv`)
   - Location: `/src/assets/sbir_ingestion.py`

2. **`raw_usaspending_recipients` & `raw_usaspending_transactions`**
   - Source: USAspending PostgreSQL dump (COPY format)
   - Method: DuckDB COPY import
   - Location: `/src/assets/usaspending_ingestion.py`

3. **`raw_uspto_patents` & `raw_uspto_assignments`**
   - Source: USPTO PatentsView API & Patent Assignment Dataset
   - Formats: NDJSON, CSV, Parquet, Stata (.dta)
   - Location: `/src/assets/uspto/`
   - Download via Lambda functions

#### Validation & Enrichment Assets
4. **`validated_sbir_awards`** - Quality gates on SBIR data
5. **`usaspending_iterative_enrichment`** - Progressive enrichment via APIs
6. **`stale_usaspending_awards`** - SLA-based refresh detection

#### Loading Assets
7. **`neo4j_sbir_awards`** - Load awards to Neo4j graph

---

### AWS Lambda Functions (Secondary Orchestration)

**Purpose:** Download external datasets and trigger processing

**Functions Deployed:**
1. **`download-csv`** - Download SBIR awards CSV
   - Source: `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`
   - Output: Stores in S3 with SHA256 hash verification
   - Location: `/scripts/lambda/download_csv/lambda_handler.py`

2. **`download-uspto-patentsview`** - PatentsView patent data
   - Tables: patent, assignee, inventor
   - S3 prefix: `raw/uspto/patentsview`
   - Location: `/scripts/lambda/download_uspto_patentsview/lambda_handler.py`

3. **`download-uspto-assignments`** - Patent assignment dataset
   - Format: CSV or DTA
   - S3 prefix: `raw/uspto/assignments`
   - Location: `/scripts/lambda/download_uspto_assignments/lambda_handler.py`

4. **`download-uspto-ai-patents`** - AI patent dataset
   - Format: CSV.zip
   - S3 prefix: `raw/uspto/ai_patents`
   - Location: `/scripts/lambda/download_uspto_ai_patents/lambda_handler.py`

5. **`validate-dataset`** - Data quality checks
6. **`profile-inputs`** - Data profiling and statistics
7. **`enrichment-checks`** - Enrichment validation
8. **`reset-neo4j`** - Clear Neo4j database
9. **`smoke-checks`** - Health checks
10. **`trigger-dagster-refresh`** - Trigger Dagster Cloud jobs

**Configuration:**
- Runtime: Python 3.11
- Timeout: 15 minutes (AWS limit)
- Memory: 512-1024 MB
- Layers: Python dependencies (shared layer)

---

### AWS Step Functions (Weekly Refresh Workflow)

**State Machine:** `sbir-analytics-weekly-refresh`

**Workflow Steps:**
```
1. DownloadCSV
   ├─→ CheckChanges
   │   ├─→ ProcessPipeline (Parallel)
   │   │   ├─→ ValidateDataset
   │   │   └─→ ProfileInputs
   │   └─→ TriggerDagsterRefresh
   │       └─→ EnrichmentChecks
   │           └─→ ResetNeo4j
   │               └─→ SmokeChecks
   │                   └─→ Success
   └─→ EndNoChanges (if no changes)
```

**Configuration File:** `/infrastructure/step-functions/weekly-refresh-state-machine.json`

**Features:**
- Hash-based change detection (skip if unchanged)
- Parallel validation and profiling
- Retry logic with exponential backoff
- Error handling and notifications

---

## 4. Configuration Files for Cloud Services

### Main Configuration Files

**Base Configuration:** `/config/base.yaml`
- Default settings (version controlled)
- 600+ lines of comprehensive defaults
- Environment overrides: `dev.yaml`, `test.yaml`, `prod.yaml` (see `config/README.md` for details)
- Docker configuration reference: `docs/deployment/docker-config-reference.md`

**Key Configuration Sections:**

#### S3/Cloud Storage
```yaml
extraction:
  sbir:
    csv_path: "data/raw/sbir/award_data.csv"      # Local fallback
    csv_path_s3: null                              # Auto-built from bucket
    use_s3_first: true                             # Try S3 first
    duckdb:
      database_path: ":memory:"
      table_name: "sbir_awards"
```

#### API Enrichment Configuration
```yaml
enrichment:
  sam_gov:
    base_url: "https://api.sam.gov/entity-information/v3"
    rate_limit_per_minute: 60
    timeout_seconds: 30

  usaspending_api:
    base_url: "https://api.usaspending.gov/api/v2"
    timeout_seconds: 30

  patentsview_api:
    base_url: "https://search.patentsview.org/api"
    rate_limit_per_minute: 60
    cache:
      enabled: true
      cache_dir: "data/cache/patentsview"
      ttl_hours: 24

  enrichment_refresh:
    usaspending:
      cadence_days: 1                              # Daily refresh
      sla_staleness_days: 1
      batch_size: 100
      max_concurrent_requests: 5
      rate_limit_per_minute: 120
      enable_delta_detection: true
      cache:
        enabled: true
        cache_dir: "data/cache/usaspending"
        ttl_hours: 24
```

#### Neo4j Configuration
```yaml
loading:
  neo4j:
    uri_env_var: "NEO4J_URI"
    user_env_var: "NEO4J_USER"
    password_env_var: "NEO4J_PASSWORD"  # pragma: allowlist secret
    batch_size: 1000
    parallel_threads: 4
    transaction_timeout_seconds: 300
    create_indexes: true
    create_constraints: true
```

#### Data Quality Thresholds
```yaml
data_quality:
  sbir_awards:
    pass_rate_threshold: 0.95
    completeness_threshold: 0.90
    uniqueness_threshold: 0.99

  enrichment:
    sam_gov_success_rate: 0.85
    usaspending_match_rate: 0.70
    regression_threshold_percent: 0.05
```

### Infrastructure Configuration

**AWS CDK:** `/infrastructure/cdk/`
- `app.py` - Main CDK application
- `stacks/storage.py` - S3 bucket configuration
- `stacks/security.py` - IAM roles and Secrets Manager
- `stacks/lambda_stack.py` - Lambda functions
- `stacks/step_functions_stack.py` - State machine definition

**Docker Compose:** `/docker-compose.yml`
- Development and CI/test profiles
- Neo4j, Dagster webserver, daemon, ETL runner services
- Volume mounts and resource limits

---

## 5. External Data Sources & ETL Processes

### Data Sources

| Source | Type | Update Cadence | Access Method | Storage |
|--------|------|----------------|---------------|---------|
| **SBIR.gov** | CSV | Weekly (max) | Direct HTTP | S3 `raw/awards/` |
| **USAspending.gov** | PostgreSQL dump | Weekly API | API & dump | DuckDB |
| **USPTO PatentsView** | CSV/Parquet | Monthly | S3 download | S3 `raw/uspto/patentsview/` |
| **USPTO Assignments** | CSV/DTA | Monthly | HTTPS | S3 `raw/uspto/assignments/` |
| **USPTO AI Patents** | CSV | Quarterly | HTTPS | S3 `raw/uspto/ai_patents/` |
| **SAM.gov** | API | Real-time | REST API | Cache + Neo4j |
| **PatentsView API** | JSON | Real-time | REST API | Cache + Neo4j |

### ETL Process Flow

```
External Data Sources
    ├─→ SBIR.gov CSV
    │   └─→ Lambda: download-csv
    │       └─→ S3: raw/awards/{date}/
    │
    ├─→ USPTO PatentsView
    │   └─→ Lambda: download-uspto-patentsview
    │       └─→ S3: raw/uspto/patentsview/
    │
    └─→ USAspending API
        └─→ Dagster: usaspending_iterative_enrichment
            └─→ Cache + Neo4j

Step Functions Orchestration (Weekly)
    ├─→ DownloadCSV (Lambda)
    │   └─→ Hash check for changes
    │
    ├─→ Parallel Processing
    │   ├─→ ValidateDataset (Lambda)
    │   └─→ ProfileInputs (Lambda)
    │
    ├─→ TriggerDagsterRefresh (Lambda)
    │   └─→ Dagster Cloud sbir_weekly_refresh_job
    │       ├─→ raw_sbir_awards (extract)
    │       ├─→ validated_sbir_awards (validate)
    │       └─→ neo4j_sbir_awards (load)
    │
    └─→ Post-Processing
        ├─→ EnrichmentChecks (Lambda)
        ├─→ ResetNeo4j (Lambda)
        └─→ SmokeChecks (Lambda)

Final State
    └─→ Neo4j Aura: Graph of companies, awards, patents
```

### API Clients

**Implemented API Integrations:**

1. **USAspending API** (`/src/enrichers/usaspending/client.py`)
   - Async client with rate limiting
   - Delta detection (SHA256 hashing)
   - State management and checkpointing
   - Configurable retry and backoff strategies

2. **PatentsView API** (`/src/enrichers/patentsview.py`)
   - Patent search and retrieval
   - API key authentication
   - Response caching (configurable TTL)
   - Rate limiting

3. **SAM.gov API** (configured, not fully implemented)
   - Entity information lookup
   - Rate limiting: 60 req/min
   - Timeout: 30 seconds

### Data Transformation Pipeline

**Location:** `/src/assets/`, `/src/transformers/`

**Key Transformations:**
- SBIR award normalization and validation
- USAspending join and enrichment
- Patent data parsing (NDJSON, CSV, DTA formats)
- Company deduplication via fuzzy matching
- NAICS to BEA sector mapping

---

## 6. Summary: Key Infrastructure Components

### Production Deployment Stack
```
Dagster Cloud Serverless
├── Code Location: src.definitions
├── Orchestrates: Extraction, validation, enrichment, loading
├── Compute: Dagster Cloud managed
└── Monitoring: Built-in Dagster observability

↓↓↓

AWS Infrastructure
├── S3: sbir-etl-production-data bucket
│   └── Raw data, transformed outputs, caches
├── Lambda: 10 lightweight functions
│   └── Data downloads, validation, checks
└── Step Functions: Weekly refresh state machine
    └── Orchestrates Lambda + Dagster workflows

↓↓↓

External Services
├── Neo4j Aura: Graph database
│   └── Stores companies, awards, patents, relationships
├── External APIs:
│   ├── SAM.gov (entity information)
│   ├── USAspending (award details)
│   ├── PatentsView (patent search)
│   └── USPTO (patent data dumps)
└── Data Warehouses:
    └── DuckDB (local query engine)
```

### Development Deployment Stack
```
Docker Compose (Local)
├── Neo4j 5.20.0 (Bolt 7687, HTTP 7474)
├── Dagster Webserver (port 3000)
├── Dagster Daemon
├── ETL Runner
└── Tools Container

Data Storage
├── Local volumes: ./data, ./reports, ./logs
├── Named volumes: neo4j_data, neo4j_logs, neo4j_import
└── In-memory: DuckDB (:memory: or ./data/processed/)
```

---

## 7. Typical Data Ingestion Flow

### Weekly SBIR Refresh Cycle

**Trigger:** CloudWatch scheduled event or manual trigger

**Step 1: Download Latest Data**
- Lambda `download-csv` fetches SBIR CSV from sbir.gov
- Computes SHA256 hash of file
- Uploads to S3 with metadata
- Returns change status

**Step 2: Validate & Profile** (Parallel)
- Lambda `validate-dataset`: Quality checks (schema, completeness, uniqueness)
- Lambda `profile-inputs`: Data statistics and distribution analysis

**Step 3: Trigger Dagster Pipeline**
- Lambda `trigger-dagster-refresh` calls Dagster Cloud API
- Starts `sbir_weekly_refresh_job`:
  - Extract CSV from S3 to DuckDB
  - Validate against defined rules
  - Load into Neo4j

**Step 4: Post-Processing**
- Lambda `enrichment-checks`: Verify enrichment success
- Lambda `reset-neo4j`: Optional database reset
- Lambda `smoke-checks`: Final health checks

**Step 5: Continuous Enrichment** (Asynchronous)
- Dagster continuously runs `usaspending_iterative_enrichment`
  - Refreshes stale enrichment records
  - Caches API responses (24-hour TTL)
  - Updates Neo4j with new data

---

## 8. Configuration & Environment Management

### Environment Variables
```bash
# AWS
AWS_ACCOUNT_ID=<account-id>
AWS_REGION=us-east-2

# S3
SBIR_ANALYTICS_S3_BUCKET=sbir-etl-production-data
S3_BUCKET=sbir-etl-production-data

# Neo4j
NEO4J_URI=bolt://neo4j-aura.databases.neo4j.io:7687
NEO4J_USER=<username>
NEO4J_PASSWORD=<password>

# External APIs
SAM_GOV_API_KEY=<api-key>
PATENTSVIEW_API_KEY=<api-key>
HF_TOKEN=<huggingface-token>

# Dagster Cloud
DAGSTER_CLOUD_ORGANIZATION=<org-name>
DAGSTER_CLOUD_AGENT_TOKEN=<agent-token>
```

### Configuration Hierarchy
1. **Base Config** (`config/base.yaml`) - Defaults
2. **Environment Config** (`config/{env}.yaml`) - Environment-specific overrides
3. **Environment Variables** - Runtime overrides
4. **Command-line Args** - Temporary overrides

---

## Conclusion

The SBIR Analytics platform uses a **modern, scalable cloud architecture** with:

- **AWS S3** as the primary data lake
- **Dagster Cloud** as the production orchestration engine
- **Neo4j Aura** as the graph database for entity relationships
- **AWS Lambda + Step Functions** for serverless weekly workflows
- **Multiple external APIs** for continuous data enrichment
- **DuckDB** for efficient local data processing
- **Docker Compose** for local development

This architecture supports **daily incremental updates**, **quality gates**, **error recovery**, and **comprehensive observability**, while remaining **cost-effective** and **maintainable**.
