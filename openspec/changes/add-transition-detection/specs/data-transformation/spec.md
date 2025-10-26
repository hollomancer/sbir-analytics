# Data Transformation - Transition Detection Delta

## ADDED Requirements

### Requirement: Vendor Identity Resolution

The system SHALL resolve vendor identity across SBIR awards and federal contracts using multi-identifier cross-walk to enable accurate transition detection.

#### Scenario: Exact UEI match

- **WHEN** an SBIR award has UEI="ABC123XYZ" and a contract has UEI="ABC123XYZ"
- **THEN** the system matches vendors with method="uei_exact" and confidence=0.99
- **AND** stores the matched identifier for audit trail

#### Scenario: CAGE code fallback

- **WHEN** an SBIR award has no UEI but has CAGE="1A2B3"
- **AND** a contract has CAGE="1A2B3"
- **THEN** the system matches vendors with method="cage_exact" and confidence=0.95

#### Scenario: Fuzzy name matching

- **WHEN** an SBIR award recipient is "International Business Machines Corp"
- **AND** a contract recipient is "IBM Corporation"
- **THEN** the system normalizes both names
- **AND** calculates fuzzy similarity = 0.92
- **AND** matches if similarity ≥ 0.90 with method="name_fuzzy" and confidence=0.92

#### Scenario: No match found

- **WHEN** no identifier matches and name similarity < 0.90
- **THEN** the system returns None (no vendor match)
- **AND** logs the failed match attempt for review queue

### Requirement: Transition Likelihood Scoring

The system SHALL calculate likelihood scores for award-contract pairs using weighted multi-signal scoring algorithm.

#### Scenario: High-confidence transition (sole source, same agency, immediate)

- **WHEN** evaluating an award-contract pair with signals:
  - same_agency=true
  - sole_source=true
  - days_after_completion=45
  - has_patent=true
  - patent_filed_before_contract=true
- **THEN** the system calculates composite score:
  - Base: 0.15
  - Agency: 0.25
  - Timing: 0.15 × 1.0 = 0.15 (immediate)
  - Competition: 0.20 (sole source)
  - Patent: 0.05 + 0.03 = 0.08
  - Total: 0.83
- **AND** classifies as confidence="Likely" (≥0.65 but <0.85)

#### Scenario: Highest-confidence transition (all signals strong)

- **WHEN** evaluating with signals:
  - same_agency=true
  - sole_source=true
  - days_after_completion=30
  - has_patent=true
  - patent_filed_before_contract=true
  - patent_topic_similarity=0.85
  - award_cet_id = contract_cet_id (inferred)
- **THEN** total score = 0.15 + 0.25 + 0.15 + 0.20 + 0.10 + 0.05 = 0.90
- **AND** classifies as confidence="High" (≥0.85)

#### Scenario: Low-confidence transition (cross-agency, full competition, late)

- **WHEN** evaluating with signals:
  - same_agency=false (but same department)
  - full_competition=true
  - days_after_completion=680 (22 months)
  - has_patent=false
- **THEN** total score = 0.15 + 0.125 + 0.08 = 0.355
- **AND** classifies as confidence="Possible" (<0.65)

#### Scenario: Outside timing window

- **WHEN** contract starts 780 days after SBIR completion (>24 months)
- **THEN** timing_score = 0.0
- **AND** detection is excluded from results

### Requirement: Evidence Bundle Generation

The system SHALL generate comprehensive evidence bundles for all transition detections to support validation and audit.

#### Scenario: Complete evidence bundle

- **WHEN** detecting a transition with all available signals
- **THEN** the evidence bundle includes:
  - detection_id (UUID)
  - sbir_award_id, contract_piid
  - likelihood_score, confidence classification
  - agency_signals (same_agency, agencies, score contribution)
  - timing_signals (dates, days_after_completion, timing_score)
  - competition_signals (competition_type, score contribution)
  - patent_signals (if applicable: patents, filing dates, similarity)
  - cet_signals (if applicable: CET areas, alignment, score)
  - vendor_match (method, confidence, matched_on)
  - contract_details (PIID, agency, amount, start_date)
  - detection_date, detection_version
- **AND** evidence bundle serializes to JSON (≤2KB)

#### Scenario: Patent-backed transition evidence

- **WHEN** a transition includes patent signals
- **THEN** patent_signals includes:
  - has_patent=true
  - patent_count=2
  - patent_numbers=["5858003", "6123456"]
  - patent_filed_before_contract=true
  - patent_filing_lag_days=245
  - patent_topic_similarity=0.82
  - patent_score=0.10
- **AND** evidence links to Patent nodes via grant_doc_num

### Requirement: Patent Signal Extraction

The system SHALL extract patent-based transition signals when patents exist between SBIR completion and contract start.

#### Scenario: Identify relevant patents

- **WHEN** an SBIR award completes on 2020-06-30
- **AND** a contract starts on 2021-09-15
- **AND** patents filed: 2019-01-15 (before), 2020-10-22 (between), 2022-03-10 (after)
- **THEN** the system identifies patent 2020-10-22 as relevant
- **AND** excludes patents filed before completion or after contract start

#### Scenario: Calculate patent timing signals

- **WHEN** relevant patent filed 2020-10-22 (114 days after SBIR completion)
- **AND** contract starts 2021-09-15 (328 days after patent filing)
- **THEN** patent_filing_lag_days=114
- **AND** patent_filed_before_contract=true
- **AND** contributes +0.03 to transition score

#### Scenario: Calculate patent topic similarity

- **WHEN** SBIR abstract contains "machine learning algorithms for autonomous vehicle perception"
- **AND** patent title+abstract contains "deep neural network system for real-time object detection in autonomous driving"
- **THEN** the system calculates TF-IDF similarity=0.87
- **AND** patent_topic_similarity ≥ 0.7 threshold
- **AND** contributes +0.02 to transition score

### Requirement: CET Area Transition Tracking

The system SHALL track transition rates by Critical and Emerging Technology areas to measure technology-specific effectiveness.

#### Scenario: Link award CET to transition

- **WHEN** an award is classified with primary_cet_id="artificial_intelligence"
- **AND** the award transitions to a contract
- **THEN** the system associates the transition with CET area "Artificial Intelligence"
- **AND** tracks this transition in CET area metrics

#### Scenario: Calculate CET area transition rate

- **WHEN** calculating transition metrics for "Quantum Computing" CET area
- **AND** there are 2,156 quantum computing awards
- **AND** 1,298 of those awards transitioned (detected)
- **THEN** transition_rate = 1,298 / 2,156 = 0.602 (60.2%)
- **AND** compares to overall transition rate of 69.0%
- **AND** identifies Quantum as underperforming

#### Scenario: Track patent-backed transitions by CET

- **WHEN** analyzing "Artificial Intelligence" CET area
- **AND** 11,234 AI awards transitioned
- **AND** 4,718 transitions included patent signals
- **THEN** patent_backed_rate = 4,718 / 11,234 = 0.42 (42%)
- **AND** provides insight into IP protection strategies by technology

### Requirement: Dual-Perspective Analytics

The system SHALL calculate both award-level and company-level transition metrics to provide tactical and strategic views of success.

#### Scenario: Award-level transition rate

- **WHEN** analyzing 252,025 SBIR awards
- **AND** 173,897 awards have detected transitions
- **THEN** award_level_transition_rate = 173,897 / 252,025 = 0.690 (69.0%)
- **AND** reports this as individual award success metric

#### Scenario: Company-level sustained commercialization rate

- **WHEN** analyzing 33,583 companies with SBIR awards
- **AND** 2,653 companies have ≥2 transitions
- **THEN** company_level_success_rate = 2,653 / 33,583 = 0.079 (7.9%)
- **AND** reports this as sustained commercialization capability

#### Scenario: Phase effectiveness comparison

- **WHEN** calculating transition rates by phase
- **THEN** Phase I transition rate = 65.9%
- **AND** Phase II transition rate = 74.1%
- **AND** Phase II advantage = 74.1% - 65.9% = 8.2 percentage points
- **AND** validates that Phase II awards are more likely to transition

### Requirement: Configurable Detection Parameters

The system SHALL support configurable transition detection parameters via YAML to enable algorithm tuning without code changes.

#### Scenario: High-precision preset

- **WHEN** using "high-precision" detection preset
- **THEN** high_confidence_threshold = 0.90
- **AND** likely_confidence_threshold = 0.80
- **AND** timing_window_months = 18
- **AND** vendor_fuzzy_threshold = 0.95
- **AND** produces fewer detections with higher precision

#### Scenario: Broad-discovery preset

- **WHEN** using "broad-discovery" detection preset
- **THEN** high_confidence_threshold = 0.70
- **AND** likely_confidence_threshold = 0.50
- **AND** timing_window_months = 36
- **AND** vendor_fuzzy_threshold = 0.85
- **AND** produces more detections with higher recall

#### Scenario: Custom scoring weights

- **WHEN** adjusting scoring weights in configuration
- **THEN** agency_weight, timing_weight, competition_weight, patent_weight, cet_weight can be modified
- **AND** weights sum to ≤1.0
- **AND** enables experimentation with signal importance
