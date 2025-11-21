# sbir-analytics/tests/conftest.py
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

import sys
from pathlib import Path

import pytest
from loguru import logger


def _find_repo_root(start: Path | None = None) -> Path:
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

    # Fallback: assume project root is one level up (sbir-analytics/)
    fallback = Path(__file__).resolve().parents[1]
    return fallback


_repo_root = _find_repo_root()
_repo_root_str = str(_repo_root)

# Insert repo root into sys.path if not already present, at highest priority.
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

# Configure test logging using loguru for consistency with application code
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} {level} {name}: {message}",
)

logger.debug("Added repository root to sys.path: {}", _repo_root_str)


# Pytest Configuration
# ===================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "fast: Fast unit tests that should complete in < 1 second",
    )
    config.addinivalue_line(
        "markers",
        "slow: Slow tests that may take > 1 second to complete",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests that require external services",
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests that test full pipeline",
    )
    config.addinivalue_line(
        "markers",
        "real_data: Tests that require real data files (may be large)",
    )
    config.addinivalue_line(
        "markers",
        "transition: Tests related to transition detection",
    )
    config.addinivalue_line(
        "markers",
        "fiscal: Tests related to fiscal analysis",
    )
    config.addinivalue_line(
        "markers",
        "cet: Tests related to CET classification",
    )
    config.addinivalue_line(
        "markers",
        "neo4j: Tests that require Neo4j database",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """
    Return the repository root Path for tests that need to read files relative to the project.
    """
    return _repo_root


# SBIR Data Fixtures
# ===================


@pytest.fixture(scope="session")
def sbir_sample_csv_path(repo_root: Path) -> Path:
    """
    Path to the small SBIR sample CSV fixture (100 records).
    Use for fast unit and integration tests.
    """
    path = repo_root / "tests" / "fixtures" / "sbir_sample.csv"
    if not path.exists():
        pytest.skip(f"SBIR sample fixture not found at {path}")
    return path


@pytest.fixture(scope="session")
def sbir_award_data_csv_path(repo_root: Path) -> Path:
    """
    Path to the real SBIR award_data.csv file (full dataset, ~381MB).

    This file is stored in Git LFS at data/raw/sbir/award_data.csv.
    Tests using this fixture should be marked with @pytest.mark.slow or @pytest.mark.real_data
    as they may take longer to run.

    If the file is not available (LFS not pulled), the test will be skipped.
    """
    path = repo_root / "data" / "raw" / "sbir" / "award_data.csv"
    if not path.exists():
        pytest.skip(f"Real SBIR award data not found at {path}. Run 'git lfs pull' to fetch.")
    # Check if it's an LFS pointer file (< 200 bytes typically)
    if path.stat().st_size < 200:
        pytest.skip(
            f"SBIR award data at {path} appears to be a Git LFS pointer. Run 'git lfs pull' to fetch the actual file."
        )
    return path


@pytest.fixture(scope="session")
def sbir_company_csv_paths(repo_root: Path) -> dict[str, Path]:
    """
    Paths to real SBIR company search CSV files, organized by agency/category.

    Returns a dictionary mapping agency identifiers to their respective CSV paths:
    - 'nsf': NSF company data
    - 'nasa': NASA company data
    - 'dow_af': DOD Air Force company data
    - 'dow_army_navy': DOD Army/Navy company data
    - 'dow_other': DOD other company data
    - 'hhs_nih': HHS/NIH company data
    - 'nih_other': NIH other company data
    - 'other': Other agencies company data

    Files are stored in Git LFS. If not available, the fixture returns an empty dict.
    """
    data_dir = repo_root / "data" / "raw" / "sbir"

    # Map friendly names to actual filenames
    file_mapping = {
        "nsf": "nsf-company_search_1762794217.csv",
        "nasa": "nasa-company_search_1762794301.csv",
        "hhs_nih": "hhs-nih-company_search_1762794442.csv",
        "nih_other": "nih-other-company_search_1762794533.csv",
        "dow_af": "dow-af-company_search_1762794564.csv",
        "dow_other": "dow-other-company_search_1762794672.csv",
        "dow_army_navy": "dow-army-navy-company_search_1762794752.csv",
        "other": "other-company_search_1762793931.csv",
    }

    result = {}
    for key, filename in file_mapping.items():
        path = data_dir / filename
        if path.exists() and path.stat().st_size >= 200:  # Not an LFS pointer
            result[key] = path

    return result


@pytest.fixture(scope="function")
def use_real_sbir_data(request) -> bool:
    """
    Determine whether to use real SBIR data or sample fixtures.

    Returns True if:
    - Test is marked with @pytest.mark.real_data
    - Environment variable USE_REAL_SBIR_DATA=1 is set

    Otherwise returns False (use sample fixtures).
    """
    import os

    # Check for marker
    has_marker = request.node.get_closest_marker("real_data") is not None

    # Check environment variable
    env_flag = os.getenv("USE_REAL_SBIR_DATA", "").lower() in ("1", "true", "yes")

    return has_marker or env_flag


@pytest.fixture(scope="function")
def sbir_csv_path(
    use_real_sbir_data: bool,
    sbir_sample_csv_path: Path,
    sbir_award_data_csv_path: Path,
) -> Path:
    """
    Smart fixture that returns either sample or real SBIR data path.

    Automatically selects:
    - Real data if test is marked with @pytest.mark.real_data or USE_REAL_SBIR_DATA=1
    - Sample data otherwise (fast tests)

    Usage in tests:
        def test_my_feature(sbir_csv_path):
            df = pd.read_csv(sbir_csv_path)
            # Test will use sample by default, or real data when marked
    """
    return sbir_award_data_csv_path if use_real_sbir_data else sbir_sample_csv_path
