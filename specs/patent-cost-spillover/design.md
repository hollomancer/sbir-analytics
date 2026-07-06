# Patent Cost and Spillover Analysis — Design

## Architecture

Builds on the existing patent-award linkage pipeline. New analytical code lives in
`packages/sbir-analytics/sbir_analytics/tools/mission_b/` (knowledge-output metrics
are an innovation/commercialization outcome, consistent with the mission_b namespace).

### Precondition: USPTO citation ingestion

The existing USPTO pipeline ingests patent grant data but **does not yet ingest patent
citation pairs** (citing_patent → cited_patent). The `PatentCitation` model exists in the
graph schema but citations are not yet loaded as graph relationships
(`docs/research-questions.md` A2 note). Citation ingestion is a hard prerequisite for
Requirement 2 (spillover) and must be completed before Phase 2 of this spec begins.
Phase 1 (marginal cost) has no citation dependency and can proceed independently.

### Data Flow

```
SBIR awards (SBIR.gov)
    ↓
patent-award linkage (sbir_etl/transformers/patent_transformer.py)
    ↓ patent_id → award_id pairs
PatentCostCalculator
    ↓ marginal cost per agency / CET / vintage
    ↓
    ←── USPTO citation pairs (precondition ingestion)
CitationNetworkBuilder
    ↓ directed citation graph (SBIR-labeled nodes)
SpilloverCalculator
    ↓ inbound/outbound multipliers per agency
    ↓
NASEMReconciler
    ↓
reports/patent-spillover/
    ├── cost_by_agency.json
    ├── spillover_by_agency.json
    ├── stratified/
    │   ├── by_cet_area.json
    │   ├── by_firm_size.json
    │   └── by_vintage.json
    └── reconciliation/
        ├── reconciliation.json
        └── reconciliation.md
```

### Key Components

**`PatentCostCalculator`** (`patent_cost_analysis.py`)
Inputs: patent-award linkage table, SBIR award amounts.
Outputs: marginal-cost-per-patent DataFrame by agency, CET area, firm size, and vintage.
Suppresses cells with <20 linked patents; reports match-rate metadata alongside every
figure.

**`CitationNetworkBuilder`** (`citation_network.py`)
Inputs: USPTO citing → cited pairs (after precondition ingestion), patent-award linkage.
Outputs: directed citation graph with SBIR/non-SBIR node labels, serialized as an
adjacency list for SpilloverCalculator (not loaded into Neo4j in this spec — separate
concern).

**`SpilloverCalculator`**
Inputs: citation graph from CitationNetworkBuilder.
Outputs: inbound spillover multiplier (non-SBIR → SBIR citations / SBIR patent count),
U.S.-retained fraction, per-agency and per-CET breakdowns. Documents citation-window
cutoff in every output artifact.

**`NASEMReconciler`**
Stores benchmark constants (NIH ~$1.5M, DOE ~3×, ~60% U.S.-retained).
Produces structured reconciliation comparing pipeline output to each benchmark, with
methodology-difference attribution. Emits JSON + markdown.

### Output Format

All analytical output lands in `reports/patent-spillover/`. Dagster asset wrappers
(Phase 5 in tasks.md) read from this directory and expose the artifacts as materializations.
Human-readable markdown summaries are co-emitted alongside every JSON artifact for
direct review without tooling.

### Implementation Phase Ordering

Phase 1 (marginal cost) is independent of citation ingestion and can start immediately.
Phase 2 (citation network) requires the citation-ingestion precondition. Track the
precondition as a separate prerequisite task in tasks.md before beginning Phase 2.
