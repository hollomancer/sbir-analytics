---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Transition Detection Documentation

This directory contains comprehensive documentation for the technology transition detection system in the SBIR ETL project.

## Overview

The transition detection system identifies successful transitions of SBIR/STTR-funded research into commercial applications, procurement contracts, and economic outcomes. This system combines multiple data sources and signals to detect and score technology transitions.

## Quick Start

New to transition detection? Start here:

1. **[Complete Overview](overview.md)** - Comprehensive system overview with quick start
2. **[MVP Guide](mvp.md)** - Quick start and minimum viable product overview
3. **[Detection Algorithm](detection-algorithm.md)** - Core algorithm and methodology

## Core Documentation

### Detection and Scoring

- **[Detection Algorithm](detection-algorithm.md)** - Core detection methodology
  - Signal detection logic
  - Transition identification
  - Algorithm implementation details
  - Confidence scoring

- **[Scoring Guide](scoring-guide.md)** - Detailed transition scoring
  - Scoring methodology
  - Signal weights and factors
  - Score interpretation
  - Thresholds and classifications

### Data Integration

- **[Vendor Matching](vendor-matching.md)** - Vendor resolution and matching
  - Name normalization
  - Entity resolution algorithms
  - Matching confidence scoring
  - Disambiguation strategies

- **[Evidence Bundles](evidence-bundles.md)** - Evidence collection and structure
  - Evidence types and sources
  - Bundle structure and organization
  - Evidence quality assessment
  - Supporting data relationships

### Integration Points

- **[CET Integration](cet-integration.md)** - CET classification alignment
  - CET signal incorporation
  - Commercialization indicators
  - Classification-based scoring
  - Combined analysis approach

- **[USAspending Integration](usaspending-integration.md)** - Federal contract data
  - Contract data extraction
  - Transition signal detection from contracts
  - Spend analysis integration
  - Vendor matching with USAspending

## System Architecture

```
┌────────────────────────────────────────────────────┐
│         Transition Detection System                │
│                                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │  Data Sources                                 │ │
│  │  - SBIR Awards (base data)                   │ │
│  │  - USAspending (contracts)                   │ │
│  │  - USPTO Patents                             │ │
│  │  - CET Classifications                       │ │
│  └──────────────────────────────────────────────┘ │
│           ↓                                        │
│  ┌──────────────────────────────────────────────┐ │
│  │  Detection Pipeline                          │ │
│  │  1. Vendor Matching                          │ │
│  │  2. Signal Detection                         │ │
│  │  3. Evidence Collection                      │ │
│  │  4. Scoring & Classification                 │ │
│  └──────────────────────────────────────────────┘ │
│           ↓                                        │
│  ┌──────────────────────────────────────────────┐ │
│  │  Outputs                                     │ │
│  │  - Transition Profiles (Neo4j)              │ │
│  │  - Confidence Scores                        │ │
│  │  - Evidence Bundles                         │ │
│  │  - Transition Analytics                     │ │
│  └──────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

## Key Concepts

### Transition Types

The system detects several types of transitions:

1. **Commercialization** - Technology productization and market entry
2. **Procurement** - Federal/defense procurement contracts
3. **Follow-on Funding** - Subsequent awards and investments
4. **Patent Activity** - Patent filings and licensing

### Signal Categories

Signals are organized into categories:

- **Strong Signals** - Direct evidence of transition (e.g., procurement contract)
- **Moderate Signals** - Indirect indicators (e.g., patent filing)
- **Weak Signals** - Supporting evidence (e.g., company growth)

### Confidence Scoring

Transitions are scored on confidence levels:

- **High Confidence** (>0.75) - Multiple strong signals with corroboration
- **Medium Confidence** (0.50-0.75) - Clear signals with some corroboration
- **Low Confidence** (0.25-0.50) - Limited signals or weak evidence
- **Tentative** (<0.25) - Minimal evidence, requires review

## Implementation Guides

### Running Transition Detection

```python
# Via Dagster UI
# Navigate to Assets → Transition Detection → Materialize

# Via CLI
dagster asset materialize -m src.definitions --select transition_profiles
```

### Querying Transitions

See the [Transition Queries](../queries/transition-queries.md) documentation for Neo4j query examples.

### Graph Schema

Transition data is stored in Neo4j. For schema details:

- **[Transition Graph Schema](../schemas/transition-graph-schema.md)** - Neo4j schema for transitions
- **[Neo4j Schema Reference](../schemas/neo4j.md)** - Overall graph schema

## Data Flow

1. **Data Ingestion** - Awards, contracts, patents ingested from sources
2. **Vendor Matching** - Entity resolution across data sources
3. **Signal Detection** - Identify transition signals in the data
4. **Evidence Collection** - Gather supporting evidence for signals
5. **Scoring** - Calculate confidence scores for detected transitions
6. **Storage** - Write transition profiles to Neo4j
7. **Analysis** - Query and analyze transition data

## Configuration

Transition detection configuration:

- **Scoring Thresholds** - Configurable in `config/transition/`
- **Signal Weights** - Adjustable weights for different signal types
- **Matching Parameters** - Vendor matching sensitivity settings

## Related Documentation

- **[ML/CET Documentation](../ml/)** - CET classification system
- **[Schema Documentation](../schemas/)** - Graph schema details
- **[Queries](../queries/)** - Example Neo4j queries
- **[Architecture](../architecture/)** - System architecture

## Performance and Validation

- **Detection Accuracy** - ~85% precision on validated transitions
- **Coverage** - Detects transitions for ~60% of mature awards
- **Processing Time** - ~2-3 minutes per 1000 awards

For historical validation reports, see `docs/archive/transition/status-reports/`.

## Research and Development

The transition detection system is an active area of research. Future improvements:

- Enhanced machine learning integration
- Additional signal types (publications, partnerships)
- Real-time detection for recent awards
- Improved vendor matching algorithms

---

For questions about transition detection or to report issues, refer to the detailed guides above or consult the main [project README](../../README.md).
