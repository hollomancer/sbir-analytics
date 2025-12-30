# USPTO Patent Assignment Table Schemas and Relationships

## Overview

The USPTO maintains patent assignment data across five interdependent Stata tables linked via the `rf_id` (reel/frame identifier). This document provides detailed schema documentation for each table, relationships, and integration with the SBIR ETL pipeline.

### Data Volume

- `assignment.dta`: 780MB (~5-7M records) - Core assignment records
- `documentid.dta`: 1.6GB (~5-7M records) - Patent document metadata
- `assignee.dta`: 892MB (~8-10M records) - Assignment recipients
- `assignor.dta`: 620MB (~8-10M records) - Assignment originators
- `assignment_conveyance.dta`: 158MB (~5-7M records) - Conveyance type classification

**Total Compressed**: 6.3GB → Estimated ~30M entities after full expansion

---

## 1. Core Assignment Table (`assignment.dta`)

### Purpose

Records patent assignment transactions, including correspondent information, reel/frame locations, and raw conveyance description text.

### Schema

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `rf_id` | int32 | No | **Primary Key** - Reel/Frame Identifier, uniquely identifies this assignment | 12800340 |
| `file_id` | int8 | No | File sequence (always 1 in current data) | 1 |
| `cname` | object (str) | No | Correspondent name (law firm or individual handling assignment) | "OBLON, FISHER, SPIVAK," |
| `caddress_1` | object (str) | No | Correspondent address line 1 (street/suite) | "500 GOULD DRIVE" |
| `caddress_2` | object (str) | No | Correspondent address line 2 (city/state/zip) | "ACTON, MA 01720" |
| `caddress_3` | object (str) | Yes | Correspondent address line 3 (optional) | NULL |
| `caddress_4` | object (str) | Yes | Correspondent address line 4 (country, optional) | NULL |
| `reel_no` | int32 | No | USPTO reel number (filing location) | 5023 |
| `frame_no` | int16 | No | Frame within reel (record position) | 234 |
| `convey_text` | object (str) | Yes | Raw conveyance description (fee text, notes) | "ASSIGNMENT OF PATENT" |

### Key Characteristics

- **Primary Key**: `rf_id` uniquely identifies each assignment transaction
- **Grain**: One row per assignment transaction
- **Completeness**: ~100% non-null for key fields (rf_id, cname, addresses, reel_no, frame_no)
- **Cardinality**: ~5-7M unique rf_id values
- **Relationship**: One-to-many with documentid (one assignment can cover multiple patents)
- **Historical Note**: The `convey_text` field contains brief summaries; full conveyance type is in `assignment_conveyance.dta`

### Data Quality Notes

- Correspondent names have **significant variation** (abbreviated company names, misspellings)
- Address fields are **semi-structured** (no strict parsing, mixed formats)
- `convey_text` values are **sparse** and **inconsistent** (many NULL, varied formats)
- Reel/frame combinations are **unique** (no duplicates observed)

---

## 2. Patent Document Table (`documentid.dta`)

### Purpose

Contains patent metadata linked to assignments, including title, patent numbers (application, publication, grant), and filing dates.

### Schema

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `rf_id` | int32 | No | **Foreign Key** → assignment.rf_id | 12800340 |
| `title` | object (str) | No | Patent title | "METHOD AND APPARATUS FOR CONTROLLING..." |
| `lang` | object (str) | No | Patent language (language code) | "ENGLISH" |
| `appno_doc_num` | object (str) | Yes | Patent application number (formatted) | "2016-123456" |
| `appno_date` | datetime64 | Yes | Application filing date | 2016-01-15 |
| `appno_country` | object (str) | Yes | Application country code | "US" |
| `pgpub_doc_num` | object (str) | Yes | Patent grant/publication number (formatted) | "10,123,456" |
| `pgpub_date` | datetime64 | Yes | Grant/publication date | 2018-11-20 |
| `pgpub_country` | object (str) | Yes | Grant country code | "US" |
| `grant_doc_num` | object (str) | **Yes (~30% NULL)** | Patent grant number (as integer string, used for SBIR linkage) | "10123456" |

### Key Characteristics

- **Foreign Key**: `rf_id` links to assignment.rf_id
- **Grain**: Multiple rows per rf_id (one patent per row; assignments can cover batches)
- **Cardinality**: ~5-7M rows (similar volume to assignment table, some rf_ids have multiple rows)
- **Grant Number Format**: `grant_doc_num` is critical for linking to SBIR awards
  - Format: 7-8 digit patent number (e.g., "10123456")
  - Completeness: ~70% of records have non-NULL grant_doc_num
  - NULL values indicate incomplete processing or pre-grant assignments
- **Dates**: Filing dates more complete (~68%) than publication dates (~0% in sample)
- **Title**: Primary text field for patent topic analysis and keyword matching

### Data Quality Issues

1. **Missing grant_doc_num** (~30% NULL): Limits SBIR linkage capability
   - Mitigation: Use grant_doc_num when available; fall back to pgpub_doc_num for formatting
2. **Publication dates incomplete** (~0% in sample): Affects transition timing analysis
   - Mitigation: Use appno_date as proxy when pgpub_date unavailable
3. **Title length varies** (10-400 characters): Impacts keyword matching accuracy
4. **Language mostly English** (99%+): Some international patents present

### SBIR Linkage Strategy

The `grant_doc_num` field enables direct linking to SBIR awards:

1. SBIR awards database may include patent numbers in free-text fields
2. Exact match: patent.grant_doc_num == sbir_award.patent_number
3. Fuzzy match: Similarity threshold ≥0.80 on grant_doc_num + title
4. Expected linkage rate: 50-70% (many SBIR companies generate patents, not all documented)

---

## 3. Patent Assignee Table (`assignee.dta`)

### Purpose

Records the recipients of patent rights in assignments (companies, individuals, universities).

### Schema

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `rf_id` | int32 | No | **Foreign Key** → assignment.rf_id | 12800340 |
| `ee_name` | object (str) | No | Assignee name (recipient of patent rights) | "IBM CORPORATION" |
| `ee_address_1` | object (str) | No | Assignee address line 1 (street/suite) | "1701 N. STREET NW" |
| `ee_address_2` | object (str) | Yes | Assignee address line 2 (city/state/zip) | "WASHINGTON, DC 20036" |
| `ee_city` | object (str) | Yes | City name (extracted) | "WASHINGTON" |
| `ee_state` | object (str) | Yes | State/province code | "DC" |
| `ee_postcode` | object (str) | Yes | Postal code (ZIP or international) | "20036" |
| `ee_country` | object (str) | Yes | Country code | "US" |

### Key Characteristics

- **Foreign Key**: `rf_id` links to assignment.rf_id
- **Grain**: One row per rf_id per assignee (typically one assignee per assignment)
- **Cardinality**: ~8-10M rows (potential for multiple assignees per assignment)
- **Name Variation**: High variability in company names
  - Legal entity variations ("INTERNATIONAL BUSINESS MACHINES", "IBM", "IBM CORP")
  - Abbreviations and special characters
  - Ownership structure prefixes (parent company vs. subsidiary)
- **Address Completeness**: ~60-70% of records have complete address
- **International Coverage**: ~30% of assignees have non-US addresses

### Data Quality Issues

1. **Name normalization required**: Fuzzy matching threshold ≥0.80 recommended
2. **Address parsing**: Multi-line format requires parsing for standardization
3. **Missing or incomplete addresses**: 30-40% lack full address details
4. **Subsidiary/parent ambiguity**: Need to resolve corporate hierarchies for company linkage

### SBIR Company Linkage

Assignee records enable matching to SBIR companies:

1. Exact match: Normalized ee_name == normalized SBIR_company_name
2. Fuzzy match: ee_name similarity ≥0.85 against SBIR companies
3. Address-based match: Postal code + state match (when full address unavailable)
4. UEI cross-walk: If ee_name has UEI in SBIR database, high-confidence link

---

## 4. Patent Assignor Table (`assignor.dta`)

### Purpose

Records the originators of patent rights in assignments (often inventors, universities, or parent companies).

### Schema

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `rf_id` | int32 | No | **Foreign Key** → assignment.rf_id | 12800340 |
| `or_name` | object (str) | No | Assignor name (originator of patent rights) | "JOHN SMITH" |
| `exec_dt` | datetime64 | Yes (~4% NULL) | Execution date (when assignor signed assignment) | 2020-03-15 |
| `ack_dt` | datetime64 | Yes (~100% NULL in sample) | Acknowledgment date (notary confirmation, rarely used) | NULL |

### Key Characteristics

- **Foreign Key**: `rf_id` links to assignment.rf_id
- **Grain**: Multiple rows per rf_id (one assignor per row; assignments can have multiple inventors)
- **Cardinality**: ~8-10M rows (potential for 2-5 assignors per assignment)
- **Execution Date**: ~96% non-NULL; critical for assignment chain timeline
- **Acknowledgment Date**: ~0% in practice (rarely recorded in modern USPTO data)
- **Name Format**: Inventor names (personal or entity names)

### Data Quality Issues

1. **Missing execution dates** (~4% NULL): Gaps in assignment timeline
2. **No acknowledgment dates**: Historical field, not used in modern assignments
3. **Name variations**: Multiple name formats (full name, surname, initials)
4. **Inventor vs. organization ambiguity**: Field can contain both inventor names and corporate entities

### Analysis Use Cases

- **Assignment timeline**: Track when assignment was executed
- **Inventor tracking**: Identify original patent creators
- **Technology transfer**: Detect M&A activity through chain of assignors
- **Compensation tracking**: Correlate execution dates with business events

---

## 5. Conveyance Type Table (`assignment_conveyance.dta`)

### Purpose

Classifies the type of assignment transaction (assignment, license, security interest, merger, etc.).

### Schema

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| `rf_id` | int32 | No | **Primary/Foreign Key** → assignment.rf_id | 12800340 |
| `convey_ty` | object (str) | No | Conveyance type classification | "ASSIGNMENT" |
| `employer_assign` | int8 | No | Flag: 1 if employer assignment, 0 otherwise | 1 |

### Key Characteristics

- **Relationship**: One-to-one with assignment (one row per rf_id)
- **Conveyance Types**: Enumerated values
  - "ASSIGNMENT" (~80%): Full patent rights transfer
  - "LICENSE" (~10%): Right to use, not ownership transfer
  - "SECURITY INTEREST" (~5%): Collateral pledge
  - Other types: Mergers, reorganizations, corrections (~5%)
- **Employer Assignment Flag**: Indicates employer-executed assignment
  - Value 1: Employer directly assigns employee inventor patents
  - Value 0: Individual inventor or third party executes assignment
- **Completeness**: 100% non-NULL for both fields

### Data Quality Notes

- **Clear classification**: Well-structured, low ambiguity
- **Type validation**: Enumeration is consistent and complete
- **Employer flag**: Useful for corporate vs. independent inventor distinction

---

## 6. Relationship Diagram

```text
                    ┌──────────────────────┐
                    │   ASSIGNMENT (PK)    │
                    ├──────────────────────┤
                    │ rf_id (PK)           │
                    │ file_id              │
                    │ cname                │
                    │ caddress_1..4        │
                    │ reel_no, frame_no    │
                    │ convey_text          │
                    └──────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐
│  DOCUMENTID      │ │   ASSIGNEE       │ │ ASSIGNMENT_CONVEYANCE    │
├──────────────────┤ ├──────────────────┤ ├──────────────────────────┤
│ rf_id (FK)       │ │ rf_id (FK)       │ │ rf_id (PK, FK)           │
│ title            │ │ ee_name          │ │ convey_ty                │
│ lang             │ │ ee_address_*     │ │ employer_assign          │
│ appno_doc_num    │ │ ee_city          │ └──────────────────────────┘
│ appno_date       │ │ ee_state         │
│ pgpub_doc_num    │ │ ee_postcode      │
│ pgpub_date       │ │ ee_country       │
│ grant_doc_num    │ └──────────────────┘
└──────────────────┘
        │                  ▲
        │                  │
        └──────────────────┴────────────────┐
                                            ▼
                                   ┌──────────────────┐
                                   │   ASSIGNOR       │
                                   ├──────────────────┤
                                   │ rf_id (FK)       │
                                   │ or_name          │
                                   │ exec_dt          │
                                   │ ack_dt           │
                                   └──────────────────┘

SBIR Integration:
────────────────

DOCUMENTID.grant_doc_num  ┌─ SBIR_AWARD.patent_number
                          │  (exact match or fuzzy match ≥0.80)
                          ▼
ASSIGNEE.ee_name          ┌─ SBIR_COMPANY.legal_name
                          │  (fuzzy match ≥0.85)
                          │  + SAM.gov UEI cross-walk
                          │  + address-based fallback
                          ▼
                    [Company Linkage]
```

---

## 7. Integration with Neo4j Graph Schema

### Proposed Node Types

```python

## Patent Information

Patent {
    grant_doc_num,      # Primary identifier for SBIR linkage
    title,              # Patent title
    appno_doc_num,      # Application number
    appno_date,         # Filing date
    pgpub_doc_num,      # Publication number
    pgpub_date,         # Publication date
    lang,               # Language code
    source_table: "documentid"  # Lineage
}

## Assignment Transaction

PatentAssignment {
    rf_id,              # Primary identifier (reel/frame)
    reel_no,
    frame_no,
    convey_type,        # from assignment_conveyance.convey_ty
    employer_assign,    # from assignment_conveyance.employer_assign
    exec_date,          # from assignor.exec_dt
    recorded_date,      # inferred from rf_id registration
    correspondent_name, # from assignment.cname
}

## Assignment Participant (Assignee or Assignor)

PatentEntity {
    name,               # Normalized entity name
    address,            # Parsed/standardized address
    city, state, postcode, country,
    entity_type,        # "assignee" or "assignor"
    normalized_name,    # For matching
}
```

### Proposed Relationships

```cypher
(Patent)-[:ASSIGNED_VIA]->(PatentAssignment)
(PatentAssignment)-[:ASSIGNED_TO]->(PatentEntity {entity_type: "assignee"})
(PatentAssignment)-[:ASSIGNED_FROM]->(PatentEntity {entity_type: "assignor"})
(Patent)-[:GENERATED_FROM]->(Award)  # For SBIR-linked patents
(Company)-[:OWNS]->(Patent)      # Direct ownership via entity resolution
```

---

## 8. Data Quality Baseline Report

### Completeness Metrics (from analysis of 100-sample per table)

| Table | Critical Fields | Completeness |
|-------|-----------------|--------------|
| assignment | rf_id, cname, reel_no, frame_no | 100% |
| documentid | rf_id, title, grant_doc_num | 70% (grant_doc_num), 100% (title) |
| assignee | rf_id, ee_name | 100% |
| assignor | rf_id, or_name, exec_dt | 100%, 96% (exec_dt) |
| assignment_conveyance | rf_id, convey_ty, employer_assign | 100% |

### Uniqueness & Cardinality

| Table | Estimated Rows | Unique rf_id | Notes |
|-------|----------------|--------------|-------|
| assignment | 5-7M | ~7M | Primary; one per transaction |
| documentid | 5-7M | 5-7M | Multiple rows per rf_id possible |
| assignee | 8-10M | 8-10M | Multiple assignees per rf_id |
| assignor | 8-10M | 8-10M | Multiple inventors per rf_id |
| assignment_conveyance | 5-7M | ~7M | One-to-one with assignment |

### Known Issues

1. **Missing grant_doc_num** in 30% of documentid records
2. **Sparse convey_text** in assignment table (many NULL values)
3. **Name normalization required** across all entity fields
4. **Date range spanning 1790-present** (historical data includes old formats)

---

## 9. Mapping to Pydantic Models

### Model Classes (Implementation in `src/models/uspto_models.py`)

```python
class PatentDocument(BaseModel):
    rf_id: int
    title: str
    lang: Optional[str]
    appno_doc_num: Optional[str]
    appno_date: Optional[datetime]
    pgpub_doc_num: Optional[str]
    pgpub_date: Optional[datetime]
    grant_doc_num: Optional[str]

class PatentAssignee(BaseModel):
    rf_id: int
    ee_name: str
    ee_address_1: str
    ee_address_2: Optional[str]
    ee_city: Optional[str]
    ee_state: Optional[str]
    ee_postcode: Optional[str]
    ee_country: Optional[str]

class PatentAssignor(BaseModel):
    rf_id: int
    or_name: str
    exec_dt: Optional[datetime]

class PatentConveyance(BaseModel):
    rf_id: int
    convey_type: str  # enum: ASSIGNMENT, LICENSE, SECURITY_INTEREST
    employer_assign: bool

class PatentAssignment(BaseModel):
    rf_id: int
    file_id: int
    correspondent_name: str
    correspondent_address: str
    reel_no: int
    frame_no: int
    conveyance_type: str
    documents: List[PatentDocument]
    assignees: List[PatentAssignee]
    assignors: List[PatentAssignor]
```

---

## 10. References & Further Reading

- **USPTO Assignment Documentation**: <https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data>
- **Stata File Format**: `pyreadstat` documentation for pandas integration
- **Data Quality Thresholds**: Target ≥95% completeness for critical fields (rf_id, dates, entity names)
- **SBIR Linkage Rate**: Expected 50-70% of SBIR companies have documented patents
