# Skipped Tests Analysis & Refactoring Recommendations

**Generated:** 2025-11-29

## Executive Summary

**Total Skipped Tests:** 30+ across unit, integration, e2e, functional, and validation test suites

**Key Opportunities:**
1. **Parametrization:** 15+ tests can be consolidated using `@pytest.mark.parametrize`
2. **Shared Fixtures:** 10+ tests duplicate fixture setup (S3, Neo4j, data files)
3. **Conditional Skips:** 8+ tests use runtime skips that could be pytest markers
4. **Missing Fixtures:** 5+ tests skip due to missing golden/reference data

---

## Category 1: Data File Dependencies (High Priority)

### Pattern: Tests skip when data files don't exist

**Current Issues:**
- Runtime `pytest.skip()` checks for file existence
- Duplicate file path definitions
- No centralized fixture management

### Tests Affected:

#### USAspending Data (2 tests)
```python
# tests/unit/test_usaspending_index.py
def test_parse_toc_table_dat_map():
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")

def test_extract_naics_sample():
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")
```

#### NAICS Integration (2 tests)
```python
# tests/integration/test_naics_integration.py
def test_naics_enricher_with_real_index():
    if not path.exists():
        pytest.skip("naics index parquet not present")
    if not enr.award_map and not enr.recipient_map:
        pytest.skip("index has no entries")
```

#### BEA Mapping (1 test)
```python
# tests/unit/test_naics_to_bea.py
def test_naics_to_bea_mapping():
    if not Path(bea_csv_path).exists():
        pytest.skip(f"BEA CSV fixture not found: {bea_csv_path}")
```

#### Functional Pipeline Outputs (4 tests)
```python
# tests/functional/test_pipelines.py
def test_transition_outputs_valid_schema():
    if not output_path.exists():
        pytest.skip("Transition output not found")

def test_cet_outputs_valid_schema():
    if not output_path.exists():
        pytest.skip("CET output not found")

def test_fiscal_outputs_valid_schema():
    if not output_path.exists():
        pytest.skip("Fiscal output not found")

def test_paecter_outputs_valid_schema():
    if not output_path.exists():
        pytest.skip("PaECTER output not found")
```

### Recommended Refactoring:

**1. Create Centralized Data Fixtures (conftest.py)**

```python
# tests/conftest.py

import pytest
from pathlib import Path
from typing import Optional

# Data file paths
DATA_PATHS = {
    "usaspending_zip": Path("data/raw/usaspending.zip"),
    "naics_index": Path("data/processed/naics_index.parquet"),
    "bea_mapping": Path("data/reference/naics_to_bea.csv"),
    "transition_output": Path("data/processed/transitions.parquet"),
    "cet_output": Path("data/processed/cet_classifications.parquet"),
    "fiscal_output": Path("data/processed/fiscal_returns.parquet"),
    "paecter_output": Path("data/processed/paecter_embeddings.parquet"),
}

@pytest.fixture
def usaspending_zip() -> Path:
    """Fixture for USAspending zip file."""
    path = DATA_PATHS["usaspending_zip"]
    if not path.exists():
        pytest.skip(f"USAspending data not available: {path}")
    return path

@pytest.fixture
def naics_index() -> Path:
    """Fixture for NAICS index parquet."""
    path = DATA_PATHS["naics_index"]
    if not path.exists():
        pytest.skip(f"NAICS index not available: {path}")
    return path

@pytest.fixture
def bea_mapping() -> Path:
    """Fixture for BEA mapping CSV."""
    path = DATA_PATHS["bea_mapping"]
    if not path.exists():
        pytest.skip(f"BEA mapping not available: {path}")
    return path

@pytest.fixture(params=["transition", "cet", "fiscal", "paecter"])
def pipeline_output(request) -> Path:
    """Parametrized fixture for pipeline outputs."""
    output_type = request.param
    path = DATA_PATHS[f"{output_type}_output"]
    if not path.exists():
        pytest.skip(f"{output_type.upper()} output not available: {path}")
    return path
```

**2. Refactor Tests to Use Fixtures**

```python
# tests/unit/test_usaspending_index.py

def test_parse_toc_table_dat_map(usaspending_zip: Path):
    """Test parsing TOC table from USAspending zip."""
    mapping = parse_toc_table_dat_map(usaspending_zip)
    assert any(k.endswith(".naics") or k == "public.naics" for k in mapping.keys())

def test_extract_naics_sample(usaspending_zip: Path):
    """Test extracting NAICS sample from USAspending zip."""
    mapping = parse_toc_table_dat_map(usaspending_zip)
    dat = mapping.get("public.naics") or mapping.get("naics")
    assert dat is not None
    sample = extract_table_sample(usaspending_zip, dat, n_lines=5)
    assert len(sample) > 0
```

**3. Parametrize Pipeline Output Tests**

```python
# tests/functional/test_pipelines.py

@pytest.mark.parametrize("output_type,required_cols", [
    ("transition", ["award_id", "contract_id", "transition_score", "confidence"]),
    ("cet", ["award_id", "cet_id", "score", "classification"]),
    ("fiscal", ["award_id", "roi", "federal_tax_receipts", "economic_impact"]),
    ("paecter", ["award_id", "patent_id", "similarity_score"]),
])
def test_pipeline_output_schema(output_type: str, required_cols: list[str]):
    """Test that pipeline outputs have valid schema."""
    output_path = Path(f"data/processed/{output_type}_output.parquet")
    if not output_path.exists():
        pytest.skip(f"{output_type} output not found")

    df = pd.read_parquet(output_path)

    # Validate schema
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"

    # Validate data quality
    assert len(df) > 0, "Output is empty"
    assert df[required_cols[0]].notna().all(), f"Null values in {required_cols[0]}"
```

**Impact:** Reduces 9 tests to 2 parametrized tests + shared fixtures

---

## Category 2: AWS/S3 Integration Tests (Medium Priority)

### Pattern: Tests skip without AWS credentials

**Current Issues:**
- Class-level `@pytest.mark.skipif` on 5 test classes
- Duplicate AWS credential checks
- No shared S3 setup/teardown

### Tests Affected:

```python
# tests/integration/test_s3_operations.py

@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Upload:
    def test_upload_small_file(self, ...): ...
    def test_upload_large_file(self, ...): ...

@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Download:
    def test_download_file(self, ...): ...
    def test_download_nonexistent_file(self, ...): ...

@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Fallback:
    def test_fallback_to_local_when_s3_missing(self, ...): ...

@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3PathBuilding:
    def test_build_s3_path_with_bucket(self, ...): ...

@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Permissions:
    def test_can_list_bucket(self, ...): ...
```

### Recommended Refactoring:

**1. Create Custom Pytest Marker**

```python
# tests/conftest.py

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "requires_aws: mark test as requiring AWS credentials"
    )

@pytest.fixture
def aws_credentials():
    """Fixture that skips if AWS credentials not available."""
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS credentials required (set AWS_ACCESS_KEY_ID)")
    return {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }
```

**2. Refactor Test Classes**

```python
# tests/integration/test_s3_operations.py

@pytest.mark.requires_aws
class TestS3Upload:
    """Test S3 upload operations."""

    def test_upload_small_file(self, aws_credentials, s3_client, ...):
        """Test uploading a small file to S3."""
        # Test implementation
        pass

@pytest.mark.requires_aws
class TestS3Download:
    """Test S3 download operations."""

    def test_download_file(self, aws_credentials, s3_client, ...):
        """Test downloading a file from S3."""
        # Test implementation
        pass
```

**3. Add pytest.ini Configuration**

```ini
# pytest.ini

[pytest]
markers =
    requires_aws: Tests requiring AWS credentials
    requires_neo4j: Tests requiring Neo4j connection
    requires_r: Tests requiring R/rpy2
    requires_hf: Tests requiring HuggingFace token
```

**Impact:** Cleaner test organization, easier to run subsets with `-m requires_aws`

---

## Category 3: Optional Dependencies (Medium Priority)

### Pattern: Tests skip when optional packages unavailable

**Current Issues:**
- Inconsistent skip patterns (some use `@pytest.mark.skipif`, others use runtime checks)
- Duplicate import checks
- No centralized dependency fixtures

### Tests Affected:

#### Neo4j Driver (2 tests)
```python
# tests/unit/test_cet_award_relationships.py

HAVE_NEO4J = importlib.util.find_spec("neo4j") is not None

@pytest.mark.skipif(not HAVE_NEO4J, reason="neo4j driver missing")
def test_create_award_cet_relationships_builds_primary_and_supporting(): ...

@pytest.mark.skipif(not HAVE_NEO4J, reason="neo4j driver missing")
def test_create_award_cet_relationships_missing_award_id_skips_and_errors(): ...
```

#### Pandas (2 tests)
```python
# tests/unit/utils/test_date_utils.py

def test_parse_date_pandas_timestamp(self):
    try:
        import pandas as pd
        # test code
    except ImportError:
        pytest.skip("pandas not available")

def test_parse_date_pandas_na(self):
    try:
        import pandas as pd
        # test code
    except ImportError:
        pytest.skip("pandas not available")
```

#### R/rpy2 (2 tests)
```python
# tests/functional/test_pipelines.py

@pytest.mark.skipif(
    not pytest.importorskip("rpy2", reason="R/rpy2 not available"),
    reason="Fiscal analysis requires R",
)
def test_fiscal_run_produces_outputs(): ...

@pytest.mark.skipif(
    not pytest.importorskip("rpy2", reason="R/rpy2 not available"),
    reason="Fiscal analysis requires R",
)
def test_fiscal_outputs_valid_schema(): ...
```

#### Sentence Transformers (2 tests)
```python
# tests/functional/test_pipelines.py

@pytest.mark.skipif(
    not pytest.importorskip("sentence_transformers", reason="sentence-transformers not available"),
    reason="PaECTER requires sentence-transformers",
)
def test_paecter_run_produces_outputs(): ...

@pytest.mark.skipif(
    not pytest.importorskip("sentence_transformers", reason="sentence-transformers not available"),
    reason="PaECTER requires sentence-transformers",
)
def test_paecter_outputs_valid_schema(): ...
```

#### HuggingFace Token (1 test)
```python
# tests/integration/test_paecter_client.py

@pytest.fixture
def paecter_client_api():
    if not os.getenv("HF_TOKEN"):
        pytest.skip("HF_TOKEN environment variable required for API mode")
    # fixture code
```

### Recommended Refactoring:

**1. Create Dependency Check Fixtures**

```python
# tests/conftest.py

import pytest
import importlib.util
from typing import Any

def _check_import(module_name: str) -> bool:
    """Check if a module can be imported."""
    return importlib.util.find_spec(module_name) is not None

@pytest.fixture
def neo4j_driver():
    """Fixture that provides neo4j driver or skips."""
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
    token = os.getenv("HF_TOKEN")
    if not token:
        pytest.skip("HF_TOKEN environment variable required")
    return token
```

**2. Refactor Tests to Use Fixtures**

```python
# tests/unit/test_cet_award_relationships.py

def test_create_award_cet_relationships_builds_primary_and_supporting(neo4j_driver):
    """Test creating award-CET relationships."""
    from src.loaders.neo4j import CETLoader, LoadMetrics
    # Test implementation using neo4j_driver
    pass

# tests/unit/utils/test_date_utils.py

def test_parse_date_pandas_timestamp(pandas_available):
    """Test parsing pandas Timestamp."""
    pd = pandas_available
    ts = pd.Timestamp("2023-01-15")
    result = parse_date(ts)
    assert result == ts

# tests/functional/test_pipelines.py

def test_fiscal_run_produces_outputs(rpy2_available):
    """Test that fiscal pipeline produces expected outputs."""
    # Test implementation
    pass

def test_paecter_run_produces_outputs(sentence_transformers_available):
    """Test that PaECTER pipeline produces expected outputs."""
    # Test implementation
    pass
```

**3. Add Custom Markers**

```python
# tests/conftest.py

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "requires_neo4j: Tests requiring Neo4j driver")
    config.addinivalue_line("markers", "requires_r: Tests requiring R/rpy2")
    config.addinivalue_line("markers", "requires_hf: Tests requiring HuggingFace token")
    config.addinivalue_line("markers", "requires_ml: Tests requiring ML dependencies")
```

**Impact:** Consistent dependency handling, easier to run subsets with markers

---

## Category 4: Large Data/Integration Tests (Low Priority)

### Pattern: Tests skip due to requiring large datasets or complex setup

**Current Issues:**
- Tests marked with permanent skip
- No clear path to enable these tests
- Missing documentation on what's needed

### Tests Affected:

#### NAICS Enricher (2 tests)
```python
# tests/unit/test_naics_enricher.py

def test_build_index_sampled(tmp_path):
    pytest.skip("Test requires large USAspending data - use integration test with fixture")

def test_enrich_awards_with_index(tmp_path):
    pytest.skip("Test requires large USAspending data - use integration test with fixture")
```

#### Transition MVP (3 tests)
```python
# tests/integration/test_transition_mvp_chain.py

@pytest.mark.skip(
    reason="Asset uses get_config() which requires complex mocking for test isolation"
)
def test_contracts_ingestion_reuses_existing_output(tmp_path, monkeypatch): ...

@pytest.mark.skip(
    reason="Asset uses get_config() which requires complex mocking for test isolation"
)
def test_contracts_ingestion_force_refresh(tmp_path, monkeypatch): ...

@pytest.mark.skip(
    reason="Golden fixture file missing: tests/data/transition/golden_transitions.ndjson"
)
def test_transition_mvp_golden(tmp_path, monkeypatch): ...
```

#### CLI Integration (4 tests)
```python
# tests/integration/cli/test_cli_integration.py

@pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
def test_status_summary_command(self, runner: CliRunner): ...

@pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
def test_metrics_latest_command(self, runner: CliRunner): ...

@pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
def test_ingest_dry_run(self, runner: CliRunner): ...

@pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
def test_error_handling(self, runner: CliRunner): ...
```

#### Exception Handling (4 tests)
```python
# tests/integration/test_exception_handling.py

@pytest.mark.skip(reason="Module refactored - see INTEGRATION_TEST_ANALYSIS.md")
def test_company_enricher_missing_column_raises_validation_error(self): ...

@pytest.mark.skip(reason="Module refactored - see INTEGRATION_TEST_ANALYSIS.md")
def test_economic_model_missing_columns_raises_validation_error(self): ...

@pytest.mark.skip(reason="Module refactored - see INTEGRATION_TEST_ANALYSIS.md")
def test_neo4j_loader_without_driver_raises_configuration_error(self): ...

@pytest.mark.skip(reason="Module refactored - see INTEGRATION_TEST_ANALYSIS.md")
def test_validation_error_shows_available_columns(self): ...
```

#### Enrichment Pipeline (1 test)
```python
# tests/integration/test_sbir_enrichment_pipeline.py

@pytest.mark.skip(reason="Test fixture companies don't exist in enrichment data source")
def test_enrichment_pipeline_runs_and_merges_company_data(tmp_path, monkeypatch, sbir_csv_path): ...
```

#### E2E Multi-Source (2 tests)
```python
# tests/e2e/test_multi_source_enrichment.py

def test_real_sbir_with_real_usaspending(self, tmp_path):
    pytest.skip("This test requires real data files. Run with: pytest -m real_data --run-real-data")

def test_real_sbir_with_real_sam_gov(self, tmp_path):
    pytest.skip("This test requires real data files. Run with: pytest -m real_data --run-real-data")
```

#### Fiscal Reference Validation (1 test)
```python
# tests/validation/test_fiscal_reference_validation.py

@pytest.mark.skip(reason="Requires R reference implementation")
def test_validate_against_r_reference(self): ...
```

### Recommended Refactoring:

**1. Create Test Data Generators**

```python
# tests/fixtures/data_generators.py

import pandas as pd
from pathlib import Path
from typing import Optional

def generate_usaspending_sample(
    output_path: Path,
    n_records: int = 1000,
    seed: int = 42
) -> Path:
    """Generate synthetic USAspending data for testing."""
    import random
    random.seed(seed)

    data = {
        "award_id": [f"AWARD_{i:06d}" for i in range(n_records)],
        "recipient_uei": [f"UEI{i:012d}" for i in range(n_records)],
        "naics_code": [random.choice(["541715", "541712", "334111"]) for _ in range(n_records)],
        "award_amount": [random.uniform(50000, 1000000) for _ in range(n_records)],
    }

    df = pd.DataFrame(data)
    df.to_parquet(output_path)
    return output_path

def generate_golden_transitions(
    output_path: Path,
    n_records: int = 100,
    seed: int = 42
) -> Path:
    """Generate golden transition data for testing."""
    import random
    random.seed(seed)

    data = {
        "award_id": [f"AWARD_{i:06d}" for i in range(n_records)],
        "contract_id": [f"CONTRACT_{i:06d}" for i in range(n_records)],
        "transition_score": [random.uniform(0.5, 1.0) for _ in range(n_records)],
        "confidence": [random.choice(["high", "medium", "low"]) for _ in range(n_records)],
    }

    df = pd.DataFrame(data)
    df.to_json(output_path, orient="records", lines=True)
    return output_path
```

**2. Create Setup Fixtures**

```python
# tests/conftest.py

@pytest.fixture
def usaspending_sample(tmp_path):
    """Generate synthetic USAspending sample data."""
    from tests.fixtures.data_generators import generate_usaspending_sample
    return generate_usaspending_sample(tmp_path / "usaspending_sample.parquet")

@pytest.fixture
def golden_transitions(tmp_path):
    """Generate golden transition data."""
    from tests.fixtures.data_generators import generate_golden_transitions
    return generate_golden_transitions(tmp_path / "golden_transitions.ndjson")

@pytest.fixture
def mock_config(tmp_path):
    """Provide mock configuration for asset tests."""
    from src.config.schemas import PipelineConfig

    config = PipelineConfig(
        data_quality={"max_duplicate_rate": 0.10},
        enrichment={"batch_size": 100},
        pipeline={"chunk_size": 1000},
        neo4j={"uri": "bolt://localhost:7687"},
    )
    return config
```

**3. Refactor Tests to Use Fixtures**

```python
# tests/unit/test_naics_enricher.py

def test_build_index_sampled(usaspending_sample):
    """Test building NAICS index from sample data."""
    naics_mod = _load_naics_module()
    NAICSEnricher = naics_mod.NAICSEnricher
    NAICSEnricherConfig = naics_mod.NAICSEnricherConfig

    config = NAICSEnricherConfig(
        usaspending_zip=str(usaspending_sample),
        sample_rate=1.0,
    )
    enr = NAICSEnricher(config)
    enr.build_index()

    assert len(enr.award_map) > 0 or len(enr.recipient_map) > 0

# tests/integration/test_transition_mvp_chain.py

def test_transition_mvp_golden(golden_transitions, mock_config):
    """Compare outputs to golden fixtures."""
    # Test implementation using golden_transitions fixture
    pass
```

**Impact:** Enables previously skipped tests with synthetic data

---

## Category 5: Module Refactoring (Low Priority)

### Pattern: Tests skip because modules were refactored

**Tests Affected:**
- 4 tests in `test_exception_handling.py` marked as "Module refactored"
- 1 test in `test_sbir_enrichment_pipeline.py` marked as "Test fixture companies don't exist"

### Recommended Action:

**Option 1: Update Tests**
- Refactor tests to match new module structure
- Update import paths and function signatures

**Option 2: Remove Tests**
- If functionality is covered elsewhere, remove obsolete tests
- Document removal in commit message

**Option 3: Create New Tests**
- Write new tests for refactored modules
- Use modern patterns (fixtures, parametrization)

---

## Summary of Refactoring Benefits

### Before Refactoring:
- 30+ skipped tests
- Duplicate setup code across test files
- Inconsistent skip patterns
- Hard to run test subsets
- No clear path to enable skipped tests

### After Refactoring:
- **Shared Fixtures:** Centralized in `conftest.py`
- **Parametrization:** 15+ tests consolidated to 5-6 parametrized tests
- **Custom Markers:** Easy to run subsets (`-m requires_aws`, `-m requires_neo4j`)
- **Data Generators:** Synthetic data enables previously impossible tests
- **Consistent Patterns:** All skips use fixtures, not runtime checks

### Estimated Impact:
- **Code Reduction:** ~40% fewer lines in test files
- **Maintainability:** Single source of truth for fixtures
- **Test Coverage:** Enable 10+ previously skipped tests
- **CI/CD:** Easier to configure test subsets in workflows

---

## Implementation Priority

### Phase 1 (High Priority - Week 1)
1. Create centralized data fixtures in `conftest.py`
2. Refactor data file dependency tests (9 tests)
3. Add custom pytest markers

### Phase 2 (Medium Priority - Week 2)
1. Create dependency check fixtures
2. Refactor optional dependency tests (8 tests)
3. Refactor AWS/S3 integration tests (5 test classes)

### Phase 3 (Low Priority - Week 3)
1. Create data generators for synthetic test data
2. Enable large data/integration tests (10+ tests)
3. Update or remove refactored module tests (5 tests)

### Phase 4 (Maintenance - Ongoing)
1. Document fixture usage in test documentation
2. Add examples to CONTRIBUTING.md
3. Update CI/CD workflows to use markers

---

## Example: Complete Refactoring

### Before:

```python
# tests/unit/test_usaspending_index.py

USASPENDING_ZIP = "data/raw/usaspending.zip"

def test_parse_toc_table_dat_map():
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")
    mapping = parse_toc_table_dat_map(USASPENDING_ZIP)
    assert any(k.endswith(".naics") for k in mapping.keys())

def test_extract_naics_sample():
    if not os.path.exists(USASPENDING_ZIP):
        pytest.skip("usaspending zip not present")
    mapping = parse_toc_table_dat_map(USASPENDING_ZIP)
    dat = mapping.get("public.naics")
    assert dat is not None
    sample = extract_table_sample(USASPENDING_ZIP, dat, n_lines=5)
    assert len(sample) > 0
```

### After:

```python
# tests/conftest.py

@pytest.fixture
def usaspending_zip() -> Path:
    """Fixture for USAspending zip file."""
    path = Path("data/raw/usaspending.zip")
    if not path.exists():
        pytest.skip(f"USAspending data not available: {path}")
    return path

# tests/unit/test_usaspending_index.py

def test_parse_toc_table_dat_map(usaspending_zip: Path):
    """Test parsing TOC table from USAspending zip."""
    mapping = parse_toc_table_dat_map(usaspending_zip)
    assert any(k.endswith(".naics") for k in mapping.keys())

def test_extract_naics_sample(usaspending_zip: Path):
    """Test extracting NAICS sample from USAspending zip."""
    mapping = parse_toc_table_dat_map(usaspending_zip)
    dat = mapping.get("public.naics")
    assert dat is not None
    sample = extract_table_sample(usaspending_zip, dat, n_lines=5)
    assert len(sample) > 0
```

**Benefits:**
- ✅ No duplicate file path definitions
- ✅ No runtime skip checks in test body
- ✅ Fixture can be reused across test files
- ✅ Clear dependency declaration in function signature
- ✅ Easier to mock for unit tests

---

## Next Steps

1. **Review this analysis** with the team
2. **Prioritize phases** based on current sprint goals
3. **Create tickets** for each phase
4. **Implement incrementally** to avoid breaking existing tests
5. **Update documentation** as fixtures are added

## Questions to Consider

1. Should we generate synthetic data for all large data tests?
2. Which skipped tests should be removed vs. enabled?
3. Should we add CI jobs for optional dependency tests?
4. How do we handle tests that require external services (Neo4j, S3)?
