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

#### Signal 1: Agency Continuity (Weight: 0.25)

**Logic**: Federal agencies that award SBIR contracts often have related procurement needs.

### Scoring

- Same agency: +0.25 bonus × 0.25 weight = **+0.0625**
- Cross-service (same department): +0.125 bonus × 0.25 weight = **+0.03125**
- Different department: +0.05 bonus × 0.25 weight = **+0.00125**

### Example

- Award: NSF (National Science Foundation)
- Contract: NSF procurement → Same agency → High score contribution
- Award: DOD → Contract: Navy → Same department → Moderate score contribution

**Data Fields**: `agency`, `sub_agency`, `department`

#### Signal 2: Timing Proximity (Weight: 0.20)

**Logic**: Commercial transitions typically occur within a defined window after research completion.

**Scoring** (days between award completion and contract start):
- 0-90 days: 1.0× multiplier → **+0.20**
- 91-365 days: 0.75× multiplier → **+0.15**
- 366-730 days: 0.50× multiplier → **+0.10**
- Beyond 730 days: 0.0 (outside window)

### Configurable Parameters

- `timing_window`: Min/max days (default: 0-730)
- Multiplier curves per preset (high_precision: 12mo, broad_discovery: 36mo)

**Edge Cases**: Contracts pre-dating award completion are scored as 0.0 (timing anomaly).

#### Signal 3: Competition Type (Weight: 0.20)

**Logic**: Sole source and limited competition contracts indicate targeted, vendor-specific procurement (prior relationship signal).

### Scoring

- Sole source: +0.20 bonus × 0.20 weight = **+0.04**
- Limited competition: +0.10 bonus × 0.20 weight = **+0.02**
- Full and open: 0.0 (any vendor can bid)

**Data Source**: USAspending `extent_competed` field

### Mapping

- Full/open: FULL, FSS, A&A, CDO codes
- Sole source: NONE, NDO codes
- Limited: LIMITED, RESTRICTED patterns

#### Signal 4: Patent Signal (Weight: 0.15)

**Logic**: Patent activity indicates technology maturity and commercialization readiness.

### Components

- **Has patent bonus**: +0.05 (award has ≥1 associated patent)
- **Pre-contract bonus**: +0.03 (patent filed before contract start)
- **Topic match bonus**: +0.02 (patent abstract similarity ≥ 0.7 to contract description)

**Topic Similarity**: TF-IDF cosine similarity between patent abstract and contract description.

### Scoring

```text
patent_score = (has_patent × 0.05 +
                pre_contract × 0.03 +
                topic_match × 0.02) × 0.15 (weight)
```

**Data Fields**: Patent filing date, abstract, assignee; Contract start date, description

#### Signal 5: CET Alignment (Weight: 0.10)

**Logic**: Technology area consistency between award and contract indicates sustained technology focus.

### Scoring

- Same CET area: +0.05 bonus × 0.10 weight = **+0.005**
- Different CET area: 0.0

**CET Areas** (10 critical emerging technologies):
- AI & Machine Learning
- Advanced Computing
- Biotechnology & Advanced Biology
- Advanced Manufacturing
- Quantum Computing
- Biodefense
- Microelectronics
- Hypersonics
- Space Systems
- Climate Resilience

**Award CET**: From SBIR classification (explicit field)
**Contract CET**: Inferred from contract description via keyword matching

#### Signal 6: Text Similarity (Weight: 0.0 - Optional/Disabled)

**Logic**: Similar technical descriptions suggest related work.

**Method**: TF-IDF cosine similarity between award description and contract description.

**Status**: Currently disabled (weight = 0.0) due to high false-positive rate; available for future enhancement.

### 4. Composite Scoring

**Base Score**: 0.15 (minimum baseline)

### Final Score Calculation

```text
final_score = base_score + (
    agency_score +
    timing_score +
    competition_score +
    patent_score +
    cet_score +
    text_similarity_score
)
```

**Range**: 0.0 - 1.0 (normalized)

**Deterministic**: Same inputs always produce same output.

### 5. Confidence Classification

**Purpose**: Categorize detections into confidence bands for downstream decision-making.

**Thresholds** (configurable):
- **HIGH**: score ≥ 0.85 (strong evidence, high precision)
- **LIKELY**: 0.65 ≤ score < 0.85 (moderate evidence, balanced)
- **POSSIBLE**: score < 0.65 (weak evidence, high recall)

**Usage**: Stakeholders typically focus on HIGH and LIKELY confidence transitions; POSSIBLE used for research/discovery.

### 6. Evidence Bundle

**Purpose**: Provide transparent, auditable justification for each detection.

**Contents** (JSON structure):

```json
{
  "transition_id": "trans_abc123",
  "award_id": "award_123",
  "contract_id": "contract_456",
  "signals": {
    "agency": {
      "snippet": "Same agency (NSF → NSF)",
      "details": {"same_agency": true, "score": 0.0625}
    },
    "timing": {
      "snippet": "45 days after completion (high proximity)",
      "details": {"days_between": 45, "score": 0.20}
    },
    "competition": {
      "snippet": "Limited competition (vendor-targeted)",
      "details": {"competition_type": "LIMITED", "score": 0.02}
    },
    "patent": {
      "snippet": "2 patents filed; 1 pre-contract",
      "details": {"patent_count": 2, "pre_contract_count": 1, "score": 0.06}
    },
    "cet": {
      "snippet": "CET area match (AI & ML)",
      "details": {"award_cet": "AI", "contract_cet": "AI", "score": 0.005}
    }
  },
  "vendor_match": {
    "method": "UEI",
    "confidence": 0.99,
    "award_uei": "ABC123DEF456",  # pragma: allowlist secret
    "contract_uei": "ABC123DEF456"  # pragma: allowlist secret
  },
  "contract_details": {
    "piid": "FA1234-20-C-0001",
    "agency": "DOD",
    "action_date": "2020-06-15",
    "obligated_amount": 500000
  }
}
```

**Storage**: NDJSON (newline-delimited JSON) for efficient streaming and Neo4j relationship storage.

**Validation**: All required fields present, scores within [0, 1], consistency checks.

## Configuration & Customization

### Presets

**High Precision** (Conservative)
- Confidence threshold: ≥0.85
- Time window: 12 months
- Use case: Stakeholder reporting, high-confidence findings

**Balanced** (Default)
- Confidence threshold: ≥0.65
- Time window: 24 months
- Use case: General analysis, development

**Broad Discovery** (Exploratory)
- Confidence threshold: ≥0.50
- Time window: 36 months
- Use case: Research, hypothesis generation

**Research** (No threshold)
- Confidence threshold: None (all detections)
- Time window: 48 months
- Use case: Scientific exploration

### Phase II Focus

- Optimized for Phase II awards
- Weights emphasis on timing and competition signals
- Use case: Phase II program analysis

### CET Focused

- CET alignment weight increased to 0.20
- Other weights reduced proportionally
- Use case: Critical technology analysis

### Environment Variables

```bash

## Scoring thresholds

SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.85
SBIR_ETL__TRANSITION__DETECTION__LIKELY_CONFIDENCE_THRESHOLD=0.65

## Timing window (days)

SBIR_ETL__TRANSITION__DETECTION__MIN_DAYS=0
SBIR_ETL__TRANSITION__DETECTION__MAX_DAYS=730

## Signal weights (must sum to 1.0)

SBIR_ETL__TRANSITION__DETECTION__AGENCY_WEIGHT=0.25
SBIR_ETL__TRANSITION__DETECTION__TIMING_WEIGHT=0.20
SBIR_ETL__TRANSITION__DETECTION__COMPETITION_WEIGHT=0.20
SBIR_ETL__TRANSITION__DETECTION__PATENT_WEIGHT=0.15
SBIR_ETL__TRANSITION__DETECTION__CET_WEIGHT=0.10
```

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
