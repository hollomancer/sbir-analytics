# Add Critical and Emerging Technology Classification Module

## Why

The SBIR program aims to fund innovation in Critical and Emerging Technologies (CET) that are vital to national security and economic competitiveness. Currently, the pipeline lacks the ability to:

- **Classify awards, companies, and patents** against the 21 NSTC CET technology areas
- **Track CET portfolio distribution** and identify gaps in technology coverage
- **Enable CET-based queries** in Neo4j for technology-focused analysis
- **Link technology trends** across awards, patents, and commercialization outcomes
- **Support strategic planning** with evidence-based CET applicability scores

Without CET classification, analysts cannot:
- Identify which technology areas are receiving the most SBIR funding
- Detect emerging technology gaps in the SBIR portfolio
- Track technology transition from research to patents to commercialization
- Query for companies working in specific CET areas (e.g., "all quantum computing companies")
- Measure SBIR program effectiveness in advancing critical technologies

## What Changes

- **Add ML-based CET classification module** adapted from production-ready sbir-cet-classifier
  - Integrate TF-IDF + Logistic Regression classifier (97.9% success rate, 0.17ms latency)
  - 21 CET categories following NSTC framework with hierarchical taxonomy
  - Evidence-based explainability with sentence-level supporting excerpts
  - Confidence scoring with 3-band classification (High: 70-100, Medium: 40-69, Low: 0-39)
- **Add CET classification to Awards transformation**
  - Classify SBIR awards based on abstract, keywords, and solicitation text
  - Store primary CET area + up to 3 supporting areas per award
  - Extract evidence statements (up to 3) with source location and rationale
- **Add CET classification to Companies transformation**
  - Aggregate company CET profile from all awards received
  - Calculate company CET specialization scores (dominant technology areas)
  - Track CET evolution over time (Phase I → Phase II → Phase III)
- **Add CET classification to Patents transformation**
  - Classify patents based on title and assignee entity type
  - Link patent CET areas to originating SBIR award CET areas
  - Track technology transition (award CET → patent CET alignment)
- **Add Neo4j CET graph model**
  - Create CETArea nodes with taxonomy metadata
  - Add APPLICABLE_TO relationships from Awards/Companies/Patents to CETArea nodes
  - Store classification metadata (score, confidence, evidence) on relationships
  - Enable CET-based queries and portfolio analysis
- **Add configuration system for CET parameters**
  - Externalize CET taxonomy (taxonomy.yaml)
  - Externalize ML hyperparameters (classification.yaml)
  - Support taxonomy versioning for longitudinal analysis
- **Add evaluation framework**
  - Validation against human-labeled ground truth
  - Agreement metrics and quality monitoring
  - Performance benchmarking (throughput, latency)

## Impact

### Affected Specs
- **data-transformation**: Add CET classification transformation for Awards, Companies, Patents
- **data-loading**: Add CETArea nodes and APPLICABLE_TO relationships to Neo4j
- **configuration**: Add CET taxonomy and classification configuration management

### Affected Code
- `src/ml/`: New ML classification module (models, features, evaluation)
  - `models/cet_classifier.py`: TF-IDF + LogReg pipeline
  - `features/evidence_extractor.py`: Evidence extraction with spaCy
  - `config/taxonomy_loader.py`: YAML configuration loader
- `src/transformers/`: Enhanced transformers with CET classification
  - `award_transformer.py`: Add CET classification step
  - `company_transformer.py`: Aggregate company CET profiles
  - `patent_transformer.py`: Add patent CET classification
- `src/loaders/`: Neo4j loaders for CET graph model
  - `cet_loader.py`: Create CETArea nodes and relationships
- `src/models/`: New Pydantic models for CET data
  - `cet_models.py`: CETArea, CETClassification, EvidenceStatement
- `src/assets/`: New Dagster assets for CET pipeline
  - `cet_assets.py`: cet_taxonomy, cet_classifications, cet_graph
- `config/`: CET configuration files
  - `cet/taxonomy.yaml`: 21 CET category definitions
  - `cet/classification.yaml`: ML hyperparameters
- `tests/`: Comprehensive test suite
  - `tests/unit/ml/`: CET classifier unit tests
  - `tests/integration/`: End-to-end classification tests
  - `tests/fixtures/`: Sample annotated awards

### Dependencies
**New Dependencies:**
- `scikit-learn >= 1.4.0`: ML pipeline (TF-IDF, LogReg, calibration)
- `spacy >= 3.7.0`: NLP for evidence extraction and sentence segmentation
- `en_core_web_sm`: spaCy English model for NLP processing

**Already Available:**
- pandas >= 2.2.0: Data processing
- pydantic >= 2.8.0: Data validation
- pyyaml >= 6.0.0: YAML configuration

### Integration Approach

**Embedded Module (Recommended)**:
- CET classifier runs as Dagster asset within existing pipeline
- Shares configuration management with main pipeline
- Direct integration with Award/Company/Patent transformers
- No separate service to maintain

**Advantages**:
- Unified data lineage in Dagster
- Simplified deployment (single application)
- Shared configuration and monitoring
- Lower operational complexity

### Performance Considerations
- **Throughput**: 5,979 awards/second (tested on 214k awards in 35.85s)
- **Latency**: 0.17ms per award (vs 500ms target)
- **Memory**: ~200MB for loaded model + vectorizer
- **Batch Processing**: Efficient vectorization of award batches
- **Neo4j Impact**: +21 CETArea nodes, +210k APPLICABLE_TO relationships (for 210k awards)

### Data Quality Metrics
- **Classification Success Rate**: 97.9% (from sbir-cet-classifier)
- **Evidence Coverage**: ~80% of classifications include supporting evidence
- **High Confidence Rate**: ~60% of classifications score ≥70
- **Validation**: Human agreement metrics tracked via evaluation framework
