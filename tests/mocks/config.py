"""Mock factories for configuration objects."""

from unittest.mock import Mock


class ConfigMocks:
    """Factory for configuration mock objects."""

    @staticmethod
    def pipeline_config(**overrides) -> Mock:
        """Create a mock pipeline configuration."""
        config = Mock()

        config.chunk_size = overrides.get("chunk_size", 10000)
        config.batch_size = overrides.get("batch_size", 1000)
        config.enable_incremental = overrides.get("enable_incremental", True)
        config.timeout_seconds = overrides.get("timeout_seconds", 300)

        config.data_quality = ConfigMocks.data_quality_config(**overrides.get("data_quality", {}))
        config.enrichment = ConfigMocks.enrichment_config(**overrides.get("enrichment", {}))
        config.neo4j = ConfigMocks.neo4j_config(**overrides.get("neo4j", {}))

        return config

    @staticmethod
    def data_quality_config(**overrides) -> Mock:
        """Create a mock data quality configuration."""
        config = Mock()
        config.max_duplicate_rate = overrides.get("max_duplicate_rate", 0.10)
        config.max_missing_rate = overrides.get("max_missing_rate", 0.15)
        config.min_enrichment_success = overrides.get("min_enrichment_success", 0.90)
        return config

    @staticmethod
    def enrichment_config(**overrides) -> Mock:
        """Create a mock enrichment configuration."""
        config = Mock()
        config.batch_size = overrides.get("batch_size", 100)
        config.max_retries = overrides.get("max_retries", 3)
        config.timeout_seconds = overrides.get("timeout_seconds", 30)
        config.rate_limit_per_second = overrides.get("rate_limit_per_second", 10.0)
        return config

    @staticmethod
    def neo4j_config(**overrides) -> Mock:
        """Create a mock Neo4j configuration."""
        config = Mock()
        config.uri = overrides.get("uri", "bolt://localhost:7687")
        config.username = overrides.get("username", "neo4j")
        config.password = overrides.get("password", "password")
        config.database = overrides.get("database", "neo4j")
        config.batch_size = overrides.get("batch_size", 1000)
        return config
