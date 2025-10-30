# Steering Documents Guide

This directory contains agent steering documents that provide architectural guidance, patterns, and standards for the SBIR ETL Pipeline project.

## Document Overview

### Core Technical Patterns
- **[data-quality.md](data-quality.md)** - Data quality framework, validation methods, and quality dimensions
- **[enrichment-patterns.md](enrichment-patterns.md)** - Hierarchical enrichment strategy, confidence scoring, and evidence tracking
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Dagster asset patterns, quality gates, and performance optimization
- **[neo4j-patterns.md](neo4j-patterns.md)** - Graph database modeling, relationship patterns, and query optimization

### Configuration & Reference
- **[configuration-patterns.md](configuration-patterns.md)** - Centralized configuration examples and YAML patterns
- **[quick-reference.md](quick-reference.md)** - Condensed reference for common patterns and configurations

### Project Foundation
- **[product.md](product.md)** - Product overview, core purpose, and business value
- **[structure.md](structure.md)** - Project organization, directory conventions, and architectural patterns
- **[tech.md](tech.md)** - Technology stack, development tools, and common commands

## Navigation Guide

### For Data Quality Implementation
1. Start with **[data-quality.md](data-quality.md)** for quality framework
2. Reference **[configuration-patterns.md](configuration-patterns.md)** for quality thresholds
3. See **[pipeline-orchestration.md](pipeline-orchestration.md)** for asset check implementation

### For Data Enrichment Implementation
1. Start with **[enrichment-patterns.md](enrichment-patterns.md)** for enrichment strategy
2. Reference **[configuration-patterns.md](configuration-patterns.md)** for enrichment configuration
3. See **[pipeline-orchestration.md](pipeline-orchestration.md)** for performance monitoring

### For Pipeline Development
1. Start with **[pipeline-orchestration.md](pipeline-orchestration.md)** for Dagster patterns
2. Reference **[structure.md](structure.md)** for code organization
3. See **[tech.md](tech.md)** for development commands

### For Graph Database Work
1. Start with **[neo4j-patterns.md](neo4j-patterns.md)** for graph modeling
2. Reference **[configuration-patterns.md](configuration-patterns.md)** for Neo4j configuration
3. See **[pipeline-orchestration.md](pipeline-orchestration.md)** for loading patterns

### For Project Setup
1. Start with **[product.md](product.md)** for project understanding
2. Reference **[structure.md](structure.md)** for code organization
3. See **[tech.md](tech.md)** for development setup

## Quick Decision Tree

**Need to implement data validation?** → `data-quality.md` + `configuration-patterns.md`

**Need to enrich data from external sources?** → `enrichment-patterns.md` + `configuration-patterns.md`

**Need to create Dagster assets?** → `pipeline-orchestration.md` + `structure.md`

**Need to work with Neo4j?** → `neo4j-patterns.md` + `configuration-patterns.md`

**Need configuration examples?** → `configuration-patterns.md`

**Need quick lookup?** → `quick-reference.md`

**New to the project?** → `product.md` → `structure.md` → `tech.md`

## Document Relationships

```
product.md (What & Why)
    ↓
structure.md (How - Organization)
    ↓
tech.md (How - Tools)
    ↓
┌─────────────────────────────────────────┐
│ Technical Implementation Patterns       │
├─────────────────────────────────────────┤
│ data-quality.md ←→ pipeline-orchestration.md │
│ enrichment-patterns.md ←→ pipeline-orchestration.md │
│ neo4j-patterns.md ←→ pipeline-orchestration.md │
└─────────────────────────────────────────┘
    ↓
configuration-patterns.md (Centralized Config)
    ↓
quick-reference.md (Quick Lookup)
```

## Maintenance Guidelines

### When Adding New Patterns
1. Determine which existing document should contain the pattern
2. If it doesn't fit existing documents, consider if a new document is needed
3. Update this README with navigation guidance
4. Add cross-references in related documents

### When Updating Configuration
1. Update `configuration-patterns.md` as the single source of truth
2. Remove duplicate configuration from other documents
3. Add references to `configuration-patterns.md` from other documents

### When Refactoring
1. Maintain the document relationships shown above
2. Keep cross-references updated
3. Update this README if document purposes change
4. Ensure `quick-reference.md` stays current

## Historical Context

These steering documents were created during the migration from OpenSpec to Kiro specifications. They preserve essential architectural patterns and technical guidance from the original OpenSpec specifications while organizing them for better agent guidance and developer reference.

For historical OpenSpec content, see `archive/openspec/` (read-only reference only).