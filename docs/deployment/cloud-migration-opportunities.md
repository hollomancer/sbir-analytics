# Cloud Migration Opportunities

**Date**: January 2025  
**Purpose**: Identify infrastructure components that can be migrated to fully hosted cloud services, avoiding VMs and self-hosting

---

## Executive Summary

This document identifies infrastructure components currently running in Docker containers or on local filesystems that can be migrated to fully managed cloud services. The goal is to eliminate VM management and self-hosted infrastructure while maintaining functionality and reducing operational overhead.

---

## Current Infrastructure Assessment

### Currently Self-Hosted/Containerized

1. **Neo4j Database** - Docker containers (`docker-compose.yml`)
2. **Dagster Orchestration** - Docker containers (webserver + daemon)
3. **File Storage** - Local filesystem (`data/`, `reports/`, `logs/` directories)
4. **Logging** - Local log files (`logs/` directory)
5. **Metrics/Reports** - Local JSON files (`reports/metrics/`)

### Already Cloud-Hosted

- ✅ **CI/CD**: GitHub Actions (fully managed)
- ✅ **Source Control**: GitHub (fully managed)
- ✅ **Container Registry**: Likely Docker Hub/GitHub Container Registry (fully managed)

---

## Migration Opportunities

### 1. Neo4j → Neo4j Aura (Fully Managed)

**Current State**: Docker containers with local volumes  
**Target**: Neo4j Aura (cloud-hosted)

**Benefits**:
- ✅ No container management
- ✅ Automatic backups
- ✅ Auto-scaling
- ✅ High availability (99.95% SLA on Professional tier)
- ✅ Built-in monitoring
- ✅ SSL/TLS encryption by default

**Options**:
- **Aura Free**: 200k nodes + relationships, 50MB storage (free)
- **Aura Professional**: Starting at ~$65/month (1GB RAM, 8GB storage)
- **Aura Enterprise**: Custom pricing for larger deployments

**Migration Path**:
1. Create Neo4j Aura instance
2. Update connection strings in config (already supports Aura URIs)
3. Migrate data using existing Neo4j export/import tools
4. Update environment variables (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`)

**Status**: ✅ Already partially supported (see `docs/data/neo4j-aura-setup.md`)

---

### 2. Dagster → Dagster Cloud (Fully Managed)

**Current State**: Docker containers (`dagster-webserver`, `dagster-daemon`)  
**Target**: Dagster Cloud (fully managed orchestration)

**Benefits**:
- ✅ No container orchestration management
- ✅ Built-in scheduling and monitoring
- ✅ Automatic scaling
- ✅ Integrated with GitHub for deployments
- ✅ Built-in alerting and notifications
- ✅ Asset lineage visualization
- ✅ Code location management

**Your Current Setup Analysis**:
- **Assets**: ~117 assets across 32 files
- **Jobs**: 10 jobs (SBIR ingestion, ETL, CET, Transition, Fiscal, etc.)
- **Schedules**: 3 schedules (daily runs)
- **Sensors**: 1 sensor (USAspending refresh)
- **Code Locations**: 8+ modules (assets, fiscal_assets, sbir_ingestion, usaspending_ingestion, uspto_assets, cet_assets, transition_assets, etc.)

**Dagster Cloud Tier Recommendation**:

**Note**: Dagster Cloud does not offer a free plan. The cheapest option is the **Solo Plan** at $10/month. However, all plans include a **30-day free trial** to test before committing.

#### Option 0: Solo Plan ($10/month) - **Cheapest option, but very limited**
- **1 user** ⚠️ (single user only)
- **1 code location** ❌ (you have 8+ modules - **won't work**)
- **7,500 Dagster Credits/month** (may be tight for your workload)
- **1 deployment** ✅

**Verdict**: ❌ **Not viable** - You have 8+ code locations and need more than 1 user. This plan won't work for your setup.

#### Option 1: Starter Plan ($100/month) - **Recommended if you can consolidate**
- **Up to 3 users** ✅ (good for small team)
- **5 code locations** ⚠️ (you have 8+ modules - need to consolidate)
- **30,000 Dagster Credits/month** (likely sufficient for your workload)
- **1 deployment** ✅
- **30-day free trial** ✅

**Action Required**: Consolidate your 8+ code location modules into 5 or fewer. You can combine related modules (e.g., merge all `uspto_assets` into one location, combine `transition_assets` modules).

**What you can do with Starter Plan**:
- ✅ Run all your 10 jobs
- ✅ Use all 3 schedules (daily runs)
- ✅ Use your 1 sensor
- ✅ Access Dagster UI and monitoring
- ✅ GitHub integration for deployments
- ✅ Environment variable management
- ✅ Asset lineage visualization

#### Option 2: Pro Plan (Contact Sales) - **Best fit for current structure**
- **Unlimited code locations** ✅ (no consolidation needed)
- **Unlimited deployments** ✅
- **Cost tracking and insights** ✅
- **Personalized onboarding** ✅
- **Uptime SLAs** ✅
- **30-day free trial** ✅

**Recommendation**: 
1. **Try the 30-day free trial** on Starter Plan to test consolidation
2. If consolidation works well, stick with **Starter Plan ($100/month)**
3. If consolidation is too difficult or you need multiple deployments, upgrade to **Pro Plan**

**Migration Path**:
1. Sign up for Dagster Cloud account (30-day free trial available)
2. Connect GitHub repository
3. Configure code locations (consolidate if using Starter)
4. Set environment variables via Dagster Cloud UI (Neo4j Aura credentials, etc.)
5. Deploy assets and jobs
6. Configure schedules (your 3 daily schedules will work automatically)

**Considerations**:
- Dagster Cloud requires code to be in a Git repository (✅ already on GitHub)
- Supports environment variable management
- Can connect to Neo4j Aura seamlessly
- Code location consolidation: You can merge modules by updating `src/definitions.py` to load from fewer locations

**Status**: ⚠️ Mentioned as optional in `archive/openspec/openspec/project.md` but not implemented

---

### 3. File Storage → Cloud Object Storage

**Current State**: Local filesystem (`data/`, `reports/`, `logs/` directories)  
**Target**: AWS S3, Google Cloud Storage, or Azure Blob Storage

**Benefits**:
- ✅ Unlimited scalability
- ✅ Automatic backups and versioning
- ✅ Lifecycle policies (archive old data)
- ✅ Cross-region replication
- ✅ Access control and encryption
- ✅ Cost-effective for large datasets

**Use Cases**:
1. **Raw Data Storage** (`data/raw/`)
   - SBIR CSV files
   - USPTO patent data
   - USAspending dumps
   
2. **Processed Data** (`data/processed/`, `data/enriched/`)
   - Intermediate pipeline outputs
   - Validated datasets
   
3. **Artifacts & Reports** (`reports/`)
   - Validation reports
   - Performance metrics
   - Analysis outputs
   
4. **Backups** (mentioned in `archive/openspec/openspec/changes/add-neo4j-backup-sync/proposal.md`)
   - Neo4j database backups
   - State files

**Migration Path**:
1. Create S3/GCS/Azure storage bucket
2. Update code to use cloud storage SDKs:
   - `boto3` for AWS S3
   - `google-cloud-storage` for GCS
   - `azure-storage-blob` for Azure
3. Update configuration paths to use cloud URIs
4. Migrate existing data (one-time)
5. Update Dagster assets to read/write from cloud storage

**Code Changes Needed**:
- Replace `Path()` operations with cloud storage clients
- Update `config/base.yaml` paths to use cloud URIs (e.g., `s3://bucket-name/data/raw/`)
- Consider using `cloudpathlib` (already in `uv.lock`) for cloud-agnostic path handling

**Cost**: 
- **AWS S3**: ~$0.023/GB/month (Standard tier)
- **GCS**: ~$0.020/GB/month (Standard storage)
- **Azure Blob**: ~$0.018/GB/month (Hot tier)

**Status**: ⚠️ Not implemented (local filesystem only)

---

### 4. Logging → Cloud Logging Services

**Current State**: Local log files (`logs/` directory) using `loguru`  
**Target**: CloudWatch, Datadog, Loggly, or GCP Cloud Logging

**Benefits**:
- ✅ Centralized log aggregation
- ✅ Search and filtering across all logs
- ✅ Alerting on error patterns
- ✅ Log retention policies
- ✅ Integration with monitoring tools
- ✅ No local disk space concerns

**Options**:

#### AWS CloudWatch Logs
- Integrated with AWS ecosystem
- Pay per GB ingested (~$0.50/GB)
- 30-day retention included

#### Datadog
- Advanced log analytics
- Integration with metrics and APM
- Starting at ~$15/month per host

#### Google Cloud Logging
- Integrated with GCP services
- Free tier: 50GB ingestion/month
- Pay-as-you-go after free tier

#### Loggly
- Simple, focused on log management
- Starting at ~$79/month

**Migration Path**:
1. Choose logging service (recommend **Datadog** for simplicity)
2. Install SDK/client library (`pip install datadog` or `boto3` for CloudWatch)
3. Add ~20 lines to `src/utils/logging_config.py` to add cloud sink
4. Set environment variables for credentials
5. Configure log retention policies in cloud service
6. Set up alerts for critical errors

**Code Changes Needed**:
- Add cloud logging sink to `loguru` configuration (very simple!)
- Update `setup_logging()` to optionally send to cloud
- Maintain local logging as fallback option

**Example Implementation** (Datadog):
```python
# In src/utils/logging_config.py, add after line 89:

# Optional: Add Datadog sink if credentials are available
if os.getenv("DD_API_KEY"):
    from datadog import initialize, api
    initialize(api_key=os.getenv("DD_API_KEY"), app_key=os.getenv("DD_APP_KEY"))
    
    def datadog_sink(message):
        """Send log message to Datadog."""
        record = message.record
        api.Event.create(
            title=f"{record['level'].name}",
            text=record['message'],
            tags=[f"stage:{record['extra'].get('stage', 'unknown')}"],
            alert_type=record['level'].name.lower()
        )
    
    logger.add(datadog_sink, level=safe_level, serialize=True)
```

**Status**: ⚠️ Not implemented (local files only) - **EASIEST TO IMPLEMENT NEXT**

---

### 5. Metrics & Monitoring → Cloud Observability Platforms

**Current State**: Local JSON files (`reports/metrics/`)  
**Target**: Datadog, New Relic, or CloudWatch Metrics

**Benefits**:
- ✅ Real-time dashboards
- ✅ Custom alerts and notifications
- ✅ Historical trend analysis
- ✅ Integration with logging and tracing
- ✅ Team collaboration features

**Use Cases**:
1. **Pipeline Metrics** (`reports/metrics/enrichment_freshness.json`)
   - Execution times
   - Throughput (records/second)
   - Success rates
   
2. **Performance Metrics**
   - Memory usage
   - API response times
   - Error rates

3. **Data Quality Metrics**
   - Validation pass rates
   - Data freshness
   - Completeness scores

**Options**:

#### Datadog
- Comprehensive observability platform
- Custom metrics, dashboards, alerts
- Starting at ~$15/month per host

#### New Relic
- Application performance monitoring
- Custom metrics and dashboards
- Free tier available (100GB/month)

#### AWS CloudWatch Metrics
- Integrated with AWS services
- Custom metrics support
- Pay per metric (~$0.30/metric/month)

**Migration Path**:
1. Choose observability platform
2. Install SDK/client library
3. Update `src/utils/performance_monitor.py` to send metrics
4. Create dashboards for key metrics
5. Configure alerts for thresholds

**Status**: ⚠️ Not implemented (local JSON files only)

---

### 6. Container Registry → Cloud Container Registries

**Current State**: Likely Docker Hub or GitHub Container Registry  
**Target**: Fully managed container registries

**Options**:
- ✅ **GitHub Container Registry (ghcr.io)**: Already available, fully managed
- ✅ **AWS ECR**: Integrated with AWS services
- ✅ **Google Container Registry**: Integrated with GCP
- ✅ **Azure Container Registry**: Integrated with Azure

**Status**: ✅ Likely already using cloud-hosted registry

---

## Migration Priority & Roadmap

### ⚡ EASIEST: Cloud Logging (Start Here!)

**Why it's easiest:**
- ✅ You already use `loguru` which has built-in sink support
- ✅ Minimal code changes (~20 lines)
- ✅ Can be done incrementally (keep local logging as fallback)
- ✅ No data migration needed
- ✅ Immediate value for debugging

**Quick Implementation:**
1. Choose a service (recommend **Datadog** or **CloudWatch** for simplicity)
2. Add ~20 lines to `src/utils/logging_config.py` to add a cloud sink
3. Set environment variables for credentials
4. Done! Logs now go to both local files AND cloud

**Estimated time:** 30-60 minutes

### Phase 1: Quick Wins (Low Effort, High Value)
1. ✅ **Neo4j Aura** - Already set up!
2. ⚡ **Cloud Logging** - Easiest next step (see above)
3. **Cloud Object Storage** - High impact, but requires more code changes

### Phase 2: Orchestration (Medium Effort, High Value)
4. **Dagster Cloud** - Eliminates container orchestration complexity

### Phase 3: Observability (Medium Effort, Medium Value)
5. **Cloud Metrics** - Better visibility into pipeline performance

---

## Implementation Considerations

### Cost Optimization
- Use free tiers where available (Neo4j Aura Free, GitHub Container Registry)
- Implement lifecycle policies for object storage (move old data to cheaper tiers)
- Use appropriate log retention periods
- Monitor usage to avoid unexpected costs

### Security
- Use IAM roles and service accounts (avoid hardcoded credentials)
- Enable encryption at rest for all cloud services
- Use VPC endpoints for AWS services (if applicable)
- Implement least-privilege access policies

### Data Migration
- Plan for downtime during initial migration
- Test migration scripts on small datasets first
- Keep local backups during transition period
- Verify data integrity after migration

### Code Changes Required
- Update configuration files to use cloud URIs
- Replace filesystem operations with cloud SDKs
- Add retry logic for cloud API calls
- Update error handling for cloud-specific errors
- Add connection pooling for cloud services

---

## Recommended Cloud Provider Stack

### Option A: AWS Stack
- **Neo4j**: Neo4j Aura (provider-agnostic)
- **Dagster**: Dagster Cloud (provider-agnostic)
- **Storage**: AWS S3
- **Logging**: CloudWatch Logs
- **Metrics**: CloudWatch Metrics
- **Container Registry**: ECR or GitHub Container Registry

### Option B: Multi-Cloud (Current Approach)
- **Neo4j**: Neo4j Aura (provider-agnostic)
- **Dagster**: Dagster Cloud (provider-agnostic)
- **Storage**: Cloud-agnostic (use `cloudpathlib` for abstraction)
- **Logging**: Datadog (provider-agnostic)
- **Metrics**: Datadog (provider-agnostic)
- **Container Registry**: GitHub Container Registry (provider-agnostic)

**Recommendation**: Option B provides flexibility and avoids vendor lock-in.

---

## Next Steps

1. **Evaluate Costs**: Calculate estimated monthly costs for each service
2. **Proof of Concept**: Start with Neo4j Aura migration (already partially supported)
3. **Storage Migration**: Implement cloud object storage for `data/` directories
4. **Orchestration**: Evaluate Dagster Cloud for production workloads
5. **Observability**: Add cloud logging and metrics incrementally

---

## References

- Neo4j Aura Setup: `docs/data/neo4j-aura-setup.md`
- Containerization Guide: `docs/deployment/containerization.md`
- Dagster Cloud Docs: https://docs.dagster.io/dagster-cloud
- Neo4j Aura Docs: https://neo4j.com/docs/aura/
- Cloud Storage Libraries: `cloudpathlib` (already in dependencies)

