"""Configuration loaders for CET taxonomy and hyperparameters."""

# Import PaECTERClientConfig from parent ml.config.py module
# Use a relative import that avoids the config package
import importlib.util
from pathlib import Path

from .taxonomy_loader import ClassificationConfig, TaxonomyConfig, TaxonomyLoader


_parent_dir = Path(__file__).parent.parent
_config_py = _parent_dir / "config.py"
if _config_py.exists():
    _spec = importlib.util.spec_from_file_location("_ml_config", _config_py)
    if _spec is not None:  # type: ignore[misc]
        _ml_config_module = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        if _spec.loader is not None:  # type: ignore[misc]
            _spec.loader.exec_module(_ml_config_module)  # type: ignore[union-attr]
    PaECTERClientConfig = _ml_config_module.PaECTERClientConfig
    del _spec, _ml_config_module  # Clean up
else:
    # Fallback: raise error
    raise ImportError(f"Could not find {_config_py} to import PaECTERClientConfig")


__all__ = [
    "ClassificationConfig",
    "TaxonomyConfig",
    "TaxonomyLoader",
    "PaECTERClientConfig",
]
