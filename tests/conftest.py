# sbir-analytics/tests/conftest.py
#
# Test bootstrap for pytest: ensure repository root is on sys.path so tests can import
# the `src` package without requiring PYTHONPATH to be explicitly set by the caller.
#
# Fixture Organization:
# - This file: Core fixtures (repo_root, config, data paths, dependency checks)
# - tests/conftest_shared.py: Domain fixtures (Neo4j, enrichment, fiscal, transition)
#   Import these explicitly in subdirectory conftest.py files as needed.
# - tests/factories.py: Test data factories (AwardFactory, DataFrameBuilder)
# - tests/mocks/: Mock factories (Neo4jMocks, ConfigMocks, etc.)
#
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
    config.addinivalue_line(
        "markers",
        "requires_aws: Tests requiring AWS credentials",
    )
    config.addinivalue_line(
        "markers",
        "requires_neo4j: Tests requiring Neo4j driver",
    )
    config.addinivalue_line(
        "markers",
        "requires_r: Tests requiring R/rpy2",
    )
    config.addinivalue_line(
        "markers",
        "requires_hf: Tests requiring HuggingFace token",
    )
    config.addinivalue_line(
        "markers",
        "requires_ml: Tests requiring ML dependencies",
    )
    config.addinivalue_line(
        "markers",
        "s3: Tests requiring S3 access",
    )
    config.addinivalue_line(
        "markers",
        "unit: Pure unit tests with no I/O",
    )
    config.addinivalue_line(
        "markers",
        "smoke: Quick smoke tests for CI",
    )
    config.addinivalue_line(
        "markers",
        "regression: Regression tests for known bugs",
    )
    config.addinivalue_line(
        "markers",
        "performance: Performance/benchmark tests",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """
    Return the repository root Path for tests that need to read files relative to the project.
    """
    return _repo_root


# Cached Test Data Fixtures
# =========================


@pytest.fixture(scope="session")
def cached_sbir_sample_df(sbir_sample_csv_path: Path):
    """
    Load SBIR sample CSV once per session and cache in memory.
    Significantly faster than reloading for each test.
    """
    import pandas as pd

    return pd.read_csv(sbir_sample_csv_path)


@pytest.fixture(scope="session")
def cached_test_companies():
    """
    Generate test company data once per session.
    Reused across multiple tests to avoid regeneration overhead.
    """
    return [
        {"name": "Acme Corp", "uei": "TEST001", "duns": "123456789"},
        {"name": "TechStart Inc", "uei": "TEST002", "duns": "987654321"},
        {"name": "Innovation Labs", "uei": "TEST003", "duns": "456789123"},
    ]


@pytest.fixture(scope="session")
def cached_test_awards():
    """
    Generate test award data once per session.
    Reused across multiple tests to avoid regeneration overhead.
    """
    from datetime import date

    return [
        {
            "award_id": "AWARD001",
            "company_name": "Acme Corp",
            "award_amount": 100000,
            "award_date": date(2023, 1, 15),
            "phase": "Phase I",
        },
        {
            "award_id": "AWARD002",
            "company_name": "TechStart Inc",
            "award_amount": 750000,
            "award_date": date(2023, 6, 20),
            "phase": "Phase II",
        },
    ]


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

    This file is located at data/raw/sbir/award_data.csv.
    Tests using this fixture should be marked with @pytest.mark.slow or @pytest.mark.real_data
    as they may take longer to run.

    If the file is not available, the test will be skipped.
    """
    path = repo_root / "data" / "raw" / "sbir" / "award_data.csv"
    if not path.exists():
        pytest.skip(f"Real SBIR award data not found at {path}")
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

    Files are located in data/raw/sbir/. If not available, the fixture returns an empty dict.
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
        if path.exists():
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


# Neo4j Test Fixtures
# ===================


@pytest.fixture(scope="session")
def neo4j_driver():
    """
    Session-scoped Neo4j driver for tests requiring real database connection.
    Connection is reused across all tests in the session for better performance.

    Tests using this fixture should be marked with @pytest.mark.neo4j
    """
    import os
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")

    yield driver
    driver.close()


@pytest.fixture
def neo4j_session(neo4j_driver):
    """
    Function-scoped Neo4j session that cleans up after each test.
    Provides isolated test environment while reusing connection pool.
    """
    with neo4j_driver.session() as session:
        yield session
        # Cleanup: delete all test data
        session.run("MATCH (n) WHERE n.test_marker = true DETACH DELETE n")


# Configuration Fixtures
# ======================


@pytest.fixture(scope="session")
def test_config():
    """
    Load test configuration once per session.
    Cached to avoid repeated file I/O.
    """
    from src.config.loader import get_config

    return get_config()


# Temporary Directory Fixtures
# ============================


@pytest.fixture(scope="session")
def session_tmp_dir(tmp_path_factory):
    """
    Session-scoped temporary directory for shared test artifacts.
    Useful for caching expensive computations across tests.
    """
    return tmp_path_factory.mktemp("session_data")


# Mock Fixtures
# =============


@pytest.fixture
def mock_context():
    """
    Shared mock Dagster execution context with logging.
    Uses ContextMocks factory for consistency.
    """
    from tests.mocks import ContextMocks

    return ContextMocks.context_with_logging()


@pytest.fixture
def mock_config():
    """
    Shared mock pipeline configuration.
    Uses consolidated config mock utility for consistency.
    """
    from tests.utils.config_mocks import create_mock_pipeline_config

    return create_mock_pipeline_config()


# Data File Fixtures
# ==================


@pytest.fixture
def usaspending_zip(repo_root: Path) -> Path:
    """Fixture for USAspending zip file."""
    path = repo_root / "data" / "raw" / "usaspending.zip"
    if not path.exists():
        pytest.skip(f"USAspending data not available: {path}")
    return path


@pytest.fixture
def naics_index(repo_root: Path) -> Path:
    """Fixture for NAICS index parquet."""
    # Check fixture first, then processed data
    fixture_path = repo_root / "tests" / "fixtures" / "naics_index_sample.parquet"
    processed_path = repo_root / "data" / "processed" / "naics_index.parquet"

    path = fixture_path if fixture_path.exists() else processed_path
    if not path.exists():
        pytest.skip(f"NAICS index not available: {path}")
    return path


@pytest.fixture
def bea_mapping(repo_root: Path) -> Path:
    """Fixture for BEA mapping CSV."""
    path = repo_root / "data" / "reference" / "naics_to_bea.csv"
    if not path.exists():
        pytest.skip(f"BEA mapping not available: {path}")
    return path


@pytest.fixture
def golden_transitions(repo_root: Path) -> Path:
    """Fixture for golden transition data."""
    path = repo_root / "tests" / "data" / "transition" / "golden_transitions.ndjson"
    if not path.exists():
        pytest.skip(f"Golden transitions not available: {path}")
    return path


@pytest.fixture(
    params=["transitions", "cet_classifications", "fiscal_returns", "paecter_embeddings"]
)
def pipeline_output(request, repo_root: Path) -> tuple[str, Path]:
    """Parametrized fixture for pipeline outputs."""
    output_type = request.param
    path = repo_root / "data" / "processed" / f"{output_type}.parquet"
    if not path.exists():
        pytest.skip(f"{output_type} output not available: {path}")
    return output_type, path


# Dependency Check Fixtures
# =========================


def _check_import(module_name: str) -> bool:
    """Check if a module can be imported."""
    import importlib.util

    return importlib.util.find_spec(module_name) is not None


def neo4j_running() -> bool:
    """Check if Neo4j is available and running for testing.

    This is a helper function (not a fixture) for use with pytest.mark.skipif.
    """
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "test"))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


@pytest.fixture
def neo4j_available():
    """Fixture that skips if neo4j driver not available."""
    if not _check_import("neo4j"):
        pytest.skip("neo4j driver not installed")
    from neo4j import GraphDatabase

    return GraphDatabase


@pytest.fixture
def pandas_available():
    """Fixture that skips if pandas not available."""
    if not _check_import("pandas"):
        pytest.skip("pandas not installed")
    import pandas as pd

    return pd


@pytest.fixture
def rpy2_available():
    """Fixture that skips if R/rpy2 not available."""
    if not _check_import("rpy2"):
        pytest.skip("R/rpy2 not installed")
    import rpy2

    return rpy2


@pytest.fixture
def sentence_transformers_available():
    """Fixture that skips if sentence-transformers not available."""
    if not _check_import("sentence_transformers"):
        pytest.skip("sentence-transformers not installed")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


@pytest.fixture
def hf_token():
    """Fixture that provides HuggingFace token or skips."""
    import os

    token = os.getenv("HF_TOKEN")
    if not token:
        pytest.skip("HF_TOKEN environment variable required")
    return token


# AWS Fixtures
# ============


@pytest.fixture
def aws_credentials():
    """Fixture that skips if AWS credentials not available."""
    import os

    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials required (set AWS_ACCESS_KEY_ID)")
    return {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-2"),
    }


# Data Generator Fixtures
# =======================


@pytest.fixture
def usaspending_sample(tmp_path):
    """Generate synthetic USAspending sample data."""
    import pandas as pd
    import random

    random.seed(42)
    n_records = 1000

    data = {
        "award_id": [f"AWARD_{i:06d}" for i in range(n_records)],
        "recipient_uei": [f"UEI{i:012d}" for i in range(n_records)],
        "naics_code": [random.choice(["541715", "541712", "334111"]) for _ in range(n_records)],
        "award_amount": [random.uniform(50000, 1000000) for _ in range(n_records)],
    }

    df = pd.DataFrame(data)
    output_path = tmp_path / "usaspending_sample.parquet"
    df.to_parquet(output_path)
    return output_path


@pytest.fixture
def mock_pipeline_config(tmp_path):
    """Provide mock configuration for asset tests."""
    from src.config.schemas import (
        PipelineConfig,
        DataQualityConfig,
        EnrichmentConfig,
        Neo4jConfig,
    )

    return PipelineConfig(
        data_quality=DataQualityConfig(
            max_duplicate_rate=0.10,
            max_missing_rate=0.15,
            min_enrichment_success=0.90,
        ),
        enrichment=EnrichmentConfig(
            batch_size=100,
            max_retries=3,
            timeout_seconds=30,
        ),
        neo4j=Neo4jConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",  # pragma: allowlist secret
        ),
    )
