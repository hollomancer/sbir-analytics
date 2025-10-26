# USPTO Patent Data Field Mapping to Neo4j Graph Schema

**Purpose**: Maps each field from USPTO Stata files to Neo4j node properties and relationships  
**Date**: 2025-10-26  
**Status**: Reference Guide for ETL Implementation

---

## Overview

This document provides a comprehensive field-by-field mapping from USPTO patent assignment Stata tables to the Neo4j graph schema. Use this guide during ETL implementation to ensure accurate data transformation.

**Key Principles**:
- One-to-one field mappings where possible
- Composite fields split into separate properties
- Derived fields computed during transformation
- Audit trail fields preserved for traceability

---

## 1. Patent Mapping (documentid.dta → :Patent node)

### Primary Identifiers

| Stata Field | Type | Neo4j Property | Format | Required | Notes |
|-------------|------|----------------|--------|----------|-------|
| rf_id | int32 | linked_assignment_rf_id | Integer | Yes | Foreign key to assignment |
| grant_doc_num | string | grant_doc_num | String | No* | ~70% complete; PRIMARY KEY when available |
| appno_doc_num | string | appno_doc_num | String | Yes | Application number format |
| pgpub_doc_num | string | pgpub_doc_num | String | Yes | Publication number format |

**Constraint**: `grant_doc_num` is UNIQUE when not NULL (create constraint in Neo4j)

---

### Patent Metadata

| Stata Field | Type | Neo4j Property | Format | Required | Notes |
|-------------|------|----------------|--------|----------|-------|
| title | string | title | String | Yes | Patent title (max 380 chars observed) |
| lang | string | language | String | Yes | Language code (mostly "ENGLISH") |

---

### Filing & Publication Timeline

| Stata Field | Type | Neo4j Property | Format | Required | Notes |
|-------------|------|----------------|--------|----------|-------|
| appno_date | datetime64 | application_date | ISO 8601 | No | Filing date; ~68% complete |
| appno_country | string | application_country | String | No | Country code (usually "US") |
| pgpub_date | datetime64 | publication_date | ISO 8601 | No | Grant date; ~0% in current sample |
| pgpub_country | string | publication_country | String | No | Country code (usually "US") |

**Handling Sparse Fields**:
- If `pgpub_date` NULL: use `appno_date` as proxy
- If both NULL: set `timeline_confidence = "LOW"`

---

### Derived Properties (Computed During Transform)

| Derived Property | Source | Calculation | Notes |
|---|---|---|---|
| grant_doc_num_missing | grant_doc_num | `grant_doc_num IS NULL` | Flag for linkage strategy |
| patent_age_years | appno_date | `YEAR(NOW()) - YEAR(appno_date)` | Age since filing |
| timeline_confidence | appno_date, pgpub_date | "HIGH" if both; "MED" if app only | Quality metric |

---

### Audit Trail Properties

| Property | Value | Source |
|---|---|---|
| source_table | "documentid" | Constant |
| source_rf_id | rf_id | Foreign key reference |
| loaded_date | NOW() | Timestamp |
| data_version | "april-2024" | Configuration |

---

## 2. PatentAssignment Mapping (assignment.dta + assignment_conveyance.dta → :PatentAssignment node)

### Primary Identifier

| Stata Field | Table | Neo4j Property | Format | Required | Notes |
|-------------|-------|----------------|--------|----------|-------|
| rf_id | assignment | rf_id | Integer | Yes | PRIMARY KEY (unique) |

---

### Filing Information

| Stata Field | Table | Neo4j Property | Format | Required | Notes |
|-------------|-------|----------------|--------|----------|-------|
| reel_no | assignment | reel_no | Integer | Yes | USPTO filing reel |
| frame_no | assignment | frame_no | Integer | Yes | Frame within reel |

---

### Transaction Classification

| Stata Field | Table | Neo4j Property | Format | Required | Notes |
|-------------|-------|----------------|--------|----------|-------|
| convey_ty | assignment_conveyance | convey_type | String (enum) | Yes | ASSIGNMENT, LICENSE, SECURITY_INTEREST, etc. |
| employer_assign | assignment_conveyance | employer_assigned | Boolean | Yes | Flag: employer-initiated? |

---

### Correspondent Information

| Stata Field | Table | Neo4j Property | Format | Required | Notes |
|-------------|-------|----------------|--------|----------|-------|
| cname | assignment | correspondent_name | String | Yes | Law firm or handler name |
| caddress_1 | assignment | correspondent_address_line1 | String | Yes | Street address |
| caddress_2 | assignment | correspondent_address_line2 | String | Yes | City/state/zip |
| caddress_3 | assignment | correspondent_address_line3 | String | No | Optional address extension |
| caddress_4 | assignment | correspondent_address_country | String | No | International address |

**Address Parsing**:
```
Combined: caddress_1 + caddress_2 + caddress_3 + caddress_4
Parsed into:
- correspondent_address (full string)
- correspondent_city (extracted from line 2)
- correspondent_state (extracted from line 2)
- correspondent_postcode (extracted from line 2)
```

---

### Transaction Metadata

| Stata Field | Table | Neo4j Property | Format | Required | Notes |
|-------------|-------|----------------|--------|----------|-------|
| convey_text | assignment | conveyance_notes | String | No | Raw text; sparse (45% complete) |

**Note**: Use structured `convey_type` field instead; this is audit trail only

---

### Derived Properties

| Derived Property | Source Fields | Calculation | Notes |
|---|---|---|---|
| num_patents | documentid joins | COUNT(DISTINCT grant_doc_num) | Batch size indicator |
| num_assignees | assignee joins | COUNT(DISTINCT ee_name) | Participant count |
| num_assignors | assignor joins | COUNT(DISTINCT or_name) | Inventor count |
| exec_date | assignor.exec_dt | MIN(exec_dt) or MAX(exec_dt) | Assignment execution |
| recorded_date | rf_id + era | Estimated from reel_no | Approximate filing date |
| is_batch | num_patents > 1 | Boolean | Batch assignment flag |

---

## 3. PatentEntity Mapping (assignee.dta + assignor.dta → :PatentEntity node)

### From assignee.dta (entity_type = "ASSIGNEE")

| Stata Field | Neo4j Property | Transform | Required | Notes |
|-------------|----------------|-----------|----------|-------|
| rf_id | source_assignment_rf_id | Direct | Yes | Foreign key reference |
| ee_name | name | Direct | Yes | Assignee name |
| ee_name | normalized_name | UPPER + remove_special_chars | Yes | For matching |
| ee_address_1 | address_line1 | Direct | Yes | Street address |
| ee_address_2 | address_line2 | Direct | No | City/state/zip |
| ee_city | city | Extract or direct | No | City name |
| ee_state | state | Extract or direct | No | State/province code |
| ee_postcode | postcode | Parse & validate | No | Postal code |
| ee_country | country | Direct | No | Country code |

**Entity ID Calculation** (for deduplication):
```python
entity_id = hash(normalized_name + "|" + country + "|" + state + "|" + postcode)
```

---

### From assignor.dta (entity_type = "ASSIGNOR")

| Stata Field | Neo4j Property | Transform | Required | Notes |
|-------------|----------------|-----------|----------|-------|
| rf_id | source_assignment_rf_id | Direct | Yes | Foreign key reference |
| or_name | name | Direct | Yes | Assignor name |
| or_name | normalized_name | UPPER + remove_special_chars | Yes | For matching |
| exec_dt | execution_date | Direct | No | When assignment signed (~96% complete) |
| ack_dt | acknowledgment_date | Direct | No | Rarely used (~0% in modern data) |

**Entity ID Calculation** (for deduplication):
```python
entity_id = hash(normalized_name + "|INDIVIDUAL|" + state_if_available)
```

---

### Derived Properties (Both Types)

| Derived Property | Calculation | Purpose |
|---|---|---|
| entity_type | Table source | "ASSIGNEE" or "ASSIGNOR" |
| entity_category | Name parsing + heuristics | "COMPANY", "INDIVIDUAL", "UNIVERSITY", "GOVERNMENT" |
| entity_id | Composite hash | Deduplication key |
| source_tables | Union of sources | Audit trail |
| first_seen_date | MIN(exec_date or recorded_date) | Timeline |
| last_seen_date | MAX(exec_date or recorded_date) | Timeline |
| num_assignments | COUNT(*) group by entity_id | Activity metric |

---

### SBIR Integration Properties

| Property | Source | Calculation | Notes |
|---|---|---|---|
| sbir_linked | Manual match | `EXISTS(company_id)` | Is this an SBIR company? |
| sbir_company_id | Company fuzzy match | Match normalized_name ≥0.85 | Link to SBIR database |
| sbir_uei | Company SAM data | Copy from Company.uei | Unique Entity ID |
| linkage_confidence | Match scoring | 0.95 (exact), 0.85 (fuzzy), 0.70 (address) | Quality metric |

---

## 4. Relationship Mapping

### ASSIGNED_VIA Relationship

**From**: `:Patent` node  
**To**: `:PatentAssignment` node

| Source Property | Target Property | Transform |
|---|---|---|
| grant_doc_num | (query parameter) | Match via rf_id join |
| (derived) exec_date | exec_date | Inherited from assignment |

**Relationship Properties**:
```cypher
{
  position_in_batch: <integer>,        // 1, 2, 3, ... if batch
  total_in_batch: <integer>,           // Total count in batch
  exec_date: <datetime>,               // When assignment executed
  recorded_date: <datetime>            // When USPTO recorded
}
```

---

### ASSIGNED_TO Relationship

**From**: `:PatentAssignment` node  
**To**: `:PatentEntity {entity_type: "ASSIGNEE"}` node

| Source Field | Target Property | Transform |
|---|---|---|
| rf_id | (query key) | Join to assignee records |
| assignment.exec_date | effective_date | When rights transferred |
| convey_type | convey_type | Inherited property |

**Relationship Properties**:
```cypher
{
  assignment_role: <string>,           // "PRIMARY_ASSIGNEE", "CO_ASSIGNEE"
  effective_date: <datetime>,          // When assignee acquired rights
  source_ee_name: <string>             // Original assignee name (audit)
}
```

---

### ASSIGNED_FROM Relationship

**From**: `:PatentAssignment` node  
**To**: `:PatentEntity {entity_type: "ASSIGNOR"}` node

| Source Field | Target Property | Transform |
|---|---|---|
| rf_id | (query key) | Join to assignor records |
| assignor.exec_dt | exec_date | When assignor signed |
| (inferred) | originator_role | "INVENTOR", "EMPLOYER", etc. |

**Relationship Properties**:
```cypher
{
  originator_role: <string>,           // "INVENTOR", "EMPLOYER", "PRIOR_OWNER"
  exec_date: <datetime>,               // When assignor executed
  source_or_name: <string>             // Original assignor name (audit)
}
```

---

### FUNDED_BY Relationship

**From**: `:Patent` node  
**To**: `:Award` node (existing SBIR node)

| Source Field | Target Property | Transform |
|---|---|---|
| grant_doc_num | award.patent_number | Exact or fuzzy match |
| (derived) | linkage_method | "exact_grant_num", "fuzzy_match", "manual" |
| (derived) | confidence_score | 0.95, 0.80, 0.70, etc. |

**Relationship Properties**:
```cypher
{
  linkage_method: <string>,            // How the link was created
  confidence_score: <float>,           // 0.0-1.0 quality metric
  linked_date: <datetime>              // When link was created
}
```

---

### OWNS Relationship

**From**: `:Company` node (existing SBIR node)  
**To**: `:Patent` node

| Source | Target | Transform |
|---|---|---|
| Company.company_id | Company (via entity resolution) | Fuzzy match PatentEntity.sbir_company_id |
| PatentEntity | Patent (via ASSIGNED_TO chain) | Trace ownership chain |

**Relationship Properties**:
```cypher
{
  acquisition_date: <datetime>,        // When acquired
  acquisition_method: <string>,        // "SBIR_FUNDED", "ASSIGNMENT", "MERGER"
  ownership_type: <string>,            // "FULL", "PARTIAL", "LICENSED"
  confidence: <float>                  // Entity matching confidence
}
```

---

## 5. Data Transformation Logic

### Name Normalization

Apply to: `cname`, `ee_name`, `or_name`, correspondent fields

```python
def normalize_name(name: str) -> str:
    """
    Normalize entity names for matching.
    
    Steps:
    1. Uppercase
    2. Remove trailing punctuation (,.;:)
    3. Remove leading/trailing whitespace
    4. Collapse multiple spaces to single
    5. Remove special characters except &, -, /
    """
    if not name:
        return ""
    
    # Step 1-4
    name = name.strip().upper()
    name = re.sub(r'\s+', ' ', name)
    
    # Step 5: Remove special chars except &, -, /
    name = re.sub(r'[^\w\s&\-/]', '', name)
    
    # Remove trailing punctuation
    name = name.rstrip('.,;:')
    
    return name.strip()
```

---

### Date Parsing

Apply to: `appno_date`, `pgpub_date`, `exec_dt`, `ack_dt`

```python
def parse_date(date_val) -> Optional[datetime]:
    """
    Parse date from various formats.
    
    Handles:
    - datetime64[ns] (pandas)
    - ISO 8601 strings
    - Common date formats (MM/DD/YYYY, YYYY-MM-DD)
    """
    if pd.isna(date_val):
        return None
    
    if isinstance(date_val, pd.Timestamp):
        return date_val.to_pydatetime()
    
    if isinstance(date_val, str):
        # Try ISO 8601 first
        try:
            return datetime.fromisoformat(date_val)
        except ValueError:
            pass
        
        # Try common formats
        for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%Y/%m/%d']:
            try:
                return datetime.strptime(date_val, fmt)
            except ValueError:
                pass
    
    return None
```

---

### Address Parsing

Apply to: Correspondent address (caddress_1-4), Assignee address (ee_address_1-2), Assignor address (if any)

```python
def parse_address(line1: str, line2: str, line3: str = "", line4: str = "") -> dict:
    """
    Parse multi-line address into components.
    
    Returns:
    {
        'full_address': concatenated lines,
        'street': extracted from line1,
        'city': extracted from line2,
        'state': extracted from line2,
        'postcode': extracted from line2,
        'country': extracted from line4 or inferred
    }
    """
    # For US addresses, line2 typically: "CITY, STATE ZIP"
    # For international: may vary
    
    full = " ".join(filter(None, [line1, line2, line3, line4]))
    
    # Simple parsing (could use libpostal for better results)
    city, state, postcode = "", "", ""
    
    if line2:
        # Try to parse "CITY, STATE ZIP"
        parts = line2.split(',')
        if len(parts) >= 2:
            city = parts[0].strip()
            state_zip = parts[1].strip()
            state_parts = state_zip.split()
            state = state_parts[0] if state_parts else ""
            postcode = state_parts[1] if len(state_parts) > 1 else ""
    
    country = line4.strip() if line4 else "US"
    
    return {
        'full_address': full,
        'street': line1.strip(),
        'city': city,
        'state': state,
        'postcode': postcode,
        'country': country
    }
```

---

### Entity Deduplication

Apply to: PatentEntity creation

```python
def compute_entity_id(
    name: str,
    entity_type: str,  # "ASSIGNEE" or "ASSIGNOR"
    country: str = "US",
    state: str = "",
    postcode: str = ""
) -> str:
    """
    Compute deduplication key for PatentEntity.
    
    Combines normalized name with geographic key to handle:
    - Company name variations
    - Multiple offices of same company
    - International entities
    """
    normalized = normalize_name(name)
    
    # Geographic key
    geo_key = f"{country}|{state}|{postcode}".upper()
    
    # Composite key
    composite = f"{normalized}|{geo_key}"
    
    # Hash for consistent ID
    entity_id = hashlib.md5(composite.encode()).hexdigest()
    
    return entity_id
```

---

### Conveyance Type Classification

Apply to: `convey_ty` field mapping

```python
CONVEYANCE_TYPES = {
    "ASSIGNMENT": "Full patent rights transfer",
    "LICENSE": "Licensee right to use",
    "SECURITY_INTEREST": "Collateral pledge",
    "MERGER": "Corporate merger/consolidation",
    "CORRECTION": "Administrative correction",
    "REASSIGNMENT": "Reassignment of rights",
    "LIEN": "Legal lien",
    "COVENANT": "Covenant/promise",
}

def classify_conveyance(convey_ty: str) -> str:
    """Ensure convey_ty is valid enumeration."""
    convey_ty_upper = convey_ty.strip().upper()
    
    if convey_ty_upper in CONVEYANCE_TYPES:
        return convey_ty_upper
    
    # Default to ASSIGNMENT if unknown
    return "ASSIGNMENT"
```

---

## 6. Validation Rules

### Patent Node Validation

```python
def validate_patent(patent: dict) -> List[str]:
    """Validate Patent node before insert."""
    errors = []
    
    # Required fields
    if not patent.get('title'):
        errors.append("title is required")
    
    # Grant doc number should be ~70% present
    if patent.get('grant_doc_num') is None:
        errors.append("grant_doc_num is NULL (acceptable, ~30% of records)")
    
    # Date validation
    if patent.get('appno_date'):
        app_date = parse_date(patent['appno_date'])
        if app_date and (app_date.year < 1790 or app_date.year > datetime.now().year):
            errors.append(f"appno_date out of range: {app_date}")
    
    return errors
```

### PatentAssignment Node Validation

```python
def validate_assignment(assignment: dict) -> List[str]:
    """Validate PatentAssignment node before insert."""
    errors = []
    
    # Required fields
    if not assignment.get('rf_id'):
        errors.append("rf_id is required (primary key)")
    
    if not assignment.get('convey_type'):
        errors.append("convey_type is required")
    elif assignment['convey_type'] not in CONVEYANCE_TYPES:
        errors.append(f"convey_type '{assignment['convey_type']}' not in enum")
    
    # Employer flag must be 0 or 1
    if assignment.get('employer_assigned') not in [0, 1]:
        errors.append("employer_assigned must be 0 or 1")
    
    return errors
```

### PatentEntity Node Validation

```python
def validate_entity(entity: dict) -> List[str]:
    """Validate PatentEntity node before insert."""
    errors = []
    
    # Required fields
    if not entity.get('name'):
        errors.append("name is required")
    
    if not entity.get('entity_type'):
        errors.append("entity_type is required")
    elif entity['entity_type'] not in ["ASSIGNEE", "ASSIGNOR"]:
        errors.append(f"entity_type must be ASSIGNEE or ASSIGNOR, got {entity['entity_type']}")
    
    if not entity.get('entity_id'):
        errors.append("entity_id is required (dedup key)")
    
    return errors
```

---

## 7. Quality Metrics

### Field Completeness Check

| Field | Expected % | Acceptable | Action |
|-------|-----------|-----------|--------|
| Patent.title | 100% | ≥99% | Warn if <99% |
| Patent.grant_doc_num | 70% | ≥70% | Expected NULL rate |
| PatentAssignment.rf_id | 100% | =100% | Fail if <100% |
| PatentAssignment.convey_type | 100% | =100% | Fail if <100% |
| PatentEntity.name | 100% | =100% | Fail if <100% |
| PatentEntity.exec_date | 96% | ≥96% | Warn if <96% |

---

## 8. Implementation Checklist

**Before Loading**:
- [ ] Confirm Stata file formats (Stata 117/118)
- [ ] Validate rf_id cardinality across tables
- [ ] Test name normalization on sample names
- [ ] Test date parsing on sample dates

**During Loading**:
- [ ] Implement chunked reading (10K records)
- [ ] Log all validation errors
- [ ] Count NULL rates per field
- [ ] Track deduplication metrics for PatentEntity

**After Loading**:
- [ ] Verify all constraints created
- [ ] Run quality metrics report
- [ ] Test cross-graph queries
- [ ] Generate linkage statistics

---

## 9. References

- USPTO Assignment Data Documentation: https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data
- Field-level specifications: See `docs/schemas/patent-assignment-schema.md`
- Neo4j Schema Design: See `docs/schemas/patent-neo4j-schema.md`
- SBIR Integration: See transition detection documentation