# LightRAG Implementation Plan

**Date:** 2026-04-02
**Status:** Plan Complete
**Prerequisites:** [LightRAG Evaluation](./lightrag-evaluation.md), [RAG Data Evaluation](./rag-data-evaluation.md)

## Architecture Overview

LightRAG integrates as a new package `packages/sbir-rag/` that bridges the existing Neo4j graph, ModernBERT-Embed embedding pipeline, and Dagster orchestration. It does **not** replace the existing infrastructure -- it creates a *semantic overlay* on top of the structured graph and fills gaps identified in the evaluation (semantic search, NL queries, implicit relationships, thematic summarization).

> **Note on naming:** The embedding client and Dagster assets still use legacy `paecter` names in code (`PaECTERClient`, `paecter_client.py`, `assets/paecter/`), but the underlying model is **ModernBERT-Embed** (`nomic-ai/modernbert-embed-base`, 768-dim). New LightRAG code should reference the module paths as-is but avoid introducing new `paecter` names. A future rename is out of scope for this plan.

```
                    ┌──────────────────────────────────────┐
                    │          Query Interface              │
                    │  sbir-cli rag query "..."             │
                    │  SBIRQueryService (4 modes)           │
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────┐
                    │          LightRAG Core                │
                    │  packages/sbir-rag/sbir_rag/          │
                    │  ├── factory.py (instance creation)   │
                    │  ├── embedding_adapter.py (ModernBERT) │
                    │  ├── document_prep.py (Award → doc)   │
                    │  └── query_service.py (retrieval)     │
                    └──────────┬───────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
   ┌──────────▼──────┐ ┌──────▼──────┐ ┌───────▼──────────┐
   │  Neo4j 5.x      │ │  Embedding  │ │  Dagster Assets   │
   │  (existing +    │ │  Client     │  │  (new lightrag    │
   │   LightRAG      │ │  (768-dim   │  │   asset group)    │
   │   nodes/rels)   │ │  ModernBERT)│ │                   │
   └─────────────────┘ └─────────────┘ └───────────────────┘
```

### Three Integration Surfaces

1. **Embedding adapter** -- wraps the existing embedding client (`paecter_client.py:PaECTERClient`) so LightRAG uses ModernBERT-Embed (768-dim) instead of its default OpenAI embeddings
2. **Neo4j storage backend** -- LightRAG uses the existing Neo4j instance; its internal nodes (`__entity__`, `__relationship__`, `__community__`) coexist with Award/Company/Patent/CET nodes via double-underscore prefix isolation
3. **Dagster assets** -- new `lightrag` asset group for ingestion, community detection, vector indexing, and cross-referencing

### Schema Isolation Strategy

LightRAG's Neo4j backend creates nodes with `__entity__`, `__relationship__`, `__community__` labels (double-underscore prefixed). These do not collide with existing labels (Award, Company, Patent, CETArea, Transition, Contract, Organization). A post-ingestion Dagster asset creates cross-reference relationships linking extracted entities back to structured nodes.

---

## Phase 1: Foundation (Week 1-2)

### 1.1 Create `packages/sbir-rag/` package

**New files:**

| File | Purpose |
|------|---------|
| `packages/sbir-rag/pyproject.toml` | Package config; deps: `lightrag-hku>=1.0.0`, `sbir-ml`, `sbir-graph`, `sbir-etl` |
| `packages/sbir-rag/sbir_rag/__init__.py` | Package init |
| `packages/sbir-rag/sbir_rag/config.py` | `LightRAGConfig` Pydantic model |
| `packages/sbir-rag/sbir_rag/embedding_adapter.py` | ModernBERT-Embed → LightRAG embedding function adapter |
| `packages/sbir-rag/sbir_rag/factory.py` | LightRAG instance factory with Neo4j backend |

### 1.2 LightRAGConfig

Pydantic config model following the `PaECTERClientConfig` pattern in `packages/sbir-ml/sbir_ml/ml/config/__init__.py`:

```python
class LightRAGConfig(BaseModel):
    workspace: str = "sbir"
    neo4j_uri: str
    neo4j_username: str = "neo4j"
    neo4j_password: str
    neo4j_database: str = "neo4j"
    embedding_model: str = "nomic-ai/modernbert-embed-base"
    embedding_dim: int = 768
    use_local_embeddings: bool = False
    llm_model: str = "claude-haiku-4-5-20251001"
    chunk_size: int = 1200
    chunk_overlap: int = 100
    community_algorithm: str = "leiden"
    max_community_levels: int = 3
```

### 1.3 Embedding Adapter

Wraps the existing embedding client's `generate_embeddings()` (sync) as the async function LightRAG expects. The adapter references the legacy `PaECTERClient` class name (the underlying model is ModernBERT-Embed):

```python
# packages/sbir-rag/sbir_rag/embedding_adapter.py
async def create_embedding_func(config: LightRAGConfig) -> Callable:
    client = PaECTERClient(config=PaECTERClientConfig(
        model_name=config.embedding_model,
        use_local=config.use_local_embeddings,
        enable_cache=True,
    ))

    async def embed(texts: list[str]) -> np.ndarray:
        result = await asyncio.to_thread(
            client.generate_embeddings, texts, normalize=True
        )
        return result.embeddings

    return embed
```

This ensures the existing 768-dim ModernBERT-Embed vectors are used consistently. LightRAG's default (OpenAI ada-002, 1536-dim) would create an incompatible parallel embedding space.

### 1.4 LightRAG Instance Factory

```python
# packages/sbir-rag/sbir_rag/factory.py
async def create_lightrag_instance(config: LightRAGConfig) -> LightRAG:
    embedding_func = await create_embedding_func(config)

    rag = LightRAG(
        working_dir=f"/tmp/lightrag_{config.workspace}",
        embedding_func=EmbeddingFunc(
            embedding_dim=config.embedding_dim,
            max_token_size=8192,  # ModernBERT context window
            func=embedding_func,
        ),
        graph_storage="Neo4JStorage",
        vector_storage="Neo4JStorage",
        kv_storage="Neo4JStorage",
        graph_storage_params={
            "uri": config.neo4j_uri,
            "user": config.neo4j_username,
            "password": config.neo4j_password,
            "database": config.neo4j_database,
        },
    )
    return rag
```

### 1.5 Neo4j Migration

**New file: `migrations/versions/004_lightrag_schema.py`**

Following the pattern from `migrations/versions/001_initial_schema.py`:

```python
# Vector index for Award embeddings (replaces DataFrame storage)
CREATE VECTOR INDEX award_embedding IF NOT EXISTS
  FOR (a:Award) ON (a.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }}

# Vector index for Patent embeddings
CREATE VECTOR INDEX patent_embedding IF NOT EXISTS
  FOR (p:Patent) ON (p.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }}

# Index for LightRAG entity cross-references
CREATE INDEX lrag_entity_source_id IF NOT EXISTS
  FOR (e:__entity__) ON (e.source_id)
```

### 1.6 Configuration

Add to `config/base.yaml`:

```yaml
lightrag:
  enabled: false  # Opt-in
  workspace: "sbir"
  llm:
    model: "claude-haiku-4-5-20251001"
    max_tokens: 4096
    temperature: 0.0
  chunking:
    chunk_size: 1200
    chunk_overlap: 100
  community_detection:
    algorithm: "leiden"
    max_levels: 3
    resolution: 1.0
  retrieval:
    default_mode: "hybrid"
    top_k: 10
    similarity_threshold: 0.75
```

---

## Phase 2: Document Ingestion Pipeline (Week 2-3)

### 2.1 Document Preparation

**New file: `packages/sbir-rag/sbir_rag/document_prep.py`**

Converts Award records into LightRAG documents. Reuses the embedding client's `prepare_award_text()` text composition logic but adds structured context headers for better entity extraction:

```python
def prepare_award_document(row: pd.Series) -> dict:
    """Convert a DataFrame row (from validated_sbir_awards) to a LightRAG document."""
    parts = []
    for field in ["award_title", "abstract"]:
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            parts.append(str(val).strip())
    text = " ".join(parts)

    header = f"Agency: {row.get('agency', 'Unknown')}. Phase: {row.get('phase', '')}. "
    keywords = row.get("keywords")
    if pd.notna(keywords) and str(keywords).strip():
        header += f"Keywords: {keywords}. "
    return {
        "content": header + text,
        "metadata": {
            "award_id": str(row.get("award_id", "")),
            "agency": row.get("agency"),
            "phase": row.get("phase"),
            "award_year": row.get("award_year"),
        },
    }
```

### 2.2 Dagster Assets

**New files:**

| File | Asset | Depends On |
|------|-------|------------|
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/__init__.py` | Module init | -- |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/ingestion.py` | `lightrag_document_ingestion` | `validated_sbir_awards` |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/vector_index.py` | `neo4j_award_embeddings` | `paecter_embeddings_awards` |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/cross_reference.py` | `lightrag_entity_cross_references` | `lightrag_document_ingestion` |

**Asset: `lightrag_document_ingestion`**

```python
@asset(
    description="Ingest SBIR awards into LightRAG knowledge graph",
    group_name="lightrag",
    compute_kind="llm",
)
async def lightrag_document_ingestion(
    context, validated_sbir_awards: pd.DataFrame
) -> Output[dict]:
    config = LightRAGConfig.from_yaml(get_config())
    rag = await create_lightrag_instance(config)

    documents = [prepare_award_document(row) for _, row in validated_sbir_awards.iterrows()]
    for batch in batched(documents, batch_size=100):
        await rag.ainsert([doc["content"] for doc in batch])

    return Output({"documents_ingested": len(documents)}, ...)
```

**Asset: `neo4j_award_embeddings`** (replaces DataFrame storage)

Downstream consumer of `paecter_embeddings_awards` that writes embeddings into Award nodes via batch UNWIND, making them queryable via the vector index from migration 004.

**Asset: `lightrag_entity_cross_references`**

Post-ingestion linking of LightRAG `__entity__` nodes back to existing structured nodes (Award, Company, Organization) using UEI/name matching with the same fuzzy threshold (90% high confidence) from the enrichment pipeline.

### 2.3 Register in HEAVY_ASSET_MODULES

**Modify: `packages/sbir-analytics/sbir_analytics/assets/__init__.py`**

Add to the `HEAVY_ASSET_MODULES` set (line 22):

```python
HEAVY_ASSET_MODULES = {
    ...existing entries...
    "sbir_analytics.assets.lightrag.ingestion",    # LLM extraction, expensive
    "sbir_analytics.assets.lightrag.communities",  # Graph computation
}
```

---

## Phase 3: Community Detection & ClusterTopicsTool Replacement (Week 3-4)

### 3.1 Community Detection Asset

**New file: `packages/sbir-analytics/sbir_analytics/assets/lightrag/communities.py`**

```python
@asset(
    description="Detect topic communities using Leiden algorithm",
    group_name="lightrag",
    compute_kind="graph",
    deps=["lightrag_document_ingestion"],
)
async def lightrag_topic_communities(context) -> Output[pd.DataFrame]:
    # LightRAG builds communities during insertion
    # This asset extracts and stores community metadata
    # Queries __community__ nodes from Neo4j
```

### 3.2 LeidenTopicsTool (Replaces ClusterTopicsTool)

**New file: `packages/sbir-analytics/sbir_analytics/tools/mission_a/leiden_topics.py`**

Extends `BaseTool` with the same `ToolResult`/`ToolMetadata` interface as `ClusterTopicsTool`:

```python
class LeidenTopicsTool(BaseTool):
    """Cluster topics using LightRAG Leiden communities.

    Replacement for ClusterTopicsTool. Uses graph-based community
    detection instead of greedy agglomerative embedding clustering.
    """

    name = "leiden_topics"
    version = "2.0.0"

    def execute(self, metadata: ToolMetadata, *, ...) -> ToolResult:
        # Query LightRAG global mode for community structure
        # Return same schema: cluster_id, topic_ids, agencies, num_topics
```

**Why this is better than ClusterTopicsTool:**
- Clusters on shared extracted entities (technologies, methods, problems) not raw embedding similarity
- Hierarchical multi-resolution communities vs single-threshold clustering
- Explainable via entity co-occurrence vs opaque cosine similarity
- Cross-agency naturally without a special `cross_agency_only` flag

### 3.3 CET Sub-Community Mapping

**New file: `packages/sbir-analytics/sbir_analytics/assets/lightrag/cet_subcommunities.py`**

```python
@asset(
    description="Map Leiden sub-communities within CET taxonomy areas",
    group_name="lightrag",
    deps=["lightrag_topic_communities"],
)
def cet_subcommunity_mapping(context) -> Output[pd.DataFrame]:
    # For each of the 21 CETArea nodes, find LightRAG communities
    # whose member entities overlap with awards in that CET
    # Creates (:CETArea)-[:HAS_SUBCOMMUNITY]->(:__community__) rels
```

### 3.4 ClusterTopicsTool Deprecation Path

1. Create `LeidenTopicsTool` with matching output schema
2. Add deprecation warning to `ClusterTopicsTool.execute()`
3. Update `mission_a/__init__.py` to default to Leiden
4. After validation (1 sprint), remove `ClusterTopicsTool` from exports
5. Delete file after one release cycle

---

## Phase 4: Solicitation Topic Extraction & Ingestion (Week 4-5)

The current pipeline has **no solicitation topic descriptions**. Award records contain only solicitation metadata (`solicitation_number`, `topic_code`, `solicitation_year`, dates) -- not the 500-3000 word topic descriptions that describe the government's research needs. This is the highest-value unrealized data source for LightRAG.

### 4.1 Solicitation Data Sources

SBIR.gov provides solicitation topic data through:

1. **SBIR.gov API** (`https://api.www.sbir.gov/public/api/`) -- the existing `SbirGovClient` only queries the `/awards` endpoint. The API also exposes solicitation topics with full descriptions.
2. **Bulk downloads** (`https://www.sbir.gov/data-resources`) -- solicitation data is available alongside award data.
3. **Award records** -- topic descriptions are sometimes embedded in API award responses but not in the CSV bulk download that the current extractor uses.

### 4.2 Solicitation Extractor

**New file: `sbir_etl/extractors/solicitation.py`**

New extractor following the pattern established by `sbir_etl/extractors/sbir_gov_api.py`:

```python
class SolicitationExtractor:
    """Extract solicitation topic descriptions from SBIR.gov.

    Pulls full topic text including:
    - Topic title and description (500-3000 words)
    - Agency, branch, and program
    - Open/close dates
    - Topic number and solicitation number
    """

    def __init__(self, client: SbirGovClient | None = None):
        self.client = client or SbirGovClient()

    def extract_topics(
        self,
        *,
        agency: str | None = None,
        year: int | None = None,
    ) -> pd.DataFrame:
        """Extract solicitation topics with full descriptions."""

    def deduplicate_topics(self, topics_df: pd.DataFrame) -> pd.DataFrame:
        """Deduplicate by (topic_code, solicitation_number)."""
```

### 4.3 Solicitation Model

**New file: `sbir_etl/models/solicitation.py`**

```python
class Solicitation(BaseModel):
    """SBIR/STTR solicitation topic."""

    topic_code: str = Field(..., description="Topic identifier (e.g., 'AF231-001')")
    solicitation_number: str = Field(..., description="Parent solicitation number")
    title: str = Field(..., description="Topic title")
    description: str | None = Field(None, description="Full topic description (500-3000 words)")
    agency: str | None = Field(None, description="Issuing agency")
    branch: str | None = Field(None, description="Agency branch")
    program: str | None = Field(None, description="SBIR or STTR")
    open_date: date | None = Field(None)
    close_date: date | None = Field(None)
    year: int | None = Field(None)
```

### 4.4 Solicitation Dagster Assets

**New files:**

| File | Asset | Depends On |
|------|-------|------------|
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/solicitations.py` | `extracted_solicitation_topics` | None (raw extraction) |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/solicitations.py` | `lightrag_solicitation_ingestion` | `extracted_solicitation_topics` |

```python
@asset(
    description="Extract solicitation topics from SBIR.gov",
    group_name="lightrag",
    compute_kind="extraction",
)
def extracted_solicitation_topics(context) -> Output[pd.DataFrame]:
    extractor = SolicitationExtractor()
    topics_df = extractor.extract_topics()
    topics_df = extractor.deduplicate_topics(topics_df)
    return Output(topics_df, metadata={"topic_count": len(topics_df)})


@asset(
    description="Ingest solicitation topics into LightRAG",
    group_name="lightrag",
    compute_kind="llm",
)
async def lightrag_solicitation_ingestion(
    context, extracted_solicitation_topics: pd.DataFrame
) -> Output[dict]:
    config = LightRAGConfig.from_yaml(get_config())
    rag = await create_lightrag_instance(config)

    documents = [prepare_solicitation_document(row) for _, row in extracted_solicitation_topics.iterrows()]
    for batch in batched(documents, batch_size=100):
        await rag.ainsert([doc["content"] for doc in batch])

    return Output({"topics_ingested": len(documents)})
```

### 4.5 Document Preparation for Solicitations

Add to `packages/sbir-rag/sbir_rag/document_prep.py`:

```python
def prepare_solicitation_document(solicitation: dict) -> dict:
    """Convert solicitation topic to LightRAG document.

    Solicitation descriptions are typically 500-3000 words of technical
    prose -- far richer than award abstracts for entity extraction.
    """
    header = (
        f"Solicitation Topic: {solicitation['topic_code']}. "
        f"Agency: {solicitation.get('agency', 'Unknown')}. "
        f"Program: {solicitation.get('program', 'SBIR')}. "
    )
    body = f"{solicitation['title']}. {solicitation.get('description', '')}"
    return {
        "content": header + body,
        "metadata": {
            "topic_code": solicitation["topic_code"],
            "solicitation_number": solicitation.get("solicitation_number"),
            "agency": solicitation.get("agency"),
            "year": solicitation.get("year"),
            "document_type": "solicitation",
        },
    }
```

### 4.6 Cross-Document Linking

After both awards and solicitations are ingested, LightRAG's entity graph naturally connects them through shared extracted entities. An award abstract mentioning "counter-UAS detection in urban RF environments" and a solicitation topic describing "passive RF sensing for low-observable UAS in cluttered urban environments" will share Technology and Problem entities, creating implicit solicitation-to-award links that go beyond the `topic_code` join key.

Additionally, a post-processing Dagster asset creates explicit links between Award nodes and solicitation source documents using the existing `topic_code` + `solicitation_number` join keys:

```cypher
// Link awards to solicitation source chunks via topic_code
MATCH (a:Award), (chunk:__chunk__)
WHERE chunk.metadata_topic_code IS NOT NULL
  AND a.topic_code = chunk.metadata_topic_code
MERGE (a)-[:RESPONDS_TO_TOPIC]->(chunk)
```

> **Note:** The exact property names on LightRAG's `__chunk__` and `__entity__` nodes depend on how LightRAG's Neo4j backend stores document metadata. The cross-reference asset must inspect the actual schema after initial ingestion and adjust accordingly.

### 4.7 Estimated Volume and Cost

| Metric | Estimate |
|--------|----------|
| Solicitation topics (all agencies, all years) | ~50,000 |
| Average tokens per topic description | ~1,000-3,000 |
| LLM extraction cost (Claude Haiku) | ~$150-400 |
| Embedding cost (ModernBERT-Embed, included in existing pipeline) | Negligible |

---

## Phase 5: Query Interface (Week 5-6)

### 5.1 Query Service

**New file: `packages/sbir-rag/sbir_rag/query_service.py`**

```python
class SBIRQueryService:
    """Semantic search and NL query interface over SBIR awards."""

    async def semantic_search(self, query: str, top_k: int = 10) -> list[dict]:
        """Naive mode: vector-only search."""

    async def entity_neighborhood(self, query: str) -> list[dict]:
        """Local mode: entity-centric retrieval with graph context."""

    async def thematic_summary(self, query: str) -> str:
        """Global mode: community-based thematic summarization."""

    async def hybrid_query(self, query: str) -> dict:
        """Hybrid mode: local + global combined."""
```

### 5.2 Interactive Similarity Search

**New file: `packages/sbir-rag/sbir_rag/interactive_similarity.py`**

Replaces the batch `paecter_award_patent_similarity` for interactive queries using Neo4j vector index k-NN:

```python
async def find_similar_awards(query_text: str, top_k: int = 10) -> list[dict]:
    """Real-time similarity search using Neo4j vector index."""
    # Generate query embedding via embedding client (ModernBERT-Embed)
    # CALL db.index.vector.queryNodes('award_embedding', $k, $embedding)
```

The batch `paecter_award_patent_similarity` asset is **kept** for the transition detection scoring pipeline (must maintain >=85% precision).

### 5.3 CLI Integration

**Modify: `packages/sbir-analytics/sbir_analytics/cli/`**

Add subcommands:

```
sbir-cli rag query "what SBIR topics relate to autonomous vehicles?"
sbir-cli rag search "quantum computing" --top-k 20
sbir-cli rag communities --cet-area artificial_intelligence
sbir-cli rag status  # ingestion stats, community count, index health
```

---

## Phase 6: Dagster Pipeline Integration (Week 6-7)

### 6.1 Job Definition

**New file: `packages/sbir-analytics/sbir_analytics/assets/jobs/lightrag_job.py`**

Following the pattern in `assets/jobs/paecter_job.py`:

```python
lightrag_ingestion_job = define_asset_job(
    name="lightrag_ingestion_job",
    selection=AssetSelection.groups("lightrag"),
    description="Ingest SBIR awards into LightRAG and build communities",
)
```

### 6.2 Asset Dependency Graph

```
validated_sbir_awards
    │
    ├── lightrag_document_ingestion (LLM extraction → Neo4j __entity__/__relationship__)
    │       │
    │       ├── lightrag_entity_cross_references (__entity__ → Award/Company linking)
    │       │
    │       └──┐
    │          │
    │   extracted_solicitation_topics (NEW: SBIR.gov topic extraction)
    │       │
    │       └── lightrag_solicitation_ingestion (LLM extraction from topic descriptions)
    │               │
    │               └──┐
    │                  │
    │          lightrag_topic_communities (Leiden detection → __community__ nodes)
    │                  │  (depends on both award + solicitation ingestion)
    │                  │
    │                  └── cet_subcommunity_mapping (CETArea → __community__ linking)
    │
    └── paecter_embeddings_awards (existing, unchanged)
            │
            ├── neo4j_award_embeddings (NEW: write to Neo4j vector index)
            │
            └── paecter_award_patent_similarity (existing, unchanged)
```

### 6.3 Package Dependency Updates

| File | Change |
|------|--------|
| `packages/sbir-analytics/pyproject.toml` | Add `sbir-rag` to dependencies |
| `pyproject.toml` (root) | Add `sbir-rag` to dev extras |

---

## Testing Strategy

Following the existing pytest marker system in `pyproject.toml`:

### Unit Tests

| File | Tests |
|------|-------|
| `tests/sbir_rag/test_embedding_adapter.py` | Embedding adapter produces 768-dim, handles batching, caching |
| `tests/sbir_rag/test_document_prep.py` | Award-to-document conversion, null handling, header formatting |
| `tests/sbir_rag/test_config.py` | LightRAGConfig validation, YAML loading, env overrides |
| `tests/sbir_rag/test_query_service.py` | Query routing to correct LightRAG mode (mocked) |
| `tests/sbir_rag/test_solicitation_extractor.py` | Solicitation extraction, deduplication, null descriptions |
| `tests/sbir_rag/test_solicitation_prep.py` | Solicitation-to-document conversion, metadata mapping |

### Integration Tests (`@pytest.mark.integration`)

| File | Tests |
|------|-------|
| `tests/sbir_rag/test_neo4j_vector_index.py` | Vector index creation, k-NN queries (`@pytest.mark.requires_neo4j`) |
| `tests/sbir_rag/test_lightrag_ingestion.py` | End-to-end ingestion with mocked LLM |
| `tests/sbir_rag/test_cross_reference.py` | Entity-to-Award linking accuracy |
| `tests/sbir_rag/test_solicitation_ingestion.py` | Solicitation ingestion with mocked LLM, cross-document entity linking |

### Regression Tests

| File | Tests |
|------|-------|
| `tests/sbir_rag/test_transition_precision.py` | Transition detection stays >=85% after integration (`@pytest.mark.transition`) |
| `tests/sbir_rag/test_cluster_parity.py` | LeidenTopicsTool output compared against ClusterTopicsTool baseline |

### E2E Tests (`@pytest.mark.e2e`)

| File | Tests |
|------|-------|
| `tests/sbir_rag/test_lightrag_pipeline.py` | Full Dagster pipeline materialization |
| `tests/sbir_rag/test_query_modes.py` | All 4 retrieval modes against ingested data |

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| **LLM cost for 200K award extraction** | Start with Phase II/III subset (~15K awards). Use Claude Haiku for extraction. Cache results. Estimated: ~$50-100 for subset, ~$300-600 for full corpus. |
| **Neo4j schema collision** | LightRAG uses `__entity__`/`__relationship__`/`__community__` labels (double-underscore prefix). No collision with existing Award/Company/Patent labels. |
| **Transition detection regression** | Scoring pipeline (`sbir_ml/transition/detection/scoring.py`) is untouched. Its input (`paecter_embeddings_awards` DataFrame) is preserved. Neo4j vector index is an additional output path. |
| **Async/sync boundary** | LightRAG is async-first. Embedding adapter uses `asyncio.to_thread()` to wrap sync `generate_embeddings()`. Dagster supports `async def` assets. |
| **LLM extraction quality** | Validate extracted entities against CET taxonomy keywords. Run precision/recall on a labeled sample before full corpus ingestion. |
| **Entity deduplication** | LightRAG extracts "ML", "machine learning", "Machine Learning" as separate entities. Post-processing step normalizes against a controlled vocabulary derived from CET keywords. |

---

## File Summary

### New Files (20)

| File | Phase |
|------|-------|
| `packages/sbir-rag/pyproject.toml` | 1 |
| `packages/sbir-rag/sbir_rag/__init__.py` | 1 |
| `packages/sbir-rag/sbir_rag/config.py` | 1 |
| `packages/sbir-rag/sbir_rag/embedding_adapter.py` | 1 |
| `packages/sbir-rag/sbir_rag/factory.py` | 1 |
| `packages/sbir-rag/sbir_rag/document_prep.py` | 2 |
| `packages/sbir-rag/sbir_rag/query_service.py` | 5 |
| `packages/sbir-rag/sbir_rag/interactive_similarity.py` | 5 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/__init__.py` | 2 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/ingestion.py` | 2 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/vector_index.py` | 2 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/cross_reference.py` | 2 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/communities.py` | 3 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/cet_subcommunities.py` | 3 |
| `packages/sbir-analytics/sbir_analytics/tools/mission_a/leiden_topics.py` | 3 |
| `sbir_etl/extractors/solicitation.py` | 4 |
| `sbir_etl/models/solicitation.py` | 4 |
| `packages/sbir-analytics/sbir_analytics/assets/lightrag/solicitations.py` | 4 |
| `packages/sbir-analytics/sbir_analytics/assets/jobs/lightrag_job.py` | 6 |
| `migrations/versions/004_lightrag_schema.py` | 1 |

### Modified Files (4)

| File | Change | Phase |
|------|--------|-------|
| `config/base.yaml` | Add `lightrag:` config section | 1 |
| `packages/sbir-analytics/sbir_analytics/assets/__init__.py` | Add lightrag modules to `HEAVY_ASSET_MODULES` | 2 |
| `packages/sbir-analytics/pyproject.toml` | Add `sbir-rag` dependency | 6 |
| `pyproject.toml` (root) | Add `sbir-rag` to dev extras | 6 |

### Deprecated Files (1)

| File | Replacement | Phase |
|------|-------------|-------|
| `packages/sbir-analytics/sbir_analytics/tools/mission_a/cluster_topics.py` | `packages/sbir-analytics/sbir_analytics/tools/mission_a/leiden_topics.py` | 3 |
