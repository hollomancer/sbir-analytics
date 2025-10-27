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
