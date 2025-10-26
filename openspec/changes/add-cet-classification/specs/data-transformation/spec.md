# Data Transformation - CET Classification Delta

## ADDED Requirements

### Requirement: CET Award Classification

The system SHALL classify SBIR awards against 21 Critical and Emerging Technology (CET) areas using machine learning with evidence-based explainability.

#### Scenario: Classify award with high confidence

- **WHEN** processing an award with abstract="Advanced neural network development for autonomous vehicle perception..."
- **THEN** the system classifies the award with primary CET area="artificial_intelligence"
- **AND** score=85, classification="High"
- **AND** supporting CET areas include ["autonomous_systems", "advanced_communications"]
- **AND** evidence statements (up to 3) contain relevant sentences with keyword highlights

#### Scenario: Extract supporting evidence

- **WHEN** classifying an award against CET area "artificial_intelligence"
- **THEN** the system extracts up to 3 sentences containing CET keywords
- **AND** each evidence statement includes:
  - excerpt (≤50 words)
  - source_location ("abstract", "keywords", or "solicitation")
  - rationale_tag (e.g., "Contains: neural network, machine learning")

#### Scenario: Handle low-confidence classifications

- **WHEN** an award has unclear or multi-disciplinary technology focus (score <40)
- **THEN** the system assigns classification="Low"
- **AND** may assign primary CET area="uncategorized"
- **AND** logs the award for potential manual review

#### Scenario: Batch classification for efficiency

- **WHEN** classifying 10,000 awards
- **THEN** the system processes awards in batches of 1,000
- **AND** vectorizes text in batch for TF-IDF efficiency
- **AND** achieves throughput ≥1,000 awards/second
- **AND** average per-award latency ≤1 second

### Requirement: Company CET Aggregation

The system SHALL aggregate CET classifications from all awards to generate company-level CET specialization profiles.

#### Scenario: Calculate dominant CET area

- **WHEN** a company has received 5 AI awards (avg score 80), 2 Cybersecurity awards (avg score 65), 1 Quantum award (score 50)
- **THEN** the system identifies dominant CET area="artificial_intelligence"
- **AND** calculates specialization_score = 5 / 8 = 0.625 (62.5% concentration)

#### Scenario: Track CET evolution over time

- **WHEN** a company received Phase I AI awards in 2020, Phase II AI+Cybersecurity awards in 2022, Phase III Cybersecurity awards in 2024
- **THEN** the system tracks CET progression: AI → AI+Cybersecurity → Cybersecurity
- **AND** stores first_award_date and last_award_date per CET area
- **AND** identifies CET pivot or expansion patterns

#### Scenario: Calculate company-CET metrics

- **WHEN** aggregating company CET profile
- **THEN** the system calculates per-CET metrics:
  - award_count (number of awards in CET)
  - total_funding (sum of award amounts in CET)
  - avg_score (average CET classification score)
  - dominant_phase ("I", "II", "III", or "Mixed")

### Requirement: Patent CET Classification

The system SHALL classify patents based on title and assignee entity context to enable technology transition tracking.

#### Scenario: Classify patent from title

- **WHEN** classifying a patent with title="Systems and Methods for Quantum Error Correction in Superconducting Qubits"
- **THEN** the system classifies with primary CET area="quantum_computing"
- **AND** score ≥70 (high confidence)
- **AND** extracts evidence from title

#### Scenario: Validate with USPTO AI predictions

- **WHEN** classifying a patent with grant_doc_num="10000002"
- **AND** USPTO AI dataset has predict93_any_ai=1 (high confidence AI patent)
- **THEN** the system checks if CET classification aligns with USPTO prediction
- **AND** if CET area="artificial_intelligence" and score ≥70, validation status="ALIGNED"
- **AND** if CET area ≠ "artificial_intelligence" or score <70, validation status="MISALIGNED"
- **AND** logs validation metrics for model improvement

#### Scenario: Track technology transition alignment

- **WHEN** a patent originates from an SBIR award (Award → FUNDED → Patent)
- **THEN** the system compares award CET area with patent CET area
- **AND** calculates cet_alignment = (award_primary_cet == patent_primary_cet)
- **AND** tracks transition_score = max(award_score, patent_score) if aligned, else average of both
- **AND** enables queries for successful technology transitions

### Requirement: CET Confidence Scoring

The system SHALL provide multi-threshold confidence scoring (High/Medium/Low) based on calibrated probability estimates.

#### Scenario: Three-band confidence classification

- **WHEN** the ML model outputs probability=0.85 for CET area="artificial_intelligence"
- **THEN** the system converts to score=85
- **AND** classification="High" (score ≥70)

- **WHEN** probability=0.55
- **THEN** score=55, classification="Medium" (40 ≤ score <70)

- **WHEN** probability=0.30
- **THEN** score=30, classification="Low" (score <40)

#### Scenario: Calibrated probability scores

- **WHEN** training the CET classifier
- **THEN** the system applies sigmoid calibration with 3-fold cross-validation
- **AND** ensures probabilities are well-calibrated (reliability diagram within acceptable bounds)
- **AND** enables threshold adjustment without retraining

### Requirement: CET Taxonomy Versioning

The system SHALL support multiple CET taxonomy versions to enable longitudinal analysis and taxonomy evolution.

#### Scenario: Version all classifications

- **WHEN** classifying an award on 2025-10-26 using NSTC-2025Q1 taxonomy
- **THEN** the classification stores taxonomy_version="NSTC-2025Q1"
- **AND** classified_at=datetime("2025-10-26T12:00:00Z")

#### Scenario: Reclassify with new taxonomy

- **WHEN** NSTC releases updated taxonomy (NSTC-2025Q2) with new CET area "Synthetic Biology"
- **THEN** the system provides reclassification job
- **AND** preserves historical classifications with old taxonomy_version
- **AND** generates new classifications with taxonomy_version="NSTC-2025Q2"
- **AND** enables comparison across taxonomy versions

#### Scenario: Handle taxonomy changes

- **WHEN** a CET category is renamed (e.g., "Semiconductors" → "Semiconductors & Microelectronics")
- **THEN** the system tracks category lineage
- **AND** provides mapping from old to new category IDs
- **AND** updates visualizations and queries to use new names while preserving historical data
