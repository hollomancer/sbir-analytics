# LightRAG Evaluation for SBIR Data

**Date:** 2026-04-02
**Status:** Evaluation Complete
**Prerequisite:** [RAG Data Evaluation](./rag-data-evaluation.md) (general data assessment)

## Executive Summary

This document evaluates the feasibility and value of implementing [LightRAG](https://github.com/HKUDS/LightRAG) for SBIR award, solicitation, and USAspending data. LightRAG is a graph-augmented RAG framework that extracts entities and relationships from text via LLM, builds a knowledge graph, and supports four retrieval modes (naive, local, global, hybrid). The key question is whether LightRAG's LLM-extracted graph adds sufficient value over our **existing Neo4j knowledge graph** to justify the implementation and LLM extraction cost.

**Verdict:** LightRAG's graph extraction is **largely redundant** with the existing Neo4j graph for structured entity relationships (companies, awards, patents, agencies). However, LightRAG's **community detection and global retrieval** offer genuine value for thematic summarization queries that the current system cannot answer well. A **hybrid approach** -- using the existing Neo4j graph as LightRAG's storage backend while selectively applying LLM extraction to text-heavy fields (abstracts, solicitation topics) -- is the recommended path.

---

## 1. LightRAG Architecture vs Existing Infrastructure

### LightRAG's Core Components

| Component | LightRAG Approach | Existing SBIR Equivalent |
|-----------|-------------------|--------------------------|
| **Entity extraction** | LLM-based NER from text | Structured Pydantic models (Award, Company, Patent, CET) |
| **Relationship extraction** | LLM-based RE from text | Explicit graph relationships (AWARDED_TO, FUNDED, TRANSITIONED_TO) |
| **Knowledge graph** | In-memory or Neo4j/Milvus backend | Neo4j 5.x with 8+ node types, migrations, batch loading |
| **Vector store** | nano-vectordb, Neo4j Vector, or Milvus | ModernBERT-Embed (768-dim) stored in DataFrames (no queryable index) |
| **Community detection** | Leiden algorithm for global summaries | **Not implemented** -- gap |
| **Retrieval modes** | naive/local/global/hybrid | Pathway queries (Cypher) + embedding similarity (batch only) |

### Key Overlap Assessment

**High overlap (LightRAG adds little value):**
- Entity nodes: Company, Award, Patent, CETArea, Contract, Transition -- all already modeled
- Core relationships: AWARDED_TO, FUNDED, TRANSITIONED_TO, APPLICABLE_TO, OWNS -- already in Neo4j
- Metadata filtering: agency, phase, program, year, amount -- already in DuckDB + Neo4j

**Low overlap (LightRAG adds genuine value):**
- Community detection / global summarization across award abstracts
- Implicit relationships extracted from abstract text (e.g., "collaborates with", "builds upon", "addresses challenge of")
- Cross-document thematic clustering beyond CET taxonomy
- Natural language query interface with hybrid retrieval

---

## 2. Data Source Evaluation for LightRAG

### 2.1 SBIR Award Data

**Volume:** ~200,000 documents
**LightRAG-relevant text fields:**

| Field | Entity Extraction Value | Relationship Extraction Value |
|-------|------------------------|-------------------------------|
| `abstract` (200-2000 chars) | **High** -- mentions technologies, methods, materials, applications, collaborators | **High** -- describes research relationships, problem-solution pairs, application domains |
| `award_title` (50-200 chars) | **Medium** -- technology and domain keywords | **Low** -- too short for relationship context |
| `keywords` (20-200 chars) | **Low** -- already structured; redundant with extraction | **None** -- no relational content |

**Entity types extractable from abstracts:**
- Technologies (e.g., "machine learning", "gallium nitride", "hypersonic propulsion")
- Research methods (e.g., "finite element analysis", "Monte Carlo simulation")
- Application domains (e.g., "battlefield communications", "cancer diagnostics")
- Materials (e.g., "carbon fiber composites", "perovskite solar cells")
- Institutions (when mentioned as collaborators in abstract text)
- Problems/challenges (e.g., "signal interference in GPS-denied environments")

**Relationship types extractable from abstracts:**
- `ADDRESSES_PROBLEM` -- research targeting specific challenges
- `USES_METHOD` -- methodological approaches
- `APPLIES_TO_DOMAIN` -- application areas
- `BUILDS_UPON` -- references to prior work or existing capabilities
- `PRODUCES_MATERIAL` -- material science outputs

**Assessment:** Award abstracts are the **highest-value input** for LightRAG. The text is dense with implicit entity-relationship pairs that the existing structured graph does not capture. The existing graph knows "Company X received Award Y in CET area Z" but not "Award Y uses reinforcement learning to solve autonomous navigation in GPS-denied environments."

**Cost estimate:** 200K awards x ~500 tokens avg x $3/MTok (input) + extraction output = **~$300-600 one-time LLM cost** for full corpus extraction (using Claude Haiku or similar).

### 2.2 Solicitation Topic Data

**Volume:** ~50,000 estimated topics (not yet extracted)
**Current state:** Only metadata on awards (solicitation_number, topic_code, solicitation_year). Full topic descriptions not in pipeline.

**LightRAG value if extracted:**

| Aspect | Value |
|--------|-------|
| Entity extraction | **Very High** -- solicitation topics describe specific technical problems, desired capabilities, and technology areas in detail |
| Relationship extraction | **Very High** -- topics describe problem-solution relationships, technology dependencies, and capability gaps |
| Community detection | **Very High** -- clustering solicitation topics reveals agency research themes and strategic priorities |

**Example solicitation topic text** (typical DOD SBIR):
> "Develop advanced algorithms for real-time detection and classification of low-observable unmanned aerial systems (UAS) in cluttered urban environments using passive radio frequency (RF) sensing..."

This single sentence contains extractable entities (UAS, RF sensing, urban environments) and relationships (detection APPLIED_TO UAS, RF sensing USED_FOR detection, urban environments CONSTRAINS detection).

**Assessment:** Solicitation topics are the **highest-value unrealized data source** for LightRAG. They describe the government's research needs in rich technical prose. However, a new extractor must be built first (see [RAG Data Evaluation, Section 2](./rag-data-evaluation.md#2-solicitation-data)).

**Recommendation:** P1 -- build solicitation extractor, then apply LightRAG extraction.

### 2.3 USAspending Data

**Volume:** ~100K+ recipient records, millions of transactions
**LightRAG-relevant text fields:**

| Field | Entity Extraction Value | Relationship Extraction Value |
|-------|------------------------|-------------------------------|
| Award descriptions (50-200 chars) | **Low** -- short, often generic ("SBIR Phase I") | **Very Low** -- no relational content |
| NAICS descriptions | **Low** -- standardized industry codes, already structured | **None** |
| Recipient business names | **Low** -- already captured as Company entities | **None** |

**Assessment:** USAspending data is **not a good fit for LightRAG text extraction**. It is transactional and structured, not narrative. Its value remains as metadata enrichment on SBIR award chunks (funding amounts, NAICS codes, congressional districts), as identified in the general RAG evaluation.

**Recommendation:** P3 -- use as metadata overlay, not as LightRAG input documents.

---

## 3. LightRAG Retrieval Mode Analysis

### 3.1 Naive Mode (Vector Search Only)

**How it works:** Standard vector similarity search against document chunks.
**SBIR applicability:** Equivalent to what ModernBERT-Embed embeddings would provide once indexed.
**Example query:** "SBIR awards related to quantum computing"
**Value over current system:** Moderate -- we have embeddings but no queryable vector index.

### 3.2 Local Mode (Entity-Neighborhood Search)

**How it works:** Finds relevant entities via vector search, then traverses their immediate graph neighborhood for context.
**SBIR applicability:** Maps well to existing pathway queries but adds natural language query parsing.
**Example query:** "What technologies has Raytheon developed through SBIR funding?"
**Value over current system:** **Low-Moderate** -- existing Neo4j pathway queries already support this pattern. LightRAG would add natural language interface but the graph structure is already there.

### 3.3 Global Mode (Community Summarization)

**How it works:** Uses Leiden community detection to cluster the knowledge graph, generates LLM summaries per community, then searches communities for query-relevant themes.
**SBIR applicability:** **High value** -- answers thematic questions the current system cannot.
**Example queries:**
- "What are the emerging research themes across DOD SBIR Phase II awards in 2025?"
- "How do SBIR investments in AI differ between DOD and HHS?"
- "What technology areas are seeing increased Phase I to Phase II transition rates?"

**Value over current system:** **High** -- the existing CET taxonomy provides coarse-grained categorization (21 areas), but community detection on LLM-extracted entities from abstracts would reveal finer-grained research clusters and cross-cutting themes.

### 3.4 Hybrid Mode (Local + Global)

**How it works:** Combines entity-neighborhood traversal with community-level context.
**SBIR applicability:** Best for complex analytical queries that need both specific details and thematic context.
**Example query:** "What Phase II SBIR companies are working on counter-UAS technology and what broader defense trends do they connect to?"
**Value over current system:** **Highest** -- combines the specificity of existing pathway queries with the thematic awareness that community detection provides.

---

## 4. Existing Neo4j Graph as LightRAG Backend

LightRAG supports Neo4j as a storage backend. Rather than building a parallel graph, the recommended approach is to **extend the existing Neo4j schema** with LightRAG-specific node types and relationships.

### Schema Extension Proposal

```
# New node types (LightRAG-extracted)
(:Technology {name, description, embedding})
(:ResearchMethod {name, description})
(:ApplicationDomain {name, description})
(:Problem {name, description})
(:Community {id, summary, level})       # Leiden communities

# New relationships (LightRAG-extracted from abstracts)
(award:Award)-[:MENTIONS_TECHNOLOGY]->(t:Technology)
(award:Award)-[:USES_METHOD]->(m:ResearchMethod)
(award:Award)-[:ADDRESSES_PROBLEM]->(p:Problem)
(award:Award)-[:APPLIES_TO_DOMAIN]->(d:ApplicationDomain)
(t:Technology)-[:RELATED_TO]->(t2:Technology)

# Community membership
(award:Award)-[:BELONGS_TO_COMMUNITY]->(c:Community)
(t:Technology)-[:BELONGS_TO_COMMUNITY]->(c:Community)
```

### Coexistence with Existing Schema

| Existing Node | LightRAG Interaction |
|--------------|---------------------|
| `Award` | Source document for entity extraction; gains new outgoing relationships to extracted entities |
| `Company` | No change; already well-modeled. LightRAG may extract company mentions from abstracts but should resolve to existing Company nodes |
| `Patent` | Additional extraction source (patent abstracts); gains MENTIONS_TECHNOLOGY relationships |
| `CETArea` | Coarse taxonomy complement; LightRAG communities provide finer granularity within CET areas |
| `Transition` | Not a text source; existing structured relationships preserved |
| `Contract` | Not a text source; existing structured relationships preserved |

---

## 5. Implementation Cost-Benefit Analysis

### Costs

| Cost Category | Estimate | Notes |
|--------------|----------|-------|
| LLM extraction (full corpus) | $300-600 | One-time; 200K awards x ~500 tokens avg |
| LLM extraction (incremental) | ~$5-15/month | Weekly award refresh (~500 new awards/week) |
| Community summarization | $50-100 | Leiden communities + LLM summary generation |
| Development effort | 2-3 weeks | Integration with existing Neo4j, Dagster assets, embedding pipeline |
| Neo4j storage overhead | ~20-30% increase | New node types and relationships |

### Benefits

| Benefit | Impact | Current Gap Filled |
|---------|--------|-------------------|
| Natural language query over SBIR corpus | **High** | No NL query interface today |
| Thematic research cluster discovery | **High** | CET taxonomy too coarse (21 areas) |
| Cross-award technology relationship mapping | **Medium** | Only explicit structured relationships exist |
| Implicit collaboration/dependency discovery | **Medium** | Abstract text not mined for relationships |
| Solicitation-to-award semantic matching | **High** (with solicitation extractor) | Only topic_code linkage exists |

### Break-Even Assessment

LightRAG is worth implementing if the primary use case involves **analytical/thematic queries** ("what research themes are emerging?", "how do investments in X relate to Y?"). It is **not worth implementing** if queries are purely structured lookups ("show me Phase II awards for Company X in 2024") -- those are already well-served by Neo4j Cypher and DuckDB.

---

## 6. Recommended Implementation Approach

### Phase 1: Vector Index Foundation (P0)

Index existing ModernBERT-Embed embeddings into a queryable store. This enables LightRAG's naive mode and provides the vector search layer that all other modes depend on.

- Add Neo4j Vector Index on Award nodes (768-dim, cosine similarity)
- Add query-time embedding endpoint using the embedding client (ModernBERT-Embed)
- Integrate as Dagster asset downstream of `paecter_embeddings_awards`

### Phase 2: LightRAG Entity Extraction on Awards (P1)

Apply LLM-based entity/relationship extraction to award abstracts. Use the existing Neo4j as storage backend.

- Configure LightRAG with Neo4j backend pointing to existing database
- Define extraction schema (Technology, Method, Domain, Problem entities)
- Run extraction on award abstracts, resolve Company entities to existing nodes
- Add as Dagster asset downstream of `validated_sbir_awards`

### Phase 3: Community Detection and Global Mode (P1)

Run Leiden community detection on the combined graph (existing + extracted).

- Apply Leiden algorithm to the Neo4j graph
- Generate LLM summaries for each community
- Enable global and hybrid retrieval modes
- Validate community quality against CET taxonomy (communities should refine, not contradict CET areas)

### Phase 4: Solicitation Topic Integration (P2)

Build solicitation extractor and apply LightRAG extraction.

- New `sbir_etl/extractors/solicitation.py` to pull topic descriptions
- Apply LightRAG extraction to solicitation text
- Link solicitation entities to award entities via shared Technology/Problem nodes
- Enables "what SBIR topics address X?" queries

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM extraction quality inconsistent across abstract styles | Medium | Medium | Use structured extraction prompts; validate against CET labels |
| Duplicate entities from extraction (e.g., "ML" vs "machine learning") | High | Medium | Entity resolution pipeline; normalize against controlled vocabulary |
| Community detection produces non-meaningful clusters | Medium | Medium | Tune Leiden resolution parameter; validate against domain expert expectations |
| LLM cost overruns on large corpus | Low | Low | Use Haiku-class model for extraction; batch processing |
| Neo4j performance degradation with added nodes/relationships | Low | Medium | Use separate relationship types; index extraction-derived nodes |
| Overlap with CET taxonomy causes confusion | Medium | Low | Position communities as refinement within CET areas, not replacement |

---

## 8. Comparison Matrix: LightRAG vs Current System

| Query Type | Current System | With LightRAG | Delta |
|-----------|---------------|---------------|-------|
| "Awards by company X in year Y" | DuckDB/Neo4j (excellent) | Same | None |
| "Awards related to quantum computing" | No semantic search | Naive mode (good) | **+++ Major** |
| "What technologies does company X work on?" | CET areas only | Local mode (detailed) | **++ Significant** |
| "Emerging research themes in DOD SBIR" | Manual analysis | Global mode (automated) | **+++ Major** |
| "Award → Patent → Transition pathway" | Pathway queries (excellent) | Same | None |
| "How do AI investments differ across agencies?" | CET + manual aggregation | Hybrid mode (thematic) | **++ Significant** |
| "Find companies working on similar problems" | Embedding similarity (batch only) | Local mode (real-time) | **+ Moderate** |

---

## 9. Decision Framework

**Implement LightRAG if:**
- Thematic/analytical queries are a primary use case
- Natural language query interface is desired
- Budget allows $300-600 one-time + $50-100/month ongoing LLM costs
- 2-3 weeks development time is acceptable

**Skip LightRAG if:**
- Queries are predominantly structured lookups
- CET taxonomy granularity is sufficient for categorization needs
- LLM cost is a concern
- The existing Neo4j + DuckDB stack meets current query needs

**Recommended:** Proceed with Phase 1 (vector index) regardless -- it's low-cost and fills a clear gap. Evaluate LightRAG extraction (Phase 2+) based on user query patterns after vector search is available.

---

## 10. Replacement Analysis: Where LightRAG Replaces vs Complements

The question of whether to **replace** existing components with LightRAG equivalents (vs layering LightRAG on top) is critical for avoiding maintenance burden from redundant systems. This section evaluates each existing component.

### 10.1 Components LightRAG Should NOT Replace

#### Neo4j Knowledge Graph (KEEP)

The existing Neo4j schema represents **curated, validated, structured relationships** with confidence scores, detection methods, and evidence metadata:

```
(a:Award)-[r:TRANSITIONED_TO {score: 0.87, confidence: "high", detection_date: ...}]->(t:Transition)
(t:Transition)-[:RESULTED_IN]->(c:Contract)
(p:Patent)-[:GENERATED_FROM]->(a:Award)
```

LightRAG's entity/relationship extraction produces **inferred, unvalidated relationships** from text. These are fundamentally different in provenance and trustworthiness. The existing graph represents ground-truth data lineage (Award X was actually awarded to Company Y); LightRAG extractions represent semantic interpretation ("this abstract mentions reinforcement learning").

**Verdict: Keep.** The existing Neo4j graph is authoritative structured data. LightRAG should write *into* this graph as additional node/relationship types, not replace it.

#### TransitionPathwayQueries (KEEP)

The 8 pathway query methods in `pathway_queries.py` are **precision-oriented analytical queries** with specific filtering (confidence levels, score thresholds, CET areas). They return structured PathwayResult objects used downstream in evaluation and reporting.

LightRAG's local mode traverses graph neighborhoods but lacks:
- Configurable confidence/score filtering
- Specific multi-hop pattern matching (Award → Patent → Transition → Contract)
- Structured aggregation (transition rates by CET area, patent-backed rates)

**Verdict: Keep.** These are analytical workhorses, not retrieval queries. LightRAG retrieval and pathway queries serve different purposes.

#### Transition Detection Scoring (KEEP)

The 6-signal scoring system (agency, timing, competition, patent, amount, text similarity) in `sbir_ml/transition/detection/scoring.py` is a validated ML pipeline with >=85% precision benchmarks. LightRAG has no equivalent for this kind of structured signal composition.

**Verdict: Keep.** Not a retrieval problem; LightRAG is irrelevant here.

#### Pydantic Data Models (KEEP)

Award, Patent, Company, Contract, Transition, CET models provide validation, serialization, and type safety throughout the ETL pipeline. LightRAG does not replace data modeling.

**Verdict: Keep.** Orthogonal concern.

### 10.2 Components LightRAG CAN Replace

#### ClusterTopicsTool -- Greedy Agglomerative Clustering (REPLACE)

**Current:** `tools/mission_a/cluster_topics.py` uses embedding cosine similarity with a greedy agglomerative approach and a fixed 0.85 threshold to cluster solicitation topics across agencies.

**LightRAG equivalent:** Global mode with Leiden community detection over LLM-extracted entity graph. This is strictly better because:

1. **Richer signal:** Clusters based on shared extracted entities (technologies, methods, problems) rather than raw embedding similarity, which conflates topical with lexical similarity
2. **Hierarchical:** Leiden produces multi-resolution communities; the current tool only supports a single threshold
3. **Explainable:** Community membership is traceable through shared entities; embedding clusters are opaque
4. **Cross-agency by design:** Community detection naturally surfaces cross-cutting themes without the `cross_agency_only` flag hack

**Migration path:** Replace `ClusterTopicsTool.execute()` internals with LightRAG global retrieval. Keep the `ToolResult` interface and `ToolMetadata` contract.

**Risk:** Low. The current tool is a standalone analysis tool, not part of the core ETL pipeline.

#### Batch Embedding Similarity (award-patent) (PARTIALLY REPLACE)

**Current:** `paecter_award_patent_similarity` Dagster asset computes an N x M cosine similarity matrix between all award and patent embeddings, filters by threshold (0.80), and outputs a DataFrame of (award_id, patent_id, similarity_score) tuples.

**LightRAG replacement potential:** LightRAG's local mode can answer "what patents relate to this award?" via entity-neighborhood traversal, which is more semantically meaningful than raw embedding cosine similarity. An award about "adaptive optics for satellite imaging" and a patent about "wavefront correction systems" might share few lexical features but share the extracted entity `adaptive_optics`.

**However:** The current batch similarity is used as an input signal for transition detection (patent_topic_similarity score feeds into the 6-signal scoring). Replacing it with graph traversal would require revalidating the >=85% precision benchmark.

**Verdict: Partial replacement.** Use LightRAG local mode for interactive "find related patents" queries. Keep batch similarity for the transition detection pipeline until revalidation confirms graph-based matching maintains precision.

#### CET Classification Granularity (SUPPLEMENT, not replace)

**Current:** 21 CET areas from the NSTC taxonomy, assigned via ML classifier with confidence scores. Coarse-grained by design (e.g., "Artificial Intelligence" covers everything from NLP to robotics).

**LightRAG addition:** Leiden communities within each CET area would provide sub-topic granularity. For example, within "Artificial Intelligence":
- Community: autonomous navigation (reinforcement learning, path planning, GPS-denied)
- Community: NLP for intelligence analysis (entity extraction, document classification)
- Community: predictive maintenance (anomaly detection, sensor fusion, digital twins)

**Verdict: Supplement.** CET taxonomy is a government-defined standard; it cannot be replaced. LightRAG communities provide valuable sub-classification within CET areas.

### 10.3 Components Where LightRAG Fills Gaps (NEW)

| Gap | Current State | LightRAG Solution |
|-----|--------------|-------------------|
| **No semantic search** | Embeddings exist in DataFrames, no query interface | Naive mode: vector index + query-time embedding |
| **No NL query interface** | All queries are Cypher or Python API | All 4 modes accept natural language queries |
| **No implicit relationship discovery** | Only explicit structured relationships | LLM extraction finds "uses", "builds upon", "addresses" from text |
| **No thematic summarization** | CET areas are static categories | Global mode generates dynamic community summaries |
| **No cross-document reasoning** | Each award is an island (except graph links) | Entity co-occurrence across documents creates implicit connections |

### 10.4 Summary: Replace, Keep, or Supplement

| Component | File(s) | Verdict | Rationale |
|-----------|---------|---------|-----------|
| Neo4j graph schema | `sbir-graph/loaders/neo4j/` | **Keep** | Authoritative structured data; LightRAG writes into it |
| TransitionPathwayQueries | `sbir-graph/queries/pathway_queries.py` | **Keep** | Analytical precision queries, not retrieval |
| Transition detection scoring | `sbir_ml/transition/detection/scoring.py` | **Keep** | Validated ML pipeline, orthogonal to RAG |
| Pydantic models | `sbir_etl/models/` | **Keep** | Data validation, orthogonal |
| Embedding client (ModernBERT-Embed) | `sbir_ml/ml/paecter_client.py` | **Keep** | LightRAG uses these embeddings as its vector layer |
| ClusterTopicsTool | `tools/mission_a/cluster_topics.py` | **Replace** | LightRAG global mode is strictly better |
| Batch award-patent similarity | `assets/paecter/embeddings.py` | **Partial** | Replace for interactive queries; keep for scoring pipeline |
| CET taxonomy (21 areas) | `sbir_ml/ml/config/taxonomy_loader.py` | **Supplement** | Add sub-topic communities within CET areas |
| Embedding storage (DataFrames) | `assets/paecter/embeddings.py` | **Replace** | Move to Neo4j Vector Index for queryable storage |
| No semantic search | N/A | **New** | LightRAG naive mode fills this gap |
| No NL query interface | N/A | **New** | All LightRAG modes provide this |
| No implicit relationships | N/A | **New** | LLM extraction from abstracts |
| No thematic summarization | N/A | **New** | Leiden community summaries |
