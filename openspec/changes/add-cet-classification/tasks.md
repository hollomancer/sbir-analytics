# Implementation Tasks

**Note**: Unit tests for CET Pydantic models (CETArea, CETClassification, EvidenceStatement, CETAssessment, CompanyCETProfile) have been created in `tests/unit/ml/test_cet_models.py` with comprehensive validation coverage.

## 1. Project Setup & Dependencies

- [x] 1.1 Add scikit-learn>=1.4.0 to pyproject.toml dependencies
- [x] 1.2 Add spacy>=3.7.0 to pyproject.toml dependencies
- [x] 1.3 Install spaCy English model: python -m spacy download en_core_web_sm
- [x] 1.4 Create src/ml/ module structure (models/, features/, evaluation/)
- [x] 1.5 Create config/cet/ directory for CET configuration files
- [x] 1.6 Add pytest fixtures for CET classification tests

## 2. Configuration Files

- [x] 2.1 Port config/taxonomy.yaml from sbir-cet-classifier (21 CET categories)
- [x] 2.2 Port config/classification.yaml from sbir-cet-classifier (ML hyperparameters)
- [x] 2.3 Create configuration loader in src/ml/config/taxonomy_loader.py
- [x] 2.4 Add CET configuration schema validation (Pydantic models)
- [x] 2.5 Add taxonomy versioning support (NSTC-2025Q1, etc.)
- [x] 2.6 Document CET taxonomy structure in config/cet/README.md

## 3. Pydantic Data Models

- [x] 3.1 Create CETArea model in src/models/cet_models.py
- [x] 3.2 Create CETClassification model (score, classification, primary/supporting)
- [x] 3.3 Create EvidenceStatement model (excerpt, source_location, rationale_tag)
- [x] 3.4 Create CETAssessment model (combines classification + evidence)
- [x] 3.5 Add CET-specific validation rules (score 0-100, classification in High/Medium/Low)
- [x] 3.6 Add type hints for all CET models

## 4. ML Classification Module - Core Model

- [x] 4.1 Port ApplicabilityModel from sbir-cet-classifier to src/ml/models/cet_classifier.py
- [x] 4.2 Port CETAwareTfidfVectorizer with keyword boosting
- [x] 4.3 Implement TF-IDF pipeline (vectorizer → feature selection → classifier → calibration)
- [x] 4.4 Add balanced class weights for handling imbalanced CET categories
- [x] 4.5 Implement multi-threshold scoring (High: ≥70, Medium: 40-69, Low: <40)
- [x] 4.6 Add batch classification method for efficient processing
- [x] 4.7 Save/load trained model (pickle or joblib)
- [x] 4.8 Add model metadata (version, training date, taxonomy version)

## 5. Evidence Extraction

- [ ] 5.1 Create EvidenceExtractor in src/ml/features/evidence_extractor.py
- [ ] 5.2 Implement spaCy-based sentence segmentation
- [ ] 5.3 Add CET keyword matching within sentences
- [ ] 5.4 Implement 50-word excerpt truncation
- [ ] 5.5 Add source location tracking (abstract, keywords, solicitation)
- [ ] 5.6 Generate rationale tags (e.g., "Contains: machine learning, neural networks")
- [ ] 5.7 Add evidence ranking (select top 3 most relevant sentences)

## 6. Training Data & Model Training

- [ ] 6.1 Port bootstrap training data from sbir-cet-classifier (1000+ annotated awards)
- [ ] 6.2 Create TrainingExample model for labeled data
- [ ] 6.3 Implement model training workflow in src/ml/models/trainer.py
- [ ] 6.4 Add cross-validation for hyperparameter tuning
- [ ] 6.5 Implement probability calibration (sigmoid, 3-fold CV)
- [ ] 6.6 Save trained model to artifacts/models/cet_classifier_v1.pkl
- [ ] 6.7 Generate training metrics report (accuracy, precision, recall, F1)

## 7. Dagster Assets - CET Taxonomy

- [ ] 7.1 Create cet_taxonomy asset in src/assets/cet_assets.py
- [ ] 7.2 Load taxonomy from config/cet/taxonomy.yaml
- [ ] 7.3 Validate taxonomy schema (required fields, unique IDs)
- [ ] 7.4 Add asset checks for taxonomy completeness
- [ ] 7.5 Output taxonomy to data/processed/cet_taxonomy.parquet

## 8. Dagster Assets - Award Classification

- [ ] 8.1 Create cet_award_classifications asset (depends on enriched_sbir_awards, cet_taxonomy)
- [ ] 8.2 Load trained CET classifier model
- [ ] 8.3 Batch classify awards (1000 awards/batch for efficiency)
- [ ] 8.4 Extract evidence for each classification
- [ ] 8.5 Calculate primary CET area + up to 3 supporting areas
- [ ] 8.6 Add asset checks for classification success rate (target: ≥95%)
- [ ] 8.7 Add asset checks for high confidence rate (target: ≥60%)
- [ ] 8.8 Add asset checks for evidence coverage (target: ≥80%)
- [ ] 8.9 Output classifications to data/processed/cet_award_classifications.parquet
- [ ] 8.10 Log classification metrics (throughput, latency, confidence distribution)

## 9. Company CET Aggregation

- [ ] 9.1 Create CompanyCETAggregator in src/transformers/company_cet_aggregator.py
- [ ] 9.2 Aggregate CET scores from all awards per company
- [ ] 9.3 Calculate dominant CET area (highest average score)
- [ ] 9.4 Calculate CET specialization score (concentration in top CET)
- [ ] 9.5 Track CET evolution over time (Phase I → Phase II → Phase III)
- [ ] 9.6 Create cet_company_profiles asset (depends on cet_award_classifications)
- [ ] 9.7 Output company profiles to data/processed/cet_company_profiles.parquet

## 10. Patent CET Classification

- [ ] 10.1 Create PatentCETClassifier in src/ml/models/patent_classifier.py
- [ ] 10.2 Classify patents based on title + assignee entity type
- [ ] 10.3 Add patent-specific feature engineering (patent title structure)
- [ ] 10.4 Create cet_patent_classifications asset (depends on transformed_patents)
- [ ] 10.5 Link patent CET to originating award CET for validation
- [ ] 10.6 Calculate technology transition alignment (award CET = patent CET)

## 11. USPTO AI Dataset Integration

- [ ] 11.1 Create USPTOAILoader in src/ml/data/uspto_ai_loader.py
- [ ] 11.2 Extract USPTO AI predictions from ai_model_predictions.dta
- [ ] 11.3 Create SQLite cache for USPTO predictions (indexed by grant_doc_num)
- [ ] 11.4 Implement chunked streaming (10K patents/chunk) for 1.2GB file
- [ ] 11.5 Add USPTO prediction lookup function (by grant_doc_num)
- [ ] 11.6 Create validation metrics comparing CET AI scores with USPTO predictions
- [ ] 11.7 Generate USPTO alignment report (precision, recall, agreement rate)
- [ ] 11.8 Add configuration flag to enable/disable USPTO integration

## 12. Neo4j CET Graph Model - Nodes

- [ ] 12.1 Create CETAreaLoader in src/loaders/cet_loader.py
- [ ] 12.2 Load 21 CET categories as CETArea nodes
- [ ] 12.3 Add CETArea node properties (cet_id, name, definition, keywords, taxonomy_version)
- [ ] 12.4 Handle hierarchical relationships (parent_cet_id)
- [ ] 12.5 Create index on CETArea.cet_id
- [ ] 12.6 Create neo4j_cet_areas asset
- [ ] 12.7 Add asset checks for CET node count (expected: 21)

## 13. Neo4j CET Graph Model - Award Relationships

- [ ] 13.1 Create APPLICABLE_TO relationships from Awards to CETArea nodes
- [ ] 13.2 Add relationship properties (score, classification, primary, evidence, classified_at, taxonomy_version)
- [ ] 13.3 Handle primary CET area (primary=true) vs supporting areas (primary=false)
- [ ] 13.4 Batch write APPLICABLE_TO relationships (1000 relationships/transaction)
- [ ] 13.5 Create neo4j_award_cet_relationships asset
- [ ] 13.6 Add asset checks for relationship count (expected: ~210k primary + ~420k supporting)

## 14. Neo4j CET Graph Model - Company Relationships

- [ ] 14.1 Create SPECIALIZES_IN relationships from Companies to CETArea nodes
- [ ] 14.2 Add relationship properties (award_count, total_funding, avg_score, dominant_phase, first_award_date, last_award_date)
- [ ] 14.3 Calculate company-level CET metrics
- [ ] 14.4 Create neo4j_company_cet_relationships asset
- [ ] 14.5 Add asset checks for relationship count

## 15. Neo4j CET Graph Model - Patent Relationships

- [ ] 15.1 Create APPLICABLE_TO relationships from Patents to CETArea nodes
- [ ] 15.2 Add relationship properties including uspto_ai_score (if available)
- [ ] 15.3 Track technology transition (Award CET → Patent CET)
- [ ] 15.4 Create neo4j_patent_cet_relationships asset
- [ ] 15.5 Add Cypher queries for technology transition analysis

## 16. CET Portfolio Analytics

- [ ] 16.1 Create CET portfolio summary queries (Cypher)
- [ ] 16.2 Query: Count awards by CET area and fiscal year
- [ ] 16.3 Query: Total funding by CET area and agency
- [ ] 16.4 Query: Top companies per CET area
- [ ] 16.5 Query: CET gap analysis (underfunded areas)
- [ ] 16.6 Query: Technology transition rate (Award CET → Patent CET alignment)
- [ ] 16.7 Document queries in docs/queries/cet_portfolio_queries.md

## 17. Evaluation & Validation

- [ ] 17.1 Create CETEvaluator in src/ml/evaluation/cet_evaluator.py
- [ ] 17.2 Implement human validation sampling (100 awards)
- [ ] 17.3 Calculate agreement metrics (precision, recall, F1, Cohen's kappa)
- [ ] 17.4 Generate confusion matrix for CET categories
- [ ] 17.5 Identify challenging cases (low confidence, misclassifications)
- [ ] 17.6 Create evaluation report with charts and statistics
- [ ] 17.7 Run USPTO AI validation for AI category (compare with predict93_any_ai)

## 18. Unit Testing

- [ ] 18.1 Unit tests for CETClassifier (training, scoring, batch processing)
- [ ] 18.2 Unit tests for EvidenceExtractor (sentence segmentation, keyword matching)
- [x] 18.3 Unit tests for TaxonomyLoader (YAML parsing, validation)
- [ ] 18.4 Unit tests for CompanyCETAggregator (aggregation logic)
- [ ] 18.5 Unit tests for PatentCETClassifier
- [ ] 18.6 Unit tests for USPTOAILoader (chunked streaming, caching)
- [ ] 18.7 Unit tests for CETAreaLoader (Neo4j node creation)
- [ ] 18.8 Unit tests for CET relationship loaders

## 19. Integration Testing

- [ ] 19.1 Integration test: Full CET classification pipeline (taxonomy → awards → Neo4j)
- [ ] 19.2 Integration test: Company CET aggregation with multiple awards
- [ ] 19.3 Integration test: Patent classification with USPTO validation
- [ ] 19.4 Integration test: Technology transition tracking (Award → Patent CET)
- [ ] 19.5 Integration test: CET portfolio queries against Neo4j
- [ ] 19.6 Test with sample dataset (1000 awards, 100 companies, 500 patents)
- [ ] 19.7 Validate data quality metrics meet targets

## 20. End-to-End Testing

- [ ] 20.1 E2E test: Dagster pipeline materialization (all CET assets)
- [ ] 20.2 E2E test: Full 210k awards classification
- [ ] 20.3 E2E test: Neo4j graph queries for CET portfolio
- [ ] 20.4 E2E test: Incremental updates (add new awards, reclassify)
- [ ] 20.5 Validate performance metrics (throughput ≥1000 awards/sec, latency ≤1s)
- [ ] 20.6 Validate quality metrics (success rate ≥95%, high confidence rate ≥60%, evidence coverage ≥80%)

## 21. Documentation

- [x] 21.1 Document CET taxonomy structure in config/cet/README.md
- [ ] 21.2 Document ML model architecture and hyperparameters in docs/ml/cet_classifier.md
- [ ] 21.3 Document evidence extraction approach in docs/ml/evidence_extraction.md
- [ ] 21.4 Document Neo4j CET graph schema in docs/schemas/cet-graph-schema.md
- [ ] 21.5 Document CET portfolio queries with examples
- [ ] 21.6 Add CET classification section to main README.md
- [ ] 21.7 Create data dictionary for CET fields

## 22. Performance Optimization (if needed)

- [ ] 22.1 Profile classification performance (vectorization, prediction)
- [ ] 22.2 Optimize batch size for memory vs throughput trade-off
- [ ] 22.3 Parallelize classification across Dagster workers (if needed)
- [ ] 22.4 Cache loaded models for reuse across batches
- [ ] 22.5 Optimize Neo4j batch write sizes

## 23. Configuration & Deployment

- [ ] 23.1 Add CET configuration to config/base.yaml (enable/disable features)
- [ ] 23.2 Add environment-specific configuration (dev/staging/prod)
- [ ] 23.3 Create deployment checklist for CET module
- [ ] 23.4 Test configuration override via environment variables
- [ ] 23.5 Document deployment procedure in docs/deployment/cet_deployment.md

## 24. Deployment & Validation

- [ ] 24.1 Run full pipeline on development environment
- [ ] 24.2 Validate all data quality metrics meet targets
- [ ] 24.3 Generate comprehensive evaluation report
- [ ] 24.4 Review evaluation report with stakeholders
- [ ] 24.5 Deploy to staging environment
- [ ] 24.6 Run regression tests on staging
- [ ] 24.7 Deploy to production
- [ ] 24.8 Monitor classification metrics post-deployment
