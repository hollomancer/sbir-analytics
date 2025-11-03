# Configuration - Transition Detection Delta

## ADDED Requirements

### Requirement: Transition Detection Configuration

The system SHALL externalize transition detection parameters in YAML format to enable algorithm tuning without code changes.

#### Scenario: Load detection configuration

- **WHEN** the system starts or reloads configuration
- **THEN** it loads config/transition/detection.yaml
- **AND** parses scoring weights, thresholds, timing windows
- **AND** validates required fields
- **AND** builds in-memory detection configuration

#### Scenario: Define scoring weights

- **WHEN** configuring scoring weights in detection.yaml
- **THEN** the configuration includes:

  ```yaml
  scoring:
    weights:
      base_score: 0.15
      agency_continuity:
        same_agency: 0.25
        cross_service: 0.125  # 50% of same_agency
      timing_proximity: 0.15
      competition_type:
        sole_source: 0.20
        limited_competition: 0.10
      patent_signals:
        has_patent: 0.05
        filed_before_contract: 0.03
        topic_similarity: 0.02
      cet_alignment: 0.05
      text_similarity: 0.10  # Optional, if enabled
  ```

- **AND** weights are validated to sum ≤ 1.0

#### Scenario: Define confidence thresholds

- **WHEN** configuring confidence classification thresholds
- **THEN** the configuration includes:

  ```yaml
  thresholds:
    high_confidence: 0.85
    likely_confidence: 0.65
    # Scores ≥0.85: "High"
    # Scores 0.65-0.84: "Likely"
    # Scores <0.65: "Possible" (excluded by default)
  ```

#### Scenario: Define timing windows

- **WHEN** configuring timing parameters
- **THEN** the configuration includes:

  ```yaml
  timing:
    window_months: 24  # 0-24 months after SBIR completion
    scoring_bands:
      immediate:
        max_months: 3
        score_factor: 1.0
      short_term:
        max_months: 12
        score_factor: 0.75
      medium_term:
        max_months: 24
        score_factor: 0.5
      excluded:
        max_months: 999
        score_factor: 0.0  # >24 months excluded
  ```

### Requirement: Detection Presets

The system SHALL support multiple pre-configured detection presets optimized for different use cases.

#### Scenario: High-precision preset

- **WHEN** using "high-precision" preset
- **THEN** config/transition/presets.yaml includes:

  ```yaml
  high_precision:
    description: "Minimize false positives, maximize precision"
    thresholds:
      high_confidence: 0.90
      likely_confidence: 0.80
    timing:
      window_months: 18  # Stricter window
    vendor:
      fuzzy_threshold: 0.95  # Stricter name matching
    filters:
      exclude_possible: true
      require_sole_source_or_patent: true
  ```

- **AND** enables analyst-approved detections only

#### Scenario: Broad-discovery preset

- **WHEN** using "broad-discovery" preset
- **THEN** the configuration includes:

  ```yaml
  broad_discovery:
    description: "Maximize recall, find all potential transitions"
    thresholds:
      high_confidence: 0.70
      likely_confidence: 0.50
    timing:
      window_months: 36  # Extended window
    vendor:
      fuzzy_threshold: 0.85  # Looser name matching
    filters:
      exclude_possible: false
      include_cross_agency: true
  ```

- **AND** produces more detections for exploratory analysis

#### Scenario: Balanced preset (default)

- **WHEN** using default "balanced" preset
- **THEN** the configuration includes:

  ```yaml
  balanced:
    description: "Balance precision and recall"
    thresholds:
      high_confidence: 0.85
      likely_confidence: 0.65
    timing:
      window_months: 24
    vendor:
      fuzzy_threshold: 0.90
    filters:
      exclude_possible: true
      include_cross_service: true
  ```

### Requirement: Vendor Matching Configuration

The system SHALL externalize vendor resolution parameters to enable identifier priority and fuzzy matching tuning.

#### Scenario: Configure identifier priority

- **WHEN** configuring vendor matching
- **THEN** the configuration specifies:

  ```yaml
  vendor_matching:
    identifier_priority:

      - type: "uei"

        confidence: 0.99
        enabled: true

      - type: "cage"

        confidence: 0.95
        enabled: true

      - type: "duns"

        confidence: 0.90
        enabled: true

      - type: "name_fuzzy"

        confidence: 0.90  # Threshold for similarity
        enabled: true
  ```

#### Scenario: Configure name normalization

- **WHEN** configuring fuzzy name matching
- **THEN** the configuration includes:

  ```yaml
  vendor_matching:
    name_normalization:
      remove_suffixes: ["INC", "LLC", "CORP", "CORPORATION", "LTD"]
      remove_words: ["THE", "A", "AN"]
      lowercase: true
      remove_punctuation: true
    fuzzy_threshold: 0.90
    fuzzy_algorithm: "token_sort_ratio"  # RapidFuzz method
  ```

### Requirement: CET Integration Configuration

The system SHALL support optional CET integration with graceful degradation when CET module is unavailable.

#### Scenario: Enable CET integration

- **WHEN** CET classification module is available
- **THEN** the configuration includes:

  ```yaml
  cet_integration:
    enabled: true
    cet_alignment_weight: 0.05
    infer_contract_cet: true  # Use keyword matching on contract description
    contract_cet_keywords_path: "config/transition/contract_cet_keywords.yaml"
  ```

#### Scenario: Disable CET integration

- **WHEN** CET classification module is not available
- **THEN** cet_integration.enabled = false
- **AND** the system skips CET signal extraction
- **AND** transitions are detected without CET scoring component
- **AND** no INVOLVES_TECHNOLOGY relationships created

#### Scenario: Partial CET integration

- **WHEN** awards have CET classifications but contract CET inference disabled
- **THEN** cet_integration.infer_contract_cet = false
- **AND** the system tracks award CET only
- **AND** does not calculate cet_alignment score

### Requirement: Patent Integration Configuration

The system SHALL support optional patent integration with configurable signal weights.

#### Scenario: Enable patent signals

- **WHEN** USPTO patent module is available
- **THEN** the configuration includes:

  ```yaml
  patent_integration:
    enabled: true
    weights:
      has_patent: 0.05
      filed_before_contract: 0.03
      topic_similarity: 0.02
    topic_similarity_threshold: 0.70
    max_filing_lag_days: 730  # 2 years
  ```

#### Scenario: Disable patent signals

- **WHEN** patent data is unavailable
- **THEN** patent_integration.enabled = false
- **AND** the system skips patent signal extraction
- **AND** transitions are detected without patent scoring component
- **AND** no ENABLED_BY relationships created

### Requirement: Performance Configuration

The system SHALL externalize performance tuning parameters for batch processing and database operations.

#### Scenario: Configure batch sizes

- **WHEN** configuring processing parameters
- **THEN** the configuration includes:

  ```yaml
  performance:
    detection_batch_size: 1000  # Awards processed per batch
    neo4j_batch_size: 1000  # Nodes/relationships per transaction
    contract_chunk_size: 100000  # Contracts loaded per chunk (14GB dataset)
    max_workers: 4  # Parallel workers for vendor matching
  ```

#### Scenario: Configure caching

- **WHEN** enabling performance optimizations
- **THEN** the configuration includes:

  ```yaml
  performance:
    caching:
      vendor_cache_enabled: true
      vendor_cache_size: 10000  # LRU cache for vendor matches
      patent_cache_enabled: true
      patent_cache_size: 5000  # LRU cache for patent lookups
  ```

### Requirement: Analytics Configuration

The system SHALL configure analytics parameters for dual-perspective and CET area metrics.

#### Scenario: Configure analytics thresholds

- **WHEN** defining success criteria
- **THEN** the configuration includes:

  ```yaml
  analytics:
    company_success_threshold: 2  # ≥2 transitions = sustained commercialization
    high_performing_company_threshold:
      min_transitions: 5
      min_success_rate: 0.60
    cet_area_analysis:
      enabled: true
      include_patent_metrics: true
      include_timing_metrics: true
  ```

#### Scenario: Configure reporting

- **WHEN** configuring output formats
- **THEN** the configuration includes:

  ```yaml
  analytics:
    reporting:
      generate_award_level: true
      generate_company_level: true
      generate_cet_level: true
      generate_agency_level: true
      output_formats: ["csv", "json", "yaml"]
  ```

### Requirement: Environment Variable Overrides

The system SHALL support overriding configuration via environment variables for deployment flexibility.

#### Scenario: Override confidence thresholds

- **WHEN** environment variable TRANSITION_HIGH_CONFIDENCE=0.90 is set
- **THEN** the system overrides high_confidence threshold from 0.85 to 0.90
- **AND** applies override without modifying YAML files

#### Scenario: Override timing window

- **WHEN** TRANSITION_TIMING_WINDOW_MONTHS=36 is set
- **THEN** the system extends timing window from 24 to 36 months

#### Scenario: Enable/disable modules

- **WHEN** TRANSITION_PATENT_ENABLED=false is set
- **THEN** the system disables patent integration
- **AND** skips patent signal extraction

### Requirement: Configuration Validation

The system SHALL validate all transition configuration files on startup to catch errors early.

#### Scenario: Validate scoring weights

- **WHEN** loading detection.yaml
- **THEN** the system validates:
  - All weights are positive floats
  - Weights sum to ≤ 1.0
  - Required weight categories present (agency, timing, competition)
  - Optional weights (patent, cet) can be 0.0 if disabled

#### Scenario: Validate thresholds

- **WHEN** loading thresholds configuration
- **THEN** the system validates:
  - 0.0 ≤ likely_confidence < high_confidence ≤ 1.0
  - Thresholds are non-overlapping
  - At least one threshold is defined

#### Scenario: Fail fast on invalid configuration

- **WHEN** configuration has invalid values
- **THEN** the system raises ConfigurationError during startup
- **AND** error message specifies the invalid field and expected format
- **AND** prevents application from starting with bad configuration

### Requirement: Configuration Documentation

The system SHALL provide comprehensive documentation for all transition configuration options.

#### Scenario: Document detection parameters

- **WHEN** users need to understand detection configuration
- **THEN** config/transition/README.md provides:
  - Complete parameter reference with descriptions
  - Example configurations for common scenarios
  - Scoring weight impact analysis
  - Threshold tuning guidance
  - Preset selection recommendations

#### Scenario: Document preset selection guide

- **WHEN** users need to choose a detection preset
- **THEN** documentation provides:
  - Use case descriptions for each preset
  - Precision/recall trade-offs
  - Expected detection counts
  - Recommended manual review workflows
  - Performance implications

#### Scenario: Document vendor matching configuration

- **WHEN** users need to tune vendor matching
- **THEN** documentation provides:
  - Identifier priority rationale
  - Fuzzy threshold impact on match rate
  - Name normalization rules
  - Common vendor matching issues and solutions
