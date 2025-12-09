"""Configuration loading utilities."""

from src.config.loader import get_config, load_config_from_files


def load_config():
    """Convenience function to load config with default paths.

    For use in notebooks and scripts where you don't need to specify paths.
    """
    return get_config()


__all__ = ["load_config", "load_config_from_files", "get_config"]
