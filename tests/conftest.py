# sbir-etl/tests/conftest.py
#
# Test bootstrap for pytest: ensure repository root is on sys.path so tests can import
# the `src` package without requiring PYTHONPATH to be explicitly set by the caller.
#
# This file is intentionally small and robust: it walks up from the tests directory
# until it finds a likely project root (pyproject.toml, src/ directory, or .git),
# then inserts that path at the front of sys.path.
#
# It also configures a sane default logging level for tests and exposes a simple
# fixture providing the repo root path for use in tests.
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import pytest


def _find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Walk upwards from `start` (defaults to this file's parent) until a likely
    repository root is found. Heuristics:
      - presence of pyproject.toml
      - presence of a `src` directory
      - presence of a .git directory

    Falls back to two levels up from this file if nothing is found.
    """
    if start is None:
        start = Path(__file__).resolve().parent

    current = start
    root_marker_names = ("pyproject.toml", "src", ".git")
    visited = set()
    while True:
        if str(current) in visited:
            break
        visited.add(str(current))
        for marker in root_marker_names:
            if (current / marker).exists():
                return current
        if current.parent == current:
            break
        current = current.parent

    # Fallback: assume project root is one level up (sbir-etl/)
    fallback = Path(__file__).resolve().parents[1]
    return fallback


_repo_root = _find_repo_root()
_repo_root_str = str(_repo_root)

# Insert repo root into sys.path if not already present, at highest priority.
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

# Configure test logging to be moderately verbose by default
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)
logger.debug("Added repository root to sys.path: %s", _repo_root_str)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """
    Return the repository root Path for tests that need to read files relative to the project.
    """
    return _repo_root
