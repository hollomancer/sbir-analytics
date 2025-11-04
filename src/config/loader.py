#!/usr/bin/env python3
"""Configuration loader: minimal file merging + get_config that applies defaults.

This module intentionally keeps `load_config_from_files` minimal: it only reads
and deep-merges YAML files (base + optional environment). All runtime defaults
and backward-compat shims are applied in `get_config()` so unit tests that
inspect raw file merging can rely on an unmodified merge output.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..exceptions import ConfigurationError
from .schemas import PipelineConfig


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _convert_env_value(value: str) -> Any:
    """Convert environment variable string to appropriate type."""
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


def _apply_env_overrides(config_dict: dict[str, Any], prefix: str = "SBIR_ETL") -> dict[str, Any]:
    """Apply environment variable overrides to configuration dictionary.

    Example:
      SBIR_ETL__NEO4J__URI=bolt://... -> config_dict["neo4j"]["uri"] = "bolt://..."
    """
    result = config_dict.copy()

    for env_key, env_value in os.environ.items():
        if not env_key.startswith(f"{prefix}__"):
            continue

        # Remove prefix and split by double underscores
        config_path = env_key[len(f"{prefix}__") :].lower().split("__")

        # Navigate to the nested location, creating dicts as needed
        current = result
        for path_part in config_path[:-1]:
            if path_part not in current or not isinstance(current[path_part], dict):
                current[path_part] = {}
            current = current[path_part]

        final_key = config_path[-1]
        current[final_key] = _convert_env_value(env_value)

    return result


def load_config_from_files(
    base_path: Path, environment: str | None = None, config_dir: Path | None = None
) -> dict[str, Any]:
    """Load configuration from YAML files with environment-specific overrides.

    This is intentionally a thin function: it only loads `base.yaml` and merges
    an optional `<environment>.yaml` on top of it. It does NOT inject defaults or
    map legacy keys; those behaviors belong to `get_config()`.
    """
    if config_dir is None:
        config_dir = Path("config")

    base_file = Path(config_dir) / "base.yaml"
    if not base_file.exists():
        raise ConfigurationError(
            f"Base configuration file not found: {base_file}",
            operation="load_config_from_files",
            details={"file_path": str(base_file), "config_dir": str(config_dir)},
        )

    try:
        with open(base_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Failed to parse base config: {e}",
            operation="load_config_from_files",
            details={"file_path": str(base_file)},
            cause=e,
        ) from e

    if environment:
        env_file = Path(config_dir) / f"{environment}.yaml"
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8") as f:
                    env_config = yaml.safe_load(f) or {}
                config = _deep_merge_dicts(config, env_config)
            except yaml.YAMLError as e:
                raise ConfigurationError(
                    f"Failed to parse {environment} config: {e}",
                    operation="load_config_from_files",
                    details={"file_path": str(env_file), "environment": environment},
                    cause=e,
                ) from e

    return config


@lru_cache(maxsize=1)
def get_config(
    environment: str | None = None,
    config_dir: Path | None = None,
    apply_env_overrides_flag: bool = True,
) -> PipelineConfig:
    """Get validated configuration with caching.

    Responsibility:
    - Load merged file config via `load_config_from_files`
    - Apply environment variable overrides (if requested)
    - Map legacy keys (e.g., `loading.neo4j`) into expected top-level keys
    - Inject runtime defaults (neo4j URI defaults, logging flags, monitoring)
    - Validate and return a PipelineConfig instance
    """
    try:
        # Determine environment name
        if environment is None:
            environment = os.getenv("SBIR_ETL__PIPELINE__ENVIRONMENT", "development")

        # Load merged files
        config_dict = load_config_from_files(
            base_path=Path.cwd(), environment=environment, config_dir=config_dir
        )

        # Backwards-compatibility: if config uses `loading: { neo4j: ... }` map it
        # to top-level `neo4j` but do not otherwise alter non-neo4j keys here.
        if isinstance(config_dict.get("loading"), dict) and "neo4j" in config_dict.get(
            "loading", {}
        ):
            loading = config_dict.get("loading", {}) or {}
            neo_from_loading = loading.get("neo4j", {})
            existing_neo = config_dict.get("neo4j", {}) or {}
            config_dict["neo4j"] = _deep_merge_dicts(existing_neo, neo_from_loading)

        # Ensure top-level neo4j dict exists and set sensible runtime defaults.
        config_dict.setdefault("neo4j", {})
        neo = config_dict["neo4j"]

        # Prioritize explicit environment variable NE04J_URI; else choose default by env
        explicit_uri = os.getenv("NEO4J_URI")
        if explicit_uri:
            default_uri = explicit_uri
        else:
            if environment and environment.lower() in ("prod", "production"):
                default_uri = "bolt://prod-neo4j:7687"
            else:
                default_uri = "bolt://localhost:7687"

        neo.setdefault("uri", default_uri)
        neo.setdefault("username", os.getenv("NEO4J_USER", "neo4j"))
        neo.setdefault("password", os.getenv("NEO4J_PASSWORD", "neo4j"))
        neo.setdefault("database", os.getenv("NEO4J_DATABASE", "neo4j"))
        neo.setdefault("batch_size", neo.get("batch_size", 1000))
        neo.setdefault("parallel_threads", neo.get("parallel_threads", 4))

        # Logging defaults
        config_dict.setdefault("logging", {})
        logging_cfg = config_dict["logging"]
        # If an env-var override already supplied these keys, don't overwrite them.
        logging_cfg.setdefault("console_enabled", logging_cfg.get("console_enabled", True))
        logging_cfg.setdefault("file_enabled", logging_cfg.get("file_enabled", True))
        logging_cfg.setdefault("level", logging_cfg.get("level", "INFO"))
        logging_cfg.setdefault("format", logging_cfg.get("format", "json"))
        logging_cfg.setdefault("file_path", logging_cfg.get("file_path", "logs/sbir-etl.log"))
        logging_cfg.setdefault("max_file_size_mb", logging_cfg.get("max_file_size_mb", 100))
        logging_cfg.setdefault("backup_count", logging_cfg.get("backup_count", 5))
        logging_cfg.setdefault("include_stage", logging_cfg.get("include_stage", True))
        logging_cfg.setdefault("include_run_id", logging_cfg.get("include_run_id", True))
        logging_cfg.setdefault("include_timestamps", logging_cfg.get("include_timestamps", True))

        # Monitoring defaults
        config_dict.setdefault("monitoring", {})
        monitoring = config_dict["monitoring"]
        monitoring.setdefault("enabled", monitoring.get("enabled", False))
        monitoring.setdefault("endpoint", monitoring.get("endpoint", None))

        # Apply environment variable overrides (high precedence) after
        # file-based merging and any backwards-compatible mapping so that
        # environment variables always take precedence.
        if apply_env_overrides_flag:
            config_dict = _apply_env_overrides(config_dict)

        # Validate with Pydantic PipelineConfig
        config = PipelineConfig(**config_dict)
        return config

    except ValidationError as e:
        raise ConfigurationError(
            f"Configuration validation failed: {e}",
            operation="get_config",
            details={"environment": environment or "development"},
            cause=e,
        ) from e
    except Exception as e:
        raise ConfigurationError(
            f"Configuration loading failed: {e}",
            operation="get_config",
            details={"environment": environment or "development"},
            cause=e,
        ) from e


def reload_config() -> None:
    """Clear configuration cache to force reload on next access."""
    get_config.cache_clear()
