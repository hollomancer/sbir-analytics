"""Data path helpers for the UCC pilot.

The pilot's data inputs (form_d_details.jsonl, sbir_ma_events.jsonl) and its
outputs live under the configured data root. ``sbir_etl.config.loader.data_root``
resolves it: ``SBIR_ETL__PATHS__DATA_ROOT``, then ``paths.data_root`` in config,
then ``data`` relative to the current working directory.
"""

from pathlib import Path

from sbir_etl.config.loader import data_root


def data_dir() -> Path:
    """Return the configured data root."""
    return data_root()


def data_path(relative_name: str) -> Path:
    """Return the absolute path for a data file by relative name.

    Rejects absolute paths to prevent accidental escape from data_dir().
    """
    p = Path(relative_name)
    if p.is_absolute():
        raise ValueError(f"data_path arg must be relative, got {relative_name}")
    return data_dir() / p
