# Design Document

## Overview

This design implements a Bayesian Mixture-of-Experts (MoE) enhanced PaECTER analysis layer that provides robust, explainable patent and SBIR award analysis with uncertainty quantification. The system follows a three-stage Bayesian routing pipeline: Classification → Similarity → Embedding, where each stage uses probabilistic expert selection to improve accuracy and provide calibrated confidence scores.

The design is strictly additive to existing CET classification systems, using Hugging Face Inference API for PaECTER embeddings and implementing Bayesian uncertainty principles from recent MoE research to create a more reliable and self-aware analysis system.

## Architecture

### High-Level Pipeline Flow

```
Documents (Patents/Awards)
    ↓
Stage 1: Bayesian Classification Routing
    ↓ (Technology Categories + Uncertainty)
Stage 2: Bayesian Similarity Routing  
    ↓ (Category-Aware Similarities + Uncertainty)
Stage 3: Bayesian Embedding Routing
    ↓ (Domain-Specialized Embeddings + Uncertainty)
Final Outputs (Neo4j, Reports, Baselines)
```

### Dagster Assets (Additive)

**Core PaECTER Assets:**
- `paecter_embeddings_patents` → `data/processed/paecter_embeddings_patents.parquet`
- `paecter_embeddings_awards` → `data/processed/paecter_embeddings_awards.parquet`
- `paecter_award_patent_similarity` → `data/processed/paecter_award_patent_similarity.parquet`
- `paecter_quality_metrics` → `data/processed/paecter_quality_metrics.json`

**Bayesian MoE Assets:**
- `bayesian_classification_routing` → `data/processed/bayesian_classifications.parquet`
- `bayesian_similarity_routing` → `data/processed/bayesian_similarities.parquet`
- `bayesian_embedding_routing` → `data/processed/bayesian_embeddings.parquet`
- `uncertainty_calibration_metrics` → `data/processed/uncertainty_calibration.json`

**Integration Assets:**
- `neo4j_bayesian_similarity_edges` (optional; off by default)
- `paecter_performance_baselines` → `reports/benchmarks/paecter_bayesian.json`

### LoRA-Based Expert Implementation Strategy

The system implements experts as **LoRA (Low-Rank Adaptation) adapters** rather than separate full models, providing several key advantages:

**Benefits of LoRA Experts:**
- **Memory Efficiency**: Share base model weights, only store small adapter matrices
- **Fast Switching**: Rapid adapter loading/unloading for dynamic expert selection  
- **Training Efficiency**: Fine-tune only adapter parameters, not full model weights
- **Modular Design**: Easy to add/remove domain-specific experts
- **Cost Effective**: Minimal storage and compute overhead per expert

**LoRA Expert Categories:**
- **Technology Domain Experts**: Biotech_LoRA, AI_LoRA, Defense_LoRA, Energy_LoRA
- **Document Type Experts**: Patent_LoRA, SBIR_Award_LoRA, Abstract_LoRA
- **Task-Specific Experts**: Classification_LoRA, Similarity_LoRA, Embedding_LoRA
- **Temporal Experts**: Recent_LoRA (2020+), Historical_LoRA (pre-2020)

### Three-Stage Bayesian Routing Architecture

#### Stage 1: Classification Routing (LoRA-based Experts)
```python
BayesianClassificationRouter:
  - Input: Raw document text (patents/awards)
  - Expert Pool: {CET_LoRA, CPC_LoRA, Biotech_LoRA, AI_LoRA, Defense_LoRA, Base_Model}
  - Implementation: LoRA adapters on base classification model
  - Routing Method: Variational inference on document features
  - Output: Technology categories + routing uncertainty
  - Uncertainty Head: ECE-calibrated confidence scores
```

#### Stage 2: Similarity Routing (LoRA-based Experts)
```python
BayesianSimilarityRouter:
  - Input: Document pairs + technology categories
  - Expert Pool: {Intra_Category_LoRA, Cross_Category_LoRA, Temporal_LoRA, Content_LoRA}
  - Implementation: LoRA adapters on base similarity computation model
  - Routing Method: Category-conditioned probabilistic routing
  - Output: Similarity scores + routing uncertainty
  - Uncertainty Head: Confidence intervals for similarity
```

#### Stage 3: Embedding Routing (LoRA-based PaECTER Experts)
```python
BayesianEmbeddingRouter:
  - Input: Documents + categories + similarity patterns
  - Expert Pool: {Biotech_PaECTER_LoRA, AI_PaECTER_LoRA, Defense_PaECTER_LoRA, Base_PaECTER}
  - Implementation: LoRA adapters on base PaECTER model
  - Routing Method: Multi-stage informed probabilistic routing
  - Output: Specialized embeddings + generation uncertainty
  - Uncertainty Head: Embedding quality confidence scores
```

## Components and Interfaces

### Core Components

#### 1. Bayesian Router Framework
```python
class BayesianRouter(ABC):
    def __init__(self, expert_pool: ExpertPool, uncertainty_head: UncertaintyHead)
    def route(self, inputs: Any) -> RoutingDecision
    def compute_uncertainty(self, routing_logits: Tensor) -> UncertaintyMetrics
    def calibrate_confidence(self, predictions: Tensor, targets: Tensor) -> ECEMetrics
```

#### 2. LoRA Expert Pool Management
```python
class LoRAExpertPool:
    def __init__(self, base_model: nn.Module, lora_configs: Dict[str, LoRAConfig])
    def load_lora_adapter(self, expert_id: str, adapter_path: str) -> None
    def unload_lora_adapter(self, expert_id: str) -> None
    def switch_adapter(self, expert_id: str) -> None
    def get_active_adapters(self) -> List[str]
    def compute_adapter_weights(self, routing_probs: Tensor) -> Tensor
    def merge_adapter_outputs(self, outputs: Dict[str, Tensor], weights: Tensor) -> Tensor
```

#### 3. Uncertainty Quantification
```python
class UncertaintyHead:
    def __init__(self, calibration_method: str = "platt_scaling")
    def compute_epistemic_uncertainty(self, routing_probs: Tensor) -> float
    def compute_aleatoric_uncertainty(self, predictions: Tensor) -> float
    def calibrate_confidence(self, logits: Tensor) -> Tensor
    def flag_uncertain_cases(self, uncertainty: float, threshold: float) -> bool
```

#### 4. LoRA-Enhanced PaECTER Integration Layer
```python
class LoRAPaECTERClient:
    def __init__(self, config: PaECTERConfig, lora_expert_pool: LoRAExpertPool)
    def generate_embeddings(self, texts: List[str], lora_adapter_id: str = None) -> EmbeddingResult
    def route_to_lora_expert(self, document: Document, routing_decision: RoutingDecision) -> str
    def batch_process_with_adapters(self, documents: List[Document]) -> BatchResult
    def handle_adapter_switching_overhead(self) -> None
    def cache_adapter_embeddings(self, cache_key: str, adapter_id: str, embeddings: Tensor) -> None
```

### Interface Contracts

#### Routing Decision Interface
```python
@dataclass
class RoutingDecision:
    expert_id: str
    routing_probabilities: Dict[str, float]
    epistemic_uncertainty: float
    aleatoric_uncertainty: float
    confidence_score: float
    requires_human_review: bool
```

#### Uncertainty Metrics Interface
```python
@dataclass
class UncertaintyMetrics:
    entropy: float
    mutual_information: float
    expected_calibration_error: float
    confidence_interval: Tuple[float, float]
    uncertainty_type: str  # "epistemic" | "aleatoric" | "total"
```

## Data Models

### Core Data Schemas

#### Bayesian Classification Output
```python
@dataclass
class BayesianClassification:
    document_id: str
    document_type: str  # "patent" | "award"
    expert_routing: RoutingDecision
    cpc_predictions: Dict[str, float]  # CPC section -> probability
    cet_predictions: Dict[str, float]  # CET area -> probability
    uncertainty_metrics: UncertaintyMetrics
    classification_timestamp: datetime
    model_version: str
```

#### Bayesian Similarity Output
```python
@dataclass
class BayesianSimilarity:
    document_pair_id: str
    source_doc_id: str
    target_doc_id: str
    expert_routing: RoutingDecision
    similarity_scores: Dict[str, float]  # expert_id -> similarity
    aggregated_similarity: float
    uncertainty_metrics: UncertaintyMetrics
    similarity_timestamp: datetime
    category_context: Dict[str, Any]
```

#### Bayesian Embedding Output
```python
@dataclass
class BayesianEmbedding:
    document_id: str
    expert_routing: RoutingDecision
    embedding_vector: List[float]
    embedding_metadata: Dict[str, Any]
    uncertainty_metrics: UncertaintyMetrics
    generation_timestamp: datetime
    domain_specialization: str
    quality_score: float
```

### Parquet Schema Definitions

#### bayesian_classifications.parquet
```
document_id: string
document_type: string
expert_id: string
routing_probabilities: map<string, double>
cpc_section: string
cpc_confidence: double
cet_area: string  
cet_confidence: double
epistemic_uncertainty: double
aleatoric_uncertainty: double
requires_review: boolean
classification_timestamp: timestamp
model_version: string
```

#### bayesian_similarities.parquet
```
source_doc_id: string
target_doc_id: string
expert_id: string
routing_probabilities: map<string, double>
similarity_score: double
confidence_interval_lower: double
confidence_interval_upper: double
uncertainty_score: double
category_match: boolean
temporal_pattern: string
similarity_timestamp: timestamp
```

#### bayesian_embeddings.parquet
```
document_id: string
expert_id: string
embedding: array<double>
domain_specialization: string
quality_score: double
uncertainty_score: double
generation_method: string
embedding_timestamp: timestamp
model_version: string
```

## Error Handling

### Uncertainty-Based Error Management

#### 1. High Uncertainty Detection
```python
class UncertaintyErrorHandler:
    def handle_high_uncertainty(self, uncertainty: float, threshold: float):
        if uncertainty > threshold:
            return ErrorAction.FLAG_FOR_REVIEW
        elif uncertainty > threshold * 0.8:
            return ErrorAction.LOG_WARNING
        else:
            return ErrorAction.CONTINUE
```

#### 2. Expert Routing Failures
```python
class RoutingErrorHandler:
    def handle_routing_failure(self, routing_error: RoutingError):
        # Fallback to general expert
        fallback_expert = self.expert_pool.get_general_expert()
        return self.route_to_expert(fallback_expert, add_uncertainty_penalty=True)
```

#### 3. Calibration Drift Detection
```python
class CalibrationMonitor:
    def detect_calibration_drift(self, current_ece: float, baseline_ece: float):
        if current_ece > baseline_ece * 1.5:
            self.trigger_recalibration()
            self.alert_system_administrators()
```

### Quality Gates and Validation

#### 1. Uncertainty Calibration Gates
- ECE threshold: < 0.1 for production deployment
- Confidence interval coverage: > 90% empirical coverage
- Uncertainty correlation: Pearson r > 0.7 with actual errors

#### 2. Expert Performance Gates  
- Individual expert accuracy: > 85% on validation set
- Routing accuracy: > 90% expert selection correctness
- Uncertainty quality: Brier score < 0.2

#### 3. System Integration Gates
- End-to-end pipeline success rate: > 95%
- Neo4j loading success rate: > 99%
- Performance regression: < 20% latency increase

## Testing Strategy

### Unit Testing

#### 1. Bayesian Router Components
```python
def test_bayesian_classification_router():
    # Test variational inference routing
    # Test uncertainty computation
    # Test expert selection logic
    # Test calibration methods

def test_uncertainty_head():
    # Test ECE computation
    # Test confidence calibration
    # Test uncertainty flagging thresholds
```

#### 2. Expert Pool Management
```python
def test_expert_pool():
    # Test expert addition/removal
    # Test dynamic expert selection
    # Test expert weight computation
    # Test fallback mechanisms
```

### Integration Testing

#### 1. End-to-End Pipeline Testing
```python
def test_bayesian_pipeline_integration():
    # Test classification → similarity → embedding flow
    # Test uncertainty propagation across stages
    # Test quality gate enforcement
    # Test Neo4j integration with uncertainty metadata
```

#### 2. Uncertainty Calibration Testing
```python
def test_uncertainty_calibration():
    # Test ECE computation on validation data
    # Test confidence interval coverage
    # Test uncertainty-error correlation
    # Test calibration drift detection
```

### Performance Testing

#### 1. Scalability Testing
- Test with 100K+ patents and awards
- Measure routing overhead vs. accuracy gains
- Test expert pool scaling behavior
- Validate memory usage with uncertainty computation

#### 2. Uncertainty Quality Testing
- Validate calibration on held-out test sets
- Test uncertainty quality across different domains
- Measure human review reduction effectiveness
- Benchmark against deterministic baselines


