# Cross-Agency Technology Taxonomy — Design

## Architecture

The analytical tools are already built. The design work is limited to wiring them
into a Dagster pipeline and defining the output schema that downstream assets consume.

```
packages/sbir-analytics/sbir_analytics/tools/mission_a/
  ├── compute_portfolio_metrics.py   HHI per CET area, company count, geo concentration
  ├── cluster_topics.py              semantic clustering of award topics
  ├── detect_gaps.py                 whitespace detection vs. CET spine
  └── extract_topics.py             topic extraction from award text

packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py
  └── classifies awards → (cet_area, confidence)
```

### Data Flow

```
SBIR.gov corpus (full, all 11 agencies)
    ↓
CET classifier (sbir-ml)
    ↓  award_id → cet_area, confidence  [Parquet artifact]
    ↓
AgencyTaxonomyAnalyzer
  ├── per-agency CET share table  (award count + dollar weight)
  ├── cross-agency Jaccard overlap matrix
  ├── HHI per CET area  (from compute_portfolio_metrics.py)
  ├── gap/whitespace detection  (from detect_gaps.py)
  └── fiscal-year trend table  (agency × cet_area × year)
    ↓
ReportBuilder
    ↓
reports/cross-agency-taxonomy/
  ├── taxonomy_YYYYMMDD.md          human-readable summary
  ├── taxonomy_YYYYMMDD.json        full structured output
  ├── classification.parquet        award-level CET assignments
  ├── overlap_matrix.json           pairwise Jaccard scores
  ├── concentration.json            per-CET-area HHI
  └── trends.json                   agency × cet_area × year shares
```

### Dagster Asset Structure

Three asset nodes, each independently materializable:

1. **`cet_classification_corpus`** — runs the CET classifier over the full corpus;
   outputs `classification.parquet`. Downstream of the weekly SBIR corpus refresh asset.
   Triggers only when new awards are present (checked via award count comparison).

2. **`cross_agency_taxonomy_metrics`** — runs AgencyTaxonomyAnalyzer over the
   classification Parquet; outputs the overlap matrix, concentration JSON, and trends
   table. Downstream of `cet_classification_corpus`.

3. **`cross_agency_taxonomy_report`** — runs ReportBuilder; outputs the dated markdown
   and JSON report. Downstream of `cross_agency_taxonomy_metrics`. This is the terminal
   asset the reporting dashboard or weekly email would consume.

### CET Taxonomy Version Pinning

The canonical taxonomy is `config/cet/taxonomy.yaml` (21 areas, `NSTC-2025Q1`).
The classification Parquet artifact SHALL carry a `taxonomy_version` metadata field.
When the taxonomy YAML changes, existing Parquet artifacts are stale and must be
re-materialized. The Dagster asset should check for taxonomy-version mismatch on
each run and force re-classification if a mismatch is detected.

### Note on the Two Divergent CET Code Taxonomies

Two code-level taxonomies are not yet reconciled to the canonical 21-area spine
(documented in `docs/research-questions.md` Maintenance section):
- 10-area set in transition-system code (`docs/transition/cet-integration.md`)
- 19-area set in `sbir_etl/utils/reporting/analyzers/cet_analyzer.py`

This spec uses only the canonical 21-area classifier. Do not use `cet_analyzer.py`
as the classification source. Reconciling the divergent taxonomies is a separate
scope item with test/precision-benchmark risk.
