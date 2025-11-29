---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-11-21
Status: active
---

# Data Sources Overview

This section provides comprehensive documentation for all data sources used in the SBIR Analytics pipeline.

## Primary Data Sources

### SBIR Awards Data

**Source:** [SBIR.gov](https://www.sbir.gov/)

- **Format:** CSV
- **Update Cadence:** Weekly (monitored)
- **Endpoint:** `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`
- **Asset:** `raw_sbir_awards`
- **Documentation:** See [SBIR Weekly Checks](sbir-weekly-checks.md) for monitoring procedures

**Key Fields:**
- Award ID, company name, agency, phase, funding amount
- Research topics, abstract, personnel information
- Geographic data (state, congressional district)

### USAspending Data

**Source:** [USAspending.gov](https://www.usaspending.gov/)

- **Format:** PostgreSQL dump (bulk data) + REST API (enrichment)
- **Update Cadence:** Daily (API), Weekly (bulk data)
- **Purpose:** Enrich SBIR awards with additional transaction details
- **Assets:**
  - `raw_usaspending_recipients`
  - `raw_usaspending_transactions`
  - `usaspending_iterative_enrichment`

**Enrichment Data:**
- Recipient details (DUNS, UEI, address)
- Transaction obligations and outlays
- Contract and grant information
- Parent organization relationships

**Related Documentation:**
- [USAspending Iterative Refresh](../enrichment/usaspending-iterative-refresh.md)
- [USAspending Cloud Integration](../USASPENDING_CLOUD_INTEGRATION.md)
- [USAspending Deployment Checklist](../USASPENDING_DEPLOYMENT_CHECKLIST.md)

### USPTO Patent Data

**Source:** [USPTO PatentsView](https://patentsview.org/) + [USPTO Bulk Data](https://bulkdata.uspto.gov/)

- **Formats:** CSV, Parquet, NDJSON, Stata (.dta)
- **Update Cadence:** Quarterly
- **Purpose:** Link patents to SBIR-funded research
- **Assets:** `raw_uspto_patents`, `raw_uspto_assignments`

**Data Types:**
- Patent grants and applications
- Inventor and assignee information
- Patent assignments and ownership transfers
- Technology classification codes
- AI-related patents dataset

**Related Documentation:**
- [USPTO Patent Data Dictionary](dictionaries/uspto-patent-data-dictionary.md)
- [Patent Neo4j Schema](../schemas/patent-neo4j-schema.md)

## External API Services

### SAM.gov Entity API

**Purpose:** Company registration and entity information

- **Rate Limit:** 60 requests/minute
- **Authentication:** API key required
- **Use Case:** Validate company information and DUNS/UEI identifiers

### PatentsView API

**Purpose:** Patent search and retrieval

- **Rate Limit:** 60 requests/minute
- **Caching:** 24-hour TTL
- **Use Case:** Real-time patent lookups and research

## Data Refresh Schedules

| Data Source | Refresh Cadence | Automation | Documentation |
|-------------|-----------------|------------|---------------|
| SBIR Awards | Weekly | AWS Step Functions | [Awards Refresh](awards-refresh.md) |
| USAspending API | Daily | Dagster sensor | [Iterative Refresh](../enrichment/usaspending-iterative-refresh.md) |
| USPTO Patents | Quarterly | Manual/scheduled | [USPTO Data Refresh Workflow](../../.github/workflows/uspto-data-refresh.yml) |
| SAM.gov | On-demand | API calls | N/A |

See [SBIR Weekly Checks](sbir-weekly-checks.md) for monitoring and validation procedures.

## Data Quality

### Quality Thresholds

**SBIR Awards:**
- Pass rate: ≥95%
- Completeness: ≥90%
- Uniqueness: ≥99%

**Enrichment:**
- SAM.gov success rate: ≥85%
- USAspending match rate: ≥70%
- Regression threshold: ≤5%

**Related Documentation:**
- [Quality Assurance Guide](../guides/quality-assurance.md)
- [Validation Testing](../testing/validation-testing.md)

## Data Storage

### Production Storage

- **Primary:** AWS S3 (`sbir-etl-production-data` bucket)
- **Graph Database:** Neo4j Aura
- **Processing:** DuckDB (in-memory or local)

**S3 Structure:**
```
s3://sbir-etl-production-data/
├── raw/
│   ├── awards/           # SBIR CSV downloads
│   ├── uspto/
│   │   ├── patentsview/  # Patent grants
│   │   ├── assignments/  # Ownership transfers
│   │   └── ai_patents/   # AI-related patents
│   └── usaspending/      # Transaction dumps
├── transformed/          # Normalized data
└── artifacts/            # Processed outputs
```

### Development Storage

- **Local:** `data/` directory (gitignored)
- **Graph Database:** Neo4j Docker container or Neo4j Aura free tier
- **Processing:** DuckDB local or in-memory

**Setup Guide:** [Neo4j Aura Setup](neo4j-aura-setup.md)

## Data Dictionaries

Detailed field-level documentation:

- [USPTO Patent Data Dictionary](dictionaries/uspto-patent-data-dictionary.md)
- [Transition Fields Dictionary](dictionaries/transition-fields-dictionary.md)

## Schema Documentation

Graph database schemas and entity relationships:

- [Neo4j Schema Overview](../schemas/neo4j.md)
- [Patent Neo4j Schema](../schemas/patent-neo4j-schema.md)

## Congressional District Analysis

For geographic analysis and funding impact assessment:

- [Congressional District Quickstart](../CONGRESSIONAL_DISTRICT_QUICKSTART.md)
- [Fiscal Impact Granularity](../FISCAL_IMPACT_GRANULARITY.md)

## Related Resources

- **Configuration:** [`config/base.yaml`](../../config/base.yaml) contains all data source configurations
- **Extractors:** [`src/extractors/`](../../src/extractors/) implements data extraction logic
- **Enrichers:** [`src/enrichers/`](../../src/enrichers/) implements API enrichment
- **Architecture:** [Detailed Overview](../architecture/detailed-overview.md)

## Getting Help

For questions about data sources or data quality issues:
1. Check the relevant data dictionary or schema documentation
2. Review the [Quality Assurance Guide](../guides/quality-assurance.md)
3. Consult the [Testing Documentation](../testing/index.md) for validation procedures
4. Open an issue on GitHub with the `data-quality` label
