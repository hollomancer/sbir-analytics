# sbir-models

Standalone Pydantic data models for SBIR analytics pipelines.

This package is **fully standalone** — it only requires `pydantic` and works
without the full `sbir-analytics` dependency tree (no Dagster, DuckDB, spacy, etc.).

## Installation

```bash
pip install sbir-models

# With pandas Timestamp support in date validators:
pip install sbir-models[pandas]
```

## Usage

```python
from sbir_models import Award, Patent, Organization, FederalContract

award = Award(
    award_id="SBIR-2024-001",
    company_name="Acme Corp",
    program="SBIR",
)
```

## Models

- **Award / RawAward** — SBIR/STTR award data with SBIR.gov CSV field aliases
- **Patent / RawPatent / PatentCitation** — USPTO patent data
- **Organization / OrganizationMatch** — Unified entity data (companies, universities, agencies)
- **Company / CompanyMatch / RawCompany** — Company data with SAM.gov enrichment
- **CETClassification / CompanyCETProfile** — Critical & Emerging Technology classification
- **FederalContract / ContractClassification** — Federal contract data for transition detection
- **QualityReport / QualityIssue** — Data quality metrics
- **Transition / TransitionProfile** — SBIR-to-production transition evidence

All models are Pydantic v2 `BaseModel` subclasses with validation and serialization.

## Dependencies

- `pydantic>=2.8.0` (required)
- `pandas>=2.2.0` (optional — for Timestamp support in date parsing)
- `loguru>=0.7.0` (optional — falls back to stdlib logging)
