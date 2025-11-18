# CET Classifier Integration Guide

## Quick Navigation

This document provides a focused guide for integrating or reviewing the CET classification system within the sbir-etl pipeline.

---

## Key Files & Modules

### CET Classification Pipeline

| File | Purpose | Key Concept |
|------|---------|-------------|
| `src/assets/cet/classifications.py` | Award/patent classification | Main entry point for ML classification |
| `src/ml/models/cet_classifier.py` | TF-IDF + Logistic Regression | Current ML model implementation |
| `src/assets/cet/taxonomy.py` | Load NSTC taxonomy | 21 CET technology areas definitions |
| `src/assets/cet/company.py` | Company CET profiles | Aggregate classifications to company level |
| `src/assets/cet/loading.py` | Load CET to Neo4j | Graph persistence (nodes + relationships) |
| `src/assets/cet/validation.py` | Quality checks & drift detection | Human sampling, IAA, evaluation metrics |
| `src/models/cet_models.py` | Pydantic data models | CETArea, CETClassification, EvidenceStatement |
| `config/cet/taxonomy.yaml` | CET definitions | Taxonomy configuration (keywords, definitions) |

### Related Transformation Pipelines

| System | Integration Point | Use Case |
|--------|-------------------|----------|
| Transition Detection | `cet_alignment` signal (10% weight) | CET area match for SBIR→Contract detection |
| Fiscal Analysis | None (yet) | Could enrich fiscal ROI by CET area |
| Patent Analysis | Patent classification | Identify SBIR-funded patents by CET area |
| Company Profiles | Specialization scoring | Rank company expertise by CET area |

---

## Data Flow: Raw SBIR Awards → CET Classifications → Neo4j

### Stage 1: Input (enriched_sbir_awards)

Parquet DataFrame with columns:
- `award_id` (unique identifier)
- `abstract` (text to classify)
- `keywords` (comma-separated keywords)
- `award_title` (title text)
- Plus enrichment fields (company, amount, date, etc.)

### Stage 2: Classification (enriched_cet_award_classifications)

1. **Load Taxonomy** → Extract CET areas + keywords from YAML
2. **Vectorize** → Convert abstract+keywords+title to TF-IDF features
3. **Boost Keywords** → Multiply CET-keyword features by 2.0
4. **Predict** → Get probabilities for all 21 CET categories
5. **Threshold** → Apply multi-level scoring (HIGH ≥70, MEDIUM 40-69, LOW <40)
6. **Extract Evidence** → Pull top 3 supporting excerpts per classification
7. **Quality Check** → Validate high-confidence rate ≥60% & evidence coverage ≥80%

### Stage 3: Persistence (Neo4j)

```cypher
-- CETArea Nodes (21 static nodes)
MERGE (cet:CETArea {cet_id: $cet_id})
SET cet.name = $name, cet.keywords = $keywords, cet.taxonomy_version = $version

-- Award Enrichment Properties
MATCH (a:Award {award_id: $award_id})
SET a.cet_primary = $primary_cet_id,
    a.cet_primary_score = $primary_score,
    a.cet_specialization_profile = $all_classifications

-- Award-CET Relationships
MATCH (a:Award {award_id: $award_id}), (cet:CETArea {cet_id: $cet_id})
CREATE (a)-[:APPLICABLE_TO {score: $score, classification: $level}]->(cet)

-- Company Enrichment (aggregated)
MATCH (c:Company {company_id: $company_id})
SET c.cet_specialization_profile = $company_profile,
    c.top_3_cet_areas = $top_3_cets

-- Company-CET Relationships
MATCH (c:Company {company_id: $company_id}), (cet:CETArea {cet_id: $cet_id})
CREATE (c)-[:SPECIALIZES_IN {score: $score, num_awards: $count}]->(cet)
```

---

## Current ML Model Details

### Architecture

```
Input Text (Abstract + Keywords + Title)
    ↓
[TF-IDF Vectorizer with CET Keyword Boosting]
    • 1000 most informative features (SelectKBest + chi2)
    • CET keywords boosted by 2.0x multiplier
    • Handles 21 output categories (multi-label capable)
    ↓
[Logistic Regression with Probability Calibration]
    • Linear classifier suited for text classification
    • CalibratedClassifierCV ensures valid probabilities
    • Outputs [0.0, 1.0] scores for each CET category
    ↓
Output: {
  'cet_id': 'artificial_intelligence',
  'score': 0.82,                    # 0-1.0 probability
  'classification': 'HIGH',          # HIGH/MEDIUM/LOW
  'evidence': [
    {'excerpt': '...', 'source': 'abstract', 'rationale': '...'},
    {'excerpt': '...', 'source': 'keywords', 'rationale': '...'},
    {'excerpt': '...', 'source': 'title', 'rationale': '...'}
  ]
}
```

### Model Training

Located: `src/assets/cet/training.py`

**Current approach:**
1. Sample awards with manual CET labels (if available)
2. Fit TF-IDF + LogisticRegression pipeline
3. Persist model as pickle file
4. Load model during classification

**Enhancement opportunities:**
- Active learning (sample disagreements for human review)
- Ensemble methods (multiple models voting)
- Fine-tuned BERT embeddings instead of TF-IDF
- LLM-based classifiers (GPT, Claude) with structured outputs

---

## Quality & Validation

### Asset Checks

**cet_award_classifications_quality_check** (`src/assets/cet/classifications.py`)

```python
# Validates against thresholds (configurable via environment)
SBIR_ETL__CET__CLASSIFICATION__HIGH_CONF_THRESHOLD = 0.60      # Default: 60%
SBIR_ETL__CET__CLASSIFICATION__EVIDENCE_COVERAGE_THRESHOLD = 0.80  # Default: 80%

# Outputs cet_award_classifications.checks.json
{
  'high_conf_rate': 0.65,           # % of awards with score ≥ 70
  'evidence_coverage_rate': 0.82,   # % of classifications with evidence
  'model_status': 'loaded_successfully',
  'timestamp': '2025-11-13T18:55:00Z'
}
```

### Human Validation

Located: `src/assets/cet/validation.py`

- **Human Sampling**: Sample N awards for manual annotation
- **Inter-Annotator Agreement (IAA)**: Compare human vs model labels
- **Disagreement Analysis**: Identify patterns where model fails
- **Drift Detection**: Compare current distribution to baseline

### Drift Detection

```python
# Executed as asset: validated_cet_drift_detection
# Compares current classification distribution to baseline
# Alerts if CET area prevalence shifts >5% or model confidence declines
```

---

## Configuration

### CET Taxonomy

**File**: `config/cet/taxonomy.yaml`

```yaml
cet_areas:
  - cet_id: artificial_intelligence
    name: "Artificial Intelligence & Machine Learning"
    definition: "AI/ML technologies including deep learning, NLP, computer vision..."
    keywords:
      - "artificial intelligence"
      - "machine learning"
      - "deep learning"
      - "neural network"
      - "LLM"
      - ...
    parent_cet_id: null
    taxonomy_version: "NSTC-2025Q1"
  
  - cet_id: quantum_computing
    name: "Quantum Computing"
    # ... similar structure
```

### Quality Thresholds

**File**: `config/base.yaml`

```yaml
cet:
  classification:
    high_confidence_threshold: 0.70    # Score ≥ 70 = HIGH
    medium_confidence_threshold: 0.40  # Score 40-69 = MEDIUM
    # Rest (<40) = LOW
    
    quality_gates:
      min_high_conf_rate: 0.60         # At least 60% of awards HIGH confidence
      min_evidence_coverage: 0.80      # At least 80% have evidence statements
      
    model_path: "models/cet_classifier.pkl"  # Where to load/save model
```

---

## Neo4j Integration

### Node & Relationship Schema

**CETArea Nodes** (21 static)

```cypher
CREATE CONSTRAINT cetarea_cet_id IF NOT EXISTS
FOR (c:CETArea) REQUIRE c.cet_id IS UNIQUE

CREATE INDEX cetarea_name_idx IF NOT EXISTS
FOR (c:CETArea) ON (c.name)

-- Properties:
{
  cet_id: string,              # e.g., "artificial_intelligence"
  name: string,                # e.g., "Artificial Intelligence & Machine Learning"
  definition: string,          # Official NSTC definition
  keywords: [string],          # Associated keywords
  taxonomy_version: string     # e.g., "NSTC-2025Q1"
}
```

**Award Enrichment Properties**

```cypher
MATCH (a:Award)
SET a.cet_primary = "artificial_intelligence",        -- Highest-scoring CET
    a.cet_primary_score = 0.82,                       -- Primary score
    a.cet_specialization_profile = {                  -- All classifications
      "artificial_intelligence": {
        "score": 0.82,
        "classification": "HIGH"
      },
      "quantum_computing": {
        "score": 0.45,
        "classification": "MEDIUM"
      },
      ...
    }
```

**Relationships**

```cypher
-- Award → CETArea (one-to-many; award applicable to multiple CET areas)
MATCH (a:Award)-[r:APPLICABLE_TO]->(cet:CETArea)
-- Properties: score, classification, evidence

-- Company → CETArea (aggregated from award classifications)
MATCH (c:Company)-[r:SPECIALIZES_IN]->(cet:CETArea)
-- Properties: score (avg or max), num_awards, classification
```

---

## Extension Points

### 1. Swap Classification Algorithm

**Where**: `src/ml/models/cet_classifier.py` + `src/assets/cet/classifications.py`

**Current**:
```python
model = Pipeline([
    ('tfidf', CETAwareTfidfVectorizer(...)),
    ('feature_selection', SelectKBest(chi2, k=1000)),
    ('classifier', CalibratedClassifierCV(LogisticRegression()))
])
```

**To replace with BERT embeddings**:
```python
from transformers import AutoTokenizer, AutoModel

model = BERTCETClassifier(
    model_name='bert-base-uncased',
    num_labels=21,
    cet_keywords=taxonomy_keywords
)
```

**To integrate LLM-based classification**:
```python
model = LLMCETClassifier(
    provider='openai',  # or 'anthropic', 'ollama'
    model='gpt-4',
    system_prompt=build_cet_classification_prompt(taxonomy)
)
```

### 2. Hierarchical Classification

**Enhancement**: Add parent-child CET relationships

```python
# Instead of flat 21 categories, organize as:
# Tier 1 (5 broad areas): Computing, Biology, Advanced Manufacturing, etc.
# Tier 2 (21 specific): AI, Quantum, Biotech, etc.

# Modify architecture:
class HierarchicalCETClassifier:
    def __init__(self):
        self.tier1_model = ...  # Predict broad category first
        self.tier2_models = {}  # Separate model per parent
    
    def predict(self, text):
        parent = self.tier1_model.predict(text)
        child_probs = self.tier2_models[parent].predict(text)
        return {parent: child_probs}
```

### 3. Multi-Modal Features

**Enhancement**: Combine text + structured fields

```python
# Current: Only uses abstract/keywords/title
# Enhanced: Also use
#   - Solicitation number (indicates agency focus area)
#   - Agency name (some agencies focus on specific technologies)
#   - Historical company CET profile (transfer learning)
#   - Patent titles/abstracts (if company has prior patents)

class MultiModalCETClassifier:
    def __init__(self):
        self.text_model = TfidfVectorizer(...)
        self.structured_encoder = StructuredFeatureEncoder(...)
        self.fusion_model = LogisticRegression()
    
    def predict(self, text_features, structured_features):
        text_emb = self.text_model.transform(text_features)
        struct_emb = self.structured_encoder.encode(structured_features)
        combined = np.hstack([text_emb, struct_emb])
        return self.fusion_model.predict_proba(combined)
```

### 4. Continuous Model Updates

**Enhancement**: Retraining pipeline

```python
# Current: Model trained once during dev, static in production
# Enhanced: Periodic retraining with new labeled data

@asset(
    name="cet_classifier_retrained",
    deps=[
        'new_labeled_sample',      # New human-labeled data
        'cet_classifier_baseline'  # Baseline model for comparison
    ]
)
def retrained_cet_classifier(new_labels, baseline_model):
    # Load baseline
    model = pickle.load(baseline_model)
    
    # Incrementally train on new data
    model.fit(new_labels['abstract'], new_labels['cet_labels'], partial=True)
    
    # Evaluate against test set
    perf = evaluate_classifier(model, test_set)
    
    # Only persist if ≥1% improvement
    if perf['f1'] > baseline_perf['f1'] * 1.01:
        save_classifier(model, 'models/cet_classifier.pkl')
        return Output(model, metadata={'improvement': perf['f1'] - baseline_perf['f1']})
    else:
        return baseline_model  # Keep baseline
```

### 5. Uncertainty Quantification

**Enhancement**: Track model confidence and uncertainty

```python
class UncertainCETClassifier:
    def predict_with_uncertainty(self, text):
        # Get probability distribution
        probs = self.model.predict_proba(text)
        
        # Compute entropy (uncertainty measure)
        entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)
        
        # Compute margin (distance between top 2 predictions)
        sorted_probs = np.sort(probs, axis=1)
        margin = sorted_probs[:, -1] - sorted_probs[:, -2]
        
        return {
            'predictions': probs,
            'entropy': entropy,      # High = uncertain
            'margin': margin,        # Low = close call between top 2
            'confidence': 1 - entropy / np.log(21)  # Normalized confidence
        }
```

### 6. Active Learning

**Enhancement**: Identify samples for human review

```python
@asset
def cet_active_learning_candidates(
    enriched_cet_award_classifications,
    num_candidates=1000
):
    """Identify N awards most beneficial to label for model improvement"""
    
    candidates = []
    
    # Strategy 1: Uncertainty sampling
    uncertain = df[df['entropy'] > entropy_threshold].head(300)
    
    # Strategy 2: Disagreement sampling  
    disagreed = df[df['margin'] < margin_threshold].head(300)
    
    # Strategy 3: Out-of-distribution detection
    outliers = detect_outliers(df['embeddings']).head(400)
    
    return pd.concat([uncertain, disagreed, outliers]).drop_duplicates()
```

---

## Testing & Validation

### Unit Tests

**Location**: `tests/unit/test_cet_*.py`

```bash
# Run CET classification tests
uv run pytest tests/unit/test_cet_*.py -v

# With coverage
uv run pytest tests/unit/test_cet_*.py --cov=src/ml --cov-report=html
```

### Integration Tests

```bash
# Test full CET pipeline (classify → validate → load)
uv run pytest tests/integration/test_cet_pipeline.py -v
```

### E2E Tests

```bash
# Full pipeline with real data (small sample)
uv run pytest tests/e2e/test_cet_e2e.py -v

# Or via Docker
make docker-e2e-standard
```

---

## Common Integration Scenarios

### Scenario 1: Review Current CET Classifications

```python
# Load the classifications parquet
import pandas as pd
df = pd.read_parquet('data/processed/enriched_cet_award_classifications.parquet')

# Check quality metrics
print(f"Total awards classified: {len(df)}")
print(f"Avg score: {df['score'].mean():.2f}")
print(f"HIGH confidence: {(df['score'] >= 70).sum()} ({(df['score'] >= 70).mean():.1%})")
print(f"MEDIUM confidence: {((df['score'] >= 40) & (df['score'] < 70)).sum()}")
print(f"LOW confidence: {(df['score'] < 40).sum()}")

# Top CET areas
print("\nTop CET areas by award count:")
print(df['cet_id'].value_counts().head(10))

# Check evidence
print(f"\nAwards with evidence: {df['evidence'].notna().sum()} ({df['evidence'].notna().mean():.1%})")
```

### Scenario 2: Add New CET Area

1. **Update taxonomy** → `config/cet/taxonomy.yaml`
   - Add new CET area with definition + keywords

2. **Retrain classifier** → `src/assets/cet/training.py`
   - Provide training samples with new label
   - Retrain TF-IDF + Logistic Regression

3. **Validate** → `src/assets/cet/validation.py`
   - Human sample new classifications
   - Check precision/recall for new area

4. **Load to Neo4j** → Automatic via `loaded_cet_areas` asset

### Scenario 3: Integrate Custom Classifier

```python
# Create new module: src/ml/models/custom_classifier.py
from typing import List, Dict

class CustomCETClassifier:
    def fit(self, texts: List[str], labels: List[Dict]):
        """Train on texts and labels"""
        # Your training logic
        pass
    
    def predict_proba(self, texts: List[str]) -> Dict[str, float]:
        """Return {cet_id: score} for each text"""
        # Your prediction logic
        return results

    def get_evidence(self, text: str, cet_id: str) -> List[str]:
        """Extract supporting evidence"""
        # Your evidence extraction logic
        return evidence_snippets

# Update classifications.py to use it
from src.ml.models.custom_classifier import CustomCETClassifier
classifier = CustomCETClassifier()  # Instead of ApplicabilityModel
```

---

## Performance & Optimization

### Current Performance

| Metric | Value |
|--------|-------|
| Throughput | 10-15K awards/min |
| Classification time per award | 0.004-0.006 seconds |
| Total classification time (250K awards) | 20-30 minutes |
| Memory per award | ~0.1-0.2 MB |
| Model file size | ~50 MB (pickle) |

### Optimization Tips

1. **Batch processing**: Use Dagster's batch framework (already done)
2. **Feature selection**: SelectKBest reduces from thousands to 1000 features
3. **Sparse matrices**: TF-IDF output is sparse (memory efficient)
4. **Model serialization**: Pickle is fast; consider joblib for larger models
5. **Parallelization**: Predict on chunks via multiprocessing

---

## Monitoring & Alerts

### Quality Metrics

Tracked in `reports/metrics/cet_*.json`:

```json
{
  "timestamp": "2025-11-13T18:55:00Z",
  "total_awards_classified": 250000,
  "high_confidence_rate": 0.65,
  "evidence_coverage": 0.82,
  "avg_score": 0.58,
  "model_status": "loaded_successfully",
  "distribution_by_cet": {
    "artificial_intelligence": 45000,
    "quantum_computing": 8000,
    ...
  }
}
```

### Performance Metrics

Tracked in `reports/alerts/`:

```json
{
  "timestamp": "2025-11-13T18:55:00Z",
  "duration_seconds": 1800.5,
  "throughput_records_per_min": 8333,
  "memory_peak_mb": 3200,
  "errors_count": 0,
  "regressions": {
    "high_confidence_rate": "↓ 5%",  # Alert if >5% decline
    "evidence_coverage": "↑ 2%"      # Normal variance
  }
}
```

---

## Useful Commands

```bash
# View classification results
uv run python -c "
import pandas as pd
df = pd.read_parquet('data/processed/enriched_cet_award_classifications.parquet')
print(df.head(10))
print(df.describe())
"

# Check Neo4j CET nodes
uv run python << 'PYTHON'
from src.loaders.neo4j import Neo4jClient, Neo4jConfig
from src.config.loader import get_config

config = get_config()
client = Neo4jClient(Neo4jConfig(**config.neo4j.dict()))

with client.session() as session:
    result = session.run("MATCH (c:CETArea) RETURN c.name, count(*) as awards")
    for record in result:
        print(f"{record['c.name']}: {record['awards']} awards")
PYTHON

# Run CET pipeline
uv run dagster job execute -m src.definitions -j cet_full_pipeline_job

# View Dagster UI
uv run dagster dev
# Then navigate to http://localhost:3000
```

---

## References

- **CET Classifier**: `src/ml/models/cet_classifier.py` (120 lines)
- **Classifications Asset**: `src/assets/cet/classifications.py` (200+ lines)
- **Neo4j Loading**: `src/assets/cet/loading.py` (180 lines)
- **Validation**: `src/assets/cet/validation.py` (250+ lines)
- **Taxonomy**: `config/cet/taxonomy.yaml`
- **Documentation**: [`docs/ml/cet-classifier.md`](cet-classifier.md), [`docs/ml/cet-award-training-data.md`](cet-award-training-data.md)
- **Tests**: `tests/unit/test_cet_*.py`, `tests/integration/test_cet_*.py`

