# CET Classification Module - Technical Design

## Context

The SBIR ETL pipeline needs to classify awards, companies, and patents against 21 Critical and Emerging Technology (CET) areas defined by the National Science and Technology Council (NSTC). This capability enables:

- Technology portfolio analysis and gap identification
- CET-based graph queries in Neo4j
- Technology transition tracking (award → patent → commercialization)
- Strategic planning with evidence-based technology classifications

**Available Resources:**
- Production-ready sbir-cet-classifier (97.9% success rate, 0.17ms latency, 232/232 tests passing)
- USPTO AI Patent Dataset (15.4M patents, 1976-2023, BERT-based classifications)
- Existing SBIR award data with abstracts and keywords
- Neo4j graph database for relationship modeling

**Constraints:**
- Must integrate seamlessly with existing Dagster pipeline
- Must support batch processing of 250k+ awards
- Must provide explainable classifications (evidence-based)
- Must handle evolving CET taxonomy (versioning)
- Must run efficiently within existing infrastructure (no separate services)

## Goals / Non-Goals

### Goals
- Classify 100% of SBIR awards, companies, and patents with CET categories
- Achieve ≥90% classification confidence for high-value entities
- Provide sentence-level evidence for all classifications
- Support multi-threshold confidence scoring (High/Medium/Low)
- Enable CET-based Neo4j queries and portfolio analytics
- Maintain ≤1 second average latency per entity
- Support CET taxonomy evolution and historical analysis
- Leverage USPTO AI dataset for AI patent validation

### Non-Goals
- Real-time classification API (batch processing only)
- Multi-language support (English only)
- Fine-tuning BERT models (use TF-IDF for simplicity)
- Manual review interface (separate tool)
- Classification of non-SBIR government grants

## Decisions

### Decision 1: Embedded ML Module vs. Separate Service

**Choice:** Embedded ML module within sbir-analytics Dagster pipeline

**Rationale:**
- Unified data lineage: All transformations tracked in single Dagster instance
- Simplified deployment: No separate service to maintain
- Shared configuration: Leverage existing YAML config system
- Lower latency: No network calls for classification
- Better testability: Unit and integration tests in same codebase

**Alternatives Considered:**
- Microservice with FastAPI: Rejected - adds operational complexity, network latency
- Separate batch job: Rejected - complicates data lineage and orchestration

**Implementation:**
```python
# Dagster asset for CET classification
@asset(deps=[enriched_sbir_awards])
def cet_classifications(
    context: AssetExecutionContext,
    enriched_sbir_awards: pd.DataFrame,
    cet_classifier: CETClassifier
) -> pd.DataFrame:
    """Classify awards against CET taxonomy."""
    classifications = []
    for batch in chunk(enriched_sbir_awards, size=1000):
        results = cet_classifier.classify_batch(batch)
        classifications.extend(results)
    return pd.DataFrame(classifications)
```

### Decision 2: ML Model Approach

**Choice:** TF-IDF + Logistic Regression (from sbir-cet-classifier)

**Rationale:**
- Proven effectiveness: 97.9% success rate in production
- Interpretability: TF-IDF weights explain feature importance
- Speed: 0.17ms per award (2,941x faster than 500ms target)
- Simplicity: No GPU required, minimal dependencies
- Training efficiency: Retrains in minutes on 1000+ examples

**Alternatives Considered:**
- BERT-based approach (like USPTO): Rejected - higher complexity, GPU requirements, longer inference time
- Rule-based keyword matching: Rejected - low recall, brittle
- Zero-shot LLM classification: Rejected - API costs, latency, non-deterministic

**Model Pipeline:**
```
Text (abstract + keywords + solicitation)
    ↓
TF-IDF Vectorization
    ├─ Unigrams, bigrams, trigrams (1-3 n-grams)
    ├─ 50k max features → chi-squared selection → 20k features
    └─ CET keyword boosting (2.0x multiplier)
    ↓
Logistic Regression
    ├─ Balanced class weights (handles imbalanced CET distribution)
    └─ Multi-core processing (n_jobs=-1)
    ↓
Probability Calibration (Sigmoid, 3-fold CV)
    └─ Reliable confidence scores
    ↓
Multi-Threshold Scoring
    ├─ High: ≥70 (adopt from sbir-cet-classifier)
    ├─ Medium: 40-69
    └─ Low: <40
```

### Decision 3: Leveraging USPTO AI Patent Dataset

**Choice:** Use USPTO AI predictions as validation ground truth and potential features

**Dataset Structure:**
- 15.4M U.S. patents (1976-2023)
- BERT-based classifications with 8 AI subcategories
- Multi-threshold predictions: predict50_*, predict86_*, predict93_*
- Continuous scores: ai_score_* (0.0-1.0)

**AI Subcategories:**
1. any_ai - Overall AI classification
2. ml - Machine Learning
3. evo - Evolutionary Computation
4. nlp - Natural Language Processing
5. speech - Speech Recognition
6. vision - Computer Vision
7. planning - AI Planning/Control
8. kr - Knowledge Representation
9. hardware - AI Hardware

**Integration Strategy:**

**Phase 1 - Validation:**
```python
# Use USPTO predictions to validate our AI CET classifications
def validate_ai_classification(patent: Patent, cet_score: float) -> ValidationMetric:
    """Compare our AI CET score with USPTO's any_ai prediction."""
    uspto_prediction = get_uspto_prediction(patent.grant_doc_num)

    if uspto_prediction and uspto_prediction['predict93_any_ai'] == 1:
        # High confidence USPTO prediction - should align with our classification
        if cet_score >= 70:  # Our high confidence threshold
            return ValidationMetric(status="ALIGNED", confidence=0.95)
        else:
            return ValidationMetric(status="MISALIGNED", confidence=0.70)

    return ValidationMetric(status="NO_GROUND_TRUTH", confidence=None)
```

**Phase 2 - Feature Enhancement (Future):**
- Include USPTO AI scores as additional features for patent classification
- Use subcategory scores to refine AI CET granularity
- Implement hierarchical AI taxonomy (AI → ML → specific techniques)

**Phase 3 - Multi-Threshold Adoption:**
- Consider adopting USPTO's 50/86/93 thresholds instead of our 40/70 thresholds
- Align confidence scoring with established USPTO methodology
- Enable cross-dataset comparisons

**Key Insights from USPTO Methodology:**
1. **Decision Boundary Optimization**: Include borderline training examples for better real-world performance
2. **Multi-Threshold Confidence**: Support varying risk tolerance for different use cases
3. **Subcategory Granularity**: Break down broad categories (AI) into specific techniques
4. **Longitudinal Tracking**: Enable 1976-2023 trend analysis for technology maturity assessment

### Decision 4: CET Taxonomy Structure

**Choice:** 21 NSTC CET categories with hierarchical support

**Taxonomy Design:**
```yaml
# config/cet/taxonomy.yaml
taxonomy_version: "NSTC-2025Q1"
effective_date: "2025-01-01"

categories:
  # Core Technologies
  - id: artificial_intelligence
    name: Artificial Intelligence
    definition: "AI and machine learning technologies including neural networks..."
    parent_cet_id: null
    keywords:
      - artificial intelligence
      - machine learning
      - neural networks
      - deep learning
      - computer vision
      - natural language processing
    subcategories:  # Informed by USPTO AI taxonomy
      - id: ai_machine_learning
        name: Machine Learning
        keywords: [machine learning, supervised learning, unsupervised learning]
      - id: ai_computer_vision
        name: Computer Vision
        keywords: [computer vision, image recognition, object detection]
      - id: ai_nlp
        name: Natural Language Processing
        keywords: [natural language processing, text analysis, language models]

  - id: quantum_computing
    name: Quantum Computing
    definition: "Quantum information science and technologies..."
    keywords: [quantum computing, qubit, quantum algorithm, quantum error correction]
    subcategories:
      - id: quantum_sensing
        name: Quantum Sensing
        parent_cet_id: quantum_computing
        keywords: [quantum sensor, quantum metrology, atomic clock]

  # ... (19 more categories)
```

**Rationale:**
- Hierarchical structure supports both broad and granular classification
- Extensible for future subcategories (e.g., AI subcategories from USPTO)
- Version tracking enables longitudinal analysis
- Keyword-based approach improves interpretability

### Decision 5: Evidence Extraction Approach

**Choice:** spaCy-based sentence-level evidence extraction

**Implementation:**
```python
from spacy.lang.en import English

class EvidenceExtractor:
    def __init__(self):
        # Lightweight sentence segmentation (no full NLP pipeline)
        self.nlp = English()
        self.nlp.add_pipe('sentencizer')

    def extract_evidence(
        self,
        text: str,
        cet_keywords: List[str],
        max_excerpts: int = 3
    ) -> List[EvidenceStatement]:
        """Extract up to 3 sentences containing CET keywords."""
        doc = self.nlp(text)
        evidence = []

        for sent in doc.sents:
            sent_text = sent.text.strip()

            # Check if sentence contains CET keywords
            matched_keywords = [
                kw for kw in cet_keywords
                if kw.lower() in sent_text.lower()
            ]

            if matched_keywords:
                evidence.append(EvidenceStatement(
                    excerpt=truncate(sent_text, max_words=50),
                    source_location="abstract",  # or "keywords", "solicitation"
                    rationale_tag=f"Contains: {', '.join(matched_keywords[:3])}"
                ))

                if len(evidence) >= max_excerpts:
                    break

        return evidence
```

**Rationale:**
- Sentence-level granularity balances precision with readability
- spaCy's sentencizer is fast (no full NLP pipeline needed)
- Keyword-based matching is interpretable and debuggable
- 50-word excerpts fit in UI/API responses without overwhelming users

### Decision 6: Neo4j Graph Model for CET

**Choice:** CETArea nodes with APPLICABLE_TO relationships

**Graph Schema:**
```cypher
// CET Area nodes (21 categories)
CREATE (ai:CETArea {
    cet_id: "artificial_intelligence",
    name: "Artificial Intelligence",
    definition: "AI and machine learning technologies...",
    taxonomy_version: "NSTC-2025Q1",
    parent_cet_id: null,
    keywords: ["artificial intelligence", "machine learning", ...]
})

// Award CET classification
CREATE (award:Award {award_id: "ABC-2023-001"})
CREATE (award)-[:APPLICABLE_TO {
    score: 85,
    classification: "High",
    primary: true,
    evidence: [
        {excerpt: "Advanced neural network development...", source: "abstract"},
        {excerpt: "Machine learning algorithms for...", source: "keywords"}
    ],
    classified_at: datetime("2025-10-26T12:00:00Z"),
    taxonomy_version: "NSTC-2025Q1"
}]->(ai)

// Supporting CET areas (up to 3)
CREATE (award)-[:APPLICABLE_TO {
    score: 62,
    classification: "Medium",
    primary: false,
    classified_at: datetime("2025-10-26T12:00:00Z")
}]->(cybersecurity:CETArea)

// Company CET profile (aggregated from awards)
CREATE (company:Company {name: "Acme Corp"})
CREATE (company)-[:SPECIALIZES_IN {
    award_count: 15,
    total_funding: 12500000,
    avg_score: 78,
    dominant_phase: "II",
    first_award_date: date("2018-03-15"),
    last_award_date: date("2024-09-20")
}]->(ai)

// Patent CET classification
CREATE (patent:Patent {grant_doc_num: "5858003"})
CREATE (patent)-[:APPLICABLE_TO {
    score: 72,
    classification: "High",
    uspto_ai_score: 0.93,  // From USPTO AI dataset
    classified_at: datetime("2025-10-26T12:00:00Z")
}]->(biotech:CETArea)

// Link to originating award for technology transition tracking
CREATE (award)-[:FUNDED]->(patent)
```

**Query Examples:**
```cypher
// Find all high-confidence AI awards
MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(cet:CETArea {cet_id: "artificial_intelligence"})
WHERE r.score >= 70
RETURN a.award_id, a.firm_name, r.score
ORDER BY r.score DESC
LIMIT 100

// Track technology transition: AI award → AI patent
MATCH (award:Award)-[:APPLICABLE_TO]->(ai_cet:CETArea {cet_id: "artificial_intelligence"})
MATCH (award)-[:FUNDED]->(patent:Patent)
MATCH (patent)-[:APPLICABLE_TO]->(patent_cet:CETArea)
RETURN
    award.award_id,
    ai_cet.name AS award_cet,
    patent.grant_doc_num,
    patent_cet.name AS patent_cet,
    ai_cet.cet_id = patent_cet.cet_id AS cet_aligned
```

**Rationale:**
- Separates CET taxonomy (nodes) from classifications (relationships)
- Supports temporal analysis (classified_at timestamp)
- Enables taxonomy versioning (multiple CETArea versions)
- Relationship properties store classification metadata
- Supports both entity-level and portfolio-level queries

## Risks / Trade-offs

### Risk 1: Model Accuracy on Edge Cases

**Impact:** Some awards/patents may be difficult to classify (borderline, multi-discipline, novel technologies)

**Mitigation:**
- Multi-threshold confidence scoring (High/Medium/Low)
- Evidence statements for manual review
- Fallback to "Uncategorized" CET area
- Track classification confidence distribution
- Human validation sampling (5-10% of classifications)

**Trade-off:** Precision vs. Recall. Conservative thresholds (≥70 for High) improve precision but may miss some valid classifications.

### Risk 2: CET Taxonomy Evolution

**Impact:** NSTC may update CET definitions, add/remove categories, or restructure hierarchy

**Mitigation:**
- Version all taxonomies (NSTC-2025Q1, NSTC-2025Q2, etc.)
- Store taxonomy_version on all classifications
- Support multiple taxonomy versions in Neo4j simultaneously
- Provide migration tools to reclassify with new taxonomy
- Track taxonomy lineage (category renames, mergers)

**Trade-off:** Historical analysis complexity. Comparing classifications across taxonomy versions requires normalization.

### Risk 3: Training Data Scarcity

**Impact:** Some CET categories may have <100 labeled training examples, leading to low model quality

**Mitigation:**
- Bootstrap from sbir-cet-classifier's 1000+ annotated examples
- Use keyword-based heuristics for rare categories
- Combine related categories during training (e.g., Quantum Computing + Quantum Sensing)
- Active learning: Flag low-confidence predictions for human labeling
- Leverage USPTO AI dataset for AI category ground truth

**Trade-off:** May need to collapse rare subcategories into parent categories initially.

### Risk 4: USPTO AI Dataset Integration Complexity

**Impact:** 1.2GB Stata file with 15.4M patents requires careful handling

**Mitigation:**
- Chunked streaming (10K patents/chunk) to manage memory
- Index on grant_doc_num for fast lookup
- Cache USPTO predictions in local SQLite database
- Only load AI scores for patents linked to SBIR companies
- Optional feature: Enable/disable via configuration flag

**Trade-off:** Additional data storage and processing time for USPTO integration.

## Migration Plan

### Phase 1: Core Classification Module (Weeks 1-2)
1. Port CET classifier from sbir-cet-classifier
   - Copy ApplicabilityModel, CETAwareTfidfVectorizer, evidence extraction
   - Adapt to sbir-analytics Pydantic schemas
   - Add configuration loader for taxonomy.yaml
2. Create Dagster assets for CET classification
   - cet_taxonomy asset (load taxonomy.yaml)
   - cet_award_classifications asset (classify awards)
3. Unit tests for classifier components
4. Integration test with sample awards

### Phase 2: Neo4j Integration (Week 3)
1. Create CETArea node loader
   - Load 21 CET categories from taxonomy.yaml
   - Create indexes on cet_id
2. Create APPLICABLE_TO relationship loader
   - Link Awards to CETArea nodes
   - Store classification metadata on relationships
3. Add Neo4j queries for CET portfolio analysis
4. Test graph queries

### Phase 3: Company & Patent Classification (Week 4)
1. Implement company CET aggregation
   - Aggregate scores from all awards per company
   - Create SPECIALIZES_IN relationships
2. Implement patent CET classification
   - Classify based on title + assignee context
   - Create APPLICABLE_TO relationships for patents
3. Add technology transition queries (Award → Patent CET alignment)

### Phase 4: USPTO AI Dataset Integration (Week 5)
1. Create USPTO AI data loader
   - Extract USPTO predictions to SQLite cache
   - Index by grant_doc_num for fast lookup
2. Add USPTO validation metrics
   - Compare AI CET classifications with USPTO predictions
   - Generate agreement reports
3. Optional: Use USPTO scores as features

### Phase 5: Validation & Deployment (Week 6)
1. Run full pipeline on development data
2. Validate classification quality metrics
   - High confidence rate (target: ≥60%)
   - Evidence coverage (target: ≥80%)
   - Processing throughput (target: ≥1000 awards/sec)
3. Human validation sampling (100 awards)
4. Generate evaluation report
5. Deploy to production

### Rollback Plan
- CET classification is additive (no changes to existing nodes/relationships)
- Can disable CET assets via Dagster configuration
- Neo4j CET data can be deleted without affecting core graph
- Rollback via Dagster asset version revert

## Open Questions

1. **Q: Should we retrain the CET classifier on our specific data or use the pre-trained model from sbir-cet-classifier?**
   - **A:** Start with pre-trained model. Retrain if validation metrics fall below targets (≥85% agreement with human labels).

2. **Q: How do we handle awards that span multiple CET areas equally (e.g., AI + Cybersecurity)?**
   - **A:** Support up to 3 supporting CET areas with separate scores. Primary CET is highest-scoring category.

3. **Q: Should we expose CET classifications via API or only in Neo4j?**
   - **A:** Neo4j only for initial release. API can be added later if needed for external consumers.

4. **Q: How do we update CET classifications when the taxonomy changes?**
   - **A:** Provide reclassification Dagster job that re-runs classification with new taxonomy version. Preserve historical classifications.

5. **Q: Should we use USPTO's 50/86/93 confidence thresholds or stick with 40/70?**
   - **A:** Start with 40/70 (proven in sbir-cet-classifier). Evaluate USPTO thresholds in Phase 4.

6. **Q: How granular should AI subcategories be (8 from USPTO vs. simpler 3-4)?**
   - **A:** Start with simple hierarchy (AI → ML, Vision, NLP). Expand to 8 subcategories if user demand justifies complexity.
