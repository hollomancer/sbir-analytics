"""Configuration loader with YAML file loading and environment variable overrides."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schemas import PipelineConfig


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""

    pass


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def _apply_env_overrides(config_dict: dict[str, Any], prefix: str = "SBIR_ETL") -> dict[str, Any]:
    """Apply environment variable overrides to configuration dictionary."""
    result = config_dict.copy()

    for env_key, env_value in os.environ.items():
        if not env_key.startswith(f"{prefix}__"):
            continue

        # Remove prefix and split by double underscores
        config_path = env_key[len(f"{prefix}__") :].lower().split("__")

        # Navigate to the nested location
        current = result
        for path_part in config_path[:-1]:
            if path_part not in current:
                current[path_part] = {}
            current = current[path_part]

        # Set the final value, attempting type conversion
        final_key = config_path[-1]
        current[final_key] = _convert_env_value(env_value)

    return result


def _convert_env_value(value: str) -> Any:
    """Convert environment variable string to appropriate type."""
    # Try boolean conversion
    if value.lower() in ("true", "false"):
        return value.lower() == "true"

    # Try integer conversion
    try:
        return int(value)
    except ValueError:
        pass

    # Try float conversion
    try:
        return float(value)
    except ValueError:
        pass

    # Return as string
    return value


def load_config_from_files(
    base_path: Path, environment: str | None = None, config_dir: Path | None = None
) -> dict[str, Any]:
    """Load configuration from YAML files with environment-specific overrides."""
    if config_dir is None:
        config_dir = Path("config")

    # Load base configuration
    base_file = config_dir / "base.yaml"
    if not base_file.exists():
        raise ConfigurationError(f"Base configuration file not found: {base_file}")

    try:
        with open(base_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse base config: {e}") from e

    # Load environment-specific overrides
    if environment:
        env_file = config_dir / f"{environment}.yaml"
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8") as f:
                    env_config = yaml.safe_load(f) or {}
                config = _deep_merge_dicts(config, env_config)
            except yaml.YAMLError as e:
                raise ConfigurationError(f"Failed to parse {environment} config: {e}") from e

    # Backwards-compatibility mapping:
    # Older configs used a `loading: { neo4j: { ... } }` structure. Map that into
    # top-level `neo4j` so Pydantic schema consumers can access `config.neo4j.*`.
    if "loading" in config and isinstance(config["loading"], dict):
        loading = config.pop("loading")
        if "neo4j" in loading:
            # If a top-level neo4j section already exists, deep-merge loading.neo4j into it.
            if "neo4j" not in config:
                config["neo4j"] = loading["neo4j"]
            else:
                config["neo4j"] = _deep_merge_dicts(
                    config.get("neo4j", {}), loading.get("neo4j", {})
                )

    # Ensure neo4j defaults are present so tests and callers can safely read expected keys.
    config.setdefault("neo4j", {})
    neo = config["neo4j"]

    # Determine default Neo4j URI with environment-specific fallback. Priority:
    # 1. Explicit environment variable NE4J_URI (if present)
    # 2. If not present, choose a sensible default based on the requested environment:
    #    - production/prod -> prod-neo4j host
    #    - otherwise -> localhost for dev/local testing
    default_uri = os.getenv("NEO4J_URI")
    if not default_uri:
        if environment in ("prod", "production"):
            default_uri = "bolt://prod-neo4j:7687"
        else:
            default_uri = "bolt://localhost:7687"

    neo.setdefault("uri", default_uri)
    neo.setdefault("username", os.getenv("NEO4J_USER", "neo4j"))
    neo.setdefault("password", os.getenv("NEO4J_PASSWORD", "neo4j"))
    neo.setdefault("database", os.getenv("NEO4J_DATABASE", "neo4j"))
    neo.setdefault("batch_size", neo.get("batch_size", 1000))
    neo.setdefault("parallel_threads", neo.get("parallel_threads", 4))

    # Ensure logging defaults (console/file enabled flags) so env overrides like
    # SBIR_ETL__LOGGING__CONSOLE_ENABLED work and attributes exist on the model.
    config.setdefault("logging", {})
    logging_cfg = config["logging"]
    logging_cfg.setdefault("console_enabled", logging_cfg.get("console_enabled", True))
    logging_cfg.setdefault("file_enabled", logging_cfg.get("file_enabled", True))
    logging_cfg.setdefault("level", logging_cfg.get("level", "INFO"))
    logging_cfg.setdefault("format", logging_cfg.get("format", "json"))

    # Provide a monitoring defaults section expected by tests/consumers.
    config.setdefault("monitoring", {})
    monitoring = config["monitoring"]
    monitoring.setdefault("enabled", monitoring.get("enabled", True))
    monitoring.setdefault("endpoint", monitoring.get("endpoint", None))

    return config


@lru_cache(maxsize=1)
def get_config(
    environment: str | None = None,
    config_dir: Path | None = None,
    apply_env_overrides_flag: bool = True,
) -> PipelineConfig:
    """Get validated configuration with caching.

    Args:
        environment: Environment name (e.g., 'dev', 'prod'). If None, uses SBIR_ETL__PIPELINE__ENVIRONMENT env var or 'development'.
        config_dir: Directory containing config files. Defaults to 'config'.
        apply_env_overrides_flag: Whether to apply environment variable overrides.

    Returns:
        Validated PipelineConfig instance.

    Raises:
        ConfigurationError: If configuration loading or validation fails.
    """
    try:
        # Determine environment
        if environment is None:
            environment = os.getenv("SBIR_ETL__PIPELINE__ENVIRONMENT", "development")

        # Load configuration from files
        config_dict = load_config_from_files(
            base_path=Path.cwd(), environment=environment, config_dir=config_dir
        )

        # Apply environment variable overrides
        if apply_env_overrides_flag:
            config_dict = _apply_env_overrides(config_dict)

        # Validate with Pydantic
        config = PipelineConfig(**config_dict)

        return config

    except ValidationError as e:
        raise ConfigurationError(f"Configuration validation failed: {e}") from e
    except Exception as e:
        raise ConfigurationError(f"Configuration loading failed: {e}") from e


def reload_config() -> None:
    """Clear configuration cache to force reload on next access."""
    get_config.cache_clear()


# Convenience function for getting current environment
def get_current_environment() -> str:
    """Get the current environment name."""
    config = get_config()
    return config.pipeline.get("environment", "development")
