# USPTO Patent Assignment Data Dictionary

## Overview

This document describes the fields in the USPTO Patent Assignment data used by the SBIR ETL pipeline. The patent assignment data is sourced from the USPTO Patent Assignment Dataset and contains records of patent transfers, assignments, licenses, and other conveyances.

**Data Source**: [USPTO Patent Assignment Dataset](https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data)
**Update Frequency**: Monthly
**Format**: CSV, Stata (.dta), Parquet

---

## Field Descriptions

### Document Fields

These fields identify and describe the patent document associated with an assignment.

| Field | Data Type | Description | Example | Mandatory | Notes |
|-------|-----------|-------------|---------|-----------|-------|
| **rf_id** | String | Repository-specific record ID; unique identifier for this assignment record | `"D123456"` | Yes | Primary key for PatentAssignment |
| **file_id** | String | File identifier linking related rows (if multi-row records) | `"F123456"` | No | Used to group related rows into single assignment |
| **grant_doc_num** | String | Patent grant number (normalized form) | `"10123456"` | Yes* | *If available; main patent identifier |
| **grant_number** | String | Raw patent number as issued by USPTO | `"10,123,456"` | No | Pre-normalized grant document number |
| **appno_doc_num** | String | Normalized application number | `"2016123456"` | No | Links to patent filing application |
| **application_number** | String | Raw application number | `"16/123,456"` | No | Pre-normalized application number |
| **pgpub_doc_num** | String | Normalized publication number | `"10123456A1"` | No | Publication/patent number (normalized) |
| **publication_number** | String | Raw publication number | `"10123456 A1"` | No | Pre-normalized publication number |
| **title** | String | Full title of the patent | `"Method and Apparatus for Processing Data"` | No | From patent document |
| **abstract** | Text | Patent abstract/summary | Long text (1,000+ chars possible) | No | Technical summary of invention |
| **filing_date** | Date (ISO 8601) | Patent application filing date | `"2016-08-15"` | No | Format: YYYY-MM-DD |
| **publication_date** | Date (ISO 8601) | Patent publication/grant date | `"2018-12-25"` | No | Format: YYYY-MM-DD |
| **grant_date** | Date (ISO 8601) | Patent grant/issue date | `"2018-12-25"` | No | Format: YYYY-MM-DD |
| **language** | String | Language code of patent document | `"ENGLISH"`, `"SPANISH"` | No | ISO 639-1 or USPTO code |

---

### Assignee Fields

These fields describe the entity receiving rights (the "TO" party in an assignment).

| Field | Data Type | Description | Example | Mandatory | Notes |
|-------|-----------|-------------|---------|-----------|-------|
| **assignee_name** | String | Name of company/entity receiving rights | `"Apple Inc."` | Yes | Indexed for search; normalized for matching |
| **assignee_street** | String | Street address of assignee | `"1 Apple Park Way"` | No | May be incomplete or missing |
| **assignee_city** | String | City of assignee | `"Cupertino"` | No | Useful for geographic analysis |
| **assignee_state** | String | State/province code (2-letter US, or full name) | `"CA"`, `"California"` | No | Standardized to state abbreviation in transformer |
| **assignee_postal_code** | String | ZIP code or postal code | `"95014"` | No | Stored as string (may have leading zeros) |
| **assignee_country** | String | Country code or name | `"US"`, `"United States"` | No | Standardized to ISO 3166-1 alpha-2 in transformer |
| **assignee_uei** | String | Unique Entity Identifier (federal identifier) | `"S12AB3CD4EF6"` | No | Enables government contract matching |
| **assignee_duns** | String | DUNS (Data Universal Numbering System) number | `"123456789"` | No | Business identifier system |
| **assignee_cage** | String | CAGE code (Commercial and Government Entity) | `"1A2B3"` | No | Used by DoD and federal procurement |

---

### Assignor Fields

These fields describe the entity transferring rights (the "FROM" party).

| Field | Data Type | Description | Example | Mandatory | Notes |
|-------|-----------|-------------|---------|-----------|-------|
| **assignor_name** | String | Name of entity transferring rights | `"John Smith"`, `"XYZ Corporation"` | Yes | May be individual or organization |
| **assignor_execution_date** | Date (ISO 8601) | Date assignor signed the document | `"2018-10-15"` | No | When rights were transferred |
| **assignor_acknowledgment_date** | Date (ISO 8601) | Date assignor acknowledged before notary | `"2018-10-16"` | No | Notarization date |

---

### Conveyance Fields

These fields describe the nature and terms of the transfer.

| Field | Data Type | Description | Example | Mandatory | Notes |
|-------|-----------|-------------|---------|-----------|-------|
| **conveyance_type** | String (Enum) | Type of transfer/conveyance | `"ASSIGNMENT"`, `"LICENSE"`, `"MERGER"`, `"SECURITY_INTEREST"` | No | Detected/normalized by transformer |
| **conveyance_description** | String | Original conveyance text | `"This is an assignment of patent application..."` | No | Raw description from USPTO record |
| **employer_assign** | Boolean | Whether this is employer assignment (work-for-hire) | `true`, `false` | No | Inferred from assignment text patterns |
| **execution_date** | Date (ISO 8601) | Date agreement was executed/signed | `"2018-10-15"` | No | When rights transfer occurred |
| **recorded_date** | Date (ISO 8601) | Date assignment was recorded with USPTO | `"2018-11-20"` | No | Official recording date; useful for chain analysis |

---

### Administrative Fields

These fields track data provenance and processing state.

| Field | Data Type | Description | Example | Mandatory | Notes |
|-------|-----------|-------------|---------|-----------|-------|
| **source_table** | String | Source data table/file name | `"documentid"`, `"transaction"` | No | Audit trail for ETL |
| **loaded_date** | Timestamp | When record was loaded into Neo4j | `"2025-01-15T14:30:00Z"` | No | Set at load time |
| **extracted_from_rf_id** | String | Reference to parent record (if multi-row) | `"D123456"` | No | Links to original USPTO record |

---

## Data Quality Notes

### Field Coverage and Completeness

- **Always present**: `rf_id`, `assignee_name`, `conveyance_description`, `recorded_date`
- **Frequently present** (>95%): `grant_doc_num`, `assignor_name`, `execution_date`
- **Often missing** (50-80%): UEI, DUNS, CAGE codes, assignor_acknowledgment_date
- **Rarely present** (<5%): `abstract`, `language` (not always digitized)

### Known Data Issues

1. **Incomplete Addresses**: Street addresses may be truncated or abbreviated
2. **Duplicate/Variant Names**: Same entity with multiple name variations (e.g., "Corp." vs "Corporation")
3. **Missing Dates**: Some historical records lack execution or acknowledgment dates
4. **Formatting Inconsistencies**: Patent numbers may appear with or without commas (10,123,456 vs 10123456)
5. **Language Variations**: Foreign patents may have translated or transliterated fields

### Normalization Applied by Transformer

The transformer applies the following normalizations (see `src/transformers/patent_transformer.py`):

- **Identifiers**: Remove punctuation, convert to uppercase
- **Names**: Collapse whitespace, normalize punctuation (commas/periods/ampersands → spaces)
- **Dates**: Parse multiple formats (ISO 8601, MM/DD/YYYY, etc.) to standard ISO format
- **Geographic Fields**: Standardize state abbreviations, country codes
- **Conveyance Detection**: Analyze description text to classify assignment type

---

## Relationships in Neo4j

Once loaded into Neo4j, these fields support the following relationship patterns:

| Relationship | From | To | Key Field | Via Field |
|--------------|------|-----|-----------|-----------|
| **ASSIGNED_VIA** | Patent | PatentAssignment | `grant_doc_num` | `rf_id` |
| **ASSIGNED_FROM** | PatentAssignment | PatentEntity (assignor) | `rf_id` | `assignor_name` |
| **ASSIGNED_TO** | PatentAssignment | PatentEntity (assignee) | `rf_id` | `assignee_name` |
| **CHAIN_OF** | PatentAssignment | PatentAssignment (next) | `rf_id` | Temporal order by `recorded_date` |
| **OWNS** | Company | Patent | `assignee_name` | `grant_doc_num` |
| **GENERATED_FROM** | Patent | Award | `grant_doc_num` | SBIR award linkage |

---

## Example Records

### Simple Assignment

```json
{
  "rf_id": "D42001234",
  "file_id": null,
  "grant_doc_num": "11123456",
  "title": "Programmable Logic Array",
  "filing_date": "2019-03-15",
  "publication_date": "2021-06-22",
  "assignee_name": "Acme Technologies Inc.",
  "assignee_city": "San Jose",
  "assignee_state": "CA",
  "assignor_name": "Jane Doe",
  "conveyance_type": "ASSIGNMENT",
  "execution_date": "2021-05-20",
  "recorded_date": "2021-06-28"
}
```

### Complex Multi-Party Assignment

```json
{
  "rf_id": "D42001235",
  "file_id": "F42001235",
  "grant_doc_num": "11654321",
  "title": "Machine Learning Algorithm for Medical Imaging",
  "assignee_name": "BigPharmaCorp LLC",
  "assignee_uei": "X1Y2Z3A4B5C6",
  "assignee_country": "US",
  "assignor_name": "Research Institute XYZ",
  "conveyance_type": "ASSIGNMENT",
  "conveyance_description": "ASSIGNMENT OF PATENT/APPLICATION; ASSIGNOR: RESEARCH INSTITUTE...",
  "employer_assign": true,
  "execution_date": "2022-02-10",
  "recorded_date": "2022-03-15"
}
```

---

## Usage in SBIR Pipeline

### Extraction (Stage 1)

- **Input**: Raw USPTO CSV/Stata files from `data/raw/uspto/`
- **Output**: `PatentAssignment` Pydantic models with normalized fields
- **Config**: `config/base.yaml` → `extraction.uspto.*`

### Transformation (Stage 4)

- **Input**: Raw `PatentAssignment` models
- **Output**: Normalized, validated, deduplicated records ready for Neo4j
- **Key Functions**:
  - Entity name normalization (fuzzy matching tolerance: 0.85)
  - Conveyance type detection (heuristic patterns)
  - Geographic standardization
- **Config**: `config/base.yaml` → `transformation.patent_*`

### Loading (Stage 5)

- **Input**: Transformed assignments from `data/transformed/uspto/`
- **Output**: Neo4j graph nodes and relationships
- **Nodes Created**: Patent, PatentAssignment, PatentEntity
- **Checks**: Load success ≥ 99%, cardinality validation
- **Config**: `config/base.yaml` → `loading.neo4j.*` and `extraction.uspto.neo4j_*`

---

## References

- [USPTO Patent Assignment Data - Official Documentation](https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data)
- [Pydantic Models](../../src/models/uspto_models.py)
- [USPTO Extractor](../../src/extractors/uspto_extractor.py)
- [Patent Transformer](../../src/transformers/patent_transformer.py)
- [Patent Loader](../../src/loaders/patent_loader.py)
- [Neo4j Schema Documentation](../../schemas/patent-neo4j-schema.md)
