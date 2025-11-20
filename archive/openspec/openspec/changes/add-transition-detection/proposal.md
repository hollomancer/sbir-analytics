# Add SBIR Transition Detection Module with Patent Traceability

## Why

The ultimate measure of SBIR program success is **technology transition** - when research funded by SBIR awards leads to follow-on government contracts, commercial products, or technology adoption. Currently, the pipeline lacks the ability to:

- **Detect successful transitions** from SBIR awards to follow-on contracts
- **Track patent-backed commercialization** where SBIR-funded research generates IP
- **Measure program effectiveness** at both award-level and company-level
- **Provide evidence-based scoring** with complete audit trails for validation
- **Enable strategic analysis** of which technologies, companies, and agencies achieve successful transition

Without transition detection, stakeholders cannot:

- Identify which SBIR investments led to real-world adoption
- Understand commercialization patterns and success factors
- Track the full innovation lifecycle (Research → Patents → Products → Contracts)
- Measure ROI and program effectiveness
- Validate transition claims with concrete evidence
- Detect technology transfer and licensing activities via patent assignments

### Critical Insight from sbir-transition-classifier:
- **Award-level success**: 69% of awards lead to follow-on work (encouraging)
- **Company-level success**: Only 7.9% of companies achieve sustained commercialization (challenging)
- This dual perspective reveals that while individual awards often succeed, building repeatable commercialization capability is rare

## What Changes

- **Add transition detection engine** adapted from production-ready sbir-transition-classifier
  - Rules-based heuristic scoring (97.9% data retention, 66K detections/minute)
  - Configurable confidence thresholds (High: ≥0.85, Likely: ≥0.65)
  - Multi-signal scoring (agency continuity, timing, competition type, sole source)
  - Evidence bundle generation for every detection (audit trail)
- **Add patent-based transition signals** (new capability beyond sbir-transition-classifier)
  - Patent filing as commercialization indicator
  - Patent-contract correlation (IP protection before contract awards)
  - Patent assignment tracking (technology transfer via licensing)
  - Patent-SBIR topic similarity scoring
- **Add federal contracts integration** from USAspending data
  - Link SBIR awards to follow-on government contracts
  - Vendor cross-walk (UEI, CAGE, DUNS identifier resolution)
  - Timing window analysis (0-24 months after Phase II completion)
  - Competition analysis (sole source, limited, full and open)
- **Add Neo4j transition graph model**
  - Create Transition nodes with likelihood scores and evidence
  - Add TRANSITIONED_TO relationships from Awards to Contracts
  - Add ENABLED_BY relationships from Patents to Transitions
  - Store evidence bundles and scoring details on relationships
  - Enable transition pathway queries (Award → Patent → Contract)
- **Add dual-perspective analytics**
  - Award-level transition rates (individual success)
  - Company-level commercialization rates (sustained capability)
  - Phase effectiveness comparison (Phase I vs Phase II)
  - Agency effectiveness tracking
- **Add configuration system for transition parameters**
  - Externalize detection thresholds (high-confidence, likely, discovery modes)
  - Externalize timing windows (0-24 months default, configurable)
  - Externalize scoring weights (agency, timing, competition, patent signals)
  - Support multiple detection presets (high-precision, broad-discovery, balanced)
- **Add transition evidence framework**
  - Generate comprehensive evidence bundles for each detection
  - Include all scoring components and signal strengths
  - Support manual review workflows
  - Track evidence sources (contracts, patents, vendor data)

## Impact

### Affected Specs

- **data-transformation**: Add transition detection transformation for Awards, Contracts, Patents
- **data-loading**: Add Transition nodes and transition relationships to Neo4j
- **configuration**: Add transition detection configuration management

### Affected Code

- `src/transition/`: New transition detection module
  - `detection/detector.py`: Core transition detection engine
  - `detection/scoring.py`: Multi-signal likelihood scoring
  - `detection/evidence.py`: Evidence bundle generation
  - `features/contract_matcher.py`: Award-contract matching logic
  - `features/patent_analyzer.py`: Patent-based transition signals
  - `features/vendor_resolver.py`: Cross-walk vendor identifiers
  - `config/presets.py`: Detection preset configurations
- `src/transformers/`: Enhanced transformers with transition detection
  - `award_transformer.py`: Add transition detection step
  - `contract_transformer.py`: Process federal contracts
  - `patent_transformer.py`: Add transition signal extraction
- `src/loaders/`: Neo4j loaders for transition graph model
  - `transition_loader.py`: Create Transition nodes and relationships
- `src/models/`: New Pydantic models for transition data
  - `transition_models.py`: Transition, EvidenceBundle, TransitionSignals
  - `contract_models.py`: FederalContract, CompetitionDetails
- `src/assets/`: New Dagster assets for transition pipeline
  - `transition_assets.py`: transition_detections, transition_evidence, transition_analytics
- `config/`: Transition configuration files
  - `transition/detection.yaml`: Scoring weights and thresholds
  - `transition/presets.yaml`: Pre-configured detection modes
- `tests/`: Comprehensive test suite
  - `tests/unit/transition/`: Transition detector unit tests
  - `tests/integration/`: End-to-end transition detection tests
  - `tests/fixtures/`: Sample contracts and known transitions

### Dependencies

### New Dependencies:
- None! All required libraries already available:
  - pandas, pydantic, pyyaml (already installed)
  - rapidfuzz (promote from dev to main - needed for vendor name matching)
  - duckdb (already installed - useful for large contract dataset analytics)

### Integration Approach

### Embedded Module (Recommended)
- Transition detector runs as Dagster asset within existing pipeline
- Shares vendor resolution with SBIR enrichment module
- Direct integration with Award/Patent/Contract transformers
- No separate database (uses Neo4j graph)

### Advantages
- Unified data lineage in Dagster
- Shared vendor cross-walk logic
- Single Neo4j graph for all relationships
- Lower operational complexity

### Data Sources Required

1. **SBIR Awards**: Already in pipeline (252K awards)
2. **Federal Contracts**: USAspending.gov data (6.7M+ contracts, 14GB+)
   - Currently available as CSV download
   - Integration with existing USAspending ingestion
3. **USPTO Patents**: Proposed USPTO ETL module (10.5M assignments)
   - Patent filing dates, assignees, topics
4. **Vendor Identifiers**: SAM.gov enrichment (already in SBIR module)
   - UEI, CAGE, DUNS cross-walk

### Performance Considerations

- **Detection Throughput**: 66,728 detections/minute (from sbir-transition-classifier)
- **Full Pipeline**: <8 hours for complete fiscal year backtest
- **Memory**: Chunked processing for 14GB+ contract dataset
- **Neo4j Impact**: +500K Transition nodes, +500K TRANSITIONED_TO relationships (estimated)
- **Evidence Storage**: Evidence bundles stored as JSON on relationships (~2KB each)

### Data Quality Metrics

- **Data Retention**: 99.99% (from sbir-transition-classifier)
- **Vendor Match Rate**: Target ≥90% (UEI cross-walk)
- **Award Coverage**: 100% of awards evaluated
- **Precision**: ≥85% for high-confidence detections (target)
- **Recall**: ≥70% against known Phase III awards (target)

### Business Value Metrics

From sbir-transition-classifier analysis:

- **Award-Level Success Rate**: 69.0% (individual transitions)
- **Company-Level Success Rate**: 7.9% (sustained commercialization)
- **Phase II Advantage**: 8.2 percentage points higher than Phase I
- **Patent Enhancement**: TBD - new capability for sbir-analytics

### Key Innovations Beyond sbir-transition-classifier

1. **Patent Integration**: First-class patent tracking as transition signal
2. **Graph Database**: Neo4j enables complex transition pathway queries
3. **Multi-Indicator Scoring**: Combines contracts + patents + CET classifications
4. **Technology Transition Paths**: Track Award → Patent → Contract sequences
5. **IP Transfer Detection**: Patent assignments reveal licensing and spin-offs
6. **CET Area Traceability**: Measure which Critical and Emerging Technology areas transition most effectively
   - Track transition rates by CET category (AI, Quantum, Hypersonics, etc.)
   - Identify high-performing vs underperforming technology areas
   - Correlate CET classification with commercialization success
   - Enable strategic investment decisions based on transition data

### CET-Transition Integration

By combining the proposed CET classification module with transition detection:

- **Technology-Specific Transition Rates**: Calculate success rates for each of 21 CET areas
- **Portfolio Optimization**: Identify which technologies have highest ROI
- **Gap Analysis**: Detect CET areas with high funding but low transition
- **Strategic Insights**:
  - Do AI awards transition better than Quantum Computing?
  - Which CET areas generate more patents?
  - Do certain technologies take longer to commercialize?
  - Are some CET areas better suited for specific agencies?

### Example Queries Enabled:

```cypher
// Transition rate by CET area
MATCH (a:Award)-[:APPLICABLE_TO]->(cet:CETArea)
OPTIONAL MATCH (a)-[:TRANSITIONED_TO]->(t:Transition)
RETURN
  cet.name,
  count(DISTINCT a) as total_awards,
  count(DISTINCT t) as transitions,
  count(DISTINCT t) * 100.0 / count(DISTINCT a) as transition_rate
ORDER BY transition_rate DESC

// Technology transition pathway analysis
MATCH path = (a:Award)-[:APPLICABLE_TO]->(cet:CETArea),
             (a)-[:FUNDED]->(p:Patent),
             (a)-[:TRANSITIONED_TO]->(trans:Transition)-[:RESULTED_IN]->(c:Contract)
WHERE trans.confidence = 'High'
RETURN
  cet.name as technology_area,
  count(DISTINCT path) as full_transition_paths,
  avg(trans.likelihood_score) as avg_transition_score
```
