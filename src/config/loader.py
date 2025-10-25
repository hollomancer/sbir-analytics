"""Configuration loader with YAML file loading and environment variable overrides."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import ValidationError

from .schemas import PipelineConfig


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""
    pass


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def _apply_env_overrides(config_dict: Dict[str, Any], prefix: str = "SBIR_ETL") -> Dict[str, Any]:
    """Apply environment variable overrides to configuration dictionary."""
    result = config_dict.copy()

    for env_key, env_value in os.environ.items():
        if not env_key.startswith(f"{prefix}__"):
            continue

        # Remove prefix and split by double underscores
        config_path = env_key[len(f"{prefix}__"):].lower().split("__")

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
    base_path: Path,
    environment: Optional[str] = None,
    config_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Load configuration from YAML files with environment-specific overrides."""
    if config_dir is None:
        config_dir = Path("config")

    # Load base configuration
    base_file = config_dir / "base.yaml"
    if not base_file.exists():
        raise ConfigurationError(f"Base configuration file not found: {base_file}")

    try:
        with open(base_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse base config: {e}")

    # Load environment-specific overrides
    if environment:
        env_file = config_dir / f"{environment}.yaml"
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    env_config = yaml.safe_load(f) or {}
                config = _deep_merge_dicts(config, env_config)
            except yaml.YAMLError as e:
                raise ConfigurationError(f"Failed to parse {environment} config: {e}")

    return config


@lru_cache(maxsize=1)
def get_config(
    environment: Optional[str] = None,
    config_dir: Optional[Path] = None,
    apply_env_overrides_flag: bool = True
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
            base_path=Path.cwd(),
            environment=environment,
            config_dir=config_dir
        )

        # Apply environment variable overrides
        if apply_env_overrides_flag:
            config_dict = _apply_env_overrides(config_dict)

        # Validate with Pydantic
        config = PipelineConfig(**config_dict)

        return config

    except ValidationError as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")
    except Exception as e:
        raise ConfigurationError(f"Configuration loading failed: {e}")


def reload_config() -> None:
    """Clear configuration cache to force reload on next access."""
    get_config.cache_clear()


# Convenience function for getting current environment
def get_current_environment() -> str:
    """Get the current environment name."""
    config = get_config()
    return config.pipeline.get("environment", "development")