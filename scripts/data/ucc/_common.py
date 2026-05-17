"""Cross-worktree data path helpers for the UCC pilot.

The pilot's data inputs (form_d_details.jsonl, sbir_ma_events.jsonl) live
in the gitignored data/ dir of the repo; outputs go alongside.

Default: the repo's own data/ directory (resolved relative to this file).
Override via the SBIR_DATA_DIR env var to point at a shared dir (e.g.,
the main repo's data/) when running from a worktree without its own copy.
"""

import os
from pathlib import Path

# Repo root's data/ dir, resolved from this file's location:
#   scripts/data/ucc/_common.py → repo_root/data
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


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
