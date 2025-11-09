# Requirements Document

## Introduction

The SBIR Transition Detection Module enables comprehensive analysis of technology transition from SBIR awards to follow-on government contracts, commercial products, and technology adoption. This system addresses the critical need to measure SBIR program effectiveness by detecting successful transitions, tracking patent-backed commercialization, and providing evidence-based scoring with complete audit trails.

The system implements multi-signal scoring, vendor resolution across datasets, and dual-perspective analytics to measure program effectiveness at both award and company levels. This capability enables stakeholders to identify successful SBIR investments, understand commercialization patterns, track the full innovation lifecycle, and validate transition claims with concrete evidence.

## Glossary

- **Transition_Detection_System**: The SBIR transition detection module that identifies technology transitions from awards to contracts
- **Vendor_Resolution_Engine**: Component that matches vendors across datasets using UEI, CAGE, DUNS, and fuzzy name matching
- **Multi_Signal_Scorer**: Component that calculates transition likelihood using agency, timing, competition, patent, and CET signals
- **Evidence_Bundle**: Structured audit trail containing all supporting evidence for a detected transition
- **Confidence_Level**: Classification of transition detection quality (High ≥0.85, Likely ≥0.65, Possible <0.65)
- **Technology_Transition**: Event where SBIR-funded research leads to follow-on contracts, products, or adoption
- **Patent_Signal**: Indicator of technology transfer based on patent filings between award completion and contract start
- **CET_Area**: Critical and Emerging Technology classification for technology alignment analysis
- **Transition_Profile**: Company-level aggregation of transition success metrics and effectiveness measures

## Requirements

### Requirement 1: Core Transition Detection

**User Story:** As a program analyst, I want to detect technology transitions from SBIR awards to follow-on contracts, so that I can measure program effectiveness and identify successful commercialization patterns.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL detect transitions between SBIR awards and federal contracts with likelihood scores between 0.0 and 1.0
2. WHEN processing award and contract datasets, THE Transition_Detection_System SHALL achieve detection throughput of at least 10,000 detections per minute
3. THE Transition_Detection_System SHALL classify each detection with confidence levels of High, Likely, or Possible based on configurable thresholds
4. THE Transition_Detection_System SHALL generate evidence bundles for 100% of detections with likelihood scores above 0.60
5. THE Transition_Detection_System SHALL maintain data retention rate of at least 97.9% during processing

### Requirement 2: Vendor Resolution and Matching

**User Story:** As a data analyst, I want to match vendors across SBIR and contract datasets using multiple identifiers, so that I can accurately link awards to follow-on contracts despite identifier variations.

#### Acceptance Criteria

1. THE Vendor_Resolution_Engine SHALL match vendors using UEI, CAGE, DUNS, and fuzzy name matching with priority-based fallback
2. WHEN exact UEI matches are available, THE Vendor_Resolution_Engine SHALL assign confidence score of 0.99
3. WHEN fuzzy name matching is required, THE Vendor_Resolution_Engine SHALL achieve minimum similarity threshold of 0.85 for primary matches
4. THE Vendor_Resolution_Engine SHALL achieve vendor match rate of at least 90% for SBIR recipients in contract datasets
5. THE Vendor_Resolution_Engine SHALL track match method and confidence score for each vendor resolution

### Requirement 3: Multi-Signal Scoring

**User Story:** As a researcher, I want transition likelihood calculated using multiple evidence signals, so that I can trust the accuracy and completeness of transition detections.

#### Acceptance Criteria

1. THE Multi_Signal_Scorer SHALL calculate composite scores using agency continuity, timing proximity, competition type, patent signals, and CET alignment
2. THE Multi_Signal_Scorer SHALL apply configurable weights for each signal type with default agency weight of 0.25
3. WHEN awards and contracts share the same agency, THE Multi_Signal_Scorer SHALL apply agency continuity bonus of 0.25
4. WHEN contracts occur within 24 months of award completion, THE Multi_Signal_Scorer SHALL apply timing proximity scoring with maximum multiplier of 1.0 for 0-3 month window
5. THE Multi_Signal_Scorer SHALL support configuration of signal weights and thresholds via YAML configuration files

### Requirement 4: Patent-Based Transition Signals

**User Story:** As a technology transfer analyst, I want to identify patent-backed transitions, so that I can track intellectual property commercialization from SBIR research.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL identify patents filed between SBIR completion and contract start dates
2. WHEN patents exist for transition candidates, THE Multi_Signal_Scorer SHALL calculate patent signal contribution with weight of 0.15
3. THE Transition_Detection_System SHALL detect technology transfer when patent assignees differ from SBIR recipients
4. THE Transition_Detection_System SHALL calculate patent-contract topic similarity using TF-IDF with minimum threshold of 0.7
5. THE Evidence_Bundle SHALL include patent filing dates, assignee information, and topic similarity scores for patent-backed transitions

### Requirement 5: CET Area Analysis

**User Story:** As a policy analyst, I want to analyze transitions by Critical and Emerging Technology areas, so that I can assess program effectiveness across strategic technology domains.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL classify awards and contracts by CET areas using keyword matching and ML classification
2. WHEN award and contract CET areas match exactly, THE Multi_Signal_Scorer SHALL apply CET alignment bonus of 0.05
3. THE Transition_Detection_System SHALL calculate transition rates by CET area with minimum sample size of 10 awards per area
4. THE Transition_Detection_System SHALL identify patent-backed transition rates by CET area for technology transfer analysis
5. THE Transition_Detection_System SHALL calculate average time-to-transition by CET area when contract dates are available

### Requirement 6: Evidence and Audit Trail

**User Story:** As a program evaluator, I want comprehensive evidence for each transition detection, so that I can validate findings and understand the basis for transition scores.

#### Acceptance Criteria

1. THE Evidence_Bundle SHALL contain structured evidence for agency signals, timing signals, competition signals, patent signals, CET signals, and vendor matching
2. THE Evidence_Bundle SHALL include contract details with PIID, agency, amount, and start date for each detection
3. THE Evidence_Bundle SHALL serialize to JSON format for storage on Neo4j relationships
4. THE Evidence_Bundle SHALL validate completeness with required fields present and score ranges between 0.0 and 1.0
5. THE Transition_Detection_System SHALL generate evidence bundles with processing time under 100 milliseconds per detection

### Requirement 7: Analytics and Reporting

**User Story:** As an executive stakeholder, I want dual-perspective analytics on transition effectiveness, so that I can understand both individual award success and company-level commercialization capability.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL calculate award-level transition rate as transitioned awards divided by total awards
2. THE Transition_Detection_System SHALL calculate company-level transition rate as companies with transitions divided by total companies
3. THE Transition_Detection_System SHALL compare Phase I versus Phase II transition effectiveness with separate rate calculations
4. THE Transition_Detection_System SHALL calculate transition rates by agency with minimum sample size of 50 awards per agency
5. THE Transition_Detection_System SHALL generate executive summary reports in markdown format with key insights and recommendations

### Requirement 8: Graph Database Integration

**User Story:** As a data scientist, I want transition data stored in Neo4j graph format, so that I can perform complex pathway analysis and relationship queries.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL create Transition nodes with properties for transition_id, likelihood_score, confidence, and detection_date
2. THE Transition_Detection_System SHALL create TRANSITIONED_TO relationships between Award and Transition nodes with evidence bundles
3. THE Transition_Detection_System SHALL create RESULTED_IN relationships between Transition and Contract nodes
4. WHEN patent signals exist, THE Transition_Detection_System SHALL create ENABLED_BY relationships between Transition and Patent nodes
5. THE Transition_Detection_System SHALL create TransitionProfile nodes with company-level aggregation metrics including success_rate and avg_likelihood_score

### Requirement 9: Performance and Quality

**User Story:** As a system administrator, I want the transition detection system to meet performance and quality targets, so that it can process large datasets efficiently and reliably.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL process at least 10,000 detections per minute on standard hardware
2. THE Transition_Detection_System SHALL achieve precision of at least 85% and recall of at least 70% when validated against ground truth
3. THE Transition_Detection_System SHALL complete processing with memory usage under 4GB for datasets up to 100,000 awards
4. THE Transition_Detection_System SHALL validate data quality with configurable gates for vendor match rate and detection success rate
5. THE Transition_Detection_System SHALL provide progress logging and metrics tracking for monitoring and debugging

### Requirement 10: Configuration and Deployment

**User Story:** As a DevOps engineer, I want flexible configuration and deployment options, so that I can adapt the system for different environments and use cases.

#### Acceptance Criteria

1. THE Transition_Detection_System SHALL support configuration via YAML files with environment-specific overrides
2. THE Transition_Detection_System SHALL accept environment variable overrides using SBIR_ETL__TRANSITION__ prefix
3. THE Transition_Detection_System SHALL provide preset configurations for high-precision, balanced, and broad-discovery modes
4. THE Transition_Detection_System SHALL integrate with Dagster pipeline orchestration as materialized assets
5. THE Transition_Detection_System SHALL include comprehensive documentation for deployment, configuration, and troubleshooting
