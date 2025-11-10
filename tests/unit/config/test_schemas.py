"""Tests for configuration schemas."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.schemas import (
    CLIConfig,
    DataQualityConfig,
    DuckDBConfig,
    EnrichmentConfig,
    EnrichmentRefreshConfig,
    EnrichmentSourceConfig,
    ExtractionConfig,
    FiscalAnalysisConfig,
    LoggingConfig,
    MetricsConfig,
    Neo4jConfig,
    PathsConfig,
    PipelineConfig,
    SbirDuckDBConfig,
    SbirValidationConfig,
    SensitivityConfig,
    StatisticalReportingConfig,
    TaxParameterConfig,
    TransformationConfig,
    ValidationConfig,
)


pytestmark = pytest.mark.fast



class TestSbirValidationConfig:
    """Tests for SbirValidationConfig model."""

    def test_default_values(self):
        """Test SbirValidationConfig default values."""
        config = SbirValidationConfig()
        assert config.pass_rate_threshold == 0.95
        assert config.completeness_threshold == 0.90
        assert config.uniqueness_threshold == 0.99

    def test_custom_thresholds(self):
        """Test SbirValidationConfig with custom thresholds."""
        config = SbirValidationConfig(
            pass_rate_threshold=0.98,
            completeness_threshold=0.85,
            uniqueness_threshold=1.0,
        )
        assert config.pass_rate_threshold == 0.98
        assert config.completeness_threshold == 0.85
        assert config.uniqueness_threshold == 1.0

    def test_threshold_validator_accepts_valid_bounds(self):
        """Test threshold validator accepts 0.0 and 1.0."""
        config_min = SbirValidationConfig(
            pass_rate_threshold=0.0,
            completeness_threshold=0.0,
            uniqueness_threshold=0.0,
        )
        assert all([config_min.pass_rate_threshold == 0.0])

        config_max = SbirValidationConfig(
            pass_rate_threshold=1.0,
            completeness_threshold=1.0,
            uniqueness_threshold=1.0,
        )
        assert all([config_max.pass_rate_threshold == 1.0])

    def test_threshold_validator_rejects_negative(self):
        """Test threshold validator rejects negative values."""
        with pytest.raises(ValidationError):
            SbirValidationConfig(pass_rate_threshold=-0.1)

    def test_threshold_validator_rejects_above_one(self):
        """Test threshold validator rejects values above 1.0."""
        with pytest.raises(ValidationError):
            SbirValidationConfig(completeness_threshold=1.5)


class TestSbirDuckDBConfig:
    """Tests for SbirDuckDBConfig model."""

    def test_default_values(self):
        """Test SbirDuckDBConfig default values."""
        config = SbirDuckDBConfig()
        assert config.csv_path == "data/raw/sbir/awards_data.csv"
        assert config.database_path == ":memory:"
        assert config.table_name == "sbir_awards"
        assert config.batch_size == 10000
        assert config.encoding == "utf-8"

    def test_custom_values(self):
        """Test SbirDuckDBConfig with custom values."""
        config = SbirDuckDBConfig(
            csv_path="/custom/path/data.csv",
            database_path="/tmp/sbir.duckdb",
            table_name="custom_table",
            batch_size=5000,
            encoding="latin-1",
        )
        assert config.csv_path == "/custom/path/data.csv"
        assert config.database_path == "/tmp/sbir.duckdb"
        assert config.table_name == "custom_table"
        assert config.batch_size == 5000
        assert config.encoding == "latin-1"


class TestDataQualityConfig:
    """Tests for DataQualityConfig model."""

    def test_default_values(self):
        """Test DataQualityConfig default values."""
        config = DataQualityConfig()
        assert isinstance(config.sbir_awards, SbirValidationConfig)
        assert config.completeness["award_id"] == 1.00
        assert config.completeness["company_name"] == 0.95
        assert config.uniqueness["award_id"] == 1.00
        assert config.validity["award_amount_min"] == 0.0

    def test_percentage_validator_accepts_valid_percentages(self):
        """Test percentage validator accepts values between 0 and 1."""
        config = DataQualityConfig(completeness={"field1": 0.85, "field2": 1.0, "field3": 0.0})
        assert config.completeness["field1"] == 0.85
        assert config.completeness["field2"] == 1.0
        assert config.completeness["field3"] == 0.0

    def test_percentage_validator_coerces_string_to_float(self):
        """Test percentage validator coerces string percentages to float."""
        config = DataQualityConfig(completeness={"field1": "0.85"})
        assert config.completeness["field1"] == 0.85
        assert isinstance(config.completeness["field1"], float)

    def test_percentage_validator_rejects_negative(self):
        """Test percentage validator rejects negative percentages."""
        with pytest.raises(ValidationError) as exc_info:
            DataQualityConfig(completeness={"field1": -0.1})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)

    def test_percentage_validator_rejects_above_one(self):
        """Test percentage validator rejects values above 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            DataQualityConfig(uniqueness={"field1": 1.5})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)

    def test_percentage_validator_rejects_non_numeric(self):
        """Test percentage validator rejects non-numeric strings."""
        with pytest.raises(ValidationError) as exc_info:
            DataQualityConfig(completeness={"field1": "not_a_number"})
        assert "must be a number" in str(exc_info.value)


class TestEnrichmentConfig:
    """Tests for EnrichmentConfig model."""

    def test_default_sam_gov_config(self):
        """Test EnrichmentConfig default SAM.gov configuration."""
        config = EnrichmentConfig()
        assert config.sam_gov["base_url"] == "https://api.sam.gov/entity-information/v3"
        assert config.sam_gov["api_key_env_var"] == "SAM_GOV_API_KEY"
        assert config.sam_gov["rate_limit_per_minute"] == 60
        assert config.sam_gov["timeout_seconds"] == 30

    def test_default_usaspending_config(self):
        """Test EnrichmentConfig default USAspending configuration."""
        config = EnrichmentConfig()
        assert config.usaspending_api["base_url"] == "https://api.usaspending.gov/api/v2"
        assert config.usaspending_api["timeout_seconds"] == 30
        assert config.usaspending_api["retry_attempts"] == 3

    def test_custom_enrichment_config(self):
        """Test EnrichmentConfig with custom values."""
        config = EnrichmentConfig(
            sam_gov={
                "base_url": "https://custom.api.com",
                "rate_limit_per_minute": 120,
            },
            usaspending_api={"timeout_seconds": 60},
        )
        assert config.sam_gov["base_url"] == "https://custom.api.com"
        assert config.sam_gov["rate_limit_per_minute"] == 120
        assert config.usaspending_api["timeout_seconds"] == 60


class TestEnrichmentSourceConfig:
    """Tests for EnrichmentSourceConfig model."""

    def test_default_values(self):
        """Test EnrichmentSourceConfig default values."""
        config = EnrichmentSourceConfig()
        assert config.cadence_days == 1
        assert config.sla_staleness_days == 1
        assert config.batch_size == 100
        assert config.max_concurrent_requests == 5
        assert config.enable_delta_detection is True
        assert config.hash_algorithm == "sha256"

    def test_custom_values(self):
        """Test EnrichmentSourceConfig with custom values."""
        config = EnrichmentSourceConfig(
            cadence_days=7,
            sla_staleness_days=14,
            batch_size=500,
            max_concurrent_requests=10,
            enable_delta_detection=False,
        )
        assert config.cadence_days == 7
        assert config.sla_staleness_days == 14
        assert config.batch_size == 500
        assert config.max_concurrent_requests == 10
        assert config.enable_delta_detection is False

    def test_batch_size_constraints(self):
        """Test batch_size has ge=1, le=1000 constraints."""
        # Valid bounds
        EnrichmentSourceConfig(batch_size=1)
        EnrichmentSourceConfig(batch_size=1000)

        # Invalid bounds
        with pytest.raises(ValidationError):
            EnrichmentSourceConfig(batch_size=0)
        with pytest.raises(ValidationError):
            EnrichmentSourceConfig(batch_size=1001)

    def test_cadence_days_constraints(self):
        """Test cadence_days has ge=1 constraint."""
        EnrichmentSourceConfig(cadence_days=1)
        with pytest.raises(ValidationError):
            EnrichmentSourceConfig(cadence_days=0)


class TestEnrichmentRefreshConfig:
    """Tests for EnrichmentRefreshConfig model."""

    def test_default_usaspending_config(self):
        """Test EnrichmentRefreshConfig has default usaspending config."""
        config = EnrichmentRefreshConfig()
        assert isinstance(config.usaspending, EnrichmentSourceConfig)
        assert config.usaspending.cadence_days == 1


class TestNeo4jConfig:
    """Tests for Neo4jConfig model."""

    def test_default_values(self):
        """Test Neo4jConfig default values."""
        config = Neo4jConfig()
        assert config.uri == "bolt://localhost:7687"
        assert config.username == "neo4j"
        assert config.password == "neo4j"
        assert config.database == "neo4j"
        assert config.batch_size == 1000
        assert config.parallel_threads == 4
        assert config.create_constraints is True
        assert config.transaction_timeout_seconds == 300

    def test_custom_connection_values(self):
        """Test Neo4jConfig with custom connection values."""
        config = Neo4jConfig(
            uri="bolt://prod-neo4j:7687",
            username="admin",
            password="secret",
            database="sbir",
        )
        assert config.uri == "bolt://prod-neo4j:7687"
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.database == "sbir"

    def test_custom_performance_values(self):
        """Test Neo4jConfig with custom performance values."""
        config = Neo4jConfig(
            batch_size=5000,
            parallel_threads=8,
            transaction_timeout_seconds=600,
            max_deadlock_retries=5,
        )
        assert config.batch_size == 5000
        assert config.parallel_threads == 8
        assert config.transaction_timeout_seconds == 600
        assert config.max_deadlock_retries == 5


class TestExtractionConfig:
    """Tests for ExtractionConfig model."""

    def test_default_values(self):
        """Test ExtractionConfig default values."""
        config = ExtractionConfig()
        assert isinstance(config.sbir, SbirDuckDBConfig)
        assert config.usaspending["database_name"] == "usaspending"
        assert config.usaspending["table_name"] == "awards"
        assert config.usaspending["import_chunk_size"] == 50000

    def test_custom_usaspending_config(self):
        """Test ExtractionConfig with custom USAspending config."""
        config = ExtractionConfig(
            usaspending={
                "database_name": "custom_db",
                "import_chunk_size": 100000,
            }
        )
        assert config.usaspending["database_name"] == "custom_db"
        assert config.usaspending["import_chunk_size"] == 100000


class TestValidationConfig:
    """Tests for ValidationConfig model."""

    def test_default_values(self):
        """Test ValidationConfig default values."""
        config = ValidationConfig()
        assert config.strict_schema is True
        assert config.fail_on_first_error is False
        assert config.sample_size_for_checks == 1000
        assert config.max_error_percentage == 0.05

    def test_custom_values(self):
        """Test ValidationConfig with custom values."""
        config = ValidationConfig(
            strict_schema=False,
            fail_on_first_error=True,
            sample_size_for_checks=5000,
            max_error_percentage=0.10,
        )
        assert config.strict_schema is False
        assert config.fail_on_first_error is True
        assert config.sample_size_for_checks == 5000
        assert config.max_error_percentage == 0.10

    def test_error_percentage_validator_accepts_valid_values(self):
        """Test error percentage validator accepts 0.0 to 1.0."""
        ValidationConfig(max_error_percentage=0.0)
        ValidationConfig(max_error_percentage=1.0)

    def test_error_percentage_validator_coerces_string(self):
        """Test error percentage validator coerces string to float."""
        config = ValidationConfig(max_error_percentage="0.15")
        assert config.max_error_percentage == 0.15

    def test_error_percentage_validator_rejects_negative(self):
        """Test error percentage validator rejects negative values."""
        with pytest.raises(ValidationError):
            ValidationConfig(max_error_percentage=-0.1)


class TestLoggingConfig:
    """Tests for LoggingConfig model."""

    def test_default_values(self):
        """Test LoggingConfig default values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.format == "json"
        assert config.file_path == "logs/sbir-etl.log"
        assert config.max_file_size_mb == 100
        assert config.backup_count == 5
        assert config.console_enabled is True
        assert config.file_enabled is True

    def test_format_normalizer_accepts_json(self):
        """Test format normalizer accepts json format."""
        config = LoggingConfig(format="json")
        assert config.format == "json"

    def test_format_normalizer_converts_pretty_to_text(self):
        """Test format normalizer converts 'pretty' to 'text'."""
        config = LoggingConfig(format="pretty")
        assert config.format == "text"

    def test_format_normalizer_converts_structured_to_json(self):
        """Test format normalizer converts 'structured' to 'json'."""
        config = LoggingConfig(format="structured")
        assert config.format == "json"

    def test_format_normalizer_case_insensitive(self):
        """Test format normalizer is case insensitive."""
        config1 = LoggingConfig(format="JSON")
        assert config1.format == "json"

        config2 = LoggingConfig(format="PRETTY")
        assert config2.format == "text"

    def test_custom_logging_values(self):
        """Test LoggingConfig with custom values."""
        config = LoggingConfig(
            level="DEBUG",
            format="text",
            file_path="custom/logs/app.log",
            max_file_size_mb=50,
            console_enabled=False,
        )
        assert config.level == "DEBUG"
        assert config.format == "text"
        assert config.file_path == "custom/logs/app.log"
        assert config.max_file_size_mb == 50
        assert config.console_enabled is False


class TestMetricsConfig:
    """Tests for MetricsConfig model."""

    def test_default_values(self):
        """Test MetricsConfig default values."""
        config = MetricsConfig()
        assert config.enabled is True
        assert config.collection_interval_seconds == 30
        assert config.persist_to_file is True
        assert config.metrics_file_path == "logs/metrics.json"
        assert config.warning_thresholds["stage_duration_seconds"] == 3600

    def test_custom_values(self):
        """Test MetricsConfig with custom values."""
        config = MetricsConfig(
            enabled=False,
            collection_interval_seconds=60,
            warning_thresholds={"custom_threshold": 1000},
        )
        assert config.enabled is False
        assert config.collection_interval_seconds == 60
        assert config.warning_thresholds["custom_threshold"] == 1000


class TestDuckDBConfig:
    """Tests for DuckDBConfig model."""

    def test_default_values(self):
        """Test DuckDBConfig default values."""
        config = DuckDBConfig()
        assert config.database_path == "data/processed/sbir.duckdb"
        assert config.memory_limit_gb == 4
        assert config.threads == 4
        assert config.enable_object_cache is True
        assert config.enable_query_profiler is False

    def test_custom_values(self):
        """Test DuckDBConfig with custom values."""
        config = DuckDBConfig(
            database_path=":memory:",
            memory_limit_gb=8,
            threads=8,
            enable_query_profiler=True,
        )
        assert config.database_path == ":memory:"
        assert config.memory_limit_gb == 8
        assert config.threads == 8
        assert config.enable_query_profiler is True


class TestStatisticalReportingConfig:
    """Tests for StatisticalReportingConfig model."""

    def test_default_generation_config(self):
        """Test StatisticalReportingConfig default generation config."""
        config = StatisticalReportingConfig()
        assert config.generation["enabled"] is True
        assert config.generation["formats"] == ["html", "json", "markdown"]
        assert config.generation["output_directory"] == "reports/statistical"

    def test_default_modules_config(self):
        """Test StatisticalReportingConfig default modules config."""
        config = StatisticalReportingConfig()
        assert config.modules["sbir_enrichment"]["enabled"] is True
        assert config.modules["patent_analysis"]["enabled"] is True

    def test_default_quality_thresholds(self):
        """Test StatisticalReportingConfig default quality thresholds."""
        config = StatisticalReportingConfig()
        assert config.quality_thresholds["data_completeness_warning"] == 0.90
        assert config.quality_thresholds["enrichment_success_error"] == 0.70

    def test_quality_thresholds_validator_accepts_valid_values(self):
        """Test quality thresholds validator accepts valid values."""
        config = StatisticalReportingConfig(
            quality_thresholds={
                "data_completeness_warning": 0.95,
                "performance_degradation_error": 2.5,
            }
        )
        assert config.quality_thresholds["data_completeness_warning"] == 0.95
        assert config.quality_thresholds["performance_degradation_error"] == 2.5

    def test_quality_thresholds_validator_rejects_invalid_completeness(self):
        """Test quality thresholds validator rejects invalid completeness values."""
        with pytest.raises(ValidationError) as exc_info:
            StatisticalReportingConfig(quality_thresholds={"data_completeness_warning": 1.5})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)

    def test_quality_thresholds_validator_rejects_invalid_performance(self):
        """Test quality thresholds validator rejects invalid performance values."""
        with pytest.raises(ValidationError) as exc_info:
            StatisticalReportingConfig(quality_thresholds={"performance_degradation_warning": 0.5})
        assert "must be >= 1.0" in str(exc_info.value)


class TestTaxParameterConfig:
    """Tests for TaxParameterConfig model."""

    def test_default_individual_income_tax(self):
        """Test TaxParameterConfig default individual income tax."""
        config = TaxParameterConfig()
        assert config.individual_income_tax["effective_rate"] == 0.22
        assert config.individual_income_tax["progressive_rates"]["10_percent"] == 0.10

    def test_default_payroll_tax(self):
        """Test TaxParameterConfig default payroll tax."""
        config = TaxParameterConfig()
        assert config.payroll_tax["social_security_rate"] == 0.062
        assert config.payroll_tax["medicare_rate"] == 0.0145

    def test_default_corporate_income_tax(self):
        """Test TaxParameterConfig default corporate income tax."""
        config = TaxParameterConfig()
        assert config.corporate_income_tax["federal_rate"] == 0.21

    def test_tax_parameters_validator_accepts_valid_rates(self):
        """Test tax parameters validator accepts valid rates."""
        config = TaxParameterConfig(
            payroll_tax={
                "social_security_rate": 0.07,
                "medicare_rate": 0.02,
            }
        )
        assert config.payroll_tax["social_security_rate"] == 0.07

    def test_tax_parameters_validator_rejects_negative_rates(self):
        """Test tax parameters validator rejects negative rates."""
        with pytest.raises(ValidationError) as exc_info:
            TaxParameterConfig(payroll_tax={"social_security_rate": -0.01})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)

    def test_tax_parameters_validator_rejects_rates_above_one(self):
        """Test tax parameters validator rejects rates above 1.0."""
        with pytest.raises(ValidationError) as exc_info:
            TaxParameterConfig(corporate_income_tax={"federal_rate": 1.5})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)


class TestSensitivityConfig:
    """Tests for SensitivityConfig model."""

    def test_default_parameter_sweep(self):
        """Test SensitivityConfig default parameter sweep."""
        config = SensitivityConfig()
        assert config.parameter_sweep["enabled"] is True
        assert config.parameter_sweep["method"] == "monte_carlo"
        assert config.parameter_sweep["num_scenarios"] == 1000

    def test_default_uncertainty_parameters(self):
        """Test SensitivityConfig default uncertainty parameters."""
        config = SensitivityConfig()
        assert config.uncertainty_parameters["tax_rates"]["variation_percent"] == 0.10
        assert config.uncertainty_parameters["multipliers"]["distribution"] == "normal"

    def test_uncertainty_parameters_validator_accepts_valid_values(self):
        """Test uncertainty parameters validator accepts valid values."""
        config = SensitivityConfig(
            uncertainty_parameters={
                "custom_param": {
                    "variation_percent": 0.20,
                    "distribution": "uniform",
                }
            }
        )
        assert config.uncertainty_parameters["custom_param"]["variation_percent"] == 0.20

    def test_uncertainty_parameters_validator_rejects_invalid_variation(self):
        """Test uncertainty parameters validator rejects invalid variation."""
        with pytest.raises(ValidationError) as exc_info:
            SensitivityConfig(uncertainty_parameters={"test": {"variation_percent": 1.5}})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)


class TestCLIConfig:
    """Tests for CLIConfig model."""

    def test_default_values(self):
        """Test CLIConfig default values."""
        config = CLIConfig()
        assert config.theme == "default"
        assert config.progress_refresh_rate == 0.1
        assert config.dashboard_refresh_rate == 10
        assert config.max_table_rows == 50

    def test_custom_values(self):
        """Test CLIConfig with custom values."""
        config = CLIConfig(
            theme="dark",
            progress_refresh_rate=0.5,
            max_table_rows=100,
        )
        assert config.theme == "dark"
        assert config.progress_refresh_rate == 0.5
        assert config.max_table_rows == 100

    def test_theme_validator_accepts_valid_themes(self):
        """Test theme validator accepts valid themes."""
        for theme in ["default", "dark", "light"]:
            config = CLIConfig(theme=theme)
            assert config.theme == theme

    def test_theme_validator_rejects_invalid_theme(self):
        """Test theme validator rejects invalid theme."""
        with pytest.raises(ValidationError) as exc_info:
            CLIConfig(theme="invalid")
        assert "must be 'default', 'dark', or 'light'" in str(exc_info.value)

    def test_refresh_rate_validator_rejects_negative(self):
        """Test refresh rate validator rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            CLIConfig(progress_refresh_rate=-0.1)
        assert "must be positive" in str(exc_info.value)


class TestFiscalAnalysisConfig:
    """Tests for FiscalAnalysisConfig model."""

    def test_default_values(self):
        """Test FiscalAnalysisConfig default values."""
        config = FiscalAnalysisConfig()
        assert config.base_year == 2023
        assert config.inflation_source == "bea_gdp_deflator"
        assert config.naics_crosswalk_version == "2022"
        assert isinstance(config.tax_parameters, TaxParameterConfig)
        assert isinstance(config.sensitivity_parameters, SensitivityConfig)

    def test_default_quality_thresholds(self):
        """Test FiscalAnalysisConfig default quality thresholds."""
        config = FiscalAnalysisConfig()
        assert config.quality_thresholds["naics_coverage_rate"] == 0.85
        assert config.quality_thresholds["geographic_resolution_rate"] == 0.90

    def test_base_year_validator_accepts_valid_years(self):
        """Test base year validator accepts valid years."""
        FiscalAnalysisConfig(base_year=1980)
        FiscalAnalysisConfig(base_year=2030)

    def test_base_year_validator_rejects_invalid_years(self):
        """Test base year validator rejects invalid years."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalAnalysisConfig(base_year=1970)
        assert "must be between 1980 and 2030" in str(exc_info.value)

    def test_quality_thresholds_validator_coerces_values(self):
        """Test quality thresholds validator coerces values to float."""
        config = FiscalAnalysisConfig(quality_thresholds={"naics_coverage_rate": "0.90"})
        assert config.quality_thresholds["naics_coverage_rate"] == 0.90

    def test_quality_thresholds_validator_rejects_out_of_range(self):
        """Test quality thresholds validator rejects out of range values."""
        with pytest.raises(ValidationError) as exc_info:
            FiscalAnalysisConfig(quality_thresholds={"naics_coverage_rate": 1.5})
        assert "must be between 0.0 and 1.0" in str(exc_info.value)


class TestPathsConfig:
    """Tests for PathsConfig model."""

    def test_default_values(self):
        """Test PathsConfig default values."""
        config = PathsConfig()
        assert config.data_root == "data"
        assert config.raw_data == "data/raw"
        assert config.usaspending_dump_dir == "data/usaspending"
        assert config.transition_contracts_output == "data/transition/contracts_ingestion.parquet"

    def test_custom_paths(self):
        """Test PathsConfig with custom paths."""
        config = PathsConfig(
            data_root="/custom/data",
            raw_data="/custom/data/raw",
        )
        assert config.data_root == "/custom/data"
        assert config.raw_data == "/custom/data/raw"

    def test_resolve_path_with_default_project_root(self):
        """Test resolve_path with default project root."""
        config = PathsConfig(data_root="data")
        resolved = config.resolve_path("data_root")
        assert isinstance(resolved, Path)
        assert resolved.is_absolute()

    def test_resolve_path_with_custom_project_root(self):
        """Test resolve_path with custom project root."""
        config = PathsConfig(data_root="data")
        project_root = Path("/custom/project")
        resolved = config.resolve_path("data_root", project_root=project_root)
        assert resolved == (project_root / "data").resolve()

    def test_resolve_path_raises_for_invalid_key(self):
        """Test resolve_path raises ValueError for invalid key."""
        config = PathsConfig()
        with pytest.raises(ValueError) as exc_info:
            config.resolve_path("invalid_key")
        assert "Unknown path key: invalid_key" in str(exc_info.value)

    def test_resolve_path_with_absolute_path(self):
        """Test resolve_path with absolute path."""
        config = PathsConfig(data_root="/absolute/path/data")
        resolved = config.resolve_path("data_root")
        assert resolved == Path("/absolute/path/data")

    def test_expand_variables_with_simple_reference(self):
        """Test _expand_variables with simple reference."""
        config = PathsConfig()
        context = {"section": {"key": "value"}}
        result = config._expand_variables("${section.key}", context)
        assert result == "value"

    def test_expand_variables_with_no_reference(self):
        """Test _expand_variables with no variable reference."""
        config = PathsConfig()
        result = config._expand_variables("plain/path", {})
        assert result == "plain/path"


class TestPipelineConfig:
    """Tests for PipelineConfig root model."""

    def test_default_values(self):
        """Test PipelineConfig default values."""
        config = PipelineConfig()
        assert config.pipeline["name"] == "sbir-etl"
        assert config.pipeline["version"] == "0.1.0"
        assert config.pipeline["environment"] == "development"
        assert isinstance(config.paths, PathsConfig)
        assert isinstance(config.data_quality, DataQualityConfig)
        assert isinstance(config.neo4j, Neo4jConfig)

    def test_nested_config_access(self):
        """Test accessing nested configuration objects."""
        config = PipelineConfig()
        assert config.logging.level == "INFO"
        assert config.neo4j.uri == "bolt://localhost:7687"
        assert config.duckdb.database_path == "data/processed/sbir.duckdb"

    def test_custom_nested_values(self):
        """Test PipelineConfig with custom nested values."""
        config = PipelineConfig(
            logging=LoggingConfig(level="DEBUG"),
            neo4j=Neo4jConfig(uri="bolt://prod:7687"),
        )
        assert config.logging.level == "DEBUG"
        assert config.neo4j.uri == "bolt://prod:7687"

    def test_extra_fields_allowed(self):
        """Test PipelineConfig allows extra fields."""
        config = PipelineConfig(custom_field="custom_value")
        # Should not raise ValidationError
        assert config.model_config["extra"] == "allow"

    def test_all_sub_configs_instantiated(self):
        """Test all sub-configuration objects are instantiated."""
        config = PipelineConfig()
        assert isinstance(config.paths, PathsConfig)
        assert isinstance(config.data_quality, DataQualityConfig)
        assert isinstance(config.enrichment, EnrichmentConfig)
        assert isinstance(config.enrichment_refresh, EnrichmentRefreshConfig)
        assert isinstance(config.neo4j, Neo4jConfig)
        assert isinstance(config.extraction, ExtractionConfig)
        assert isinstance(config.validation, ValidationConfig)
        assert isinstance(config.transformation, TransformationConfig)
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.metrics, MetricsConfig)
        assert isinstance(config.duckdb, DuckDBConfig)
        assert isinstance(config.statistical_reporting, StatisticalReportingConfig)
        assert isinstance(config.fiscal_analysis, FiscalAnalysisConfig)
        assert isinstance(config.cli, CLIConfig)


class TestTransformationConfig:
    """Tests for TransformationConfig model."""

    def test_default_values(self):
        """Test TransformationConfig default values."""
        config = TransformationConfig()
        assert config.company_deduplication["similarity_threshold"] == 0.85
        assert config.company_deduplication["min_company_name_length"] == 3
        assert config.award_normalization["currency"] == "USD"
        assert config.graph_preparation["batch_size"] == 1000

    def test_custom_values(self):
        """Test TransformationConfig with custom values."""
        config = TransformationConfig(
            company_deduplication={"similarity_threshold": 0.90},
            award_normalization={"currency": "EUR"},
        )
        assert config.company_deduplication["similarity_threshold"] == 0.90
        assert config.award_normalization["currency"] == "EUR"
