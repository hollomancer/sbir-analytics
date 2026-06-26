# USPTO Patents — Source, Field Reference, and Graph Mapping

## Overview

This document covers USPTO patent assignment data end to end:

1. The raw USPTO Stata source tables.
2. The nested Pydantic model produced by the ETL (`sbir_etl/models/uspto_models.py`).
3. How that data is written into Neo4j by `packages/sbir-graph/sbir_graph/loaders/neo4j/patents.py`.

For the overall graph index see [neo4j.md](neo4j.md). For the unified node references
see [organization-schema.md](organization-schema.md) and [individual-schema.md](individual-schema.md).

**Data source:** [USPTO Patent Assignment Dataset](https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset)
**Update frequency:** Monthly
**Format:** Stata (`.dta`), also available as CSV / Parquet

---

## 1. Raw USPTO source tables

The USPTO maintains patent assignment data across five interdependent Stata tables
linked via `rf_id` (the reel/frame identifier).

| Table | Approx. size | Grain | Purpose |
|-------|--------------|-------|---------|
| `assignment.dta` | ~780 MB | one row per assignment | Core assignment record (correspondent, reel/frame, raw conveyance text) |
| `documentid.dta` | ~1.6 GB | one row per patent (many per `rf_id`) | Patent document metadata (title, numbers, dates) |
| `assignee.dta` | ~892 MB | one row per assignee | Recipients of patent rights |
| `assignor.dta` | ~620 MB | one row per assignor | Originators of patent rights (often inventors) |
| `assignment_conveyance.dta` | ~158 MB | one row per `rf_id` | Conveyance type classification |

### `assignment.dta`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `rf_id` | int32 | No | **Primary key** — reel/frame identifier |
| `file_id` | int8 | No | File sequence (usually 1) |
| `cname` | str | No | Correspondent name (law firm / handler) |
| `caddress_1`..`caddress_4` | str | Mixed | Correspondent address lines (1–2 present, 3–4 optional) |
| `reel_no` | int32 | No | USPTO reel number |
| `frame_no` | int16 | No | Frame within reel |
| `convey_text` | str | Yes | Raw conveyance description (sparse) |

### `documentid.dta`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `rf_id` | int32 | No | Foreign key → `assignment.rf_id` |
| `title` | str | No | Patent title |
| `lang` | str | No | Language code (mostly `ENGLISH`) |
| `appno_doc_num` | str | Yes | Application number (formatted) |
| `appno_date` | datetime64 | Yes | Application filing date (~68% present) |
| `appno_country` | str | Yes | Application country code |
| `pgpub_doc_num` | str | Yes | Publication number (formatted) |
| `pgpub_date` | datetime64 | Yes | Publication/grant date (sparse in sample) |
| `pgpub_country` | str | Yes | Publication country code |
| `grant_doc_num` | str | Yes (~30% NULL) | Patent grant number; **the SBIR linkage key** |

`grant_doc_num` is a 7–8 digit patent number (e.g. `"10123456"`) and is UNIQUE when present.

### `assignee.dta`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `rf_id` | int32 | No | Foreign key → `assignment.rf_id` |
| `ee_name` | str | No | Assignee name (recipient) |
| `ee_address_1` | str | No | Address line 1 |
| `ee_address_2` | str | Yes | Address line 2 (city/state/zip) |
| `ee_city`, `ee_state`, `ee_postcode`, `ee_country` | str | Yes | Parsed location fields |

### `assignor.dta`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `rf_id` | int32 | No | Foreign key → `assignment.rf_id` |
| `or_name` | str | No | Assignor name (originator) |
| `exec_dt` | datetime64 | Yes (~4% NULL) | Execution date (signing) |
| `ack_dt` | datetime64 | Yes (~100% NULL) | Acknowledgment date (rarely recorded) |

### `assignment_conveyance.dta`

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `rf_id` | int32 | No | Primary/foreign key → `assignment.rf_id` |
| `convey_ty` | str | No | Conveyance type (e.g. `ASSIGNMENT` ~80%, `LICENSE` ~10%, `SECURITY INTEREST` ~5%) |
| `employer_assign` | int8 | No | 1 if employer assignment, else 0 |

### Table relationships

```text
assignment (rf_id PK)
  ├──< documentid          (many patents per rf_id)
  ├──< assignee            (recipients)
  ├──< assignor            (originators)
  └──1 assignment_conveyance  (one-to-one)
```

---

## 2. ETL model (`sbir_etl/models/uspto_models.py`)

Unlike the flat raw tables, the ETL produces a **nested** `PatentAssignment` model that
composes the document, conveyance, assignee, and assignor into one object.

```text
PatentAssignment
  ├─ document:    PatentDocument
  ├─ conveyance:  PatentConveyance
  ├─ assignee:    PatentAssignee
  └─ assignor:    PatentAssignor
```

### `PatentAssignment`

| Field | Type | Notes |
|-------|------|-------|
| `rf_id` | `str \| None` | Repository record id |
| `file_id` | `str \| None` | Groups related rows |
| `document` | `PatentDocument \| None` | Nested |
| `conveyance` | `PatentConveyance \| None` | Nested |
| `assignee` | `PatentAssignee \| None` | Nested |
| `assignor` | `PatentAssignor \| None` | Nested |
| `execution_date`, `recorded_date` | `date \| None` | Top-level dates |
| `normalized_assignee_name`, `normalized_assignor_name` | `str \| None` | For matching |
| `metadata` | `dict` | Raw / extra |

### `PatentDocument`

| Field | Type | Notes |
|-------|------|-------|
| `rf_id` | `str \| None` | Record id |
| `application_number`, `publication_number`, `grant_number` | `str \| None` | Normalized identifiers (uppercased, punctuation stripped) |
| `filing_date`, `publication_date`, `grant_date` | `date \| None` | Parsed dates |
| `language`, `title`, `abstract` | `str \| None` | Text fields |
| `raw` | `dict` | Original row |

### `PatentAssignee`

| Field | Type | Notes |
|-------|------|-------|
| `rf_id` | `str \| None` | Record id |
| `name` | `str` | **Required** (non-empty, whitespace-normalized) |
| `street`, `city`, `state`, `postal_code`, `country` | `str \| None` | Location |
| `uei`, `cage`, `duns` | `str \| None` | Federal identifiers (normalized) |
| `metadata` | `dict` | Extra |

### `PatentAssignor`

| Field | Type | Notes |
|-------|------|-------|
| `rf_id` | `str \| None` | Record id |
| `name` | `str \| None` | Normalized name |
| `execution_date`, `acknowledgment_date` | `date \| None` | Parsed dates |
| `metadata` | `dict` | Extra |

### `PatentConveyance`

| Field | Type | Notes |
|-------|------|-------|
| `rf_id` | `str \| None` | Record id |
| `conveyance_type` | `ConveyanceType` | Defaults to `assignment` |
| `description` | `str \| None` | Raw conveyance text |
| `employer_assign` | `bool \| None` | Work-for-hire flag |
| `recorded_date` | `date \| None` | Parsed date |
| `metadata` | `dict` | Extra |

### `ConveyanceType` enum

Lowercase values: `assignment`, `license`, `security_interest`, `merger`, `other`.

### Data quality notes

- `grant_doc_num` / `grant_number` missing in ~30% of records (limits SBIR linkage).
- Publication dates sparse; `appno_date` / `filing_date` used as a proxy.
- Entity names require normalization (fuzzy match tolerance ~0.85); same entity
  appears with multiple name variants.
- Patent numbers appear with or without commas (`10,123,456` vs `10123456`).

---

## 3. Neo4j graph mapping

The loader (`patents.py`) writes the following labels and relationships. There is **no**
`:PatentEntity` node and **no** `FUNDED_BY` edge for patents — assignees/assignors become
unified `Organization` or `Individual` nodes, and SBIR linkage uses `GENERATED_FROM`.

### Nodes

| Label | Key | Source |
|-------|-----|--------|
| `Patent` | `grant_doc_num` | `documentid` / `PatentDocument` |
| `PatentAssignment` | `rf_id` | `assignment` + `assignment_conveyance` |
| `Organization` | `organization_id` (`org_patent_<entity_id>`) | non-individual assignees/assignors (`COMPANY`, `UNIVERSITY`, `GOVERNMENT`) |
| `Individual` | `individual_id` (`ind_patent_<entity_id>`) | individual assignees/assignors |

`Patent` node properties include `grant_doc_num`, `title`, `abstract`, `language`,
`appno_date`, `grant_date`, `publication_date`, `filing_date`, `raw_metadata`.
`PatentAssignment` properties include `rf_id`, `file_id`, `conveyance_type`,
`conveyance_description`, `employer_assign`, `grant_doc_num`, `execution_date`,
`recorded_date`.

> Patent assignees/assignors are routed to the unified `Organization` / `Individual`
> labels (see [organization-schema.md](organization-schema.md) and
> [individual-schema.md](individual-schema.md)); the legacy `PatentEntity` constraint/index
> definitions remain in the loader for backward compatibility but no `:PatentEntity`
> nodes are created.

### Relationships

| Type | Direction |
|------|-----------|
| `ASSIGNED_VIA` | `Patent` → `PatentAssignment` |
| `ASSIGNED_TO` | `PatentAssignment` → `Organization` / `Individual` (assignee, by `entity_id`) |
| `ASSIGNED_FROM` | `PatentAssignment` → `Organization` / `Individual` (assignor, by `entity_id`) |
| `CHAIN_OF` | `PatentAssignment` → `PatentAssignment` (sequential ownership) |
| `OWNS` | `Organization` (COMPANY, by `uei`) → `Patent` |
| `GENERATED_FROM` | `Patent` → `Award` (SBIR-funded patents, by `award_id`) |

### Constraints and indexes (from `patents.py`)

- `Patent.grant_doc_num` UNIQUE; index on `appno_date`.
- `PatentAssignment.rf_id` UNIQUE; index on `exec_date`.
- `Organization.organization_id` UNIQUE; indexes on `entity_id`, `normalized_name`.

### Example queries

```cypher
// All assignments for a patent, in execution order
MATCH (p:Patent {grant_doc_num: "10123456"})-[:ASSIGNED_VIA]->(a:PatentAssignment)
RETURN a
ORDER BY a.execution_date ASC
```

```cypher
// Patent portfolio of an SBIR company
MATCH (o:Organization {organization_type: "COMPANY"})-[:OWNS]->(p:Patent)
RETURN o.name, count(p) AS patent_count
ORDER BY patent_count DESC
```

```cypher
// SBIR-funded patents linked to their source award
MATCH (p:Patent)-[:GENERATED_FROM]->(ft:FinancialTransaction {transaction_type: "AWARD"})
RETURN p.grant_doc_num, p.title, ft.award_id
```

---

## References

- [USPTO Patent Assignment Dataset](https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset)
- Pydantic models: `sbir_etl/models/uspto_models.py`
- USPTO extractor: `sbir_etl/extractors/uspto_extractor.py`
- Patent transformer: `sbir_etl/transformers/patent_transformer.py`
- Patent loader: `packages/sbir-graph/sbir_graph/loaders/neo4j/patents.py`
- Graph index: [neo4j.md](neo4j.md)
