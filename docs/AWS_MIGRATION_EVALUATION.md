# AWS Migration Evaluation: SBIR-ETL Platform

**Document Version:** 1.0
**Date:** 2025-11-15
**Status:** Draft
**Target AWS Services:** SageMaker, Neptune, Glacier, S3

---

## Executive Summary

This document evaluates the migration of the SBIR-ETL platform from a self-hosted, Docker-based architecture to AWS cloud services. The migration would leverage:

- **Amazon S3**: Primary data storage for raw/processed files (replacing local filesystem)
- **Amazon SageMaker**: ML model training and inference (replacing local scikit-learn/spaCy)
- **Amazon Neptune**: Managed graph database (replacing self-hosted Neo4j)
- **Amazon Glacier/S3 Glacier**: Long-term archival storage for historical data

**Key Findings:**
- **Estimated Migration Effort**: 8-12 weeks (2-3 engineer-months)
- **Complexity**: Medium-High
- **Primary Benefits**: Scalability, reduced operational overhead, better disaster recovery
- **Primary Risks**: Cost management, vendor lock-in, Neptune compatibility gaps
- **Recommended Approach**: Phased migration starting with S3, then Neptune, then SageMaker

---

## Table of Contents

1. [Current Architecture Overview](#1-current-architecture-overview)
2. [AWS Service Mapping](#2-aws-service-mapping)
3. [Migration Analysis by Service](#3-migration-analysis-by-service)
4. [Effort Estimation](#4-effort-estimation)
5. [Cost Analysis](#5-cost-analysis)
6. [Risks and Mitigation](#6-risks-and-mitigation)
7. [Migration Roadmap](#7-migration-roadmap)
8. [Technical Recommendations](#8-technical-recommendations)
9. [Decision Matrix](#9-decision-matrix)

---

## 1. Current Architecture Overview

### 1.1 Technology Stack

| Component | Current Technology | Purpose |
|-----------|-------------------|---------|
| **Graph Database** | Neo4j 5.20.0 (Docker) | Entity relationships, network analysis |
| **Analytics DB** | DuckDB 1.0.0 | In-memory SQL analytics, CSV preprocessing |
| **File Storage** | Local filesystem + Docker volumes | Raw/processed data, reports, logs |
| **ML Framework** | scikit-learn 1.4.0 + spaCy 3.7.0 | CET classification, NLP |
| **Orchestration** | Dagster 1.7.0 | Pipeline scheduling, asset management |
| **Container Runtime** | Docker Compose | Service orchestration |

### 1.2 Data Volumes

- **SBIR Awards**: ~250K records, ~500MB CSV
- **Federal Contracts**: ~6.7M records, ~15GB parquet
- **USAspending DB**: ~5GB (ZIP compressed)
- **Patents**: ~50K records, ~200MB
- **Processed Artifacts**: ~10GB parquet files
- **Neo4j Database**: ~2-5GB (nodes + relationships)
- **Logs & Reports**: ~1GB/month
- **Total Active Storage**: ~35-40GB
- **Growth Rate**: ~5-10GB/year

### 1.3 Current Infrastructure Costs

**Self-Hosted (Estimated):**
- Server/VM: $100-200/month
- Backup storage: $20/month
- **Total: ~$120-220/month** (~$1,440-2,640/year)

---

## 2. AWS Service Mapping

### 2.1 Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud Environment                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐        ┌──────────────┐                       │
│  │   Amazon S3  │        │  S3 Glacier  │                       │
│  │  (Standard)  │◄───────│  Deep Archive│                       │
│  │              │        │              │                       │
│  │ • Raw data   │        │ • Historical │                       │
│  │ • Processed  │        │   awards     │                       │
│  │ • Reports    │        │ • Old dumps  │                       │
│  └──────┬───────┘        └──────────────┘                       │
│         │                                                         │
│         │ Read/Write                                             │
│         ▼                                                         │
│  ┌──────────────────────────────────────────────┐               │
│  │         Dagster (ECS/Fargate or EC2)          │               │
│  │  ┌────────────────────────────────────────┐  │               │
│  │  │  ETL Pipeline (Python)                 │  │               │
│  │  │  • Extractors  • Transformers          │  │               │
│  │  │  • Enrichers   • Validators            │  │               │
│  │  └────────┬──────────────────┬────────────┘  │               │
│  └───────────┼──────────────────┼───────────────┘               │
│              │                  │                                 │
│              │                  │                                 │
│       ┌──────▼──────┐    ┌─────▼────────┐                       │
│       │   SageMaker │    │   Neptune    │                       │
│       │             │    │              │                       │
│       │ • CET Model │    │ • Graph DB   │                       │
│       │ • Inference │    │ • Gremlin    │                       │
│       │ • Training  │    │ • SPARQL     │                       │
│       └─────────────┘    └──────────────┘                       │
│                                                                   │
│  ┌──────────────────────────────────────────────┐               │
│  │  Additional AWS Services (Optional)          │               │
│  │  • Athena: SQL queries on S3 (replaces       │               │
│  │    DuckDB for ad-hoc analytics)              │               │
│  │  • Glue: ETL jobs, data catalog              │               │
│  │  • CloudWatch: Monitoring & logging          │               │
│  │  • Secrets Manager: Credentials              │               │
│  └──────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Service Mapping Table

| Current | AWS Service | Replacement Strategy |
|---------|-------------|---------------------|
| **Local filesystem** | **S3 Standard** | Full replacement for active data |
| **Docker volumes (old data)** | **S3 Glacier Deep Archive** | Archive data >1 year old |
| **Neo4j 5.20.0** | **Neptune** | Direct migration with Cypher or Gremlin |
| **scikit-learn + spaCy** | **SageMaker** | Model training/inference endpoints |
| **DuckDB** | **Athena + Glue** | SQL on S3 (optional, DuckDB can remain) |
| **Docker Compose** | **ECS Fargate or EC2** | Container orchestration |
| **Dagster** | **Dagster on ECS/EC2** | Same framework, cloud deployment |

---

## 3. Migration Analysis by Service

### 3.1 Amazon S3 (Object Storage)

#### 3.1.1 Use Cases

**Primary Storage:**
- Raw data files (SBIR CSV, USAspending dumps, patents)
- Processed parquet files (transitions, vendor resolution)
- Intermediate artifacts (DuckDB files)
- Reports (JSON, Markdown, HTML)
- Logs (application logs, performance metrics)
- Configuration files (YAML)

#### 3.1.2 Migration Effort

**Complexity: LOW**

**Code Changes Required:**
1. **Path abstraction layer** - Create S3-aware file handlers
   - Replace `pathlib.Path` with `s3fs` or `boto3`
   - Update `src/config/schemas.py` PathsConfig
   - Modify all file I/O operations (20-30 files)

2. **Updated modules:**
   - `src/extractors/*.py` - Read from S3 instead of local paths
   - `src/loaders/*.py` - Write to S3
   - `src/utils/statistical_reporter.py` - Save reports to S3
   - `src/config/loader.py` - Load YAML from S3
   - `src/assets/*.py` - Update all asset paths

3. **Dagster integration:**
   - Configure S3 I/O manager (`dagster-aws` library)
   - Update asset materializations to use S3 paths
   - Configure S3 resource in Dagster definitions

**Example Code Change:**

```python
# BEFORE (current)
import pandas as pd
df = pd.read_csv("data/raw/sbir/awards.csv")

# AFTER (S3-based)
import pandas as pd
from s3fs import S3FileSystem
s3 = S3FileSystem()
df = pd.read_csv("s3://sbir-etl-data/raw/sbir/awards.csv", storage_options={"client": s3})
```

**Estimated Effort: 2-3 weeks**

#### 3.1.3 Benefits
- **Durability**: 99.999999999% (11 nines) data durability
- **Scalability**: No storage limits
- **Versioning**: Built-in version control for data files
- **Lifecycle policies**: Automatic transition to Glacier
- **Access control**: IAM policies, bucket policies
- **Integration**: Native support in pandas, DuckDB, Athena

#### 3.1.4 Considerations
- **Latency**: Network I/O slower than local disk (10-50ms vs <1ms)
- **Costs**: $0.023/GB/month (Standard), egress charges apply
- **Access patterns**: Optimize for bulk reads (use Range GETs)
- **DuckDB compatibility**: Can query S3 directly with httpfs extension

---

### 3.2 Amazon S3 Glacier Deep Archive (Archival Storage)

#### 3.2.1 Use Cases

**Long-term archival (>1 year retention):**
- Historical SBIR awards (pre-2020)
- Old USAspending database dumps
- Deprecated reports and logs
- Compliance/audit data

#### 3.2.2 Migration Effort

**Complexity: LOW**

**Implementation:**
1. **Lifecycle policies**: Automatic transition from S3 Standard
   - Transition to Glacier after 90 days
   - Transition to Glacier Deep Archive after 180 days
2. **Inventory management**: S3 Inventory for archived objects
3. **Retrieval process**: Implement restore workflow (12-48hr retrieval time)

**Estimated Effort: 1 week**

#### 3.2.3 Benefits
- **Cost**: $0.00099/GB/month (99% cheaper than S3 Standard)
- **Compliance**: Long-term retention for audits
- **Automatic**: Lifecycle policies handle transitions

#### 3.2.4 Considerations
- **Retrieval time**: 12-48 hours (not for active data)
- **Minimum storage**: 180-day minimum charge
- **Retrieval cost**: $0.02/GB (infrequent access acceptable)

---

### 3.3 Amazon Neptune (Graph Database)

#### 3.3.1 Use Cases

**Replace Neo4j for:**
- Entity relationships (Company, Award, Contract, Patent)
- Graph traversals (transition paths, citation networks)
- Network analysis (researcher collaborations, agency patterns)
- Cypher/Gremlin queries for analytics

#### 3.3.2 Migration Effort

**Complexity: MEDIUM-HIGH**

**Major Tasks:**

1. **Query Language Selection**
   - **Option A**: Use Neptune's openCypher support (similar to Neo4j)
   - **Option B**: Migrate to Gremlin (AWS-recommended, better performance)
   - **Recommendation**: Start with openCypher for faster migration, optimize with Gremlin later

2. **Schema Migration**
   - Export Neo4j data using `neo4j-admin export`
   - Convert to Neptune-compatible format (CSV or JSON)
   - Use Neptune Bulk Loader for initial load
   - Recreate constraints and indexes

3. **Code Changes** (Significant):
   - **Replace `neo4j` driver** with `gremlinpython` or AWS Neptune library
   - Update `src/loaders/neo4j/client.py` → `src/loaders/neptune/client.py`
   - Rewrite queries in Gremlin (if using Gremlin):
     - `src/loaders/neo4j/*.py` - All loader logic
     - Dagster assets that query Neptune
   - Update connection management (SSL/IAM auth)
   - Modify batch loading logic (Neptune has different limits)

4. **Testing & Validation**
   - Verify all queries return same results
   - Performance testing (Neptune may differ in query patterns)
   - Update integration tests

**Example Query Migration:**

```python
# BEFORE (Neo4j Cypher)
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))
with driver.session() as session:
    result = session.run("""
        MATCH (c:Company)-[:RECEIVED]->(a:Award)-[:TRANSITIONED_TO]->(ct:Contract)
        WHERE a.amount > $min_amount
        RETURN c.name, count(ct) as transitions
    """, min_amount=100000)

# AFTER (Neptune Gremlin)
from gremlin_python.driver import client as gremlin_client
client = gremlin_client.Client(
    f'wss://{neptune_endpoint}:8182/gremlin',
    'g'
)
result = client.submit("""
    g.V().hasLabel('Company')
     .outE('RECEIVED').inV().hasLabel('Award').has('amount', gt(min_amount))
     .outE('TRANSITIONED_TO').inV().hasLabel('Contract')
     .group().by(select('Company').values('name')).by(count())
""", {'min_amount': 100000})

# AFTER (Neptune openCypher - easier migration)
from neo4j import GraphDatabase  # Neptune supports Neo4j driver!
driver = GraphDatabase.driver(
    f"bolt://{neptune_endpoint}:8182",
    auth=None,  # IAM auth handled separately
    encrypted=True
)
# Same Cypher query works with minor adjustments
```

**Estimated Effort: 4-6 weeks**

#### 3.3.3 Benefits
- **Managed service**: No Neo4j version upgrades, patching
- **Scalability**: Read replicas, auto-scaling storage
- **High availability**: Multi-AZ deployments
- **Backup**: Automated snapshots
- **Security**: IAM integration, VPC isolation
- **Monitoring**: CloudWatch metrics

#### 3.3.4 Considerations & Risks

**Compatibility Gaps:**
- Neptune openCypher **does NOT support**:
  - APOC procedures (currently using APOC in Neo4j)
  - Some Neo4j-specific functions
  - Full-text search (requires Amazon OpenSearch integration)
- Gremlin has learning curve for team

**Performance Differences:**
- Neptune optimized for Gremlin, not Cypher
- Query patterns may need optimization
- Different indexing strategy (composite indexes)

**Vendor Lock-in:**
- Gremlin queries not portable to Neo4j
- Migration back to Neo4j requires re-migration

**Cost:**
- Minimum instance: db.r5.large ($0.348/hr = $250/month)
- Storage: $0.10/GB-month
- I/O: $0.20 per million requests
- **Total estimate: $300-500/month** (vs. $0 for self-hosted Neo4j)

**APOC Replacement:**
- Need to identify all APOC usage in codebase
- Implement custom Gremlin steps or application-level logic
- Example: APOC path algorithms → custom graph traversals

---

### 3.4 Amazon SageMaker (ML Platform)

#### 3.4.1 Use Cases

**Replace local ML training:**
- CET classification model training (scikit-learn)
- Model versioning and experiment tracking
- Hosted inference endpoints for classification

#### 3.4.2 Migration Effort

**Complexity: MEDIUM**

**Major Tasks:**

1. **Containerize ML Training**
   - Package `src/ml/models/cet_classifier.py` as SageMaker training job
   - Create training script with SageMaker entry point
   - Configure hyperparameters and input channels
   - Save model artifacts to S3

2. **Model Deployment**
   - Deploy model to SageMaker endpoint
   - Configure auto-scaling for inference
   - Update Dagster assets to call SageMaker endpoint

3. **Code Changes**:
   - `src/ml/models/cet_classifier.py` - Add SageMaker training entry point
   - `src/assets/cet/classification.py` - Call SageMaker endpoint instead of local model
   - `src/ml/features/*.py` - Ensure feature extraction works with SageMaker format
   - Remove local model training from pipeline (or keep as fallback)

**Example Training Job:**

```python
# BEFORE (local training)
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer

vectorizer = TfidfVectorizer(max_features=1000)
X_train = vectorizer.fit_transform(abstracts)
model = LogisticRegression().fit(X_train, y_train)

# Save locally
import pickle
with open('models/cet_classifier.pkl', 'wb') as f:
    pickle.dump(model, f)

# AFTER (SageMaker training)
import sagemaker
from sagemaker.sklearn import SKLearn

estimator = SKLearn(
    entry_point='train.py',
    role='SageMakerRole',
    instance_type='ml.m5.xlarge',
    framework_version='1.2-1',
    hyperparameters={
        'max_features': 1000,
        'C': 1.0
    }
)

estimator.fit({'train': 's3://sbir-etl-data/ml/training_data/'})
# Model automatically saved to S3
```

**Example Inference:**

```python
# BEFORE (local inference)
model = pickle.load(open('models/cet_classifier.pkl', 'rb'))
predictions = model.predict(X_test)

# AFTER (SageMaker endpoint)
import boto3
runtime = boto3.client('sagemaker-runtime')

response = runtime.invoke_endpoint(
    EndpointName='cet-classifier-endpoint',
    ContentType='application/json',
    Body=json.dumps({'instances': test_abstracts})
)

predictions = json.loads(response['Body'].read())
```

**Estimated Effort: 3-4 weeks**

#### 3.4.3 Benefits
- **Experiment tracking**: SageMaker Studio for model lineage
- **Distributed training**: Train on larger datasets (future-proofing)
- **Model registry**: Versioned models with approval workflows
- **Auto-scaling**: Inference endpoints scale with demand
- **Built-in algorithms**: Access to AWS pre-built models
- **Feature Store**: (Optional) Centralized feature management

#### 3.4.4 Considerations

**Cost:**
- Training: $0.269/hr (ml.m5.xlarge) - only during training
- Inference: $0.228/hr (ml.m5.large) 24/7 = $164/month
- Alternative: **Batch Transform** for async inference ($0 idle cost)
- **Recommendation**: Use Batch Transform, not real-time endpoints

**Complexity:**
- SageMaker adds operational overhead for simple models
- Current model is relatively simple (TF-IDF + LogisticRegression)
- Training time: ~10 minutes locally (infrequent retraining)

**When SageMaker Makes Sense:**
- Frequent model retraining (currently infrequent)
- Need distributed training (current data fits in memory)
- Multiple data scientists need shared infrastructure
- Regulatory requirements for model governance

**Recommendation: DEFER SageMaker**
- Keep local training for now
- Re-evaluate when:
  - Training data exceeds single-machine capacity
  - Retraining becomes daily/weekly
  - Team grows beyond 1-2 ML engineers

---

### 3.5 Amazon Athena (Optional: DuckDB Replacement)

#### 3.5.1 Use Cases

**Ad-hoc SQL queries on S3 data:**
- Replace DuckDB for exploratory analysis
- Query parquet files directly on S3
- Generate reports without ETL

#### 3.5.2 Migration Effort

**Complexity: LOW**

**Implementation:**
- Create Glue Data Catalog for S3 data
- Define tables pointing to parquet files
- Update ad-hoc query scripts to use Athena

**Estimated Effort: 1-2 weeks**

#### 3.5.3 Considerations

**Keep DuckDB if:**
- Need fast local development/testing
- Prefer embedded database (no network calls)
- Cost-sensitive (Athena charges $5/TB scanned)

**Use Athena if:**
- Need multi-user access to query S3
- Want separation of compute/storage
- Okay with pay-per-query model

**Recommendation: HYBRID APPROACH**
- Keep DuckDB for development/CI
- Use Athena for production analytics/reporting

---

## 4. Effort Estimation

### 4.1 Detailed Breakdown

| Task | Complexity | Effort (weeks) | Team Size | Dependencies |
|------|-----------|----------------|-----------|--------------|
| **Phase 1: S3 Migration** | | | | |
| - Create S3-aware file I/O layer | LOW | 1 | 1 engineer | None |
| - Update extractors/loaders | MEDIUM | 1 | 1 engineer | File I/O layer |
| - Update Dagster I/O managers | LOW | 0.5 | 1 engineer | File I/O layer |
| - Testing & validation | MEDIUM | 0.5 | 1 engineer | All above |
| **Phase 1 Subtotal** | | **3 weeks** | | |
| | | | | |
| **Phase 2: Glacier Setup** | | | | |
| - Define lifecycle policies | LOW | 0.5 | 1 engineer | S3 migration |
| - Archive historical data | LOW | 0.5 | 1 engineer | Lifecycle policies |
| **Phase 2 Subtotal** | | **1 week** | | |
| | | | | |
| **Phase 3: Neptune Migration** | | | | |
| - Export Neo4j data | LOW | 0.5 | 1 engineer | None |
| - Neptune instance setup | LOW | 0.5 | 1 engineer | None |
| - Bulk load data | MEDIUM | 1 | 1 engineer | Export complete |
| - Query language decision | LOW | 0.5 | Team | None |
| - Rewrite loaders (Gremlin/openCypher) | HIGH | 2 | 1 engineer | Query language |
| - Update Dagster assets | MEDIUM | 1 | 1 engineer | Loader rewrite |
| - APOC replacement analysis | MEDIUM | 1 | 1 engineer | None |
| - Testing & validation | HIGH | 1.5 | 2 engineers | All above |
| **Phase 3 Subtotal** | | **6 weeks** | | |
| | | | | |
| **Phase 4: Infrastructure** | | | | |
| - ECS/Fargate setup for Dagster | MEDIUM | 1 | 1 DevOps | None |
| - IAM roles & policies | LOW | 0.5 | 1 DevOps | None |
| - VPC configuration | LOW | 0.5 | 1 DevOps | None |
| - CloudWatch logging/monitoring | MEDIUM | 1 | 1 DevOps | None |
| - CI/CD pipeline updates | MEDIUM | 1 | 1 DevOps | None |
| **Phase 4 Subtotal** | | **4 weeks** | | |
| | | | | |
| **Phase 5: SageMaker (Optional)** | | | | |
| - Containerize training job | MEDIUM | 1 | 1 engineer | S3 migration |
| - Deploy batch transform | MEDIUM | 1 | 1 engineer | Training job |
| - Update inference logic | MEDIUM | 1 | 1 engineer | Batch transform |
| - Testing | MEDIUM | 1 | 1 engineer | All above |
| **Phase 5 Subtotal** | | **4 weeks** | | |

### 4.2 Total Effort

**Minimum Viable Migration (S3 + Neptune + Infrastructure):**
- **Duration**: 8-10 weeks (calendar time with parallelization)
- **Effort**: 13 weeks (engineer-weeks)
- **Team**: 1-2 engineers + 1 DevOps

**Full Migration (Including SageMaker):**
- **Duration**: 10-12 weeks
- **Effort**: 17 weeks
- **Team**: 2 engineers + 1 DevOps

---

## 5. Cost Analysis

### 5.1 Monthly Cost Estimates

#### Current State (Self-Hosted)
| Component | Cost/Month |
|-----------|-----------|
| VM/Server (2 vCPU, 8GB RAM) | $100-200 |
| Backup storage | $20 |
| **Total** | **$120-220** |

#### AWS Migration (Base Configuration)

| Service | Configuration | Monthly Cost | Notes |
|---------|--------------|--------------|-------|
| **S3 Standard** | 50GB active data | $1.15 | $0.023/GB |
| **S3 Glacier Deep Archive** | 100GB archived | $0.10 | $0.00099/GB |
| **S3 Requests** | 1M PUT, 10M GET | $10 | $0.005/1K PUT, $0.0004/1K GET |
| **Neptune** | db.r5.large (2 vCPU, 16GB) | $250 | $0.348/hr |
| **Neptune Storage** | 10GB | $1 | $0.10/GB-month |
| **Neptune I/O** | 10M requests | $2 | $0.20/1M requests |
| **ECS Fargate** | 0.5 vCPU, 1GB RAM (Dagster) | $15 | $0.04048/hr for vCPU, $0.004445/hr for GB |
| **EC2 (Alternative)** | t3.medium (Dagster) | $30 | $0.0416/hr |
| **CloudWatch Logs** | 10GB logs/month | $5 | $0.50/GB ingested |
| **Data Transfer Out** | 10GB/month | $0.90 | $0.09/GB |
| **NAT Gateway** | (if using private VPC) | $32 | $0.045/hr + $0.045/GB processed |
| | | | |
| **Total (Base)** | | **$285-300/month** | Without SageMaker |
| **Total (with SageMaker)** | | **$450-500/month** | With ml.m5.large endpoint |

#### Alternative Configurations

**Cost-Optimized (Batch Processing):**
- Use Neptune Serverless (auto-scales, pay per request)
- Use SageMaker Batch Transform (no always-on endpoint)
- Estimated: **$200-250/month**

**High-Availability (Production):**
- Multi-AZ Neptune with read replicas
- Larger ECS Fargate tasks
- Enhanced monitoring
- Estimated: **$600-800/month**

### 5.2 Annual Cost Comparison

| Scenario | Annual Cost | vs. Self-Hosted |
|----------|-------------|-----------------|
| Self-Hosted | $1,440-2,640 | Baseline |
| AWS Base | $3,420-3,600 | **+138% to +150%** |
| AWS Optimized | $2,400-3,000 | **+67% to +114%** |
| AWS High-Availability | $7,200-9,600 | **+364%** |

### 5.3 Cost Drivers

**Largest costs:**
1. **Neptune** (85% of base cost) - $250-300/month
2. **ECS/EC2 compute** (10%) - $15-30/month
3. **S3 + other** (5%) - $15-20/month

**Cost Optimization Strategies:**
1. **Neptune Serverless** - Only available in limited regions, may reduce cost by 30-50%
2. **Reserved Instances** - 1-year commitment saves 30%, 3-year saves 50%
3. **Spot Instances** - For Dagster compute (70% savings, but interruptible)
4. **S3 Intelligent-Tiering** - Automatic cost optimization (saves 10-15%)
5. **Athena instead of DuckDB** - Pay-per-query vs. always-on compute

---

## 6. Risks and Mitigation

### 6.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Neptune query incompatibility** | HIGH | MEDIUM | - Thorough APOC usage audit<br>- POC with representative queries<br>- Keep Neo4j as fallback during migration |
| **Performance degradation** | MEDIUM | MEDIUM | - Benchmark before/after<br>- Optimize indexes<br>- Consider read replicas |
| **S3 latency impact** | LOW | HIGH | - Use S3 Transfer Acceleration<br>- Cache frequently accessed files<br>- Batch operations |
| **SageMaker complexity** | LOW | LOW | - Defer SageMaker to Phase 2<br>- Keep local training |
| **Data loss during migration** | HIGH | LOW | - Comprehensive backups<br>- Parallel run period<br>- Validation checksums |
| **Vendor lock-in** | MEDIUM | HIGH | - Abstract AWS-specific code<br>- Use open formats (Parquet, CSV)<br>- Document exit strategy |

### 6.2 Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Cost overruns** | MEDIUM | MEDIUM | - Set billing alarms ($500/month)<br>- Use Cost Explorer<br>- Tag resources for tracking |
| **Team learning curve** | LOW | HIGH | - AWS training for team<br>- Start with S3 (easiest)<br>- Hire AWS consultant |
| **Migration timeline slippage** | MEDIUM | MEDIUM | - Phased approach<br>- Clear milestones<br>- Buffer 20% extra time |
| **Downtime during cutover** | MEDIUM | LOW | - Blue-green deployment<br>- Parallel run period<br>- Rollback plan |

### 6.3 Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **ROI not achieved** | HIGH | MEDIUM | - Clear success metrics<br>- Cost-benefit analysis<br>- Re-evaluate after Phase 1 |
| **Compliance issues** | MEDIUM | LOW | - Review data residency requirements<br>- Enable encryption<br>- Audit CloudTrail logs |
| **Skills gap** | LOW | MEDIUM | - Training budget<br>- AWS certification for team<br>- Managed services reduce burden |

---

## 7. Migration Roadmap

### 7.1 Recommended Phased Approach

```
Phase 1: S3 Foundation (Weeks 1-3)
  └─ Low risk, high value, enables other phases

Phase 2: Infrastructure (Weeks 2-5, parallel with Phase 1)
  └─ ECS/Fargate, IAM, VPC setup

Phase 3: Glacier Archival (Week 6)
  └─ Quick win, cost savings

Phase 4: Neptune Migration (Weeks 7-12)
  └─ Highest risk, most complex

Phase 5: SageMaker (Weeks 13-16, OPTIONAL)
  └─ Defer if not needed
```

### 7.2 Detailed Timeline

#### **Phase 1: S3 Migration (Weeks 1-3)**

**Week 1:**
- [ ] Create S3 buckets (dev, staging, prod)
- [ ] Implement S3FileSystem abstraction layer
- [ ] Update `src/config/schemas.py` for S3 paths
- [ ] Migrate extractors to read from S3

**Week 2:**
- [ ] Migrate loaders to write to S3
- [ ] Update Dagster I/O managers
- [ ] Configure S3 resources in Dagster
- [ ] Upload test data to S3

**Week 3:**
- [ ] End-to-end testing with S3
- [ ] Performance benchmarking
- [ ] Update documentation
- [ ] Deploy to dev environment

**Milestone: All file I/O via S3**

---

#### **Phase 2: Infrastructure (Weeks 2-5, parallel)**

**Week 2-3:**
- [ ] Design VPC architecture (public/private subnets)
- [ ] Create IAM roles for ECS tasks
- [ ] Set up ECS cluster
- [ ] Containerize Dagster for ECS

**Week 4:**
- [ ] Deploy Dagster to ECS Fargate
- [ ] Configure Application Load Balancer
- [ ] Set up CloudWatch dashboards
- [ ] Implement secrets in Secrets Manager

**Week 5:**
- [ ] CI/CD pipeline for ECS deployments
- [ ] Testing & validation
- [ ] Disaster recovery procedures

**Milestone: Dagster running on AWS**

---

#### **Phase 3: Glacier Archival (Week 6)**

**Week 6:**
- [ ] Identify archival candidates (data >1 year old)
- [ ] Create S3 Lifecycle policies
- [ ] Test retrieval process
- [ ] Archive historical data

**Milestone: Long-term archival in place**

---

#### **Phase 4: Neptune Migration (Weeks 7-12)**

**Week 7:**
- [ ] Provision Neptune cluster (dev environment)
- [ ] Export Neo4j data (`neo4j-admin export`)
- [ ] Analyze APOC usage in codebase
- [ ] Decide: openCypher vs. Gremlin

**Week 8-9:**
- [ ] Convert Neo4j export to Neptune format
- [ ] Bulk load data to Neptune
- [ ] Verify data integrity (node/edge counts)
- [ ] Create indexes and constraints

**Week 10:**
- [ ] Rewrite `src/loaders/neo4j/` → `src/loaders/neptune/`
- [ ] Migrate queries (Cypher → Gremlin/openCypher)
- [ ] Update Dagster assets

**Week 11:**
- [ ] Integration testing
- [ ] Performance benchmarking
- [ ] Query optimization

**Week 12:**
- [ ] Parallel run (Neo4j + Neptune)
- [ ] Validation (compare results)
- [ ] Cutover to Neptune
- [ ] Decommission Neo4j

**Milestone: Neptune fully operational**

---

#### **Phase 5: SageMaker (Weeks 13-16, OPTIONAL)**

**Week 13:**
- [ ] Containerize CET classifier training
- [ ] Create SageMaker training job
- [ ] Test training on sample data

**Week 14:**
- [ ] Deploy batch transform job
- [ ] Update inference logic in Dagster
- [ ] Integrate with S3 for model artifacts

**Week 15-16:**
- [ ] End-to-end testing
- [ ] Performance validation
- [ ] Documentation

**Milestone: SageMaker-based ML pipeline**

---

### 7.3 Rollback Plan

**At each phase:**
1. **Maintain parallel systems** during migration
2. **Validation period** (1-2 weeks) before cutover
3. **Rollback triggers**:
   - Data validation failures
   - Performance degradation >20%
   - Cost overruns >50%
   - Critical bugs in production

**Rollback procedures:**
- **S3**: Revert file paths to local filesystem
- **Neptune**: Fall back to Neo4j (keep running during migration)
- **SageMaker**: Revert to local training (lowest risk)

---

## 8. Technical Recommendations

### 8.1 Architecture Decisions

#### Decision 1: Neptune Query Language

**Recommendation: Start with openCypher, migrate to Gremlin later**

**Rationale:**
- openCypher provides faster migration (minimal code changes)
- Gremlin offers better performance but steeper learning curve
- Can optimize to Gremlin incrementally after migration

**Implementation:**
```python
# Use Neptune's Neo4j driver compatibility
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    f"bolt://{neptune_endpoint}:8182",
    auth=None,  # Use IAM instead
    encrypted=True
)
```

#### Decision 2: DuckDB vs. Athena

**Recommendation: Keep DuckDB, add Athena for ad-hoc queries**

**Rationale:**
- DuckDB excellent for development/testing
- Athena useful for multi-user access to S3
- No need to replace if both serve different purposes

#### Decision 3: SageMaker Timing

**Recommendation: DEFER SageMaker to Phase 2 (post-migration)**

**Rationale:**
- Current ML workload is simple (TF-IDF + LogisticRegression)
- Training is infrequent (monthly or less)
- Focus on higher-value migrations first (S3, Neptune)
- Re-evaluate in 6 months when on AWS

### 8.2 Code Organization

**Create abstraction layers:**

```python
# src/storage/base.py
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    @abstractmethod
    def read_csv(self, path: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def write_parquet(self, df: pd.DataFrame, path: str):
        pass

# src/storage/local.py
class LocalStorage(StorageBackend):
    def read_csv(self, path: str):
        return pd.read_csv(path)

# src/storage/s3.py
class S3Storage(StorageBackend):
    def read_csv(self, path: str):
        return pd.read_csv(path, storage_options={"client": self.s3fs})

# src/config/loader.py
def get_storage() -> StorageBackend:
    if config.storage_backend == "s3":
        return S3Storage()
    return LocalStorage()
```

**Benefits:**
- Easy to switch backends
- Testable (mock storage)
- Future-proof (add Azure, GCP later)

### 8.3 Monitoring & Observability

**Implement from Day 1:**

1. **CloudWatch Dashboards**:
   - S3 request metrics (GET/PUT latency)
   - Neptune query performance
   - ECS task health
   - Dagster job success rates

2. **Alarms**:
   - Cost threshold ($500/month)
   - Neptune CPU >80%
   - S3 4xx/5xx errors
   - Dagster job failures

3. **Logging**:
   - Structured JSON logs to CloudWatch
   - Retain for 90 days (compliance)
   - Cross-reference with Dagster run IDs

4. **Tracing** (Optional):
   - AWS X-Ray for distributed tracing
   - Track S3 → Dagster → Neptune flows

---

## 9. Decision Matrix

### 9.1 Go/No-Go Criteria

**PROCEED with migration if:**
- [ ] Team has 2+ engineers available for 3 months
- [ ] Budget approved for $300-500/month ongoing costs
- [ ] APOC usage is minimal or replaceable
- [ ] Business requires scalability/HA not achievable with current setup
- [ ] Compliance/security requires managed services

**DO NOT MIGRATE if:**
- [ ] Budget constrained (<$200/month)
- [ ] Team size <1 engineer
- [ ] Heavy APOC usage with no Gremlin equivalent
- [ ] Current system meets all requirements
- [ ] Organizational preference for on-prem

### 9.2 Service-Level Recommendations

| Service | Recommendation | Priority | Rationale |
|---------|---------------|----------|-----------|
| **S3** | **PROCEED** | HIGH | Low risk, high value, foundational for other services |
| **Glacier** | **PROCEED** | MEDIUM | Easy cost savings for archival data |
| **Neptune** | **PROCEED WITH CAUTION** | MEDIUM | High value but significant effort, validate APOC compatibility first |
| **SageMaker** | **DEFER** | LOW | Current ML needs met by local training, revisit in 6 months |
| **Athena** | **OPTIONAL** | LOW | Nice-to-have for ad-hoc queries, not essential |

### 9.3 Final Recommendation

**Recommended Path: Phased Migration**

1. **Phase 1 (Weeks 1-6)**: S3 + Infrastructure + Glacier
   - **Invest**: 4 weeks engineering effort
   - **Return**: Scalable storage, better disaster recovery
   - **Risk**: Low

2. **Evaluation Point** (Week 7): Re-assess Neptune
   - Conduct APOC compatibility audit
   - POC with representative queries
   - Make go/no-go decision

3. **Phase 2 (Weeks 7-12)**: Neptune migration (if approved)
   - **Invest**: 6 weeks engineering effort
   - **Return**: Managed graph DB, HA, auto-scaling
   - **Risk**: Medium

4. **Phase 3 (6 months later)**: SageMaker evaluation
   - Re-assess ML needs
   - Migrate if training becomes frequent/distributed

**Total Investment (Phases 1-2):**
- **Duration**: 12 weeks
- **Effort**: 10-13 engineer-weeks
- **Cost**: +$150-280/month ongoing

---

## Appendix A: APOC Compatibility Audit

**ACTION ITEM: Search codebase for APOC usage**

```bash
# Find APOC procedure calls
grep -r "apoc\." src/

# Common APOC procedures to check:
# - apoc.path.* (shortest path, all paths)
# - apoc.periodic.* (batch operations)
# - apoc.date.* (date formatting)
# - apoc.text.* (string functions)
# - apoc.algo.* (graph algorithms)
```

**Neptune Alternatives:**
- `apoc.path.*` → Custom Gremlin traversals
- `apoc.periodic.iterate` → Application-level batching
- `apoc.date.*` → Python datetime in application
- `apoc.text.*` → Python string operations
- Graph algorithms → Amazon Neptune ML or NetworkX

---

## Appendix B: AWS Service Alternatives

| Need | Primary Option | Alternative | Trade-offs |
|------|---------------|-------------|------------|
| Graph DB | Neptune | Neo4j on EC2 | EC2: More control, less managed |
| ML Platform | SageMaker | EC2 + Jupyter | EC2: Cheaper, more manual |
| SQL Analytics | Athena | Redshift Serverless | Redshift: Better for large data, more expensive |
| Container Orchestration | ECS Fargate | EKS | EKS: More complex, more powerful |
| File Storage | S3 | EFS | EFS: POSIX filesystem, higher cost |

---

## Appendix C: Cost Calculator

**Interactive cost estimation (use AWS Pricing Calculator):**

https://calculator.aws/#/

**Key inputs:**
- S3: 50GB Standard, 100GB Glacier, 1M PUT/month, 10M GET/month
- Neptune: db.r5.large, 10GB storage, 10M I/O/month
- ECS: 0.5 vCPU, 1GB RAM, 24/7
- Region: us-east-1

---

## Appendix D: Success Metrics

**Define success before migration:**

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Pipeline runtime | X minutes | ≤1.2X minutes | Dagster logs |
| Data durability | 99.9% | 99.999999999% | S3 SLA |
| Query latency (p95) | Y ms | ≤1.5Y ms | CloudWatch |
| Operational overhead | Z hrs/week | <0.5Z hrs/week | Team survey |
| Monthly cost | $150 | <$400 | AWS Cost Explorer |
| Deployment frequency | Weekly | Daily | CI/CD metrics |
| Mean time to recovery | 4 hours | <1 hour | Incident logs |

---

## Next Steps

1. **[ ] Review this document with stakeholders**
2. **[ ] Conduct APOC compatibility audit** (Appendix A)
3. **[ ] Get budget approval** ($300-500/month)
4. **[ ] Allocate team resources** (2 engineers, 1 DevOps, 12 weeks)
5. **[ ] POC Phase 1** (S3 migration on dev environment)
6. **[ ] Go/no-go decision** after Phase 1 completion

---

**Document Maintainers:**
- Primary: [Your Name]
- Reviewers: [Engineering Lead, DevOps Lead, Product Owner]

**Revision History:**
- v1.0 (2025-11-15): Initial evaluation

---

*This evaluation is based on the current architecture as of commit `ce561d1`. Re-evaluate if significant architectural changes occur.*
