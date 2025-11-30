# Test Refactoring Implementation Guide

This guide provides concrete steps and code examples for implementing the improvements identified in `TEST_IMPROVEMENT_ANALYSIS.md`.

## 🚀 Quick Start: Phase 1 Implementation

### Step 1: Create Mock Factories (2-3 hours)

Create `tests/mocks/__init__.py`:

```python
"""Shared mock factories for test suite.

Provides reusable mock objects to reduce duplication and improve consistency.
"""

from tests.mocks.neo4j import Neo4jMocks
from tests.mocks.enrichment import EnrichmentMocks
from tests.mocks.config import ConfigMocks

__all__ = ["Neo4jMocks", "EnrichmentMocks", "ConfigMocks"]
```

Create `tests/mocks/neo4j.py`:

```python
"""Mock factories for Neo4j components."""

from unittest.mock import Mock, MagicMock
from typing import Any


class Neo4jMocks:
    """Factory for Neo4j mock objects."""

    @staticmethod
    def driver(verify_connectivity: bool = True, **kwargs) -> Mock:
        """Create a mock Neo4j driver.

        Args:
            verify_connectivity: Whether verify_connectivity() should succeed
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock driver with standard methods configured
        """
        driver = Mock()
        driver.verify_connectivity = Mock(return_value=verify_connectivity)
        driver.close = Mock()
        driver.session = Mock(return_value=Neo4jMocks.session())

        for key, value in kwargs.items():
            setattr(driver, key, value)

        return driver

    @staticmethod
    def session(run_results: list[Any] | None = None, **kwargs) -> Mock:
        """Create a mock Neo4j session.

        Args:
            run_results: Results to return from session.run()
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock session with standard methods configured
        """
        session = Mock()
        session.run = Mock(return_value=run_results or [])
        session.close = Mock()
        session.begin_transaction = Mock(return_value=Neo4jMocks.transaction())

        # Support context manager protocol
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)

        for key, value in kwargs.items():
            setattr(session, key, value)

        return session

    @staticmethod
    def transaction(commit_success: bool = True, **kwargs) -> Mock:
        """Create a mock Neo4j transaction.

        Args:
            commit_success: Whether commit() should succeed
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock transaction with standard methods configured
        """
        tx = Mock()
        tx.run = Mock(return_value=[])
        tx.commit = Mock(return_value=commit_success)
        tx.rollback = Mock()

        for key, value in kwargs.items():
            setattr(tx, key, value)

        return tx

    @staticmethod
    def result(records: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock Neo4j result.

        Args:
            records: Records to return from result iteration
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock result with standard methods configured
        """
        result = Mock()
        result.data = Mock(return_value=records or [])
        result.single = Mock(return_value=records[0] if records else None)
        result.values = Mock(return_value=[list(r.values()) for r in (records or [])])

        # Support iteration
        result.__iter__ = Mock(return_value=iter(records or []))

        for key, value in kwargs.items():
            setattr(result, key, value)

        return result

    @staticmethod
    def config(uri: str = "bolt://localhost:7687", **kwargs) -> Mock:
        """Create a mock Neo4j configuration.

        Args:
            uri: Neo4j connection URI
            **kwargs: Additional config attributes

        Returns:
            Mock config object
        """
        config = Mock()
        config.uri = uri
        config.username = kwargs.get("username", "neo4j")
        config.password = kwargs.get("password", "password")
        config.database = kwargs.get("database", "neo4j")
        config.batch_size = kwargs.get("batch_size", 1000)

        for key, value in kwargs.items():
            if key not in ["username", "password", "database", "batch_size"]:
                setattr(config, key, value)

        return config
```

Create `tests/mocks/enrichment.py`:

```python
"""Mock factories for enrichment components."""

from unittest.mock import Mock
from typing import Any


class EnrichmentMocks:
    """Factory for enrichment mock objects."""

    @staticmethod
    def sam_gov_client(responses: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock SAM.gov API client.

        Args:
            responses: List of responses to return from search()
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock SAM.gov client
        """
        client = Mock()
        client.search = Mock(side_effect=responses or [])
        client.get_entity = Mock(return_value=None)
        client.rate_limit_remaining = 100

        for key, value in kwargs.items():
            setattr(client, key, value)

        return client

    @staticmethod
    def usaspending_client(responses: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock USAspending API client.

        Args:
            responses: List of responses to return from queries
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock USAspending client
        """
        client = Mock()
        client.search_awards = Mock(side_effect=responses or [])
        client.get_award_details = Mock(return_value=None)

        for key, value in kwargs.items():
            setattr(client, key, value)

        return client

    @staticmethod
    def fuzzy_matcher(match_score: float = 0.85, **kwargs) -> Mock:
        """Create a mock fuzzy matcher.

        Args:
            match_score: Default similarity score to return
            **kwargs: Additional attributes to set on the mock

        Returns:
            Mock fuzzy matcher
        """
        matcher = Mock()
        matcher.match = Mock(return_value={"score": match_score, "matched": True})
        matcher.match_batch = Mock(return_value=[])

        for key, value in kwargs.items():
            setattr(matcher, key, value)

        return matcher
```

Create `tests/mocks/config.py`:

```python
"""Mock factories for configuration objects."""

from unittest.mock import Mock
from typing import Any


class ConfigMocks:
    """Factory for configuration mock objects."""

    @staticmethod
    def pipeline_config(**overrides) -> Mock:
        """Create a mock pipeline configuration.

        Args:
            **overrides: Configuration values to override

        Returns:
            Mock pipeline config
        """
        config = Mock()

        # Default values
        config.chunk_size = overrides.get("chunk_size", 10000)
        config.batch_size = overrides.get("batch_size", 1000)
        config.enable_incremental = overrides.get("enable_incremental", True)
        config.timeout_seconds = overrides.get("timeout_seconds", 300)

        # Nested configs
        config.data_quality = ConfigMocks.data_quality_config(
            **overrides.get("data_quality", {})
        )
        config.enrichment = ConfigMocks.enrichment_config(
            **overrides.get("enrichment", {})
        )
        config.neo4j = ConfigMocks.neo4j_config(**overrides.get("neo4j", {}))

        return config

    @staticmethod
    def data_quality_config(**overrides) -> Mock:
        """Create a mock data quality configuration."""
        config = Mock()
        config.max_duplicate_rate = overrides.get("max_duplicate_rate", 0.10)
        config.max_missing_rate = overrides.get("max_missing_rate", 0.15)
        config.min_enrichment_success = overrides.get("min_enrichment_success", 0.90)
        return config

    @staticmethod
    def enrichment_config(**overrides) -> Mock:
        """Create a mock enrichment configuration."""
        config = Mock()
        config.batch_size = overrides.get("batch_size", 100)
        config.max_retries = overrides.get("max_retries", 3)
        config.timeout_seconds = overrides.get("timeout_seconds", 30)
        config.rate_limit_per_second = overrides.get("rate_limit_per_second", 10.0)
        return config

    @staticmethod
    def neo4j_config(**overrides) -> Mock:
        """Create a mock Neo4j configuration."""
        config = Mock()
        config.uri = overrides.get("uri", "bolt://localhost:7687")
        config.username = overrides.get("username", "neo4j")
        config.password = overrides.get("password", "password")
        config.database = overrides.get("database", "neo4j")
        config.batch_size = overrides.get("batch_size", 1000)
        return config
```

### Step 2: Create DataFrame Builders (2-3 hours)

Extend `tests/factories.py`:

```python
"""Factory functions and builders for creating test data objects."""

import pandas as pd
from datetime import date, datetime, timedelta
from typing import Any, Optional
from decimal import Decimal

# ... existing factory classes ...


class DataFrameBuilder:
    """Fluent builder for test DataFrames.

    Provides a clean, readable API for creating test DataFrames with
    sensible defaults and easy customization.

    Example:
        df = DataFrameBuilder.awards(10).with_agency("DOD").with_phase("II").build()
    """

    @staticmethod
    def awards(count: int = 5) -> "AwardDataFrameBuilder":
        """Create an award DataFrame builder."""
        return AwardDataFrameBuilder(count)

    @staticmethod
    def contracts(count: int = 5) -> "ContractDataFrameBuilder":
        """Create a contract DataFrame builder."""
        return ContractDataFrameBuilder(count)

    @staticmethod
    def companies(count: int = 5) -> "CompanyDataFrameBuilder":
        """Create a company DataFrame builder."""
        return CompanyDataFrameBuilder(count)

    @staticmethod
    def patents(count: int = 5) -> "PatentDataFrameBuilder":
        """Create a patent DataFrame builder."""
        return PatentDataFrameBuilder(count)


class AwardDataFrameBuilder:
    """Builder for award DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}
        self.custom_rows = []

    def with_agency(self, agency: str) -> "AwardDataFrameBuilder":
        """Set agency for all awards."""
        self.overrides["agency"] = agency
        return self

    def with_phase(self, phase: str) -> "AwardDataFrameBuilder":
        """Set phase for all awards."""
        self.overrides["phase"] = phase
        return self

    def with_amount_range(self, min_amount: float, max_amount: float) -> "AwardDataFrameBuilder":
        """Set award amount range."""
        self.overrides["amount_range"] = (min_amount, max_amount)
        return self

    def with_date_range(
        self, start_date: date, end_date: date
    ) -> "AwardDataFrameBuilder":
        """Set award date range."""
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def with_naics(self, naics: str) -> "AwardDataFrameBuilder":
        """Set NAICS code for all awards."""
        self.overrides["naics_code"] = naics
        return self

    def with_custom_row(self, **kwargs) -> "AwardDataFrameBuilder":
        """Add a custom row with specific values."""
        self.custom_rows.append(kwargs)
        return self

    def build(self) -> pd.DataFrame:
        """Build the DataFrame."""
        import random

        awards = []

        # Generate standard rows
        for i in range(1, self.count + 1):
            award_data = {
                "award_id": f"TEST-AWARD-{i:03d}",
                "company_name": f"Test Company {i}",
                "award_amount": 100000.0,
                "award_date": date(2023, 1, 1),
                "program": "SBIR",
                "phase": "I",
                "agency": "DOD",
                "branch": "Army",
                "contract": f"C-2023-{i:03d}",
                "abstract": f"Test abstract for award {i}",
                "award_title": f"Test Award Title {i}",
                "company_uei": f"UEI{i:09d}",
                "company_duns": f"{i:09d}",
                "company_address": f"{i} Test St",
                "company_city": "Test City",
                "company_state": "CA",
                "company_zip": "90210",
                "number_of_employees": 10,
                "is_hubzone": False,
                "is_woman_owned": False,
                "is_socially_disadvantaged": False,
            }

            # Apply overrides
            for key, value in self.overrides.items():
                if key == "amount_range":
                    min_amt, max_amt = value
                    award_data["award_amount"] = random.uniform(min_amt, max_amt)
                elif key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    award_data["award_date"] = start + timedelta(days=random_days)
                else:
                    award_data[key] = value

            awards.append(award_data)

        # Add custom rows
        for custom in self.custom_rows:
            award_data = awards[0].copy()  # Use first row as template
            award_data.update(custom)
            awards.append(award_data)

        return pd.DataFrame(awards)


class ContractDataFrameBuilder:
    """Builder for contract DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_agency(self, agency: str) -> "ContractDataFrameBuilder":
        """Set awarding agency for all contracts."""
        self.overrides["awarding_agency_name"] = agency
        return self

    def with_recipient(self, name: str, uei: str) -> "ContractDataFrameBuilder":
        """Set recipient information."""
        self.overrides["recipient_name"] = name
        self.overrides["recipient_uei"] = uei
        return self

    def with_date_range(
        self, start_date: date, end_date: date
    ) -> "ContractDataFrameBuilder":
        """Set action date range."""
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def build(self) -> pd.DataFrame:
        """Build the DataFrame."""
        import random

        contracts = []

        for i in range(1, self.count + 1):
            contract_data = {
                "contract_id": f"CONTRACT-{i:03d}",
                "piid": f"PIID-{i:03d}",
                "recipient_name": f"Test Company {i}",
                "recipient_uei": f"UEI{i:09d}",
                "awarding_agency_name": "DOD",
                "federal_action_obligation": 500000.0,
                "action_date": date(2023, 8, 1),
                "period_of_performance_start_date": date(2023, 8, 1),
                "period_of_performance_current_end_date": date(2024, 8, 1),
            }

            # Apply overrides
            for key, value in self.overrides.items():
                if key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    contract_data["action_date"] = start + timedelta(days=random_days)
                else:
                    contract_data[key] = value

            contracts.append(contract_data)

        return pd.DataFrame(contracts)


class CompanyDataFrameBuilder:
    """Builder for company DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_state(self, state: str) -> "CompanyDataFrameBuilder":
        """Set state for all companies."""
        self.overrides["state"] = state
        return self

    def with_size_range(self, min_employees: int, max_employees: int) -> "CompanyDataFrameBuilder":
        """Set employee count range."""
        self.overrides["size_range"] = (min_employees, max_employees)
        return self

    def build(self) -> pd.DataFrame:
        """Build the DataFrame."""
        import random

        companies = []

        for i in range(1, self.count + 1):
            company_data = {
                "name": f"Test Company {i}",
                "uei": f"UEI{i:09d}",
                "duns": f"{i:09d}",
                "address": f"{i} Test St",
                "city": "Test City",
                "state": "CA",
                "zip": "90210",
                "number_of_employees": 10,
            }

            # Apply overrides
            for key, value in self.overrides.items():
                if key == "size_range":
                    min_emp, max_emp = value
                    company_data["number_of_employees"] = random.randint(min_emp, max_emp)
                else:
                    company_data[key] = value

            companies.append(company_data)

        return pd.DataFrame(companies)


class PatentDataFrameBuilder:
    """Builder for patent DataFrames."""

    def __init__(self, count: int):
        self.count = count
        self.overrides = {}

    def with_grant_date_range(
        self, start_date: date, end_date: date
    ) -> "PatentDataFrameBuilder":
        """Set grant date range."""
        self.overrides["date_range"] = (start_date, end_date)
        return self

    def build(self) -> pd.DataFrame:
        """Build the DataFrame."""
        import random

        patents = []

        for i in range(1, self.count + 1):
            patent_data = {
                "grant_doc_num": f"{5858000 + i}",
                "title": f"Test Patent {i}",
                "abstract": f"Test patent abstract {i}",
                "grant_date": date(2023, 1, 1),
                "assignee_name": f"Test Company {i}",
            }

            # Apply overrides
            for key, value in self.overrides.items():
                if key == "date_range":
                    start, end = value
                    days_diff = (end - start).days
                    random_days = random.randint(0, days_diff)
                    patent_data["grant_date"] = start + timedelta(days=random_days)
                else:
                    patent_data[key] = value

            patents.append(patent_data)

        return pd.DataFrame(patents)
```

### Step 3: Update Existing Tests (Example)

**Before**:
```python
def test_neo4j_connection():
    # Setup
    driver = Mock()
    driver.verify_connectivity = Mock(return_value=True)
    driver.close = Mock()
    session = Mock()
    session.run = Mock(return_value=[])

    # Test
    client = Neo4jClient(driver)
    result = client.query("MATCH (n) RETURN n")

    # Assert
    assert session.run.called
    driver.close.assert_called_once()
```

**After**:
```python
from tests.mocks import Neo4jMocks

def test_neo4j_connection():
    # Setup
    driver = Neo4jMocks.driver()
    session = Neo4jMocks.session()

    # Test
    client = Neo4jClient(driver)
    result = client.query("MATCH (n) RETURN n")

    # Assert
    assert session.run.called
    driver.close.assert_called_once()
```

**Before**:
```python
def test_award_processing():
    df = pd.DataFrame([
        {
            "award_id": "A001",
            "company_name": "Test Co",
            "award_amount": 100000,
            "agency": "DOD",
            "phase": "I",
        },
        {
            "award_id": "A002",
            "company_name": "Test Co 2",
            "award_amount": 150000,
            "agency": "DOD",
            "phase": "I",
        },
    ])

    result = process_awards(df)
    assert len(result) == 2
```

**After**:
```python
from tests.factories import DataFrameBuilder

def test_award_processing():
    df = DataFrameBuilder.awards(2).with_agency("DOD").with_phase("I").build()

    result = process_awards(df)
    assert len(result) == 2
```

## 📋 Migration Checklist

### Phase 1: Foundation (Week 1)
- [ ] Create `tests/mocks/` directory structure
- [ ] Implement `Neo4jMocks` factory
- [ ] Implement `EnrichmentMocks` factory
- [ ] Implement `ConfigMocks` factory
- [ ] Extend `tests/factories.py` with DataFrame builders
- [ ] Add new fixtures to `conftest_shared.py`
- [ ] Document new patterns in `tests/README.md`

### Phase 2: Migration (Week 2-3)
- [ ] Migrate Neo4j tests to use `Neo4jMocks` (50+ files)
- [ ] Migrate enrichment tests to use `EnrichmentMocks` (30+ files)
- [ ] Migrate DataFrame creation to use builders (100+ files)
- [ ] Update test documentation

### Phase 3: Splitting Large Files (Week 4)
- [ ] Split `test_categorization_validation.py` (1513 LOC)
- [ ] Split `test_detector.py` (1085 LOC)
- [ ] Split `test_fiscal_assets.py` (1061 LOC)
- [ ] Split `test_transitions.py` (1040 LOC)
- [ ] Split `test_chunked_enrichment.py` (1030 LOC)

### Phase 4: Quality Improvements (Week 5)
- [ ] Standardize test naming conventions
- [ ] Add missing test markers
- [ ] Improve test documentation
- [ ] Add coverage for identified gaps

## 🎯 Success Metrics

Track these metrics before and after refactoring:

```python
# tests/metrics.py
"""Test suite metrics tracking."""

import subprocess
from pathlib import Path


def count_test_files():
    """Count total test files."""
    return len(list(Path("tests").rglob("test_*.py")))


def count_test_lines():
    """Count total lines of test code."""
    result = subprocess.run(
        ["find", "tests", "-name", "test_*.py", "-exec", "wc", "-l", "{}", "+"],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.strip().split("\n")
    total = int(lines[-1].split()[0])
    return total


def count_mock_usages():
    """Count Mock() usages."""
    result = subprocess.run(
        ["grep", "-r", "Mock()", "tests", "--include=*.py"],
        capture_output=True,
        text=True,
    )
    return len(result.stdout.strip().split("\n"))


def count_dataframe_creations():
    """Count pd.DataFrame creations."""
    result = subprocess.run(
        ["grep", "-r", "pd.DataFrame", "tests", "--include=*.py"],
        capture_output=True,
        text=True,
    )
    return len(result.stdout.strip().split("\n"))


def largest_test_file():
    """Find largest test file."""
    result = subprocess.run(
        ["find", "tests", "-name", "test_*.py", "-exec", "wc", "-l", "{}", "+"],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.strip().split("\n")[:-1]  # Exclude total
    largest = max(lines, key=lambda x: int(x.split()[0]))
    size, path = largest.split(maxsplit=1)
    return int(size), path


if __name__ == "__main__":
    print("Test Suite Metrics")
    print("=" * 50)
    print(f"Total test files: {count_test_files()}")
    print(f"Total test LOC: {count_test_lines():,}")
    print(f"Mock() usages: {count_mock_usages()}")
    print(f"pd.DataFrame creations: {count_dataframe_creations()}")
    size, path = largest_test_file()
    print(f"Largest test file: {size} LOC ({path})")
```

Run before refactoring:
```bash
python tests/metrics.py > tests/metrics_before.txt
```

Run after refactoring:
```bash
python tests/metrics.py > tests/metrics_after.txt
diff tests/metrics_before.txt tests/metrics_after.txt
```

## 📚 Additional Resources

- See `TEST_IMPROVEMENT_ANALYSIS.md` for detailed analysis
- See `tests/README.md` for test organization guidelines
- See `CONTRIBUTING.md` for code quality standards
- See `.kiro/steering/pipeline-orchestration.md` for asset check patterns
