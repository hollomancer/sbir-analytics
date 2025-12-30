# Company Categorization Testing Guide

This guide explains how to test the company categorization system at different levels.

## Prerequisites

1. **Install Dependencies**

   ```bash
   uv sync
   ```

2. **Verify Installation**

   ```bash
   uv run python -c "from src.transformers.company_categorization import classify_contract; print('✓ Imports working')"
   ```

---

## Testing Approaches

### 1. Quick Unit Tests (Fastest)

Run the automated test script:

```bash
uv run python tests/validation/test_categorization_quick.py
```

This tests:

- ✓ Contract classification with various PSC codes
- ✓ Contract type overrides (CPFF, T&M)
- ✓ Description inference with product keywords
- ✓ SBIR phase adjustments
- ✓ Company aggregation logic
- ✓ Confidence level assignment

**Expected Output:**

```console
================================================================================
Company Categorization - Quick Test
================================================================================

1. Testing contract classification - Numeric PSC (Product)
   PSC: 1234
   Result: Product
   Method: psc_numeric
   Confidence: 0.9
   ✓ PASS

... (10 more tests)

✓ ALL TESTS PASSED!
```

---

### 2. Interactive Python REPL Testing

Test individual functions directly:

```python
uv run python
```

```python
>>> from src.transformers.company_categorization import classify_contract

>>> # Test 1: Numeric PSC → Product
>>> contract = {
...     "award_id": "TEST001",
...     "psc": "1234",
...     "contract_type": "FFP",
...     "pricing": "FFP",
...     "award_amount": 100000
... }
>>> result = classify_contract(contract)
>>> print(f"{result.classification} ({result.method}, confidence: {result.confidence})")
Product (psc_numeric, confidence: 0.9)

>>> # Test 2: CPFF override → Service
>>> contract = {
...     "award_id": "TEST002",
...     "psc": "1234",  # Numeric but...
...     "contract_type": "CPFF",  # CPFF overrides to Service
...     "pricing": "CPFF",
...     "award_amount": 200000
... }
>>> result = classify_contract(contract)
>>> print(f"{result.classification} ({result.method})")
Service (contract_type)

>>> # Test 3: Company aggregation
>>> from src.transformers.company_categorization import aggregate_company_classification
>>> contracts = [
...     {"classification": "Product", "award_amount": 300000, "psc": "1234"},
...     {"classification": "Service", "award_amount": 100000, "psc": "R425"}
... ]
>>> company = aggregate_company_classification(contracts, "TEST123", "Test Co")
>>> print(f"{company.classification}: {company.product_pct:.1f}% Product")
Product-leaning: 75.0% Product
```

---

### 3. Integration Testing with USAspending Data

**Option A: Using Sample Data**

1. Create a test dataset with known companies:

```python
uv run python
```

```python
>>> import pandas as pd
>>> from src.extractors.usaspending import DuckDBUSAspendingExtractor
>>> from src.enrichers.company_categorization import retrieve_company_contracts

>>> # Initialize extractor
>>> extractor = DuckDBUSAspendingExtractor(":memory:")

>>> # Test with a real UEI (if you have USAspending data loaded)
>>> contracts = retrieve_company_contracts(
...     extractor,
...     uei="ABC123DEF456"  # pragma: allowlist secret  # Replace with real UEI
... )
>>> print(f"Retrieved {len(contracts)} contracts")
```

**Option B: Using the Validation Dataset**

The spec references a high-volume company dataset at:

```
data/raw/sbir/over-100-awards-company_search_1763075384.csv
```

To test against this dataset:

```python
import pandas as pd
from src.extractors.usaspending import DuckDBUSAspendingExtractor
from src.enrichers.company_categorization import retrieve_company_contracts
from src.transformers.company_categorization import (
    classify_contract,
    aggregate_company_classification
)

# Load validation dataset
companies = pd.read_csv("data/raw/sbir/over-100-awards-company_search_1763075384.csv")
print(f"Loaded {len(companies)} high-volume SBIR companies")

# Test categorization for first company
test_company = companies.iloc[0]
uei = test_company["UEI"]

# Retrieve contracts
extractor = DuckDBUSAspendingExtractor("data/processed/sbir.duckdb")
contracts_df = retrieve_company_contracts(extractor, uei=uei)

# Classify contracts
classified = []
for _, contract in contracts_df.iterrows():
    result = classify_contract(contract.to_dict())
    classified.append(result.model_dump())

# Aggregate to company level
company_result = aggregate_company_classification(
    classified,
    company_uei=uei,
    company_name=test_company.get("Company Name", "Unknown")
)

print(f"\nCompany: {company_result.company_name}")
print(f"Classification: {company_result.classification}")
print(f"Product: {company_result.product_pct:.1f}%")
print(f"Service: {company_result.service_pct:.1f}%")
print(f"Confidence: {company_result.confidence}")
print(f"Total Contracts: {company_result.award_count}")
```

---

### 4. Dagster Asset Testing

**Option A: Via Dagster UI**

1. Start the Dagster dev server:

   ```bash
   uv run dagster dev
   ```

2. Open browser to <http://localhost:3000>

3. Navigate to Assets → `enriched_sbir_companies_with_categorization`

4. Click "Materialize" to run the categorization

5. View results and asset checks:
   - `company_categorization_completeness_check`
   - `company_categorization_confidence_check`

**Option B: Via Python API**

```python
from dagster import build_asset_context, materialize
from src.assets.company_categorization import enriched_sbir_companies_with_categorization
from src.assets.sbir_ingestion import validated_sbir_awards

# Materialize the categorization asset
result = materialize(
    [validated_sbir_awards, enriched_sbir_companies_with_categorization]
)

# Check results
if result.success:
    print("✓ Categorization completed successfully")
else:
    print("✗ Categorization failed")
```

---

### 5. Pytest Integration Tests

Create integration tests in `tests/test_company_categorization.py`:

```python
import pytest
import pandas as pd
from src.transformers.company_categorization import (
    classify_contract,
    aggregate_company_classification
)

@pytest.mark.fast
class TestContractClassification:
    def test_numeric_psc_product(self):
        contract = {
            "award_id": "TEST001",
            "psc": "1234",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 100000
        }
        result = classify_contract(contract)
        assert result.classification == "Product"
        assert result.method == "psc_numeric"
        assert result.confidence == 0.9

    def test_alphabetic_psc_service(self):
        contract = {
            "award_id": "TEST002",
            "psc": "R425",
            "contract_type": "FFP",
            "pricing": "FFP",
            "award_amount": 150000
        }
        result = classify_contract(contract)
        assert result.classification == "Service"
        assert result.method == "psc_alphabetic"

    def test_cpff_override(self):
        contract = {
            "award_id": "TEST003",
            "psc": "1234",  # Numeric
            "contract_type": "CPFF",
            "pricing": "CPFF",
            "award_amount": 200000
        }
        result = classify_contract(contract)
        assert result.classification == "Service"
        assert result.method == "contract_type"

@pytest.mark.fast
class TestCompanyAggregation:
    def test_product_leaning(self):
        contracts = [
            {"classification": "Product", "award_amount": 300000, "psc": "1234"},
            {"classification": "Service", "award_amount": 100000, "psc": "R425"}
        ]
        result = aggregate_company_classification(
            contracts, "TEST123", "Test Co"
        )
        assert result.classification == "Product-leaning"
        assert result.product_pct == 75.0

    def test_uncertain_few_awards(self):
        contracts = [
            {"classification": "Product", "award_amount": 100000, "psc": "1234"}
        ]
        result = aggregate_company_classification(
            contracts, "TEST456", "Test Co 2"
        )
        assert result.classification == "Uncertain"
        assert result.confidence == "Low"
        assert result.override_reason == "insufficient_awards"
```

Run tests:

```bash
uv run pytest tests/test_company_categorization.py -v
```

---

## Validation Checklist

Use this checklist when validating the system:

### Contract Classification

- [ ] Numeric PSC → Product (e.g., "1234")
- [ ] Alphabetic PSC → Service (e.g., "R425")
- [ ] PSC starting with A/B → R&D (e.g., "A123", "B456")
- [ ] CPFF contract type → Service (overrides PSC)
- [ ] T&M pricing → Service (overrides PSC)
- [ ] FFP with "prototype" → Product
- [ ] FFP with "hardware" → Product
- [ ] FFP with "device" → Product
- [ ] SBIR Phase I → R&D (unless numeric PSC)
- [ ] SBIR Phase II → R&D (unless numeric PSC)
- [ ] SBIR Phase III → Standard rules apply

### Company Aggregation

- [ ] ≥51% Product dollars → Product-leaning
- [ ] ≥51% Service/R&D dollars → Service-leaning
- [ ] Neither threshold → Mixed
- [ ] >6 PSC families → Mixed (override)
- [ ] <2 awards → Uncertain
- [ ] ≤2 awards → Low confidence
- [ ] 2-5 awards → Medium confidence
- [ ] >5 awards → High confidence

### Asset Checks

- [ ] Uncertain rate <20%
- [ ] High confidence rate >50%
- [ ] All required fields present
- [ ] No null values in critical fields
- [ ] Confidence levels match award counts

---

## Troubleshooting

### Import Errors

```bash
# Ensure dependencies are installed
uv sync

# Verify PYTHONPATH
export PYTHONPATH=/home/user/sbir-analytics
```

### USAspending Connection Issues

```bash
# Check DuckDB database path
uv run python -c "from src.config.loader import get_config; print(get_config().duckdb.database_path)"

# Verify USAspending dump is loaded
# Check config/base.yaml: paths.usaspending_dump_file
```

### Asset Failures

- Check logs in Dagster UI
- Verify `validated_sbir_awards` asset exists
- Ensure USAspending table has been imported

---

## Next Steps

1. ✓ Run quick unit tests
2. ✓ Test with real USAspending data
3. ✓ Validate against high-volume company dataset
4. ✓ Review asset check results in Dagster UI
5. ✓ Analyze classification distribution
6. ✓ Spot-check 10-20 companies manually

For questions or issues, see: `.kiro/specs/company-categorization/`
