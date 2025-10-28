# Federal Contracts Extractor

This module extracts federal contract data from USAspending.gov PostgreSQL database dumps for SBIR Phase III transition detection.

## Overview

The `ContractExtractor` processes the `transaction_normalized` table from USAspending dumps, filtering for:
1. **Contract transactions only** (type codes 'A' and 'B')
2. **SBIR vendor matches** (by UEI, DUNS, or company name)

## Key Features

- **Streaming processing**: Memory-efficient handling of 200GB+ database dumps
- **Vendor filtering**: Only extracts contracts for ~37K SBIR awardees
- **Batch processing**: Configurable batch size (default 10K records)
- **Deobligation handling**: Preserves negative obligation amounts (see ADR-001)

## USAspending Data Structure

### Transaction Types

The `type` field (column 4, index 3) in transaction_normalized:
- `'A'` - Contract (procurement) ✓ **WE EXTRACT THIS**
- `'B'` - IDV Contract (Indefinite Delivery Vehicle) ✓ **WE EXTRACT THIS**
- `'C'` - Grant (NOT a contract)
- `'D'` - Direct Payment (NOT a contract)
- `'02'-'11'` - Financial assistance (grants, loans, insurance)

### Column Mapping

Based on observed structure of file `5530.dat.gz`:

| Column | Field | Notes |
|--------|-------|-------|
| 0 | transaction_id | Unique transaction ID |
| 1 | generated_unique_award_id | Award identifier |
| 2 | action_date | Format: YYYYMMDD |
| 3 | **type** | **Contract type (A/B = contracts)** |
| 4 | action_type | New, Revision, Continuation, etc. |
| 9 | recipient_name | Vendor name |
| 10 | recipient_unique_id | UEI (12 chars) or DUNS (9 digits) |
| 12 | awarding_agency_name | Agency |
| 14 | awarding_sub_tier_agency_name | Sub-agency |
| 28 | piid | Procurement Instrument ID |
| 29 | federal_action_obligation | **Amount (can be negative)** |

## Negative Obligation Amounts

**Important**: The `obligation_amount` field can be negative, representing deobligations (contract reductions).

- **Frequency**: ~0.03% of contract transactions
- **Meaning**: Contract modifications that reduce obligated funds
- **Handling**: Preserved as negative values; `is_deobligation=True` flag set

See [ADR-001: Allow Negative Obligation Amounts](../../docs/decisions/ADR-001-negative-obligations.md) for the decision rationale.

### Working with Deobligations

```python
# Example: Get all contract activity (including deobligations)
all_contracts = extractor.extract_from_dump(...)

# Example: Filter positive obligations only
positive_contracts = [c for c in contracts if not c.is_deobligation]

# Example: Calculate net contract value
net_value = sum(c.obligation_amount for c in contracts)

# Example: Get contract count regardless of modifications
contract_count = len(contracts)
```

## Usage

### Basic Extraction

```python
from pathlib import Path
from src.extractors.contract_extractor import ContractExtractor

# Initialize with vendor filters
extractor = ContractExtractor(
    vendor_filter_file=Path("sbir_vendor_filters.json"),
    batch_size=10000
)

# Extract from dump
num_contracts = extractor.extract_from_dump(
    dump_dir=Path("/path/to/pruned_data_store_api_dump"),
    output_file=Path("contracts.parquet"),
    table_files=["5530.dat.gz"]  # transaction_normalized table
)

print(f"Extracted {num_contracts} contracts")
```

### Vendor Filter Format

```json
{
  "uei": ["UEI1234567890", "UEI9876543210"],
  "duns": ["123456789", "987654321"],
  "company_names": ["ACME CORPORATION", "TECH INNOVATIONS INC"]
}
```

## Performance

On external SSD (USB 3.0):
- **Processing speed**: ~100,000 records/second
- **Subset (17GB)**: ~2-3 minutes for full extraction
- **Full database (200GB)**: ~30-40 minutes (estimated)

## Output Format

Parquet file with columns:
- contract_id (str)
- agency (str)
- sub_agency (str)
- vendor_name (str)
- vendor_uei (str)
- vendor_cage (str)
- vendor_duns (str)
- start_date (date)
- end_date (date)
- obligation_amount (float) - **Can be negative**
- is_deobligation (bool) - **True if negative**
- competition_type (str)
- description (str)
- metadata (json)

## Known Limitations

1. **CAGE codes**: Column not yet identified in dump structure
2. **Competition type**: Column not yet identified
3. **Period of performance dates**: Using action_date as proxy for start_date
4. **Modification chains**: Not linking modifications to base contracts

These will be addressed in future iterations.

## Related Files

- **Model**: `src/models/transition_models.py` - `FederalContract` class
- **Tests**: `tests/unit/test_contract_extractor.py`
- **Decision Records**: `docs/decisions/ADR-001-negative-obligations.md`
- **Task Plan**: `tasks.md` - Task 5: Federal Contracts Ingestion
