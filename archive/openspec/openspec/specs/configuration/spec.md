# configuration Specification

## Purpose

TBD - created by archiving change add-initial-architecture. Update Purpose after archive.

## Requirements


### Requirement: Three-Layer Configuration System

The system SHALL implement a three-layer configuration architecture: YAML files, Pydantic validation, and environment variable overrides.

#### Scenario: Base configuration loading

- **WHEN** the system starts
- **THEN** it SHALL load the base configuration from `config/base.yaml`
- **AND** the configuration SHALL be parsed successfully

#### Scenario: Environment-specific overrides

- **WHEN** an environment is specified (dev, staging, prod)
- **THEN** the system SHALL load the environment-specific YAML file (e.g., `config/prod.yaml`)
- **AND** values from the environment file SHALL override base configuration values

#### Scenario: Environment variable overrides

- **WHEN** environment variables with prefix `SBIR_ETL__` are set
- **THEN** those values SHALL override YAML configuration values
- **AND** nested paths SHALL be supported using double underscores (e.g., `SBIR_ETL__DATA_QUALITY__MAX_DUPLICATE_RATE`)

### Requirement: Type-Safe Configuration Validation

The system SHALL validate all configuration using Pydantic schemas to ensure type safety and catch errors at startup.

#### Scenario: Valid configuration

- **WHEN** configuration is loaded and validated
- **THEN** a PipelineConfig instance SHALL be returned with all fields properly typed
- **AND** the system SHALL proceed with initialization

#### Scenario: Invalid configuration

- **WHEN** configuration contains invalid values (e.g., negative numbers for positive-only fields)
- **THEN** Pydantic validation SHALL raise a detailed error
- **AND** the system SHALL fail to start with a clear error message
- **AND** the error message SHALL indicate which field is invalid and why

### Requirement: Secret Management

The system SHALL never store secrets in configuration files and SHALL require secrets to be provided via environment variables.

#### Scenario: Database password from environment

- **WHEN** the system needs database credentials
- **THEN** the password SHALL be read from an environment variable (e.g., `SBIR_ETL__NEO4J_PASSWORD`)
- **AND** the password SHALL NOT be present in any YAML configuration file

#### Scenario: API key from environment

- **WHEN** the system needs API keys (e.g., SAM.gov API key)
- **THEN** the API key SHALL be read from an environment variable
- **AND** the configuration SHALL support null/empty values in YAML files for secrets

### Requirement: Configuration Documentation

The system SHALL provide clear documentation of all configuration parameters and their valid ranges.

#### Scenario: Configuration field description

- **WHEN** a developer reviews the Pydantic schema
- **THEN** each field SHALL have a docstring or Field description
- **AND** valid ranges SHALL be enforced via Pydantic validators (e.g., `ge=0.0, le=1.0`)

#### Scenario: README guidance

- **WHEN** a user reads `config/README.md`
- **THEN** it SHALL document all available configuration sections
- **AND** it SHALL provide examples of environment variable overrides
- **AND** it SHALL explain the configuration priority order

### Requirement: Cached Configuration Loading

The system SHALL cache the loaded configuration to avoid repeated file I/O during a single run.

#### Scenario: Single configuration load per process

- **WHEN** multiple modules request configuration
- **THEN** the configuration SHALL be loaded only once
- **AND** subsequent calls SHALL return the cached instance
- **AND** the cache SHALL be scoped to a single process/run

### Requirement: CET Taxonomy Configuration

The system SHALL externalize CET taxonomy definitions in YAML format to enable updates without code changes.

#### Scenario: Load CET taxonomy from YAML

- **WHEN** the system starts or reloads configuration
- **THEN** it loads config/cet/taxonomy.yaml
- **AND** parses 21 CET category definitions
- **AND** validates required fields (cet_id, name, definition, keywords)
- **AND** builds in-memory taxonomy structure

#### Scenario: Define CET category with metadata

- **WHEN** defining "Artificial Intelligence" in taxonomy.yaml
- **THEN** the configuration includes:

  ```yaml
  - id: artificial_intelligence

    name: Artificial Intelligence
    definition: "AI and machine learning technologies including neural networks..."
    parent_cet_id: null
    keywords:

      - artificial intelligence
      - machine learning
      - neural networks
      - deep learning
      - computer vision
      - natural language processing

    taxonomy_version: "NSTC-2025Q1"
    effective_date: "2025-01-01"
    status: active
  ```

#### Scenario: Define hierarchical CET categories

- **WHEN** defining "Quantum Sensing" as a subcategory of "Quantum Computing"
- **THEN** the configuration includes:

  ```yaml
  - id: quantum_sensing

    name: Quantum Sensing
    definition: "Quantum-based sensing and metrology technologies..."
    parent_cet_id: quantum_computing
    keywords:

      - quantum sensor
      - quantum metrology
      - atomic clock
      - quantum interferometry

    taxonomy_version: "NSTC-2025Q1"
    effective_date: "2025-01-01"
    status: active
  ```

- **AND** the system builds parent-child relationships

#### Scenario: Validate taxonomy completeness

- **WHEN** loading taxonomy configuration
- **THEN** the system validates:
  - All cet_id values are unique
  - All parent_cet_id references exist (or are null)
  - All categories have at least 1 keyword
  - taxonomy_version matches expected format (e.g., "NSTC-YYYYQQ")
  - No circular parent-child relationships
- **AND** fails fast with clear error message if validation fails

### Requirement: ML Classification Configuration

The system SHALL externalize ML model hyperparameters in YAML to enable tuning without code changes.

#### Scenario: Configure TF-IDF vectorization

- **WHEN** loading classification configuration
- **THEN** the system reads config/cet/classification.yaml:

  ```yaml
  vectorizer:
    ngram_range: [1, 3]      # Unigrams, bigrams, trigrams
    max_features: 50000      # Maximum vocabulary size
    min_df: 2                 # Minimum document frequency
    max_df: 0.95             # Maximum document frequency (ignore common words)
    sublinear_tf: true       # Apply sublinear term frequency scaling
    norm: l2                 # L2 normalization
  ```

- **AND** applies these parameters when initializing TF-IDF vectorizer

#### Scenario: Configure feature selection

- **WHEN** configuring feature selection parameters
- **THEN** the system reads:

  ```yaml
  feature_selection:
    enabled: true
    method: chi2             # Chi-squared test
    k: 20000                 # Select top 20,000 features
  ```

- **AND** reduces feature space from 50,000 to 20,000 using chi-squared selection

#### Scenario: Configure classifier parameters

- **WHEN** configuring logistic regression classifier
- **THEN** the system reads:

  ```yaml
  classifier:
    max_iter: 500
    solver: lbfgs           # Limited-memory BFGS
    n_jobs: -1              # Use all CPU cores
    class_weight: balanced  # Handle imbalanced classes
    random_state: 42        # Reproducibility
  ```

#### Scenario: Configure probability calibration

- **WHEN** configuring probability calibration
- **THEN** the system reads:

  ```yaml
  calibration:
    enabled: true
    method: sigmoid         # Platt scaling
    cv: 3                   # 3-fold cross-validation
    min_samples_per_class: 3
  ```

#### Scenario: Configure confidence scoring bands

- **WHEN** configuring classification confidence bands
- **THEN** the system reads:

  ```yaml
  scoring:
    bands:
      high:
        min: 70
        max: 100
        label: "High"
      medium:
        min: 40
        max: 69
        label: "Medium"
      low:
        min: 0
        max: 39
        label: "Low"
    max_supporting: 3       # Maximum supporting CET areas
  ```

- **AND** applies these thresholds when converting scores to confidence labels

### Requirement: CET Configuration Validation

The system SHALL validate all CET configuration files on startup to catch errors early.

#### Scenario: Validate taxonomy schema

- **WHEN** loading taxonomy.yaml
- **THEN** the system validates using Pydantic schema:
  - Required fields present (id, name, definition, keywords, taxonomy_version)
  - Data types correct (id is string, effective_date is date, keywords is list)
  - Keywords list is non-empty
  - Status is one of ["active", "retired"]
  - No duplicate cet_id values

#### Scenario: Validate classification schema

- **WHEN** loading classification.yaml
- **THEN** the system validates:
  - ngram_range is list of 2 integers with min ≤ max
  - max_features, min_df, max_df are positive numbers
  - solver is one of ["lbfgs", "liblinear", "saga", "sag"]
  - n_jobs is integer (-1 for all cores, or positive number)
  - Confidence bands cover full 0-100 range without gaps or overlaps

#### Scenario: Fail fast on invalid configuration

- **WHEN** configuration file has invalid values (e.g., min_df=-1, max_features="invalid")
- **THEN** the system raises ConfigurationError during startup
- **AND** error message specifies the invalid field and expected format
- **AND** prevents application from starting with bad configuration

### Requirement: Environment Variable Overrides

The system SHALL support overriding CET configuration via environment variables for deployment flexibility.

#### Scenario: Override confidence thresholds via environment

- **WHEN** environment variable CET_CONFIDENCE_HIGH_MIN=75 is set
- **THEN** the system overrides the high confidence minimum from 70 to 75
- **AND** applies the override without modifying YAML files

#### Scenario: Override feature selection via environment

- **WHEN** CET_FEATURE_SELECTION_K=15000 is set
- **THEN** the system selects top 15,000 features instead of 20,000

#### Scenario: Enable/disable USPTO integration

- **WHEN** CET_USPTO_INTEGRATION_ENABLED=false is set
- **THEN** the system skips USPTO AI dataset loading and validation
- **AND** does not include uspto_ai_score in Patent-CET relationships

### Requirement: Configuration Versioning

The system SHALL support multiple configuration versions to enable rollback and A/B testing.

#### Scenario: Version taxonomy configuration

- **WHEN** NSTC releases updated taxonomy (NSTC-2025Q2)
- **THEN** the system stores new taxonomy as config/cet/taxonomy_2025q2.yaml
- **AND** preserves old taxonomy as config/cet/taxonomy_2025q1.yaml
- **AND** configuration specifies which version to use: taxonomy_version: "NSTC-2025Q2"

#### Scenario: Switch taxonomy versions

- **WHEN** configuration changes from taxonomy_version: "NSTC-2025Q1" to "NSTC-2025Q2"
- **THEN** the system loads new taxonomy definitions
- **AND** reclassification job uses new taxonomy
- **AND** historical classifications retain old taxonomy_version in metadata

#### Scenario: A/B test classification parameters

- **WHEN** experimenting with different confidence thresholds
- **THEN** the system supports config/cet/classification_v1.yaml and classification_v2.yaml
- **AND** Dagster job specifies which configuration version to use
- **AND** enables comparison of classification results across configurations

### Requirement: CET Configuration Documentation

The system SHALL provide comprehensive documentation for all CET configuration options.

#### Scenario: Document taxonomy structure

- **WHEN** users need to understand taxonomy configuration
- **THEN** config/cet/README.md provides:
  - Complete taxonomy schema with field descriptions
  - Example category definition
  - Hierarchy rules and parent_cet_id usage
  - Keyword selection guidelines
  - Versioning and effective date usage

#### Scenario: Document classification parameters

- **WHEN** users need to tune ML hyperparameters
- **THEN** config/cet/README.md provides:
  - TF-IDF parameter explanations with impacts
  - Feature selection trade-offs (k value selection)
  - Classifier solver options and when to use each
  - Calibration method descriptions
  - Confidence band customization guidance
  - Performance implications of parameter changes

#### Scenario: Document configuration validation rules

- **WHEN** users encounter configuration errors
- **THEN** documentation provides:
  - List of all validation rules
  - Common error messages and solutions
  - Configuration testing command: `python -m sbir_etl.ml.config.validate`
  - Example valid configuration files
