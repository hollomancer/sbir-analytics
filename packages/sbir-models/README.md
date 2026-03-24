# sbir-models

Lightweight Pydantic data models for SBIR analytics pipelines.

## Installation

```bash
pip install sbir-models
```

## Usage

```python
from sbir_models import Award, Patent, Organization

award = Award(award_id="SBIR-2024-001", ...)
```

## Models

- **Award / RawAward** - SBIR/STTR award data
- **Patent / RawPatent / PatentCitation** - USPTO patent data
- **Organization / OrganizationMatch** - Entity data
- **Company / CompanyMatch / RawCompany** - Company data
- **CETClassification / CompanyCETProfile** - Critical & Emerging Technology classification
- **FederalContract / ContractClassification** - Federal contract data
- **QualityReport / QualityIssue** - Data quality metrics
- **TransitionResult** - SBIR-to-production transition evidence

All models are Pydantic v2 `BaseModel` subclasses with validation and serialization.
