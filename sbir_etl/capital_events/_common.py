"""Cross-source helpers for the capital-event timeline builder."""

import os
import re
from datetime import datetime
from pathlib import Path

# Repo-relative default: sbir_etl/capital_events/_common.py is 2 parents
# below the repo root, so the data dir is parents[2] / "data". Matches
# the sbir_etl/ucc/_common.py pattern. Override via SBIR_DATA_DIR env var.
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def data_dir() -> Path:
    """Return the resolved data directory, honoring SBIR_DATA_DIR."""
    override = os.environ.get("SBIR_DATA_DIR")
    return Path(override) if override else DEFAULT_DATA_DIR


def data_path(relative_name: str) -> Path:
    """Return the absolute path for a data file by relative name."""
    p = Path(relative_name)
    if p.is_absolute():
        raise ValueError(f"data_path arg must be relative, got {relative_name}")
    return data_dir() / p


def normalize_date(value: str | None) -> str:
    """Convert various date representations to ISO YYYY-MM-DD.

    Accepts ISO with or without time component, MM/DD/YYYY slash format.
    Returns empty string for None, empty, or unparseable input.
    """
    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # Strip trailing time component
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    # Try ISO first
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            datetime.strptime(s, "%Y-%m-%d")
            return s
        except ValueError:
            return ""
    # Try MM/DD/YYYY
    if "/" in s:
        try:
            return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""
