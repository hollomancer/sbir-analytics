# Product Overview

## SBIR analytics

A robust ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into a Neo4j graph database for analysis and visualization.

### Core Purpose

The federal government provides vast amounts of data on innovation and government funding, but this data is spread across multiple sources and formats. This project provides a unified and enriched view of the SBIR ecosystem by:

- **Connecting disparate data sources**: Integrating SBIR awards, USAspending contracts, USPTO patents, and other publicly available data
- **Building a knowledge graph**: Structuring data in Neo4j to reveal complex relationships
- **Enabling powerful analysis**: Supporting queries that trace funding, track technology transitions, and analyze patent ownership chains

### Key Features

- **Five-stage ETL pipeline**: Extract → Validate → Enrich → Transform → Load
- **Dagster orchestration**: Asset-based pipeline with dependency management and observability
- **DuckDB processing**: Efficient querying of CSV and PostgreSQL dump data
- **Neo4j graph database**: Patent chains, award relationships, technology transition tracking
- **Quality gates**: Configurable thresholds enforce data quality throughout the pipeline
- **CET (Critical and Emerging Technologies) classification**: Automated classification of SBIR awards into CET areas

### Data Sources

- **SBIR Awards**: ~533,000 awards from SBIR.gov (1983–present)
- **USAspending**: PostgreSQL database dump for award enrichment and transaction tracking
- **USPTO Patents**: Patent Assignment Dataset for ownership chains and SBIR-funded patent tracking

### Business Value

Enables analysis of technology transition from research to commercialization, patent ownership patterns, and the effectiveness of government innovation funding programs.

## Related Documents

- **[structure.md](structure.md)** - Project organization and architectural patterns
- **[tech.md](tech.md)** - Technology stack and development tools
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Five-stage ETL pipeline implementation
- **[data-quality.md](data-quality.md)** - Quality gates and validation framework
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database modeling for SBIR ecosystem