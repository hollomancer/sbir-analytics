# SBIR Data Ingestion Proposal - Summary

**Change ID**: `implement-sbir-ingestion`
**Status**: ✅ Validated and ready for approval
**Estimated Effort**: 2-3 days
**Created**: 2025-10-25

---

## Overview

This proposal implements the first production-ready data ingestion pipeline for SBIR awards data, transforming 533,598 raw CSV records into validated, structured data ready for enrichment and Neo4j loading.

## Key Decisions Made

### 1. Award Year Filtering ✅
**Decision**: Ingest all historical data (1983-2025), allow filtering in transformation stage

**Rationale**:
- Provides complete historical context for analysis
- Filtering can be applied downstream based on use case
- Preserves full dataset for research and trend analysis

### 2. Missing UEI/DUNS ✅
**Decision**: Allow null UEI/DUNS, flag for manual enrichment

**Rationale**:
- UEI was introduced in 2022, older awards don't have it
- DUNS is optional for many awards
- Enrichment stage will attempt to fill these gaps via SAM.gov API
- Better to preserve incomplete records than lose them

### 3. Deduplication Strategy ✅
**Decision**: Preserve duplicates in extraction, each becomes separate Award node in Neo4j

**Analysis Results** (from 533K records):
- **151,773** unique Contract IDs
- **9,111** Contract IDs with duplicates (10,494 duplicate records)
- **~95%** of duplicates are Phase I → Phase II progressions for same company
- Contract ID and Agency Tracking Number are reused across phases
- **Unique key**: `(Agency Tracking Number, Phase)` provides 99.2% uniqueness

**Example Duplicate**:
```
Contract: DE-AR0001939
Company: EMVOLON, INC.

Record 1: Phase I  - $304,647   (2024)
Record 2: Phase II - $2,035,181 (2024)
```

**Decision Rationale**:
- Phase progression is valuable business information (tracks company success)
- Each phase is a distinct award with different amounts and dates
- Neo4j graph model can represent this naturally:
  ```
  (Company)-[:RECEIVED_AWARD]->(Phase I Award)
  (Phase I Award)-[:PROGRESSED_TO]->(Phase II Award)
  ```
- Transformation stage creates these relationships
- Extraction preserves data fidelity

### 4. Validation Threshold ✅
**Decision**: Configurable in YAML, default ≥95% pass rate

**Configuration**:
```yaml
# config/base.yaml
data_quality:
  sbir_awards:
    pass_rate_threshold: 0.95  # 95% of records must pass validation
    completeness_threshold: 0.90
    uniqueness_threshold: 0.99
```

**Benefits**:
- Different thresholds for dev/prod environments
- Asset check reads threshold dynamically
- Easy to adjust based on data quality trends

---

## Data Statistics

**Source File**: `data/raw/sbir/awards_data.csv`
- **Records**: 533,598 SBIR/STTR awards
- **File Size**: 364 MB
- **Columns**: 42 fields
- **Date Range**: 1983-2025
- **Unique Companies**: ~151K
- **Agencies**: NSF, DOD, DOE, HHS, NASA, etc.

**Data Dictionary**: `docs/data-dictionaries/sbir_awards_data_dictionary.xlsx`

---

## Implementation Components

### 1. SBIR Data Model
**File**: `src/models/award.py`

42-field Pydantic model:
- Company identification (Company, UEI, DUNS, Address)
- Award details (Title, Abstract, Agency, Phase, Program)
- Financial (Award Amount, Award Year)
- Timeline (Proposal Award Date, Contract End Date)
- Personnel (Contact, PI, RI)
- Business classifications (HUBZone, Woman Owned, etc.)

### 2. CSV Extractor
**File**: `src/extractors/sbir.py`

Features:
- Chunked processing (10,000 records/batch)
- Data type conversion (dates, amounts, booleans)
- Missing value handling
- Column validation
- Extraction metadata tracking

### 3. Validation Rules
**File**: `src/validators/sbir_awards.py`

**Required Field Validation**:
- Company, Award Title, Agency (non-empty)
- Phase: "Phase I", "Phase II", or "Phase III"
- Program: "SBIR" or "STTR"
- Award Year: 1983-2026
- Award Amount: $1 - $10,000,000

**Format Validation**:
- UEI: 12 alphanumeric characters
- DUNS: 9 digits
- Email: RFC 5322 format
- State: 2-letter US codes
- ZIP: 5 or 9 digits

**Business Logic**:
- Award Date ≤ Contract End Date
- Award Year matches Proposal Award Date year

### 4. Dagster Assets
**File**: `src/assets/sbir_ingestion.py`

**Assets**:
1. `raw_sbir_awards` - Extracts CSV data
2. `validated_sbir_awards` - Validates and filters to passing records
3. `sbir_validation_report` - Generates quality report

**Asset Check**:
- `sbir_data_quality_check` - Verifies pass rate ≥ threshold (configurable)

---

## Testing Strategy

### Unit Tests
- SbirAward model validation
- CSV extraction with sample data
- Validation rules (required fields, formats, business logic)
- Configuration schema validation

### Integration Tests
- Full pipeline: CSV → validated DataFrame
- Dagster asset execution
- Quality report generation
- Configuration loading from YAML

### Performance Tests
- Memory usage with 533K records
- Chunked processing efficiency
- Execution time benchmarks

### Data Quality Tests
- Validation against real SBIR records
- Edge cases (missing fields, old awards, max amounts)
- Pass rate threshold enforcement

---

## File Organization

**Created Files**:
```
openspec/changes/implement-sbir-ingestion/
├── proposal.md                          # This proposal
├── tasks.md                             # 48 implementation tasks
├── PROPOSAL_SUMMARY.md                  # This summary
└── specs/
    └── data-extraction/
        └── spec.md                      # 6 new requirements, 18 scenarios

data/raw/sbir/
└── awards_data.csv                      # 533K SBIR awards (364MB)

docs/data-dictionaries/
└── sbir_awards_data_dictionary.xlsx    # Field definitions
```

**Files to Create** (during implementation):
```
src/
├── extractors/
│   └── sbir.py                          # SBIR CSV extractor
├── models/
│   └── award.py                         # Enhanced SbirAward model
├── validators/
│   └── sbir_awards.py                   # SBIR validation rules
└── assets/
    └── sbir_ingestion.py                # Dagster assets

tests/
├── unit/
│   ├── test_sbir_award_model.py
│   ├── test_sbir_extractor.py
│   ├── test_sbir_validators.py
│   └── test_sbir_config.py
├── integration/
│   └── test_sbir_ingestion_assets.py
└── fixtures/
    └── sbir_sample.csv                  # 100 test records

config/
└── base.yaml                            # Updated with SBIR config

docs/
└── sbir_ingestion.md                    # Documentation
```

---

## Next Steps

1. **Approval**: Review and approve this proposal
2. **Implementation**: Follow 48 tasks in `tasks.md`
3. **Testing**: Run full test suite
4. **Validation**: Execute with real 533K dataset
5. **Documentation**: Update README and create usage guide

---

## Questions?

Review the full proposal:
```bash
cd /Users/conradhollomon/projects/sbir-analytics
openspec show implement-sbir-ingestion
```

View implementation tasks:
```bash
cat openspec/changes/implement-sbir-ingestion/tasks.md
```

Validate proposal:
```bash
openspec validate implement-sbir-ingestion --strict
```

---

**Status**: ✅ Proposal validated and ready for implementation
