# Design Document

## Overview

The SBIR Transition Detection Module implements a comprehensive system for identifying and analyzing technology transitions from SBIR awards to follow-on government contracts. The system uses multi-signal scoring, evidence-based detection, and graph-based analytics to measure program effectiveness at both award and company levels.

## Architecture

### Pipeline Architecture
The system follows a five-stage ETL pipeline:
1. **Extract**: Ingest SBIR awards, federal contracts, and patent data
2. **Resolve**: Match vendors across datasets using UEI, CAGE, DUNS, and fuzzy name matching
3. **Detect**: Apply multi-signal scoring to identify potential transitions
4. **Analyze**: Generate analytics and effectiveness metrics
5. **Load**: Store results in Neo4j graph database for querying

### Core Components
- **TransitionDetector**: Orchestrates the detection pipeline
- **VendorResolver**: Handles cross-dataset vendor matching
- **TransitionScorer**: Implements multi-signal likelihood scoring
- **EvidenceGenerator**: Creates audit trails for all detections
- **TransitionAnalytics**: Computes effectiveness metrics

## Components and Interfaces

### Detection Engine (`src/transition/detection/`)
- **detector.py**: Main pipeline orchestration
- **scoring.py**: Multi-signal scoring with configurable weights
- **evidence.py**: Evidence bundle generation and validation

### Feature Extraction (`src/transition/features/`)
- **vendor_resolver.py**: Vendor matching across identifiers
- **patent_analyzer.py**: Patent-based transition signals
- **cet_analyzer.py**: Critical and Emerging Technology alignment

### Analytics (`src/transition/analysis/`)
- **analytics.py**: Dual-perspective effectiveness metrics

## Data Models

### Core Models
- **Transition**: Detected transition with score, confidence, and evidence
- **TransitionSignals**: Individual signal contributions (agency, timing, competition, patent, CET)
- **EvidenceBundle**: Comprehensive audit trail for validation
- **VendorMatch**: Cross-walk resolution tracking
- **TransitionProfile**: Company-level aggregation metrics

### Graph Schema (Neo4j)
- **Nodes**: Award, Contract, Transition, Company, Patent, CETArea, TransitionProfile
- **Relationships**: TRANSITIONED_TO, RESULTED_IN, ENABLED_BY, INVOLVES_TECHNOLOGY, ACHIEVED

## Error Handling

### Quality Gates
- Configurable thresholds for vendor match rates (≥90%)
- Detection success rate validation (≥99%)
- Data completeness checks at each pipeline stage

### Graceful Degradation
- Optional signals (patents, CET) don't block processing
- Missing data handled with appropriate defaults
- Comprehensive logging for debugging and monitoring

## Testing Strategy

### Multi-Level Testing
- **Unit Tests**: Individual component validation (≥85% coverage)
- **Integration Tests**: Multi-component interaction testing
- **E2E Tests**: Full pipeline validation with sample datasets
- **Performance Tests**: Throughput validation (≥10K detections/minute)

### Quality Validation
- Precision/recall targets with ground truth data
- Confidence band effectiveness analysis
- False positive identification for algorithm tuning
