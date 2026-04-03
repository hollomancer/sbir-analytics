# SBIR RAG Data Evaluation

**Date:** 2026-04-02
**Status:** Evaluation Complete

## Executive Summary

This document evaluates SBIR award, solicitation, and USAspending data sources for Retrieval-Augmented Generation (RAG) implementation. The codebase already has a strong foundation for RAG through ModernBERT-Embed embeddings (768-dim) for award-patent similarity, DuckDB for fast analytical queries, and a Neo4j graph database for relationship traversal. The primary gap is a unified vector store and retrieval layer that combines these data sources for natural language querying.

---

## 1. SBIR Award Data

**Source:** SBIR.gov CSV (`https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`)
**Extractor:** `sbir_etl/extractors/sbir.py` (DuckDB-backed)
**Model:** `sbir_etl/models/award.py` (Pydantic `Award` with 42 fields)

### Text-Rich Fields (High RAG Value)

| Field | Description | Typical Length | RAG Suitability |
|-------|-------------|----------------|-----------------|
| `Abstract` | Project abstract describing research | 200-2000 chars | **Excellent** - Primary semantic content |
| `Award Title` | Descriptive project title | 50-200 chars | **Excellent** - Dense topic signal |
| `Keywords` | Comma-separated keyword list | 20-200 chars | **Good** - Structured topic metadata |
| `Topic Code` | Solicitation topic identifier | 5-20 chars | **Good** - Categorical linkage to solicitations |

### Structured Fields (Metadata Filtering)

| Field | RAG Use Case |
|-------|-------------|
| `Agency`, `Branch` | Filter by funding agency |
| `Phase` (I/II/III) | Filter by program maturity |
| `Program` (SBIR/STTR) | Filter by program type |
| `Award Year`, `Award Date` | Temporal filtering |
| `Award Amount` | Funding range filtering |
| `Company`, `State`, `Zip` | Geographic and entity filtering |
| `Solicitation Number`, `Solicitation Year` | Cross-reference to solicitation topics |
| `UEI`, `DUNS` | Entity resolution / join keys |

### Data Quality Assessment

- **Completeness thresholds** already configured: award_id 100%, company_name 95%, award_amount 90%, award_date 95%, program 98%
- **Uniqueness:** 99% unique contract IDs (allowing phase progressions)
- **Abstracts:** Most valuable RAG field but likely has 10-30% null rate based on missing value analysis infrastructure in extractor
- **Lenient validation:** Model accepts partial data with warnings rather than rejecting records, which is good for RAG coverage

### Chunking Strategy Recommendation

Awards are natural document units. Each award should be a single chunk containing:
- **Primary text:** `"{Award Title}. {Abstract}. Keywords: {Keywords}"`
- **Metadata envelope:** agency, phase, program, year, amount, company, state, topic_code, solicitation_number

Estimated chunk size: 300-2500 tokens per award (well within typical RAG chunk limits).

---

## 2. Solicitation Data

**Source:** SBIR.gov API (`https://api.www.sbir.gov/public/api/`) + CSV fields
**Client:** `sbir_etl/extractors/sbir_gov_api.py` (`SbirGovClient`)

### Available Fields

Solicitation data is currently embedded within award records rather than stored as standalone documents:

| Field | Source | Description |
|-------|--------|-------------|
| `Solicitation Number` | Award CSV | Links award to solicitation |
| `Solicitation Year` | Award CSV | Year of solicitation |
| `Solicitation Close Date` | Award CSV | Deadline |
| `Topic Code` | Award CSV | Specific research topic |
| `Agency` + `Branch` | Award CSV | Issuing agency |

### Gap Analysis

**Current state:** Solicitations exist only as metadata on awards. There are no standalone solicitation topic descriptions, research area narratives, or full solicitation text documents in the pipeline.

**What's missing for RAG:**
- Full solicitation topic descriptions (typically 500-3000 words each) describing research problems and desired outcomes
- Solicitation pre-announcement and BAA (Broad Agency Announcement) text
- Topic area taxonomy and cross-references

**Data availability:** SBIR.gov provides solicitation topic data via:
1. **API:** `SbirGovClient.query_awards()` returns award-level data; no dedicated solicitation endpoint is used
2. **Bulk downloads:** SBIR.gov data resources page has solicitation data
3. **Agency-specific sources:** DOD SBIR/STTR portal, NIH Reporter, NSF awards API

### Recommendation

Solicitation topics are **high-value RAG documents** because they describe the government's research needs. Users querying "what SBIR topics relate to autonomous vehicles?" need solicitation text, not just award abstracts. Priority action:

1. Add a solicitation extractor (SBIR.gov API has topic descriptions in award records)
2. Deduplicate and store solicitation topics as first-class documents
3. Link solicitations to awards via `topic_code` + `solicitation_number`

---

## 3. USAspending Data

**Source:** USAspending.gov (PostgreSQL dump + REST API v2)
**Extractor:** `sbir_etl/extractors/usaspending.py` (DuckDB import from pg_dump)
**API Client:** `sbir_etl/enrichers/usaspending/client.py` (async httpx)
**Enricher:** `sbir_etl/enrichers/usaspending/enricher.py` (identifier + fuzzy matching)

### Available Data

| Table/Entity | Key Fields | RAG Value |
|-------------|-----------|-----------|
| **recipient_lookup** | legal_business_name, uei, duns, parent_uei, address, congressional_district, business_types_codes | **Medium** - Entity resolution, company profiles |
| **transaction_normalized** | award descriptions, funding amounts, NAICS codes, product/service codes | **Medium-High** - Financial context for awards |
| **Awards API** | Award descriptions, period of performance, funding agency hierarchy | **Medium** - Enrichment overlay |

### Text Fields for RAG

USAspending data is primarily structured/transactional rather than text-rich. The most useful text fields are:
- **Award descriptions** from transaction data (often short, 50-200 chars)
- **Recipient/company names** for entity resolution
- **NAICS code descriptions** for industry classification context

### Enrichment Value (Already Implemented)

The existing enrichment pipeline (`enrich_sbir_with_usaspending`) already:
- Matches SBIR awards to USAspending recipients via UEI, DUNS, or fuzzy name matching
- Enriches awards with federal obligation amounts, NAICS codes, recipient details
- Uses configurable thresholds (high: 90%, low: 75% fuzzy match)

### RAG Recommendation

USAspending data is best used as **metadata enrichment** on SBIR award chunks rather than as standalone RAG documents:
- Add `federal_obligation_total`, `naics_code`, `naics_description` to award metadata
- Use congressional district data for geographic filtering
- Use parent organization relationships for "related awards" retrieval

---

## 4. Existing Embedding Infrastructure

### ModernBERT-Embed Embeddings (Already Built)

**Location:** `packages/sbir-analytics/sbir_analytics/assets/paecter/embeddings.py` (legacy `paecter` naming; model is ModernBERT-Embed)
**Model:** ModernBERT-Embed (`nomic-ai/modernbert-embed-base`, 768 dimensions)
**Coverage:**
- SBIR award embeddings from `{solicitation_title} + {abstract} + {award_title}`
- USPTO patent embeddings from `{title} + {abstract}`
- Cosine similarity computation between awards and patents

**Key characteristics:**
- Batch processing via Dagster assets
- Configurable batch size (default 32)
- Similarity threshold (default 0.80) for match filtering
- Coverage quality checks (95% for awards, 98% for patents)

### Strengths for RAG

1. **ModernBERT-Embed** provides strong general-purpose embeddings with 8192-token context - ideal for SBIR abstracts
2. **Infrastructure exists** for batch embedding generation at scale
3. **Quality gates** already enforce embedding coverage thresholds

### Gaps for RAG

1. **No vector store:** Embeddings are stored in DataFrames, not a queryable vector index
2. **No query-time embedding:** Only batch pre-computation, no on-the-fly query embedding
3. **No hybrid retrieval:** No combination of vector search + metadata filtering
4. **Award-only:** Solicitation topics and USAspending descriptions are not embedded

---

## 5. Neo4j Graph Database (Relationship Context)

The existing Neo4j graph provides relationship traversal that complements vector search:

| Relationship | RAG Enhancement |
|-------------|----------------|
| `COMPANY_OWNS_AWARD` | "Show me all awards by company X" |
| `AWARD_FUNDED_PATENT` | "What patents came from this SBIR research?" |
| `COMPANY_OWNS_PATENT` | "What IP does this SBIR company hold?" |
| `INDIVIDUAL_PARTICIPATED_IN` | "What has researcher Y worked on?" |

Graph traversal provides **structured relational context** that pure vector search cannot (e.g., multi-hop queries like "find companies that received Phase II awards AND have patents in AI").

---

## 6. RAG Implementation Recommendations

### Architecture

```
User Query
    ↓
Query Embedding (ModernBERT-Embed)
    ↓
┌─────────────────────────────────┐
│  Hybrid Retrieval Layer         │
│  ├── Vector Search (embeddings) │
│  ├── Metadata Filters (DuckDB) │
│  └── Graph Traversal (Neo4j)   │
└─────────────────────────────────┘
    ↓
Context Assembly + Re-ranking
    ↓
LLM Generation
```

### Document Types and Priority

| Document Type | Source | Priority | Est. Volume |
|-------------- |--------|----------|-------------|
| SBIR Award (abstract + title) | SBIR.gov CSV | **P0** - Implement first | ~200K documents |
| Solicitation Topics | SBIR.gov API/bulk | **P1** - High value, needs new extractor | ~50K documents |
| Patent Abstracts | USPTO PatentsView | **P2** - Already has embeddings | ~1M+ documents |
| Company Profiles | USAspending + SAM.gov | **P3** - Metadata enrichment | ~100K entities |

### Vector Store Options

Given the existing stack (DuckDB, Neo4j, Python, Dagster):

1. **Neo4j Vector Index** (recommended) - Neo4j 5.x supports native vector indexes. Keeps embeddings co-located with graph relationships. Enables hybrid graph+vector queries.
2. **pgvector / DuckDB VSS** - DuckDB has experimental vector similarity search. Stays within existing tooling.
3. **Dedicated vector DB** (Qdrant, Weaviate, Milvus) - Best performance at scale but adds operational complexity.

### Data Preparation Steps

1. **Award chunking:** Concatenate `Award Title + Abstract + Keywords` per award, attach structured metadata
2. **Solicitation extraction:** New extractor to pull topic descriptions from SBIR.gov, deduplicate by topic_code
3. **USAspending enrichment:** Add financial and classification metadata to award chunks before indexing
4. **Embedding generation:** Extend existing embedding pipeline to embed solicitation topics
5. **Index building:** Load embeddings + metadata into chosen vector store

### Estimated Data Characteristics

| Metric | Value |
|--------|-------|
| Total embeddable documents (awards) | ~200,000 |
| Average tokens per award chunk | ~500-1500 |
| Embedding dimension (ModernBERT-Embed) | 768 |
| Estimated index size (awards only) | ~800 MB |
| With solicitations + patents | ~5-10 GB |

---

## 7. Summary

| Data Source | Text Richness | RAG Ready? | Action Needed |
|-------------|--------------|------------|---------------|
| SBIR Awards | **High** (abstracts, titles) | Mostly - needs vector store | Index existing embeddings |
| Solicitations | **High** (topic descriptions) | No - data not extracted | New extractor + embedding |
| USAspending | **Low** (transactional) | N/A - use as metadata | Enrich award chunks |
| USPTO Patents | **High** (abstracts) | Mostly - has embeddings | Index existing embeddings |
| Neo4j Graph | N/A (structural) | Complement to vector search | Hybrid query layer |

The strongest immediate ROI is indexing the existing ModernBERT-Embed award embeddings into a vector store and adding metadata filtering. The highest-value new data to add is solicitation topic descriptions.
