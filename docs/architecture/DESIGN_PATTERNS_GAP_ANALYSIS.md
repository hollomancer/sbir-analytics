# Design Patterns Gap Analysis

**Generated:** 2025-10-25
**Status:** add-initial-architecture is 91.3% complete (95/104 tasks)

This document maps the remaining design patterns from `openspec/project.md` that are not yet implemented in the current codebase. These patterns would enhance the production-readiness of the SBIR ETL pipeline.

---

## Pattern Implementation Status

### ✅ Fully Implemented (5 patterns)

1. **Configuration Management Architecture** - Complete
   - ✅ Pydantic schemas with validation
   - ✅ YAML-based hierarchical config (base.yaml, dev.yaml, prod.yaml)
   - ✅ Environment variable overrides
   - ✅ Configuration caching with lru_cache
   - ✅ Unit and integration tests

2. **Multi-Stage Pipeline Design** - Complete
   - ✅ Five-stage structure (Extract → Validate → Enrich → Transform → Load)
   - ✅ Dagster asset-based orchestration
   - ✅ Asset dependencies and checks
   - ✅ Example assets demonstrating flow

3. **Data Quality Framework** - Complete
   - ✅ Schema validation functions
   - ✅ Completeness, uniqueness, and value range checks
   - ✅ QualitySeverity enum and QualityIssue dataclass
   - ✅ Configurable thresholds
   - ✅ Comprehensive unit tests

4. **Structured Logging** - Complete
   - ✅ Loguru-based configuration
   - ✅ Console handler (development) and JSON handler (production)
   - ✅ Daily log rotation
   - ✅ Context variables for stage and run_id tracking
   - ✅ log_with_context context manager

5. **Testing Pyramid Structure** - Complete
   - ✅ Unit tests (22 tests for metrics)
   - ✅ Integration tests (27 tests for Neo4j, 20 tests for configuration)
   - ✅ pytest configuration with coverage reporting
   - ✅ pytest-cov integration

---

## ⚠️ Partially Implemented (2 patterns)

### 6. Hierarchical Enrichment with Fallbacks

**Current Implementation:** 30%
- ✅ Basic enrichment structure in place
- ✅ EnrichmentConfig schema
- ❌ Missing 9-step hierarchical fallback workflow
- ❌ Missing EnrichmentResult with confidence scores
- ❌ Missing fallback chain (API → fuzzy → agency default → sector fallback)
- ❌ Missing enrichment source tracking

**Required Implementation:**

```python
# src/enrichers/hierarchical.py (NEW FILE)
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

class EnrichmentSource(str, Enum):
    """Source of enrichment data."""
    ORIGINAL = "original"
    USASPENDING_API = "usaspending_api"
    SAM_GOV_API = "sam_gov_api"
    FUZZY_MATCH = "fuzzy_match"
    PROXIMITY_FILTER = "proximity_filter"
    AGENCY_DEFAULT = "agency_default"
    SECTOR_FALLBACK = "sector_fallback"

@dataclass
class EnrichmentResult:
    """Result of enrichment attempt with evidence."""
    field_name: str
    enriched_value: Any
    original_value: Any
    source: EnrichmentSource
    confidence: float  # 0.0-1.0
    metadata: dict
    timestamp: datetime

def enrich_naics_hierarchical(
    award: Dict[str, Any],
    config: EnrichmentConfig
) -> EnrichmentResult:
    """9-step enrichment workflow:

    1. Original SBIR data (confidence: 0.95)
    2. USAspending API (confidence: 0.90)
    3. SAM.gov API (confidence: 0.85)
    4. Fuzzy name matching (confidence: 0.65-0.80)
    5. Proximity filtering (confidence: varies)
    6. Agency defaults (confidence: 0.50)
    7. Sector fallback (confidence: 0.30)
    """
    # Implementation needed
```

**Files to Create:**
- `src/enrichers/hierarchical.py` - Hierarchical enrichment logic
- `src/enrichers/sam_gov_client.py` - SAM.gov API client
- `src/enrichers/usaspending_client.py` - USAspending API client
- `src/enrichers/fuzzy_matcher.py` - Fuzzy matching utilities
- `tests/unit/test_hierarchical_enrichment.py` - Unit tests
- `tests/integration/test_enrichment_apis.py` - API integration tests

**Estimated Effort:** 3-4 days

---

### 7. Configuration-Driven Quality Thresholds

**Current Implementation:** 70%
- ✅ DataQualityConfig schema exists
- ✅ Configurable thresholds in YAML
- ✅ Validation functions respect thresholds
- ❌ Missing dynamic threshold adjustment based on enrichment confidence
- ❌ Missing threshold profiles for different data sources

**Required Enhancement:**

```yaml
# config/base.yaml (ENHANCEMENT)
data_quality:
  sbir_awards:
    # ... existing config ...

  enriched_awards:
    threshold_profiles:
      high_confidence:  # For enriched records with confidence ≥ 0.80
        completeness_threshold: 0.95
        uniqueness_threshold: 0.99
      medium_confidence:  # For enriched records with 0.60 ≤ confidence < 0.80
        completeness_threshold: 0.85
        uniqueness_threshold: 0.95
      low_confidence:  # For enriched records with confidence < 0.60
        completeness_threshold: 0.70
        uniqueness_threshold: 0.90
        manual_review_required: true
```

**Files to Modify:**
- `config/base.yaml` - Add threshold profiles
- `src/config/schemas.py` - Add ThresholdProfile schema
- `src/validators/quality.py` - Add confidence-based validation
- `tests/unit/test_quality_thresholds.py` - Unit tests

**Estimated Effort:** 1-2 days

---

## ❌ Not Yet Implemented (3 patterns)

### 8. Rich CLI with Progress Tracking

**Current Implementation:** 0%
- ❌ No CLI application exists
- ❌ Current interaction is Python-based or Dagster UI only

**Required Implementation:**

```python
# src/cli/app.py (NEW FILE)
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table
from rich.panel import Panel

app = typer.Typer(help="SBIR ETL Pipeline CLI")
console = Console()

@app.command()
def ingest(
    source: str = typer.Option("sbir", help="Data source (sbir, usaspending)"),
    year: Optional[int] = typer.Option(None, help="Filter by year"),
    incremental: bool = typer.Option(False, help="Incremental mode"),
):
    """Ingest data with rich progress tracking."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        download_task = progress.add_task("[cyan]Downloading data...", total=100)
        # ... download logic ...
        progress.update(download_task, completed=100)

@app.command()
def status():
    """Show pipeline status and data quality metrics."""
    # Rich table with pipeline status
    table = Table(title="Pipeline Status")
    table.add_column("Stage", style="cyan")
    table.add_column("Records", justify="right")
    table.add_column("Pass Rate", justify="right")
    # ... populate table ...
    console.print(table)

@app.command()
def metrics(run_id: str):
    """Show detailed metrics for a specific run."""
    # Rich metrics dashboard
    pass
```

**Files to Create:**
- `src/cli/__init__.py`
- `src/cli/app.py` - Main Typer application
- `src/cli/commands/ingest.py` - Ingest command
- `src/cli/commands/enrich.py` - Enrichment command
- `src/cli/commands/status.py` - Status dashboard
- `src/cli/commands/metrics.py` - Metrics viewer
- `tests/unit/test_cli.py` - CLI unit tests

**Dependencies to Add:**
```toml
# pyproject.toml
[tool.poetry.dependencies]
typer = "^0.9.0"
rich = "^13.7.0"
```

**Estimated Effort:** 3-5 days

---

### 9. Evidence-Based Explainability

**Current Implementation:** 0%
- ❌ No evidence tracking for enrichment decisions
- ❌ No confidence scoring system
- ❌ No manual review interface

**Required Implementation:**

```python
# src/models/evidence.py (NEW FILE)
from dataclasses import dataclass
from typing import List, Any
from datetime import datetime

@dataclass
class MatchEvidence:
    """Evidence supporting a match decision."""
    evidence_type: str  # "exact_match", "fuzzy_match", "api_lookup"
    confidence: float   # 0.0-1.0
    source_field: str
    matched_value: str
    original_value: str
    metadata: dict

@dataclass
class EnrichmentResult:
    """Enrichment result with supporting evidence."""
    field_name: str
    enriched_value: Any
    original_value: Any
    confidence: float
    evidence: List[MatchEvidence]
    timestamp: datetime

    def aggregate_confidence(self) -> float:
        """Calculate weighted average confidence from evidence."""
        if not self.evidence:
            return 0.0
        return sum(e.confidence for e in self.evidence) / len(self.evidence)
```

**Neo4j Schema Enhancement:**
```cypher
// Store evidence in relationship properties
CREATE (a:Award {award_id: "12345"})
CREATE (c:Company {name: "Acme Corp"})
CREATE (a)-[r:AWARDED_TO {
    matched_by: "fuzzy_match",
    confidence: 0.82,
    evidence: [
        {type: "fuzzy_match", similarity: 0.82, field: "company_name"},
        {type: "proximity", distance_miles: 5.2, field: "location"}
    ],
    enriched_at: datetime("2025-10-25T14:32:22")
}]->(c)
```

**CLI Command:**
```bash
# Review low-confidence enrichments
python -m src.cli.app review-low-confidence --threshold 0.70

# Export evidence for manual review
python -m src.cli.app export-evidence --output evidence_review.csv
```

**Files to Create:**
- `src/models/evidence.py` - MatchEvidence and EnrichmentResult models
- `src/enrichers/evidence_tracker.py` - Evidence collection utilities
- `src/cli/commands/review.py` - Manual review CLI
- `src/loaders/neo4j_evidence.py` - Evidence storage in Neo4j
- `tests/unit/test_evidence.py` - Unit tests

**Estimated Effort:** 4-6 days

---

### 10. Comprehensive Evaluation Framework

**Current Implementation:** 40%
- ✅ Basic PipelineMetrics and MetricsCollector
- ✅ Stage-level metrics tracking
- ❌ Missing enrichment breakdown tracking
- ❌ Missing error categorization
- ❌ Missing metrics dashboard CLI commands
- ❌ Missing historical trend analysis

**Required Enhancement:**

```python
# src/utils/metrics.py (ENHANCEMENT)
@dataclass
class EnrichmentMetrics:
    """Detailed enrichment metrics."""
    total_records: int
    enrichment_breakdown: Dict[EnrichmentSource, int]  # Count by source
    confidence_distribution: Dict[str, int]  # high/medium/low counts
    average_confidence: float
    api_call_count: int
    api_success_rate: float
    fallback_rate: float

@dataclass
class ErrorMetrics:
    """Categorized error tracking."""
    total_errors: int
    error_categories: Dict[str, int]  # "validation", "api_timeout", "parse_error"
    error_severity: Dict[str, int]  # "critical", "warning", "info"
    recoverable_errors: int
    unrecoverable_errors: int

class MetricsCollector:
    # ... existing implementation ...

    def track_enrichment(self, result: EnrichmentResult):
        """Track enrichment-specific metrics."""
        # Implementation needed

    def categorize_error(self, error: Exception, category: str, severity: str):
        """Categorize errors for analysis."""
        # Implementation needed

    def generate_dashboard_data(self, run_id: str) -> Dict[str, Any]:
        """Generate data for CLI dashboard."""
        # Implementation needed
```

**CLI Commands:**
```python
# src/cli/commands/metrics.py (NEW)
@app.command()
def dashboard(
    run_id: Optional[str] = None,
    last_n_runs: int = 5,
):
    """Show comprehensive metrics dashboard."""
    # Rich tables and panels showing:
    # - Enrichment source breakdown
    # - Confidence distribution
    # - Error categories
    # - Performance trends
    pass

@app.command()
def trends(days: int = 30):
    """Show historical trends over time."""
    # Line charts (using rich or export to CSV for plotting)
    pass
```

**Files to Modify/Create:**
- `src/utils/metrics.py` - Add EnrichmentMetrics and ErrorMetrics
- `src/cli/commands/metrics.py` - Metrics dashboard CLI
- `src/cli/commands/trends.py` - Historical trend analysis
- `tests/unit/test_enrichment_metrics.py` - Unit tests
- `tests/integration/test_metrics_persistence.py` - Integration tests

**Estimated Effort:** 3-4 days

---

## Summary and Recommendations

### Total Estimated Effort

| Pattern | Status | Effort | Priority |
|---------|--------|--------|----------|
| Hierarchical Enrichment with Fallbacks | 30% | 3-4 days | **HIGH** |
| Configuration-Driven Quality Thresholds | 70% | 1-2 days | MEDIUM |
| Rich CLI with Progress Tracking | 0% | 3-5 days | **HIGH** |
| Evidence-Based Explainability | 0% | 4-6 days | MEDIUM |
| Comprehensive Evaluation Framework | 40% | 3-4 days | **HIGH** |

**Total:** 14-21 days of development work

### Recommended Implementation Order

1. **Rich CLI with Progress Tracking** (Priority: HIGH, Effort: 3-5 days)
   - Provides immediate UX improvement
   - Foundation for dashboard and review commands
   - Independent of other patterns

2. **Hierarchical Enrichment with Fallbacks** (Priority: HIGH, Effort: 3-4 days)
   - Core business logic enhancement
   - Improves data quality and coverage
   - Unlocks Evidence-Based Explainability

3. **Comprehensive Evaluation Framework** (Priority: HIGH, Effort: 3-4 days)
   - Builds on existing metrics infrastructure
   - Provides visibility into enrichment quality
   - Enables data-driven optimization

4. **Evidence-Based Explainability** (Priority: MEDIUM, Effort: 4-6 days)
   - Depends on Hierarchical Enrichment completion
   - Enables manual review and quality improvement
   - Critical for production transparency

5. **Configuration-Driven Quality Thresholds** (Priority: MEDIUM, Effort: 1-2 days)
   - Enhancement to existing functionality
   - Can be implemented incrementally
   - Low-risk, high-value addition

### OpenSpec Workflow Recommendation

**Option 1: Incremental Changes (Recommended)**
- Complete `add-initial-architecture` and archive it
- Create separate OpenSpec changes for each pattern:
  - `add-rich-cli`
  - `add-hierarchical-enrichment`
  - `add-evaluation-framework`
  - `add-evidence-tracking`
  - `enhance-quality-thresholds`

**Option 2: Extended Architecture Phase**
- Keep `add-initial-architecture` open
- Add remaining patterns as new tasks in tasks.md
- Archive when all 10 patterns complete

**Recommendation:** Use **Option 1** for better change tracking and focused implementation.

---

## Next Steps

### Immediate Actions
1. **Archive `add-initial-architecture`** (91.3% complete, pending environment setup)
2. **Begin Codebase Consolidation Refactor** - Address architectural debt before adding new patterns
3. **Create `/openspec propose codebase-consolidation-refactor`** - Implement consolidation plan

### Post-Consolidation Pattern Implementation
4. **Create `/openspec propose add-rich-cli`** - Start with CLI for immediate UX value
5. **Implement Rich CLI pattern** (3-5 days)
6. **Create `/openspec propose add-hierarchical-enrichment`**
7. **Continue pattern-by-pattern implementation**

### Consolidation Integration
The remaining design patterns should be implemented **after** the codebase consolidation refactor to:
- Leverage the unified configuration system for pattern-specific settings
- Use consolidated asset framework for new pattern implementations
- Benefit from unified testing framework for pattern validation
- Integrate with centralized performance monitoring

This approach ensures new patterns are built on a solid, consolidated foundation rather than adding to the current architectural complexity.

**Recommended Sequence**:
1. Complete codebase consolidation refactor (6-8 weeks)
2. Implement remaining design patterns on consolidated architecture (4-6 weeks)
3. Total estimated effort: 10-14 weeks for complete architectural modernization

This incremental approach aligns with OpenSpec best practices and provides clear milestones for each production pattern.
