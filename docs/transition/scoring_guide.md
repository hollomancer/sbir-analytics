# Transition Detection Scoring Guide

## Overview

The Transition Detection Algorithm combines six independent signals with configurable weights to produce a composite likelihood score. This guide explains how scoring works, how to interpret scores, and how to tune weights and thresholds for your use case.

## Quick Reference

| Component | Range | Purpose |
|-----------|-------|---------|
| Base Score | 0.15 | Baseline prior probability |
| Signal Scores | 0.0–0.25 each | Individual signal contributions |
| Final Score | 0.0–1.0 | Composite likelihood (sum of all) |
| Confidence | HIGH/LIKELY/POSSIBLE | Classification threshold band |

## Scoring Mechanics

### Base Score

Every transition starts with a configurable base score (default: **0.15**). This represents the prior probability that a random award-contract pair represents commercialization, even with no signals present.

**Why**: Prevents low-signal transitions from scoring 0.0; allows weak-but-consistent evidence patterns to reach LIKELY confidence.

### Adjustment

- Increase base score (0.20) if you want more transitions to pass thresholds
- Decrease base score (0.10) if you want higher precision with fewer detections

### Signal Scores

Each signal contributes to the final score via a two-step process:

```text
Signal Score = Signal Bonus × Signal Weight
```

### Example

- Agency continuity bonus: 0.25 (same agency matched)
- Agency continuity weight: 0.25
- Agency contribution: 0.25 × 0.25 = 0.0625

### Signal Weights

Weights represent the relative importance of each signal and must sum to 1.0:

| Signal | Weight | Basis | Typical Range |
|--------|--------|-------|---|
| Agency Continuity | 0.25 | Ongoing relationship | 0.15–0.35 |
| Timing Proximity | 0.20 | Commercialization window | 0.15–0.30 |
| Competition Type | 0.20 | Vendor targeting | 0.10–0.30 |
| Patent Signal | 0.15 | Technology maturity | 0.10–0.25 |
| CET Alignment | 0.10 | Technology consistency | 0.05–0.20 |
| Text Similarity | 0.00 | Description similarity | 0.00–0.10 |
| **Total** | **1.00** | | |

**Warning**: Weights must sum exactly to 1.0. If you increase one weight, decrease others proportionally.

## Signal Details

### 1. Agency Continuity Signal (Weight: 0.25)

### Scoring Table

| Match Type | Bonus | Score | Interpretation |
|-----------|-------|-------|---|
| Same Agency | 0.25 | 0.0625 | Award and contract from same federal agency |
| Cross-Service | 0.125 | 0.03125 | Different agencies, same department (e.g., Army & Air Force both in DoD) |
| Different Department | 0.05 | 0.0125 | Different executive departments (e.g., DoD vs. NSF) |
| No Match | 0.0 | 0.0 | No agency information or no match |

### Example Scenarios

```yaml
Scenario 1: NSF Award → NSF Contract
  Award Agency: National Science Foundation (NSF)
  Contract Agency: National Science Foundation (NSF)
  Match Type: Same Agency
  Score: 0.25 × 0.25 = 0.0625
  Interpretation: Strong indicator of ongoing relationship

Scenario 2: DoD Navy Award → DoD Air Force Contract
  Award Agency: Department of Defense (Navy)
  Contract Agency: Department of Defense (Air Force)
  Match Type: Cross-Service (same Department)
  Score: 0.125 × 0.25 = 0.03125
  Interpretation: Moderate indicator; may indicate related program

Scenario 3: NSF Award → DoD Contract
  Award Agency: National Science Foundation
  Contract Agency: Department of Defense
  Match Type: Different Department
  Score: 0.05 × 0.25 = 0.0125
  Interpretation: Weak indicator; unlikely same program
```

### Configuration

```yaml
scoring:
  agency_continuity:
    enabled: true
    weight: 0.25
    same_agency_bonus: 0.25
    cross_service_bonus: 0.125
    different_dept_bonus: 0.05
```

### Tuning

- **Increase weight to 0.35** if agency alignment is strong indicator in your data
- **Decrease weight to 0.15** if awards/contracts cross agencies frequently but still represent same program
- **Disable (weight: 0.0)** for cross-agency program analysis

### 2. Timing Proximity Signal (Weight: 0.20)

### Scoring by Window

| Days After Completion | Window | Score | Interpretation |
|---|---|---|---|
| 0–90 | Immediate | 1.0 × 0.20 = 0.20 | Immediate commercialization (strong signal) |
| 91–365 | Near-term | 0.75 × 0.20 = 0.15 | Within-year commercialization (good signal) |
| 366–730 | Extended | 0.50 × 0.20 = 0.10 | 1-2 year delayed (weaker signal) |
| 731+ | Beyond window | 0.0 × 0.20 = 0.0 | Outside default window (no contribution) |
| <0 | Pre-award | 0.0 | Contract before award (anomaly, zero score) |

### Example Scenarios

```yaml
Scenario 1: Fast Commercialization
  Award Completion: 2023-01-15
  Contract Start: 2023-03-01 (45 days)
  Window: 0–90 days
  Score: 1.0 × 0.20 = 0.20
  Interpretation: Immediate transition; strong evidence

Scenario 2: Within-Year Commercialization
  Award Completion: 2023-01-15
  Contract Start: 2023-06-01 (137 days)
  Window: 91–365 days
  Score: 0.75 × 0.20 = 0.15
  Interpretation: Good transition timing

Scenario 3: Delayed Commercialization
  Award Completion: 2023-01-15
  Contract Start: 2024-06-01 (502 days)
  Window: 366–730 days
  Score: 0.50 × 0.20 = 0.10
  Interpretation: Delayed transition; weaker signal

Scenario 4: Beyond Window
  Award Completion: 2023-01-15
  Contract Start: 2025-06-01 (867 days)
  Window: Beyond 730 days
  Score: 0.0 × 0.20 = 0.0
  Interpretation: Outside commercialization window; no credit
```

### Configuration

```yaml
scoring:
  timing_proximity:
    enabled: true
    weight: 0.20
    windows:

      - range: [0, 90]

        score: 1.0

      - range: [91, 365]

        score: 0.75

      - range: [366, 730]

        score: 0.50
    beyond_window_penalty: 0.0
```

### Tuning

```yaml

## For faster commercialization (e.g., Phase IIB focus)

windows:

  - range: [0, 60]

    score: 1.0

  - range: [61, 180]

    score: 0.75

  - range: [181, 365]

    score: 0.50

## Reduces score contribution for contracts beyond 1 year

## For delayed commercialization (e.g., deep tech)

windows:

  - range: [0, 180]

    score: 1.0

  - range: [181, 730]

    score: 0.75

  - range: [731, 1095]

    score: 0.50

## Extends window to 3 years; still gives credit at low score

## Increase weight to 0.30 if timing is strong differentiator


## Decrease weight to 0.10 if timing varies widely in your domain

```

### 3. Competition Type Signal (Weight: 0.20)

### Scoring Table

| Competition Type | Bonus | Score | Interpretation |
|---|---|---|---|
| Sole Source | 0.20 | 0.04 | Vendor specifically targeted (strong signal) |
| Limited Competition | 0.10 | 0.02 | Small number of eligible vendors (moderate signal) |
| Full and Open | 0.0 | 0.0 | Unlimited vendor eligibility (no signal) |
| Unknown/Not Specified | 0.0 | 0.0 | No competition data (no contribution) |

### Competition Type Mapping

| USAspending Code | Interpretation |
|---|---|
| FULL, FSS, A&A, CDO | Full and Open |
| NONE, NDO | Sole Source |
| LIMITED, RESTRICTED, COMPETITIVE | Limited Competition |
| NULL | Unknown |

### Example Scenarios

```yaml
Scenario 1: Sole Source Procurement
  Competition Type: Sole Source
  Reason: Vendor has unique capability for specialized contract
  Score: 0.20 × 0.20 = 0.04
  Interpretation: Strong indicator of prior relationship; vendor specifically chosen

Scenario 2: Limited Competition
  Competition Type: Limited
  Reason: Contract restricted to small business set-aside
  Score: 0.10 × 0.20 = 0.02
  Interpretation: Moderate signal; vendor qualified but others could compete

Scenario 3: Full and Open
  Competition Type: Full and Open
  Reason: General market competition
  Score: 0.0 × 0.20 = 0.0
  Interpretation: No signal; any vendor could have won based on competition
```

### Configuration

```yaml
scoring:
  competition_type:
    enabled: true
    weight: 0.20
    sole_source_bonus: 0.20
    limited_bonus: 0.10
```

### Tuning

```yaml

## Increase weight to 0.30 if sole source contracts are strong indicator


##   (e.g., specialized DoD procurement)

weight: 0.30

## Decrease weight to 0.10 if competition type unreliable in your data


##   (e.g., incomplete or inconsistent coding)

weight: 0.10

## Disable entirely for R&D contracts (where competition type less relevant)

enabled: false
weight: 0.0
```

### Caveats

- Sole source doesn't always indicate commercialization; may indicate sole qualified vendor for unrelated work
- Limited competition may reflect small business set-asides rather than vendor relationships
- Full and open competitions can still represent commercialization (winning vendor is still SBIR recipient)

### 4. Patent Signal (Weight: 0.15)

### Scoring Components

| Component | Bonus | Weight | Score |
|---|---|---|---|
| Has Patents | 0.05 | 0.15 | 0.0075 |
| Pre-Contract Patents | 0.03 | 0.15 | 0.0045 |
| Topic Match (≥0.7) | 0.02 | 0.15 | 0.003 |
| No Patents | 0.0 | 0.15 | 0.0 |

### Example Scenarios

```yaml
Scenario 1: Patent-Backed Transition
  Metrics:
    Patents Filed: 2 (both by SBIR recipient)
    Pre-Contract Patents: 2 (both filed before contract start)
    Topic Similarity: 0.82 (patent abstract vs. contract description)
  Bonuses:

    - Has patents: +0.05
    - Pre-contract: +0.03
    - Topic match: +0.02

  Total Bonus: 0.10
  Score: 0.10 × 0.15 = 0.015
  Interpretation: Strong evidence of technology commercialization

Scenario 2: Patents Filed After Contract
  Metrics:
    Patents Filed: 1 (by SBIR recipient)
    Filing Date: 6 months after contract start
    Topic Similarity: 0.65 (below 0.7 threshold)
  Bonuses:

    - Has patents: +0.05
    - Pre-contract: +0.0 (filed after contract)
    - Topic match: +0.0 (below threshold)

  Total Bonus: 0.05
  Score: 0.05 × 0.15 = 0.0075
  Interpretation: Patent activity, but weak timing signal

Scenario 3: No Patents
  Metrics:
    Patents Filed: 0
  Bonuses:

    - Has patents: +0.0

  Total Bonus: 0.0
  Score: 0.0 × 0.15 = 0.0
  Interpretation: No patent signal (common in service contracts)
```

### Topic Similarity Calculation

TF-IDF Cosine Similarity between:

- Patent abstract (or patent title + abstract)
- Contract description (or contract statement of work)

```text
Similarity Score = Cosine(TF-IDF(patent), TF-IDF(contract))
Range: 0.0 (completely different) to 1.0 (identical)
Threshold: 0.7 (≥0.7 considered "topic match")
```

### Example

```text
Patent Abstract: "Neural network-based object detection system
  optimized for edge computing devices using quantization techniques"

Contract Description: "Design and develop an AI-based object
  detection system for mobile edge devices with performance
  optimization for deployment"

Similarity Score: 0.78 (≥0.7 threshold)
→ Topic match bonus applied
```

### Configuration

```yaml
scoring:
  patent_signal:
    enabled: true
    weight: 0.15
    has_patent_bonus: 0.05
    pre_contract_bonus: 0.03
    topic_match_bonus: 0.02
    topic_similarity_threshold: 0.7
```

### Tuning

```yaml

## For technology-heavy transitions (hardware, deep tech)

weight: 0.25  # Increase weight; patents more relevant
pre_contract_bonus: 0.05  # Increase bonus; pre-patent filing stronger signal
topic_similarity_threshold: 0.75  # Stricter similarity threshold

## For service-based transitions (consulting, integration)

weight: 0.05  # Decrease weight; patents less relevant
pre_contract_bonus: 0.01  # Lower bonus
topic_similarity_threshold: 0.6  # Looser similarity threshold

## For research contracts (where patents expected)

weight: 0.30  # Heavy weight; patents expected output
has_patent_bonus: 0.10  # Higher bonus for patent presence
```

### 5. CET Alignment Signal (Weight: 0.10)

### Scoring Table

| Match Type | Bonus | Score | Interpretation |
|---|---|---|---|
| Same CET Area | 0.05 | 0.005 | Award and contract in same critical technology area |
| Different CET Area | 0.0 | 0.0 | Misaligned technology areas |
| Unknown CET | 0.0 | 0.0 | Missing CET information (no contribution) |

**CET Areas** (10 critical emerging technologies):

1. **AI & Machine Learning**: Neural networks, NLP, computer vision, reinforcement learning
2. **Advanced Computing**: High-performance computing, quantum computing, neuromorphic systems
3. **Biotechnology & Advanced Biology**: Gene editing, synthetic biology, biomanufacturing
4. **Advanced Manufacturing**: 3D printing, robotics, digital twins, precision manufacturing
5. **Quantum Computing**: Quantum algorithms, quantum hardware, quantum error correction
6. **Biodefense**: Biosecurity, pandemic preparedness, infectious disease mitigation
7. **Microelectronics**: Semiconductor manufacturing, photonics, advanced materials
8. **Hypersonics**: Hypersonic vehicle design, propulsion, thermal management
9. **Space Systems**: Satellite systems, autonomous spacecraft, space infrastructure
10. **Climate Resilience**: Climate adaptation, decarbonization, environmental monitoring

### Example Scenarios

```yaml
Scenario 1: CET Alignment
  Award CET: AI & Machine Learning
  Award Title: "Federated learning for distributed edge inference"

  Contract CET: Inferred from "AI-powered anomaly detection platform"
  Inferred CET: AI & Machine Learning (confidence: 0.92)

  Match: Same CET Area
  Score: 0.05 × 0.10 = 0.005
  Interpretation: Technology area consistency

Scenario 2: CET Mismatch
  Award CET: Quantum Computing
  Award Title: "Quantum algorithm development for optimization"

  Contract Description: "Advanced manufacturing process automation"
  Inferred CET: Advanced Manufacturing

  Match: Different CET Area
  Score: 0.0 × 0.10 = 0.0
  Interpretation: Technology areas diverged; unlikely related transition

Scenario 3: Missing CET Data
  Award CET: [Not specified]
  Contract CET: [Cannot infer]

  Match: Unknown
  Score: 0.0 × 0.10 = 0.0
  Interpretation: Insufficient data; no contribution
```

### CET Inference Algorithm

Uses keyword matching on contract description:

```text
1. Tokenize and normalize contract description
2. Search for keyword patterns per CET area
3. Count keyword hits per area
4. Normalize by description length
5. Return highest-scoring CET with confidence
```

### Keyword Examples

```text
AI & Machine Learning: "machine learning", "neural network", "deep learning",
  "NLP", "computer vision", "model", "inference", "AI", "artificial intelligence"

Advanced Computing: "high-performance", "HPC", "quantum", "GPU", "parallel",
  "computing", "supercomputer", "FPGA"

Quantum: "quantum algorithm", "qubit", "quantum computing", "quantum gate",
  "quantum hardware", "quantum simulation"

Microelectronics: "semiconductor", "chip", "photonics", "wafer", "transistor",
  "circuit", "microchip", "nanotechnology"
```

### Configuration

```yaml
scoring:
  cet_alignment:
    enabled: true
    weight: 0.10
    same_cet_bonus: 0.05
```

### Tuning

```yaml

## For CET-focused analysis (critical tech areas)

weight: 0.25  # Increase to 25%; CET alignment primary signal

## Reduce weight if CET data unreliable

weight: 0.05  # Lower to 5%; minimal contribution

## Disable if CET inference low confidence

enabled: false
```

### 6. Text Similarity Signal (Weight: 0.0 - Optional)

**Status**: Disabled by default due to high false positive rate.

**Scoring Table** (if enabled):

| Similarity Score | Bonus | Contribution |
|---|---|---|
| ≥0.8 | 0.05 | 0.05 × weight |
| 0.6–0.8 | 0.02 | 0.02 × weight |
| <0.6 | 0.0 | 0.0 |

**Method**: TF-IDF cosine similarity between award description and contract description

### Example

```text
Award Description: "Machine learning models for predictive maintenance
  of industrial equipment using vibration sensors"

Contract Description: "Development of AI-based condition monitoring system
  for machinery predictive maintenance application"

Similarity Score: 0.76
Bonus: 0.02 (falls in 0.6–0.8 range)
Contribution: 0.02 × 0.0 = 0.0 (weight is 0, disabled)
```

### Why Disabled

- Award and contract descriptions often generic; high baseline similarity
- Low precision without careful tuning
- Better signals (timing, agency) more reliable

### Enable Only If

- You have high-quality, detailed descriptions
- You have ground truth to validate precision
- You're doing exploratory/broad discovery analysis

### Configuration

```yaml
scoring:
  text_similarity:
    enabled: false  # Set to true to enable
    weight: 0.0     # Set to 0.05-0.10 if enabled
    similarity_threshold: 0.7
```

## Composite Score Calculation

### Formula

```text
final_score = base_score + Σ(signal_score)

where signal_score = bonus × weight for each enabled signal
```

### Example Calculation

**Scenario**: SBIR award → federal contract

### Inputs

- Base score: 0.15
- Agency continuity: Same agency → bonus 0.25, weight 0.25
- Timing: 60 days → window score 1.0, weight 0.20
- Competition: Sole source → bonus 0.20, weight 0.20
- Patent: 1 patent filed pre-contract → bonus 0.05 + 0.03 = 0.08, weight 0.15
- CET: Different areas → bonus 0.0, weight 0.10
- Text similarity: Disabled → bonus 0.0, weight 0.0

### Calculation

```text
Agency contribution: 0.25 × 0.25 = 0.0625
Timing contribution: 1.0 × 0.20 = 0.20
Competition contribution: 0.20 × 0.20 = 0.04
Patent contribution: 0.08 × 0.15 = 0.012
CET contribution: 0.0 × 0.10 = 0.0
Text contribution: 0.0 × 0.0 = 0.0

Final Score = 0.15 + 0.0625 + 0.20 + 0.04 + 0.012 + 0.0 + 0.0
Final Score = 0.4645
```

**Confidence Classification**: 0.4645 → POSSIBLE (< 0.65)

## Confidence Thresholds

### Default Thresholds

```yaml
confidence_thresholds:
  high: 0.85
  likely: 0.65
```

### Interpretation

| Score | Confidence | Precision | Recall | Use Case |
|---|---|---|---|---|
| ≥0.85 | HIGH | ~90% | ~60% | Executive reporting, high-confidence findings |
| 0.65–0.84 | LIKELY | ~75% | ~85% | General analysis, stakeholder review |
| <0.65 | POSSIBLE | ~40% | ~95% | Research, hypothesis generation |

### Tuning Thresholds

**Increase thresholds for higher precision** (fewer false positives):

```yaml
confidence_thresholds:
  high: 0.88  # was 0.85
  likely: 0.70  # was 0.65
```

**Decrease thresholds for higher recall** (fewer false negatives):

```yaml
confidence_thresholds:
  high: 0.80
  likely: 0.60
```

## Preset Configurations

### High Precision Preset

```yaml
base_score: 0.20
scoring:
  agency_continuity:
    weight: 0.35
  timing_proximity:
    weight: 0.25
    windows:

      - range: [0, 180]

        score: 1.0

      - range: [181, 365]

        score: 0.5
  competition_type:
    weight: 0.20
  patent_signal:
    weight: 0.15
  cet_alignment:
    weight: 0.05
  text_similarity:
    weight: 0.0

confidence_thresholds:
  high: 0.88
  likely: 0.75
```

**Use Case**: Executive reporting, regulatory compliance
**Characteristics**: Conservative, fewer false positives, higher precision (~90%)

### Balanced Preset (Default)

```yaml
base_score: 0.15
scoring:
  agency_continuity:
    weight: 0.25
  timing_proximity:
    weight: 0.20
  competition_type:
    weight: 0.20
  patent_signal:
    weight: 0.15
  cet_alignment:
    weight: 0.10
  text_similarity:
    weight: 0.0

confidence_thresholds:
  high: 0.85
  likely: 0.65
```

**Use Case**: General analysis, development, stakeholder reviews
**Characteristics**: Balanced precision-recall, good all-around performance

### Broad Discovery Preset

```yaml
base_score: 0.10
scoring:
  agency_continuity:
    weight: 0.20
  timing_proximity:
    weight: 0.20
    windows:

      - range: [0, 365]

        score: 1.0

      - range: [366, 1095]

        score: 0.5
  competition_type:
    weight: 0.20
  patent_signal:
    weight: 0.15
  cet_alignment:
    weight: 0.15
  text_similarity:
    weight: 0.10  # Enabled

confidence_thresholds:
  high: 0.75
  likely: 0.50
```

**Use Case**: Research, hypothesis generation, exploratory analysis
**Characteristics**: High recall, broader window, more signals

### CET-Focused Preset

```yaml
base_score: 0.15
scoring:
  agency_continuity:
    weight: 0.15
  timing_proximity:
    weight: 0.15
  competition_type:
    weight: 0.15
  patent_signal:
    weight: 0.20
  cet_alignment:
    weight: 0.35  # Heavily weighted
  text_similarity:
    weight: 0.0

confidence_thresholds:
  high: 0.80
  likely: 0.60
```

**Use Case**: Critical technology area analysis, tech transfer metrics
**Characteristics**: CET alignment as primary signal, patent signal secondary

## Advanced Tuning

### Tuning for Different Award Types

#### Phase I Awards

- Shorter time windows (0-12 months)
- Lower patent signal weight (patents unlikely this early)
- Higher agency weight (continuity stronger indicator)

```yaml
timing_window:
  max_days: 365
scoring:
  agency_continuity:
    weight: 0.30
  patent_signal:
    weight: 0.05
```

#### Phase II Awards

- Standard configuration (0-24 months)
- Medium patent signal weight
- Balanced signals

```yaml

## Use balanced preset

```

###Phase IIB Awards

- Shorter time windows (0-18 months, commercialization push)
- High patent signal weight (typically patented)
- Increased competition weight (targeted procurement)

```yaml
timing_window:
  max_days: 545  # 18 months
scoring:
  patent_signal:
    weight: 0.20
  competition_type:
    weight: 0.25
```

### Tuning for Different Sectors

#### Defense/DoD Contracts

- High agency weight (same-agency very strong signal)
- High competition type weight (sole source common and meaningful)
- Shorter time windows (faster commercialization)

```yaml
scoring:
  agency_continuity:
    weight: 0.35
  competition_type:
    weight: 0.25
timing_window:
  max_days: 365
```

#### Civilian/NSF Contracts

- Moderate agency weight (broader agency landscape)
- Lower competition weight (full and open more common)
- Longer time windows (slower commercialization)

```yaml
scoring:
  agency_continuity:
    weight: 0.20
  competition_type:
    weight: 0.10
timing_window:
  max_days: 1095  # 36 months
```

#### Technology-Focused (AI, QC, Biotech)

- High patent signal weight (patents expected)
- High CET alignment weight
- High base score (more likely to commercialize)

```yaml
base_score: 0.20
scoring:
  patent_signal:
    weight: 0.25
  cet_alignment:
    weight: 0.20
```

## Validation & Metrics

### Scoring Validation Checklist

- [ ] All signal weights sum to 1.0
- [ ] Base score is between 0.10 and 0.25
- [ ] Confidence thresholds: high > likely > 0
- [ ] high threshold ≥ 0.75 (reasonable precision target)
- [ ] likely threshold ≤ 0.75 (distinct from high)
- [ ] All signal bonuses between 0.0 and 1.0
- [ ] All window scores between 0.0 and 1.0

### Metrics to Monitor

After applying scoring configuration:

```text
Metric                  Target    Action if Below
─────────────────────────────────────────────────
HIGH precision          ≥85%      Increase thresholds
LIKELY precision        ≥75%      Increase likely threshold
Overall recall          ≥70%      Decrease thresholds / extend time window
HIGH confidence rate    5-15%     Adjust base score
LIKELY confidence rate  15-30%    Adjust signal weights
Avg score               0.60-0.75 Increase base score
```

## Troubleshooting

### Problem: Too Many POSSIBLE Detections

### Symptoms

- Most scores fall below 0.65
- Few HIGH or LIKELY detections
- Difficult to interpret results

### Solutions

1. **Increase base score**: 0.15 → 0.20
2. **Increase signal bonuses**: e.g., same_agency_bonus 0.25 → 0.35
3. **Decrease confidence thresholds**: likely 0.65 → 0.55
4. **Enable text similarity signal**: Add 0.05 weight

### Problem: Too Few Detections

### Symptoms

- Most scores above 0.85
- Almost all HIGH confidence
- Missed obvious transitions

### Solutions

1. **Decrease base score**: 0.15 → 0.10
2. **Decrease signal weights**: Normalize to ensure diversity
3. **Extend timing window**: 730 days → 1095 days
4. **Enable fuzzy matching**: Better vendor resolution

### Problem: Inconsistent Scores Across Agencies

### Symptoms

- DoD contracts consistently score higher
- NSF contracts consistently score lower
- Agency bias apparent

### Solutions

1. **Lower agency continuity weight**: 0.25 → 0.15
2. **Create agency-specific configs**: Different thresholds per agency
3. **Review signal bonuses**: Are they agency-specific?

### Problem: Precision Too Low (Many False Positives)

### Symptoms

- Manual review shows <70% of HIGH confidence are valid
- Random-seeming detections

### Solutions

1. **Increase confidence thresholds**: high 0.85 → 0.90
2. **Reduce base score**: 0.15 → 0.10
3. **Reduce signal weights for noisy signals**: Disable text similarity
4. **Shorten timing window**: Faster commercialization more reliable
5. **Require specific signals**: Mandate agency match + patent signal

## Environment Variables

```bash

## Override base score

SBIR_ETL__TRANSITION__DETECTION__BASE_SCORE=0.20

## Override confidence thresholds

SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.88
SBIR_ETL__TRANSITION__DETECTION__LIKELY_CONFIDENCE_THRESHOLD=0.70

## Override signal weights (must sum to 1.0)

SBIR_ETL__TRANSITION__DETECTION__AGENCY_WEIGHT=0.30
SBIR_ETL__TRANSITION__DETECTION__TIMING_WEIGHT=0.20
SBIR_ETL__TRANSITION__DETECTION__COMPETITION_WEIGHT=0.20
SBIR_ETL__TRANSITION__DETECTION__PATENT_WEIGHT=0.15
SBIR_ETL__TRANSITION__DETECTION__CET_WEIGHT=0.15

## Override timing window

SBIR_ETL__TRANSITION__DETECTION__MIN_DAYS=0
SBIR_ETL__TRANSITION__DETECTION__MAX_DAYS=730
```

## Summary

Transition scoring combines multiple signals with configurable weights to balance precision, recall, and interpretability. Start with the balanced preset, validate against ground truth, and adjust incrementally based on metrics. Document all configuration changes for reproducibility and stakeholder communication.
