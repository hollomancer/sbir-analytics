"""Cross-worktree data path helpers for the UCC pilot.

The pilot's data inputs (form_d_details.jsonl, sbir_ma_events.jsonl) live
in the gitignored data/ dir of the main repo; outputs go alongside. From
worktrees, scripts must read/write that shared dir, not the worktree's
own data/ (which would be empty).

Override via the SBIR_DATA_DIR env var when running from anywhere other
than the main repo.
"""

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path("/Users/hollomancer/projects/sbir-analytics/data")


def data_dir() -> Path:
    """Return the resolved data directory, honoring SBIR_DATA_DIR."""
    override = os.environ.get("SBIR_DATA_DIR")
    return Path(override) if override else DEFAULT_DATA_DIR


def data_path(relative_name: str) -> Path:
    """Return the absolute path for a data file by relative name.

    Rejects absolute paths to prevent accidental escape from data_dir().
    """
    p = Path(relative_name)
    if p.is_absolute():
        raise ValueError(f"data_path arg must be relative, got {relative_name}")
    return data_dir() / p
