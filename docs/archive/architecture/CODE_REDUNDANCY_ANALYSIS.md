# Code Redundancy & Simplification Analysis

**Date**: 2025-11-17
**Purpose**: Identify code redundancy across the codebase and propose simplification strategies
**Status**: Analysis & Recommendations

---

## Executive Summary

Analysis of 226 Python files in `src/` reveals significant opportunities for code reuse and simplification:

- **~4,000 lines** of Neo4j loader code across 9 files with similar patterns
- **26 classes** with similar names (Loader, Client, Extractor, Transformer) suggesting redundant patterns
- **Multiple large files** (1,000+ lines) that could benefit from decomposition
- **Base classes exist** but not consistently used across all modules

**Key Recommendation**: Implement cloud-first pattern for ML inference (HuggingFace Inference API → local GPU fallback)

---

## 1. Neo4j Loaders Redundancy

### Current State

**9 loader files, ~4,000 total lines:**

```
src/loaders/neo4j/
├── client.py (768 lines) - Base client with batch operations
├── organizations.py - Organization node loading
├── patents.py (874 lines) - Patent node loading
├── patent_cet.py - Patent CET relationship loading
├── transitions.py - Transition node loading
├── cet.py - CET area loading
├── profiles.py - Company profile loading
├── categorization.py - Category loading
└── __init__.py
```

**Common patterns across loaders:**
- `load_*` methods with batch processing
- `upsert_*` methods with MERGE operations
- Similar error handling
- Similar transaction management
- Similar metrics tracking

### Redundancy Issues

1. **Duplicate batch processing logic** in each loader
2. **Similar MERGE query patterns** repeated across files
3. **Redundant metrics tracking** code
4. **No shared base loader class** for common operations

### Recommendation: Create BaseNeo4jLoader

```python
# src/loaders/neo4j/base.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from loguru import logger
from .client import Neo4jClient, LoadMetrics

class BaseNeo4jLoader(ABC):
    """Base class for all Neo4j loaders with common patterns."""

    def __init__(self, client: Neo4jClient):
        self.client = client
        self.metrics = LoadMetrics()

    def batch_upsert_nodes(
        self,
        label: str,
        nodes: List[Dict[str, Any]],
        primary_key: str,
        batch_size: int | None = None
    ) -> LoadMetrics:
        """Generic batch upsert for any node type."""
        batch_size = batch_size or self.client.config.batch_size

        query = f"""
        UNWIND $batch as node
        MERGE (n:{label} {{{primary_key}: node.{primary_key}}})
        ON CREATE SET n = node, n.__created = timestamp()
        ON MATCH SET n += node, n.__updated = timestamp()
        RETURN count(n) as updated_count
        """

        return self.client.batch_write(query, nodes, batch_size)

    def batch_create_relationships(
        self,
        from_label: str,
        to_label: str,
        rel_type: str,
        relationships: List[Dict[str, Any]],
        from_key: str = "id",
        to_key: str = "id"
    ) -> LoadMetrics:
        """Generic batch relationship creation."""
        query = f"""
        UNWIND $batch as rel
        MATCH (a:{from_label} {{{from_key}: rel.from_{from_key}}})
        MATCH (b:{to_label} {{{to_key}: rel.to_{to_key}}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += rel.properties
        RETURN count(r) as rel_count
        """

        return self.client.batch_write(query, relationships)

    @abstractmethod
    def load(self, data: Any) -> LoadMetrics:
        """Load data into Neo4j. Must be implemented by subclasses."""
        pass

    def log_metrics(self, operation: str):
        """Log loading metrics."""
        logger.info(
            f"{operation} completed: "
            f"{sum(self.metrics.nodes_created.values())} nodes created, "
            f"{sum(self.metrics.nodes_updated.values())} nodes updated, "
            f"{sum(self.metrics.relationships_created.values())} relationships created"
        )
```

**Usage Example:**

```python
# src/loaders/neo4j/patents.py (BEFORE: 874 lines)

class PatentLoader(BaseNeo4jLoader):
    """Loader for patent nodes."""

    def load(self, patents: List[Dict]) -> LoadMetrics:
        """Load patents into Neo4j."""
        # Use inherited method instead of custom code
        return self.batch_upsert_nodes(
            label="Patent",
            nodes=patents,
            primary_key="patent_id"
        )
```

**Estimated reduction:** ~60% reduction in loader code (from 4,000 to ~1,500 lines)

---

## 2. HuggingFace Inference Pattern (Cloud-First ML)

### Current State: Local GPU Only

**src/ml/paecter_client.py:**

```python
class PaECTERClient:
    def __init__(self, model_name: str = "mpi-inno-comp/paecter", device: str | None = None):
        # Always downloads model (~500MB) and runs locally
        self.model = SentenceTransformer(model_name, device=device)
```

**Problems:**
- Downloads large models to every environment
- Requires GPU for acceptable performance
- No cost-effective option for low-volume usage
- Doesn't leverage HuggingFace's managed infrastructure

### Recommendation: Cloud-First Pattern

**Priority: HuggingFace Inference API → Local GPU fallback**

```python
# src/ml/huggingface_client.py

from __future__ import annotations
import os
from typing import Protocol, runtime_checkable
import numpy as np
from loguru import logger

@runtime_checkable
class EmbeddingClient(Protocol):
    """Protocol for embedding clients."""

    def generate_embeddings(self, texts: list[str], **kwargs) -> np.ndarray:
        """Generate embeddings for texts."""
        ...

class HuggingFaceInferenceClient:
    """HuggingFace Inference API client (cloud-first).

    Benefits:
    - No model download required
    - Serverless scaling
    - Pay-per-use pricing (~$0.0002/1k tokens)
    - Low latency for small batches
    """

    def __init__(self, model_name: str, api_token: str | None = None):
        self.model_name = model_name
        self.api_token = api_token or os.getenv("HUGGINGFACE_API_TOKEN")

        try:
            from huggingface_hub import InferenceClient
            self.client = InferenceClient(token=self.api_token)
            self.available = True
            logger.info(f"Using HuggingFace Inference API for {model_name}")
        except ImportError:
            self.available = False
            logger.warning("huggingface_hub not installed, cannot use Inference API")

    def generate_embeddings(
        self,
        texts: list[str],
        normalize: bool = True
    ) -> np.ndarray:
        """Generate embeddings via HuggingFace Inference API."""
        if not self.available:
            raise RuntimeError("HuggingFace Inference API not available")

        try:
            # Use feature extraction endpoint
            embeddings = self.client.feature_extraction(
                text=texts,
                model=self.model_name
            )

            embeddings_array = np.array(embeddings)

            if normalize:
                # Normalize to unit length for cosine similarity
                norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
                embeddings_array = embeddings_array / norms

            return embeddings_array

        except Exception as e:
            logger.error(f"HuggingFace Inference API failed: {e}")
            raise

class LocalGPUClient:
    """Local GPU client (fallback).

    Use when:
    - Processing large batches (>10k texts)
    - Need offline capability
    - Have GPU available
    """

    def __init__(self, model_name: str, device: str | None = None):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name, device=device)
        logger.info(f"Using local GPU/CPU for {model_name}")

    def generate_embeddings(
        self,
        texts: list[str],
        batch_size: int = 32,
        normalize: bool = True
    ) -> np.ndarray:
        """Generate embeddings locally."""
        return self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True
        )

class PaECTERClient:
    """PaECTER client with cloud-first pattern.

    Automatically uses:
    1. HuggingFace Inference API (if token available)
    2. Falls back to local GPU/CPU
    """

    def __init__(
        self,
        model_name: str = "mpi-inno-comp/paecter",
        prefer_cloud: bool = True,
        api_token: str | None = None
    ):
        self.model_name = model_name
        self.client: EmbeddingClient | None = None

        if prefer_cloud:
            # Try cloud first
            try:
                cloud_client = HuggingFaceInferenceClient(model_name, api_token)
                if cloud_client.available:
                    self.client = cloud_client
                    logger.info("Using HuggingFace Inference API (cloud)")
                    return
            except Exception as e:
                logger.warning(f"Cloud client failed, falling back to local: {e}")

        # Fallback to local
        self.client = LocalGPUClient(model_name)
        logger.info("Using local GPU/CPU")

    def generate_embeddings(self, texts: list[str], **kwargs) -> np.ndarray:
        """Generate embeddings using configured client."""
        if self.client is None:
            raise RuntimeError("No embedding client available")
        return self.client.generate_embeddings(texts, **kwargs)
```

**Configuration:**

```yaml
# config/ml/embeddings.yaml

embeddings:
  paecter:
    model_name: "mpi-inno-comp/paecter"
    prefer_cloud: true  # Use HuggingFace Inference API first
    fallback_to_local: true

  huggingface_inference:
    # API token from environment: HUGGINGFACE_API_TOKEN
    rate_limit: 1000  # requests/min
    timeout_seconds: 30

  local_gpu:
    device: "cuda"  # or "cpu"
    batch_size: 32
```

**Environment Variables:**

```bash
# Production (cloud-first)
export HUGGINGFACE_API_TOKEN=hf_xxxxx  # Use Inference API
export ML_PREFER_CLOUD=true

# Development (local GPU)
export ML_PREFER_CLOUD=false  # Skip API, use local GPU directly
```

**Cost Analysis:**

```
HuggingFace Inference API:
- ~$0.0002 per 1k tokens
- 1k SBIR abstracts (~500 words each) = ~$0.10
- Monthly budget: $5-10 for typical usage

Local GPU:
- AWS g4dn.xlarge: ~$0.50/hour = $360/month (if running 24/7)
- Better for large batch processing (>10k texts)

Recommendation: Use Inference API for <10k texts/day, local GPU for larger batches
```

---

## 3. Extractor Redundancy

### Current State

**Multiple extractors with similar patterns:**

```
src/extractors/
├── sbir.py - SBIR CSV extraction
├── usaspending.py - USAspending DB extraction
├── uspto_extractor.py - USPTO patent extraction
├── uspto_ai_extractor.py - USPTO AI-specific extraction
└── contract_extractor.py - Contract extraction
```

**Common patterns:**
- DuckDB connections
- Pandas DataFrame operations
- Progress bar tracking
- Error handling
- Metrics reporting

### Recommendation: BaseExtractor

```python
# src/extractors/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict
import pandas as pd
import duckdb
from loguru import logger
from tqdm import tqdm

class BaseExtractor(ABC):
    """Base class for all data extractors."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics = {
            "records_extracted": 0,
            "errors": 0,
            "duration_seconds": 0.0
        }

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Extract data and return DataFrame."""
        pass

    def extract_with_duckdb(
        self,
        file_path: Path | str,
        query: str,
        show_progress: bool = True
    ) -> pd.DataFrame:
        """Common DuckDB extraction pattern."""
        logger.info(f"Extracting from {file_path}")

        conn = duckdb.connect()

        try:
            # Load file into DuckDB
            if str(file_path).endswith('.csv'):
                conn.execute(f"CREATE TABLE data AS SELECT * FROM read_csv_auto('{file_path}')")
            elif str(file_path).endswith('.parquet'):
                conn.execute(f"CREATE TABLE data AS SELECT * FROM read_parquet('{file_path}')")

            # Execute query
            result = conn.execute(query).df()

            self.metrics["records_extracted"] = len(result)
            logger.info(f"Extracted {len(result)} records")

            return result

        finally:
            conn.close()

    def log_metrics(self):
        """Log extraction metrics."""
        logger.info(f"Extraction metrics: {self.metrics}")
```

---

## 4. Transformer Redundancy

### Current Pattern

**Multiple transformers with similar structure:**
- `patent_transformer.py` (755 lines)
- `r_stateio_adapter.py` (880 lines)
- Various fiscal transformers

**Common operations:**
- DataFrame manipulations
- Data validation
- Type conversions
- Null handling

### Recommendation

Create `BaseTransformer` with common data cleaning utilities:

```python
# src/transformers/base.py

class BaseTransformer(ABC):
    """Base transformer with common utilities."""

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def safe_date(self, value: Any) -> pd.Timestamp | None:
        """Safely parse date."""
        try:
            return pd.to_datetime(value)
        except:
            return None

    def clean_text(self, text: str | None) -> str:
        """Clean and normalize text."""
        if not text:
            return ""
        return " ".join(text.strip().split())

    @abstractmethod
    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data."""
        pass
```

---

## 5. Large File Decomposition

### Files Over 1,000 Lines

```
1,634 lines - src/enrichers/company_categorization.py
1,305 lines - src/assets/fiscal_assets.py
1,150 lines - src/quality/uspto_validators.py
1,141 lines - src/utils/statistical_reporter.py
1,079 lines - src/assets/sbir_neo4j_loading.py
```

### Recommendations

**company_categorization.py (1,634 lines):**
```
Split into:
- company_categorization/client.py (API client)
- company_categorization/enrichers.py (Enrichment logic)
- company_categorization/validators.py (Validation)
- company_categorization/models.py (Data models)
```

**fiscal_assets.py (1,305 lines):**
```
Split into:
- fiscal/extraction_assets.py
- fiscal/transformation_assets.py
- fiscal/sensitivity_assets.py
- fiscal/reporting_assets.py
```

**Estimated reduction:** 5 large files → 20 focused modules (~300 lines each)

---

## 6. Overall Simplification Strategy

### Phase 1: Create Base Classes (Week 1-2)

1. **BaseNeo4jLoader** - Reduce loader code by ~60%
2. **BaseExtractor** - Standardize extraction patterns
3. **BaseTransformer** - Common data cleaning utilities
4. **BaseEnricher** - API client patterns

### Phase 2: Implement Cloud-First ML (Week 3)

1. **HuggingFaceInferenceClient** - Cloud-first embeddings
2. **Update PaECTERClient** - Use cloud API first
3. **Add fallback logic** - Graceful degradation to local GPU
4. **Update configuration** - Environment-based selection

### Phase 3: Refactor Large Files (Week 4-6)

1. **Decompose 1,000+ line files** into focused modules
2. **Extract shared utilities** to common modules
3. **Consolidate duplicate code** into base classes
4. **Update imports** across codebase

### Phase 4: Testing & Documentation (Week 7)

1. **Update tests** to use base classes
2. **Add integration tests** for cloud/local fallback
3. **Document patterns** in architecture docs
4. **Update deployment guides** with ML configuration

---

## 7. Expected Benefits

### Code Reduction

```
Before:
- 226 Python files
- ~69,539 total lines
- ~4,000 lines in loaders alone

After (estimated):
- ~210 Python files (consolidation)
- ~55,000 total lines (20% reduction)
- ~1,500 lines in loaders (60% reduction)
```

### Maintainability

- **Easier onboarding**: Common patterns in base classes
- **Consistent error handling**: Inherited from base
- **Reduced duplication**: Shared utilities
- **Better testability**: Mock base classes

### Cloud-First ML Benefits

- **Lower barrier to entry**: No model downloads required
- **Faster iteration**: API calls vs. model loading
- **Cost-effective**: Pay only for usage
- **Scalable**: HuggingFace infrastructure
- **Flexible fallback**: Local GPU when needed

### Cost Savings

```
Current (Local GPU only):
- AWS g4dn.xlarge: $360/month (if running 24/7)
- Or: No GPU = slow CPU inference

Proposed (Cloud-first):
- HuggingFace API: ~$10/month (typical usage)
- Local GPU: Only for large batches
- Savings: ~$350/month for typical workloads
```

---

## 8. Implementation Priorities

### High Priority (Do First)

1. ✅ **BaseNeo4jLoader** - Highest code duplication (4,000 lines)
2. ✅ **HuggingFace Inference Pattern** - Immediate cost & simplicity benefits
3. ✅ **BaseExtractor** - Consistent extraction patterns

### Medium Priority

4. **BaseTransformer** - Data cleaning utilities
5. **Decompose large files** - Improve navigability
6. **BaseEnricher** - API client patterns

### Low Priority (Nice to Have)

7. **Additional utility consolidation**
8. **Further file splitting**
9. **Documentation cleanup**

---

## Next Steps

1. **Review this analysis** with team
2. **Prioritize implementations** based on impact
3. **Create tracking issues** for each phase
4. **Start with BaseNeo4jLoader** (highest ROI)
5. **Implement HuggingFace pattern** (quick win)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-17
**Next Review**: After Phase 1 completion
