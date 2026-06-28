# Transition Detection Algorithm

## Overview

The Transition Detection Algorithm is a multi-signal scoring system that identifies likely commercialization pathways from SBIR awards to federal contracts. It combines evidence from six independent signals to produce a composite likelihood score and confidence classification.

**Goal**: Identify which SBIR-funded research companies likely transitioned their innovations into federal procurements or other contracts.

**Scope**: Analyzes SBIR awards (Phase I, Phase II, Phase IIB, Phase III) and federal contracts to detect commercial transitions within a configurable time window (typically 0-24 months after award completion).

## Algorithm Architecture

### High-Level Flow

```text
┌─────────────────────┐
│  SBIR Awards        │
│  Federal Contracts  │
│  Patents            │
└──────────┬──────────┘
           │
           ▼
    ┌──────────────┐
    │ Vendor       │
    │ Resolution   │
    └──────────┬───┘
               │
               ▼
      ┌────────────────┐
      │ Candidate      │
      │ Selection      │
      │ (Time Window)  │
      └────────┬───────┘
               │
               ▼
      ┌────────────────────┐
      │ Signal Extraction  │
      │ • Agency           │
      │ • Timing           │
      │ • Competition      │
      │ • Patent           │
      │ • CET              │
      │ • Text Similarity  │
      └────────┬───────────┘
               │
               ▼
      ┌────────────────┐
      │ Composite      │
      │ Scoring        │
      └────────┬───────┘
               │
               ▼
      ┌────────────────────┐
      │ Confidence         │
      │ Classification     │
      │ (HIGH/LIKELY/      │
      │  POSSIBLE)         │
      └────────┬───────────┘
               │
               ▼
      ┌────────────────────┐
      │ Evidence Bundle    │
      │ Generation         │
      └────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ Transition Detections│
    │ (Score, Confidence,  │
    │  Evidence)           │
    └──────────────────────┘
```

## Core Components

### 1. Vendor Resolution

**Purpose**: Map SBIR award recipients to federal contract vendors using multiple identifier types.

**Method**: Priority-based resolution strategy:

1. **UEI (Unique Entity Identifier)** - Primary, highest confidence (0.99)
   - 12-character standard identifier
   - Used for federal awards and contracts since 2021

2. **CAGE Code** - Secondary, defense-specific (0.95)
   - Commercial and Government Entity code
   - Used primarily by DoD for procurement

3. **DUNS Number** - Tertiary, legacy (0.90)
   - 9-digit unique business identifier
   - Legacy system, less common in modern data

4. **Fuzzy Name Matching** - Fallback, variable confidence (0.65-0.85)
   - RapidFuzz token_set_ratio algorithm
   - Normalized company names (uppercase, special char removal)
   - Configurable thresholds for primary (0.85) and secondary (0.70) matches

**Confidence Tracking**: Each resolved vendor match includes a confidence score reflecting the match method quality.

### 2. Candidate Selection

**Purpose**: Efficiently identify potential contract matches for each award using time windows.

### Filters

- Vendor matches (via resolution)
- Time window: contracts within 0-24 months after award completion (configurable)
- Contract must have valid start date and recipient information

**Efficiency**: Contracts indexed by vendor ID for O(1) lookup per award.

### 3. Signal Extraction & Scoring

The algorithm combines six independent signals, each with configurable weights summing to 1.0:

| Signal | Default Weight | Logic |
|--------|---------------|-------|
| Agency Continuity | 0.25 | Same agency = ongoing relationship |
| Timing Proximity | 0.20 | Contracts within 0–730 days of award completion |
| Competition Type | 0.20 | Sole source / limited = vendor-targeted procurement |
| Patent Signal | 0.15 | Patent activity signals technology maturity |
| CET Alignment | 0.10 | Same NSTC technology area (see `config/cet/taxonomy.yaml`) |
| Text Similarity | 0.00 | Disabled — high false-positive rate |

For full scoring tables, per-signal tuning guidance, and preset configurations, see [scoring-guide.md](scoring-guide.md).

### 4. Composite Scoring

```text
final_score = base_score (0.15) + Σ(signal_bonus × signal_weight)
```

Range: 0.0–1.0. Deterministic — same inputs always produce the same output.

### 5. Confidence Classification

| Score | Confidence | Typical Use |
|-------|-----------|-------------|
| ≥ 0.85 | HIGH | Executive reporting, high-precision findings |
| 0.65–0.84 | LIKELY | General analysis, stakeholder review |
| < 0.65 | POSSIBLE | Research, hypothesis generation |

Thresholds are configurable. See [scoring-guide.md](scoring-guide.md) for tuning and preset configurations.

### 6. Evidence Bundle

Each detection includes an auditable JSON evidence bundle recording all signal evaluations, vendor match details, and raw contract/award data. See [evidence-bundles.md](evidence-bundles.md) for the full schema and field definitions.

Storage: NDJSON file (`data/processed/transitions_evidence.ndjson`) and as a property on the `TRANSITIONED_TO` Neo4j relationship.

## Configuration & Customization

Four built-in presets (High Precision, Balanced, Broad Discovery, CET Focused) cover the main use cases. See [scoring-guide.md](scoring-guide.md) for preset YAML, advanced tuning by award phase and sector, and environment variable overrides.

## Validation & Quality Metrics

### Performance Targets

- **Throughput**: ≥10,000 detections/minute (on typical hardware)
- **Precision** (HIGH confidence): ≥85% (correct positives / total detections)
- **Recall** (HIGH + LIKELY confidence): ≥70% (found transitions / total actual transitions)
- **F1 Score**: ≥0.75 (balanced precision-recall)

### Quality Gates

**MVP Gates** (enforce in CI):

1. Vendor match rate ≥ 60% (enough candidates resolved)
2. Detection success rate ≥ 99% (pipeline completeness)
3. Manual spot-check precision ≥ 80% for score ≥ 0.80

### Production Gates

1. Precision per confidence band meets targets
2. Evidence bundle completeness 100%
3. No ERROR severity issues in checks JSON

## Example: End-to-End Detection

### Input Data

### Award

- Award ID: `SBIR-2020-PHASE-II-123`
- Recipient: Acme AI Inc.
- UEI: `ABC123DEF456`
- Completion date: 2021-06-30
- Agency: DOD
- CET area: AI & Machine Learning
- Topic: "Advanced neural network optimization for defense applications"

### Contract

- Contract ID: `FA1234-20-C-0001`
- Vendor: Acme AI Inc.
- UEI: `ABC123DEF456`
- Start date: 2021-08-15 (45 days after award completion)
- Agency: DOD (Air Force)
- Competition type: Limited
- Description: "AI-powered threat detection system"

### Patents

- Patent 1: Filed 2021-05-15 (pre-completion), "Neural network optimization"
- Patent 2: Filed 2021-08-01 (pre-contract), "Defense application framework"

### Scoring Process

1. **Vendor Resolution**
   - UEI match: ABC123DEF456 ✓
   - Confidence: 0.99
   - Match method: UEI

2. **Signal Extraction**
   - Agency: DOD → DOD (Air Force) = Same department → +0.03125
   - Timing: 45 days → 0-90 days window → +0.20
   - Competition: Limited → +0.02
   - Patent: 2 patents, 2 pre-contract, topic match 0.78 → +0.10
   - CET: AI → AI → +0.005
   - Text similarity: 0.72 (disabled) → 0.0

3. **Composite Score**
   - Base: 0.15
   - Total signals: 0.03125 + 0.20 + 0.02 + 0.10 + 0.005 + 0.0 = 0.55625
   - **Final score: 0.70625**

4. **Confidence Classification**
   - Score 0.70625 ≥ 0.65 and < 0.85 → **LIKELY**

5. **Evidence Bundle**
   - Includes all signal details, vendor match info, contract details
   - Stored as JSON on Neo4j relationship

### Output

```json
{
  "award_id": "SBIR-2020-PHASE-II-123",
  "contract_id": "FA1234-20-C-0001",
  "likelihood_score": 0.70625,
  "confidence": "LIKELY",
  "detection_date": "2025-01-15T10:30:00Z",
  "evidence": { ... }
}
```

## Limitations & Future Enhancements

### Known Limitations

1. **Identifier coverage**: ~99% SBIR awards have UEI, but legacy data may have gaps
2. **Contract ambiguity**: Single contract may represent multiple projects (task orders on IDV)
3. **Name variations**: Fuzzy matching may miss acquisitions/rebranding
4. **Patent timing**: USPTO processing delays can shift filing dates
5. **CET inference**: Contract descriptions may lack technology keywords

### Planned Enhancements

1. **Graph neural networks**: Learn signal weights from labeled ground truth
2. **Acquisition handling**: Track company acquisitions to link transitions across entities
3. **Machine learning scoring**: Replace rule-based scoring with learned models
4. **Real-time detection**: Stream federal contract data for immediate analysis
5. **Sector classification**: Include industry/NAICS code alignment
6. **Performance clustering**: Identify clusters of highly transitioned companies

## References

- **SBIR Data**: [SBIR.gov](https://www.sbir.gov)
- **Federal Contracts**: [USAspending.gov](https://www.usaspending.gov)
- **Patents**: [USPTO.gov](https://www.uspto.gov)
- **CET Classification**: [NIST Critical Emerging Technologies](https://www.nist.gov/programs/critical-emerging-technologies)
- **Vendor Identifiers**: [SAM.gov Entity Management](https://sam.gov)
