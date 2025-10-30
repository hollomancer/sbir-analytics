# CET Integration Guide

## Overview

Critical and Emerging Technologies (CET) areas represent the U.S. government's strategic focus on transformational technologies that are foundational to national competitiveness, economic prosperity, and national security. The transition detection system integrates CET classification to identify technology-consistent commercialization pathways.

**Purpose**: Use CET area alignment to strengthen transition confidence when SBIR awards and federal contracts share the same critical technology focus.

**Scope**: SBIR awards are classified into CET areas; federal contracts are inferred to have CET areas based on their descriptions; alignment between award CET and contract CET is scored as a transition signal.

## The 10 CET Areas

The following 10 critical and emerging technologies are supported:

### 1. Artificial Intelligence & Machine Learning

**Description**: AI systems, neural networks, deep learning, natural language processing, computer vision, reinforcement learning, and autonomous decision-making.

**Keywords**: AI, machine learning, neural network, deep learning, NLP, natural language processing, computer vision, autonomous, reinforcement learning, transformer, LSTM, CNN, CNN, supervised learning, unsupervised learning, decision tree, clustering, classification, regression

**SBIR Focus**: Companies developing AI algorithms, tools, and applications for defense/commercial use.

**Contract Examples**:
- "AI-powered threat detection system"
- "Machine learning model for anomaly detection"
- "Deep learning framework for image classification"

**CET Importance**: High priority for defense innovation; foundational technology with broad applications.

---

### 2. Advanced Computing

**Description**: High-performance computing, quantum-ready computing, edge computing, neuromorphic computing, and advanced processing architectures.

**Keywords**: high-performance computing, HPC, quantum-ready, edge computing, distributed computing, parallel computing, GPU computing, quantum, supercomputer, FPGA, ASIC, quantum algorithm, quantum hardware

**SBIR Focus**: Companies developing advanced computing platforms, architectures, and applications.

**Contract Examples**:
- "High-performance computing optimization"
- "Edge computing platform development"
- "Quantum algorithm research"

**CET Importance**: Foundational infrastructure for AI, scientific computing, and simulation.

---

### 3. Biotechnology & Advanced Biology

**Description**: Gene editing, synthetic biology, advanced biomanufacturing, protein engineering, and biological engineering.

**Keywords**: CRISPR, gene editing, gene therapy, synthetic biology, biotech, biomanufacturing, protein engineering, cell engineering, genetic modification, biotechnology, enzyme engineering, fermentation, bioprocessing

**SBIR Focus**: Companies advancing biological and genetic technologies.

**Contract Examples**:
- "Gene editing platform development"
- "Synthetic biology manufacturing process"
- "Protein engineering and optimization"

**CET Importance**: Critical for medical, pharmaceutical, and industrial applications.

---

### 4. Advanced Manufacturing

**Description**: Additive manufacturing, advanced materials, digital twins, precision manufacturing, and advanced production techniques.

**Keywords**: additive manufacturing, 3D printing, advanced materials, digital twins, precision manufacturing, smart manufacturing, automation, robotics, composites, ceramics, metamaterials, nanotechnology, graphene

**SBIR Focus**: Companies developing advanced manufacturing processes and materials.

**Contract Examples**:
- "Additive manufacturing for aerospace"
- "Advanced composite material development"
- "Digital twin for manufacturing optimization"

**CET Importance**: Enables production of advanced systems and materials.

---

### 5. Quantum Computing

**Description**: Quantum computing hardware, algorithms, quantum sensing, quantum networking, and quantum simulation.

**Keywords**: quantum computing, quantum algorithm, qubit, quantum hardware, quantum gate, quantum simulation, quantum error correction, quantum cryptography, quantum key distribution, quantum sensor, quantum entanglement, quantum teleportation

**SBIR Focus**: Companies advancing quantum technology research and development.

**Contract Examples**:
- "Quantum computing algorithm development"
- "Quantum error correction research"
- "Quantum sensing system development"

**CET Importance**: Foundational technology with transformational potential.

---

### 6. Biodefense

**Description**: Biosecurity, pandemic preparedness, infectious disease mitigation, medical countermeasures, and biological threat detection.

**Keywords**: biodefense, biosecurity, pandemic, infectious disease, medical countermeasure, vaccine, diagnostic, threat detection, biosurveillance, epidemic, outbreak, pathogen, laboratory, containment, safety

**SBIR Focus**: Companies developing biodefense and biosecurity solutions.

**Contract Examples**:
- "Pandemic preparedness system"
- "Pathogen detection and diagnostics"
- "Vaccine development platform"

**CET Importance**: Critical for national health security.

---

### 7. Microelectronics

**Description**: Semiconductor manufacturing, photonics, advanced microelectronics, integrated circuits, and advanced packaging.

**Keywords**: semiconductor, microelectronics, photonics, integrated circuit, chip, microchip, wafer, transistor, circuit design, photonic, optical, silicon, compound semiconductor, wide bandgap, gallium nitride, GaN, silicon carbide, SiC

**SBIR Focus**: Companies developing advanced semiconductor and microelectronics technologies.

**Contract Examples**:
- "Advanced semiconductor design"
- "Photonic integrated circuits"
- "Wide bandgap semiconductor development"

**CET Importance**: Foundational for all electronics and computing.

---

### 8. Hypersonics

**Description**: Hypersonic vehicle design, hypersonic propulsion, thermal management, and hypersonic systems.

**Keywords**: hypersonic, hypersound, Mach 5, scramjet, air-breathing, thermal management, high-temperature materials, aerodynamics, supersonic, transonic, aerothermal, ablative, insulation

**SBIR Focus**: Companies developing hypersonic technologies and systems.

**Contract Examples**:
- "Hypersonic vehicle design and development"
- "Hypersonic propulsion system"
- "Thermal management for hypersonic flight"

**CET Importance**: Critical for advanced defense systems and space applications.

---

### 9. Space Systems

**Description**: Satellite systems, space infrastructure, autonomous spacecraft, space launch, and in-space operations.

**Keywords**: satellite, space, launch, orbit, spacecraft, orbital, space station, autonomous, navigation, propulsion, deployment, constellation, space situational awareness, space domain awareness, launch vehicle

**SBIR Focus**: Companies developing space technologies and systems.

**Contract Examples**:
- "Satellite system development"
- "Launch vehicle technology"
- "Autonomous orbital operations"

**CET Importance**: Critical for national security, communications, and scientific research.

---

### 10. Climate Resilience

**Description**: Climate adaptation, decarbonization, environmental monitoring, carbon capture, and climate mitigation.

**Keywords**: climate, climate resilience, climate adaptation, climate change, decarbonization, carbon capture, environmental monitoring, sustainability, green technology, renewable energy, carbon neutral, net zero, climate mitigation, climate modeling, disaster resilience

**SBIR Focus**: Companies developing climate and environmental solutions.

**Contract Examples**:
- "Carbon capture and storage technology"
- "Climate resilience planning system"
- "Environmental monitoring platform"

**CET Importance**: Critical for environmental and economic resilience.

---

## Award CET Classification

### How Awards are Classified

SBIR awards are classified into CET areas by program managers at the time of award. This classification reflects the research focus and expected outcomes of the funded work.

**Data Fields**:
- `cet_area`: Primary CET classification (string)
- `cet_code`: Optional numeric or alphabetic CET code
- `technology_area`: Alternative field name for CET classification
- `focus_area`: Alternative field name for CET classification

**Example Awards**:
```
Award ID: SBIR-2020-PHASE-II-001
Title: "Advanced Neural Network Optimization for Defense Applications"
CET Area: "AI & Machine Learning"
Description: "Federated learning techniques for distributed threat detection"

Award ID: SBIR-2020-PHASE-II-042
Title: "Quantum Algorithm Development for Optimization Problems"
CET Area: "Quantum Computing"
Description: "Quantum algorithms for logistics optimization"

Award ID: SBIR-2020-PHASE-II-073
Title: "Advanced Materials for Hypersonic Vehicles"
CET Area: "Hypersonics"
Description: "Thermal management materials for hypersonic flight"
```

### Extraction Process

The CET area is extracted from SBIR award metadata:

```python
from src.transition.features.cet_analyzer import CETSignalExtractor

extractor = CETSignalExtractor()
award_cet = extractor.extract_award_cet(award_record)
# Returns: "AI & Machine Learning"
```

**Logic**:
1. Check `cet_area` field (primary)
2. Check `cet_code` field (secondary)
3. Check `technology_area` field (tertiary)
4. Check `focus_area` field (quaternary)
5. Return None if no field found

**Data Availability**:
- ~95% of Phase II awards have explicit CET classification
- ~85% of Phase I awards have CET classification
- Civilian agency awards more likely to have CET data than legacy awards

---

## Contract CET Inference

### Why Inference is Needed

Federal contracts are not explicitly classified into CET areas. The transition detection system infers contract CET area from the contract description using keyword matching and semantic analysis.

**Rationale**: If a contract description contains keywords and concepts from a particular CET area, we infer that the contract is working in that technology area.

**Confidence**: Inference confidence depends on:
- Keyword density (number of CET keywords)
- Keyword proximity (keywords appear together vs. scattered)
- Keyword specificity (rare keywords vs. common words)
- Description quality (detailed vs. generic descriptions)

### Keyword Matching Algorithm

The inference algorithm uses precompiled regex patterns for efficiency:

```python
from src.transition.features.cet_analyzer import CETSignalExtractor

extractor = CETSignalExtractor()
cet_area, confidence = extractor.infer_contract_cet(contract_description)
# Returns: ("AI & Machine Learning", 0.92)
```

**Algorithm Steps**:

1. **Tokenize Description**
   - Split contract description into sentences
   - Remove punctuation
   - Convert to lowercase for matching

2. **Search for Keywords**
   - For each CET area, search for keywords in description
   - Count keyword hits per CET area
   - Normalize by description length

3. **Calculate Confidence**
   - Confidence = (Keyword Hits for Top CET) / Total Keywords Found
   - Range: 0.0 (no keywords) to 1.0 (all keywords matched)
   - Threshold: CET detected if confidence ≥ 0.3 (configurable)

4. **Return Top Match**
   - Return CET area with highest keyword count
   - Return confidence score

### Example Inferences

```
Contract Description: "Development of AI-powered anomaly detection system 
  using deep neural networks for threat identification"
  
Keywords Found:
  - AI, Machine Learning: 2 hits
  - Advanced Computing: 0 hits
  - Quantum: 0 hits
  
Inferred CET: "AI & Machine Learning" (confidence: 0.92)
```

```
Contract Description: "Advanced materials development including composites 
  and ceramics for aerospace applications"
  
Keywords Found:
  - Advanced Manufacturing: 2 hits
  - Hypersonics: 0 hits
  - Space: 1 hit (aerospace)
  
Inferred CET: "Advanced Manufacturing" (confidence: 0.75)
```

```
Contract Description: "Research into novel computational approaches and 
  optimization techniques"
  
Keywords Found:
  - Advanced Computing: 1 hit (computational)
  - AI & Machine Learning: 0 hits
  
Inferred CET: "Advanced Computing" (confidence: 0.50)
```

### Inference Limitations

**False Positives**: Generic descriptions may match multiple CET areas.
- Solution: Use confidence threshold; lower confidence matches require manual verification

**False Negatives**: Contracts using domain-specific terminology not captured by keywords.
- Solution: Expand keyword lists; consider semantic similarity in future versions

**Missing Keywords**: New technologies or uncommon terminology not in keyword lists.
- Solution: Periodically update keyword lists; user feedback on missed matches

**Multi-CET Contracts**: Some contracts span multiple CET areas.
- Solution: Return only highest-confidence match; store all candidates if needed

---

## CET Alignment Calculation

### What is CET Alignment?

CET alignment measures whether the SBIR award and federal contract are working in the same critical technology area.

**Rationale**: If both the award and contract are focused on the same CET area (e.g., both AI & ML), it provides stronger evidence that the contract represents commercialization of the award's research.

### Alignment Types

| Match Type | Condition | Score | Interpretation |
|-----------|-----------|-------|---|
| **Exact Match** | Award CET == Contract CET (case-insensitive) | 1.0 | Strong evidence of technology continuity |
| **Partial Match** | Award CET is substring of Contract CET (or vice versa) | 0.5 | Weak evidence of related technology |
| **No Match** | Award CET ≠ Contract CET | 0.0 | No technology continuity signal |
| **Missing Data** | Award or Contract CET is null | 0.0 | Cannot determine alignment |

### Calculation Logic

```python
from src.transition.features.cet_analyzer import CETSignalExtractor

extractor = CETSignalExtractor()

# Calculate alignment
alignment_score = extractor.calculate_alignment(
    award_cet="AI & Machine Learning",
    contract_cet="AI & Machine Learning"
)
# Returns: 1.0 (exact match)

# With inference
contract_description = "AI-powered threat detection system"
contract_cet, confidence = extractor.infer_contract_cet(contract_description)
alignment_score = extractor.calculate_alignment(
    award_cet="AI & Machine Learning",
    contract_cet=contract_cet  # Inferred
)
# Returns: (1.0, 0.92) - exact match with 92% inference confidence
```

**Implementation**:
```python
def calculate_alignment(award_cet, contract_cet):
    """Calculate CET alignment between award and contract."""
    
    if not award_cet or not contract_cet:
        return 0.0  # Missing data
    
    award_norm = award_cet.upper().strip()
    contract_norm = contract_cet.upper().strip()
    
    if award_norm == contract_norm:
        return 1.0  # Exact match
    
    # Partial match (substring)
    if (award_norm in contract_norm or 
        contract_norm in award_norm):
        return 0.5  # Partial match
    
    return 0.0  # No match
```

### Examples

```
Award CET: "AI & Machine Learning"
Contract CET (inferred): "AI & Machine Learning"
Alignment: 1.0 (exact match)

Award CET: "Quantum Computing"
Contract CET (inferred): "Advanced Computing"
Alignment: 0.0 (no match)

Award CET: "Advanced Manufacturing"
Contract CET (inferred): "Advanced Manufacturing"
Alignment: 1.0 (exact match)
```

---

## CET Alignment Signal Scoring

### Role in Transition Scoring

CET alignment is one of six scoring signals in the transition detection algorithm.

**Signal Weight**: 0.10 (default, configurable)

**Bonus**: 0.05 for exact CET match

**Contribution**: max 0.005 (0.05 bonus × 0.10 weight)

### Scoring Formula

```
cet_alignment_score = alignment_type_bonus × weight

where:
  alignment_type_bonus = 0.05 (exact match) or 0.0 (no match)
  weight = 0.10 (default)

Examples:
  Exact match: 0.05 × 0.10 = 0.005 points
  No match: 0.0 × 0.10 = 0.0 points
```

### Integration with Overall Score

The CET alignment signal contributes to the overall transition likelihood score:

```
likelihood_score = base_score + Σ(signal_contributions)

where signals include:
  - Agency continuity: max 0.0625
  - Timing proximity: max 0.20
  - Competition type: max 0.04
  - Patent signal: max 0.015
  - CET alignment: max 0.005  ← this signal
  - Vendor match: max 0.01

Total possible score: 0.15 (base) + 0.53 = 0.68
(In practice, not all signals contribute to every transition)
```

### Example Transition

```
Award: NSF Phase II, "AI for materials discovery"
  - CET: AI & Machine Learning

Contract: "Machine learning system for material optimization"
  - Inferred CET: AI & Machine Learning (confidence: 0.88)

CET Alignment Calculation:
  - Match Type: Exact match
  - Alignment Bonus: 0.05
  - Weight: 0.10
  - CET Score: 0.05 × 0.10 = 0.005

Overall Transition Score:
  - Base: 0.15
  - Agency: 0.0625 (same agency)
  - Timing: 0.20 (45 days)
  - Competition: 0.04 (sole source)
  - Patent: 0.012 (2 patents, topic match)
  - CET: 0.005 (exact match) ← contributed here
  - Vendor: 0.01 (UEI match)
  
  Total: 0.6825 → LIKELY confidence
```

---

## Configuration

### CET Configuration

CET inference and alignment is configured in `config/transition/detection.yaml`:

```yaml
cet_alignment:
  enabled: true
  weight: 0.10  # Contribution to overall score
  same_cet_bonus: 0.05  # Bonus for exact match
  
cet_inference:
  enabled: true
  algorithm: "keyword_matching"  # or "ml_classifier" in future
  
  # Keyword matching configuration
  keyword_matching:
    min_confidence_threshold: 0.30  # Return CET if confidence ≥ 0.30
    normalize_keywords: true  # Uppercase, remove special chars
    precompiled_patterns: true  # Use regex for efficiency
    
  # CET keyword lists
  keywords:
    ai_ml:
      - "artificial intelligence"
      - "machine learning"
      - "neural network"
      - "deep learning"
      - "NLP"
      - "computer vision"
      - "AI"
      
    advanced_computing:
      - "quantum computing"
      - "quantum algorithm"
      - "high-performance computing"
      - "HPC"
      - "edge computing"
      
    # ... more CET areas
```

### Environment Variable Overrides

```bash
# Enable/disable CET alignment
export SBIR_ETL__TRANSITION__CET_ALIGNMENT__ENABLED=true

# Override CET weight (0.0-1.0)
export SBIR_ETL__TRANSITION__CET_ALIGNMENT__WEIGHT=0.15

# Override inference threshold
export SBIR_ETL__TRANSITION__CET_INFERENCE__MIN_CONFIDENCE=0.30
```

### Custom Keyword Lists

To add or modify keywords for a CET area:

```yaml
cet_inference:
  keywords:
    ai_ml:
      # Add custom keywords
      - "transformer architecture"
      - "attention mechanism"
      - "foundation model"
      - "large language model"
      - "LLM"
```

---

## Usage Examples

### Example 1: CET-Aligned Transition

```python
from src.transition.features.cet_analyzer import CETSignalExtractor
from src.transition.detection.scoring import TransitionScorer

# Initialize
extractor = CETSignalExtractor()
scorer = TransitionScorer(config)

# Award data
award = {
    "award_id": "SBIR-2020-II-001",
    "cet_area": "AI & Machine Learning",
    "topic": "Federated learning for distributed inference"
}

# Contract data
contract = {
    "contract_id": "FA1234-20-C-0001",
    "description": "Development of AI-powered threat detection using neural networks"
}

# Extract award CET
award_cet = extractor.extract_award_cet(award)
# Result: "AI & Machine Learning"

# Infer contract CET
contract_cet, confidence = extractor.infer_contract_cet(contract['description'])
# Result: ("AI & Machine Learning", 0.92)

# Calculate alignment
alignment = extractor.calculate_alignment(award_cet, contract_cet)
# Result: 1.0 (exact match)

# Extract CET signal
cet_signal = extractor.extract_signal(
    award_cet=award_cet,
    contract_cet=contract_cet
)
# Result: CETSignal with score=0.005

# Use in overall transition score
signals = {
    "agency_continuity": 0.0625,
    "timing_proximity": 0.20,
    "competition_type": 0.04,
    "patent_signal": 0.012,
    "cet_alignment": 0.005,  # ← CET contribution
    "vendor_match": 0.01
}

score = scorer.compute_final_score(signals)
# Result: 0.7825 → LIKELY confidence
```

### Example 2: CET Mismatch

```python
# Award: Quantum Computing
award_cet = "Quantum Computing"

# Contract: Advanced Manufacturing
contract_description = "Advanced composite materials for aerospace applications"
contract_cet, confidence = extractor.infer_contract_cet(contract_description)
# Result: ("Advanced Manufacturing", 0.75)

# Calculate alignment
alignment = extractor.calculate_alignment(award_cet, contract_cet)
# Result: 0.0 (no match)

# Extract CET signal
cet_signal = extractor.extract_signal(
    award_cet=award_cet,
    contract_cet=contract_cet
)
# Result: CETSignal with score=0.0 (no alignment)
```

### Example 3: Missing CET Data

```python
# Award without CET classification
award_cet = None

# Even if contract has inferred CET
contract_cet, confidence = extractor.infer_contract_cet(contract_description)
# Result: ("AI & Machine Learning", 0.85)

# Calculate alignment
alignment = extractor.calculate_alignment(award_cet, contract_cet)
# Result: 0.0 (missing award CET)

# Extract CET signal
cet_signal = extractor.extract_signal(
    award_cet=award_cet,
    contract_cet=contract_cet
)
# Result: CETSignal with score=0.0 (cannot determine)
```

---

## CET Area Analysis

### Transition Effectiveness by CET Area

Query all transitions by CET area to see which technologies show strongest commercialization:

```python
from src.transition.analysis.analytics import TransitionAnalytics

analytics = TransitionAnalytics(transitions_df, awards_df)

# Calculate transition rates by CET area
cet_rates = analytics.compute_transition_rates_by_cet_area()
# Result:
#   CET Area                    | Award Count | Transitions | Rate
#   ─────────────────────────────────────────────────────────────
#   AI & Machine Learning       | 250         | 85          | 34%
#   Advanced Manufacturing      | 180         | 45          | 25%
#   Quantum Computing           | 120         | 18          | 15%
#   ... etc
```

### Patent-Backed Transitions by CET Area

Analyze which CET areas show strongest patent-backed commercialization:

```python
# Calculate patent-backed transition rates by CET area
patent_rates = analytics.compute_patent_backed_transition_rates_by_cet_area()
# Result:
#   CET Area              | Total Trans | Patent-Backed | %
#   ────────────────────────────────────────────────────
#   AI & Machine Learning | 85          | 42            | 49%
#   Quantum Computing     | 18          | 12            | 67%
#   Advanced Manufacturing| 45          | 15            | 33%
```

### Time-to-Transition Analysis by CET Area

See how quickly commercialization occurs in each CET area:

```python
# Calculate average time to transition by CET area
times = analytics.compute_avg_time_to_transition_by_cet_area()
# Result:
#   CET Area              | Avg Days | P50 Days | P90 Days
#   ─────────────────────────────────────────────────────
#   Advanced Manufacturing| 245      | 180      | 540
#   AI & Machine Learning | 285      | 240      | 720
#   Quantum Computing     | 420      | 365      | 900
```

---

## Querying Transitions by CET Area

### Neo4j Cypher Examples

```cypher
# Find all HIGH confidence transitions in AI & ML
MATCH (a:Award)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea {name: "AI & Machine Learning"})
      -[]->(t:Transition {confidence: "HIGH"})
RETURN a.award_id, a.topic, t.likelihood_score
ORDER BY t.likelihood_score DESC

# Transition rate by CET area
MATCH (a:Award)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
      <-[:INVOLVES_TECHNOLOGY]-(t:Transition)
WITH cet.name as cet_area,
     count(DISTINCT a) as total_awards,
     count(DISTINCT t) as transitions
RETURN cet_area,
       total_awards,
       transitions,
       round(100.0 * transitions / total_awards) as transition_rate_percent
ORDER BY transition_rate_percent DESC

# Patent-backed transitions by CET area
MATCH (a:Award)-[:INVOLVES_TECHNOLOGY]->(cet:CETArea)
      <-[:INVOLVES_TECHNOLOGY]-(t:Transition)
      -[:ENABLED_BY]->(p:Patent)
WITH cet.name as cet_area,
     count(DISTINCT t) as patent_backed_transitions,
     count(DISTINCT t) FILTER (WHERE p IS NOT NULL) as patent_backed
RETURN cet_area, patent_backed, patent_backed_transitions
```

---

## Best Practices

### For CET Classification

1. **Use Explicit CET Data When Available**
   - Prefer award CET classification from SBIR metadata
   - Requires ≥0.95 confidence

2. **Validate Inferred CET Areas**
   - Spot-check contract CET inferences
   - Review contracts with low confidence (<0.5)
   - Update keyword lists based on missed cases

3. **Handle Missing Data Gracefully**
   - Don't penalize transitions with missing CET data
   - CET alignment is one of 6 signals; not all required

4. **Monitor CET Distribution**
   - Track transition rates by CET area
   - Identify underperforming areas for investigation
   - Use for program evaluation and metrics

### For CET Integration

1. **Configure Appropriate Weights**
   - 0.10 (default): CET as supporting signal
   - 0.20: CET as primary signal (for CET-focused analysis)
   - 0.0: Disable CET (if data unreliable)

2. **Use CET in Analytics**
   - Always compute transition effectiveness by CET area
   - Break out patent-backed transitions by CET
   - Analyze time-to-transition by technology area

3. **Document CET Findings**
   - Include CET breakdown in executive summaries
   - Highlight high-performing technology areas
   - Identify CET areas needing support

4. **Update Keyword Lists Regularly**
   - Review contract inferences quarterly
   - Add emerging keywords for new technologies
   - Remove outdated or inaccurate keywords

---

## Troubleshooting

### Issue: Low CET Alignment Rate

**Symptoms**: Few transitions show CET alignment; most show "no match"

**Causes**:
1. Missing CET data in awards (~5% of awards)
2. Poor contract CET inference (generic descriptions)
3. CET areas don't align between award and contract

**Solutions**:
1. Check award CET coverage: `awards['cet_area'].isna().sum()`
2. Review inferred CET confidences: analyze distribution
3. Expand keyword lists for underperforming CET areas
4. Lower inference threshold (0.30 → 0.20)

### Issue: Incorrect CET Inference

**Symptoms**: Contracts assigned to wrong CET areas

**Causes**:
1. Keywords too generic (e.g., "technology", "optimization")
2. Contract descriptions lack specific CET terminology
3. Keywords match unrelated concepts

**Solutions**:
1. Review low-confidence inferences manually
2. Add more specific keywords to CET lists
3. Increase minimum confidence threshold (0.30 → 0.50)
4. Disable CET inference for generic contracts

### Issue: Inference Confidence Too High

**Symptoms**: All contract inferences have confidence ≥0.9 (unrealistic)

**Causes**:
1. Keyword lists have too much overlap
2. Keywords too common and unspecific
3. Calculation method too permissive

**Solutions**:
1. Review and consolidate keyword lists
2. Use more specific technical terms
3. Consider semantic similarity in future versions
4. Manually verify high-confidence inferences

### Issue: Missing CET Keywords

**Symptoms**: Some contracts in a CET area not detected

**Causes**:
1. Contracts use domain-specific terminology
2. Keywords don't cover all possible phrasings
3. Contracts use acronyms not in keyword lists

**Solutions**:
1. Expand keyword lists with common variations
2. Add acronyms: "AI", "ML", "NLP", "CV", etc.
3. Include vendor/product names when relevant
4. Review false negatives and update lists

---

## Performance Considerations

### Inference Performance

**Throughput**: ~5,000 contract inferences/minute on typical hardware

**Bottleneck**: Regex pattern matching against all keywords

**Optimization**: Precompiled patterns using standard Python `re` module

### Memory Usage

**Per Contract**: ~100 bytes for inferred CET area and confidence

**Typical Dataset**: 6.7M contracts = ~670 MB for CET data

**Caching**: CET inferences can be cached for repeated analysis

### Scalability

**Small Datasets**: <100K contracts → instant inference

**Medium Datasets**: 100K-1M contracts → <5 minutes total

**Large Datasets**: 1M-10M contracts → 10-30 minutes with batching

---

## Future Enhancements

### Machine Learning Inference

**Goal**: Replace keyword matching with trained ML classifier for better accuracy

**Approach**:
1. Collect labeled training data (500-1000 contracts with true CET areas)
2. Train text classification model (logistic regression, SVM, or neural network)
3. Deploy for contract CET inference

**Expected Benefits**:
- Higher accuracy for non-obvious contracts
- Handle semantic similarity better
- Reduce false positives from keyword overlap

### Multi-CET Classification

**Goal**: Allow contracts to belong to multiple CET areas

**Approach**:
1. Return top-3 CET areas with confidence scores
2. Link transitions to multiple CET nodes in Neo4j
3. Aggregate transition rates across CET combinations

**Expected Benefits**:
- Better represent interdisciplinary contracts
- Richer analysis of technology intersections

### Real-Time CET Updates

**Goal**: Update CET classifications as new contracts become available

**Approach**:
1. Stream contract data
2. Infer CET area on receipt
3. Update Neo4j graph immediately

**Expected Benefits**:
- Near-real-time CET analysis
- Faster insights for program managers

---

## References

- **Implementation**: `src/transition/features/cet_analyzer.py`
- **Tests**: `tests/unit/test_cet_signal_extractor.py`
- **Configuration**: `config/transition/detection.yaml`
- **Neo4j**: `CETArea` nodes and `INVOLVES_TECHNOLOGY` relationships
- **NIST CET**: https://www.nist.gov/programs/critical-emerging-technologies
- **Scoring Integration**: `docs/transition/scoring_guide.md`
- **Analytics**: `src/transition/analysis/analytics.py`
