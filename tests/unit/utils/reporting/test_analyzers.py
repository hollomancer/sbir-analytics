"""Unit tests for reporting analyzer modules.

Tests for base analyzer class and all specialized analyzer implementations:
- BaseAnalyzer: Common utilities and abstract methods
- CetClassificationAnalyzer: CET classification analysis
- PatentAnalysisAnalyzer: Patent validation and loading analysis
- SbirEnrichmentAnalyzer: SBIR enrichment analysis
- TransitionDetectionAnalyzer: Transition detection analysis
"""

from typing import Any

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from sbir_etl.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport
from sbir_etl.utils.reporting.analyzers.base_analyzer import AnalysisInsight, ModuleAnalyzer
from sbir_etl.utils.reporting.analyzers.cet_analyzer import CetClassificationAnalyzer
from sbir_etl.utils.reporting.analyzers.patent_analyzer import PatentAnalysisAnalyzer
from sbir_etl.utils.reporting.analyzers.sbir_analyzer import SbirEnrichmentAnalyzer
from sbir_etl.utils.reporting.analyzers.transition_analyzer import TransitionDetectionAnalyzer


pytestmark = pytest.mark.fast


def _stable_report_dump(report: ModuleReport) -> dict[str, Any]:
    """Return the deterministic portion of a module report."""
    return report.model_dump(exclude={"timestamp"})


def _stub_domain_analysis(monkeypatch: pytest.MonkeyPatch, analyzer: ModuleAnalyzer) -> None:
    """Isolate shared lifecycle behavior from domain calculations."""
    monkeypatch.setattr(analyzer, "get_key_metrics", lambda _module_data: {"stub_metric": 1})
    monkeypatch.setattr(analyzer, "generate_insights", lambda _module_data: [])
    monkeypatch.setattr(analyzer, "_calculate_data_hygiene", lambda *_args: None)
    monkeypatch.setattr(analyzer, "_calculate_changes_summary", lambda *_args: None)


# =============================================================================
# Base Analyzer Tests
# =============================================================================


class ConcreteAnalyzer(ModuleAnalyzer):
    """Concrete implementation of ModuleAnalyzer for testing."""

    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Implement abstract analyze method."""
        return self.create_module_report(
            run_id="test_run",
            stage="test",
            total_records=100,
            records_processed=90,
            records_failed=10,
            duration_seconds=10.0,
            module_metrics={"test_metric": 123},
        )

    def get_key_metrics(self, module_data: dict[str, Any]) -> dict[str, Any]:
        """Implement abstract get_key_metrics method."""
        return {"total": len(module_data)}

    def generate_insights(self, module_data: dict[str, Any]) -> list[AnalysisInsight]:
        """Implement abstract generate_insights method."""
        return []


class TestModuleAnalyzer:
    """Tests for the base ModuleAnalyzer class."""

    def test_initialization(self):
        """Test analyzer initialization with module name and config."""
        analyzer = ConcreteAnalyzer("test_module", {"threshold": 0.5})

        assert analyzer.module_name == "test_module"
        assert analyzer.config == {"threshold": 0.5}
        assert analyzer.insights == []

    def test_initialization_without_config(self):
        """Test analyzer initialization without config."""
        analyzer = ConcreteAnalyzer("test_module")

        assert analyzer.module_name == "test_module"
        assert analyzer.config == {}

    def test_calculate_success_rate_normal(self):
        """Test success rate calculation with normal values."""
        analyzer = ConcreteAnalyzer("test")

        rate = analyzer.calculate_success_rate(80, 100)

        assert rate == 0.8

    def test_calculate_success_rate_zero_total(self):
        """Test success rate calculation with zero total."""
        analyzer = ConcreteAnalyzer("test")

        rate = analyzer.calculate_success_rate(0, 0)

        assert rate == 0.0

    def test_calculate_success_rate_perfect(self):
        """Test success rate calculation with perfect success."""
        analyzer = ConcreteAnalyzer("test")

        rate = analyzer.calculate_success_rate(100, 100)

        assert rate == 1.0

    def test_calculate_coverage_rate_normal(self):
        """Test coverage rate calculation with normal values."""
        analyzer = ConcreteAnalyzer("test")

        rate = analyzer.calculate_coverage_rate(60, 100)

        assert rate == 0.6

    def test_calculate_coverage_rate_zero_total(self):
        """Test coverage rate calculation with zero total."""
        analyzer = ConcreteAnalyzer("test")

        rate = analyzer.calculate_coverage_rate(0, 0)

        assert rate == 0.0

    def test_add_insight(self):
        """Test adding insights to analyzer."""
        analyzer = ConcreteAnalyzer("test")

        insight = AnalysisInsight(
            category="test",
            title="Test Insight",
            message="Test message",
            severity="info",
            confidence=0.9,
            affected_records=10,
            recommendations=["Fix this"],
            metadata={"key": "value"},
        )

        analyzer.add_insight(insight)

        assert len(analyzer.insights) == 1
        assert analyzer.insights[0] == insight

    def test_create_module_report(self):
        """Test creating a standardized module report."""
        analyzer = ConcreteAnalyzer("test_module")

        report = analyzer.create_module_report(
            run_id="run_123",
            stage="extract",
            total_records=1000,
            records_processed=950,
            records_failed=50,
            duration_seconds=30.0,
            module_metrics={"metric1": 100},
        )

        assert isinstance(report, ModuleReport)
        assert report.module_name == "test_module"
        assert report.run_id == "run_123"
        assert report.stage == "extract"
        assert report.total_records == 1000
        assert report.records_processed == 950
        assert report.records_failed == 50
        assert report.success_rate == 0.95
        assert report.duration_seconds == 30.0
        assert report.throughput_records_per_second == 950 / 30.0
        assert report.module_metrics == {"metric1": 100}

    def test_create_module_report_with_zero_duration(self):
        """Test creating report with zero duration."""
        analyzer = ConcreteAnalyzer("test")

        report = analyzer.create_module_report(
            run_id="run_123",
            stage="test",
            total_records=100,
            records_processed=100,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={},
        )

        assert report.throughput_records_per_second == 0.0

    def test_create_module_report_with_hygiene_and_changes(self):
        """Test creating report with data hygiene and changes summary."""
        analyzer = ConcreteAnalyzer("test")

        hygiene = DataHygieneMetrics(
            total_records=100,
            clean_records=80,
            dirty_records=20,
            clean_percentage=80.0,
            quality_score_mean=0.85,
            quality_score_median=0.90,
            quality_score_std=0.10,
            quality_score_min=0.50,
            quality_score_max=1.0,
            validation_pass_rate=0.80,
            validation_errors=20,
            validation_warnings=5,
        )

        changes = ChangesSummary(
            total_records=100,
            records_modified=50,
            records_unchanged=50,
            modification_rate=0.50,
            fields_added=["field1", "field2"],
            fields_modified=["field3"],
            enrichment_sources={"source1": 30, "source2": 20},
        )

        report = analyzer.create_module_report(
            run_id="run_123",
            stage="test",
            total_records=100,
            records_processed=100,
            records_failed=0,
            duration_seconds=10.0,
            module_metrics={},
            data_hygiene=hygiene,
            changes_summary=changes,
        )

        assert report.data_hygiene == hygiene
        assert report.changes_summary == changes

    def test_detect_anomalies_no_anomaly(self):
        """Test anomaly detection with normal values."""
        analyzer = ConcreteAnalyzer("test")

        is_anomaly = analyzer.detect_anomalies(100, 110, threshold=0.2)

        assert is_anomaly is False

    def test_detect_anomalies_with_anomaly(self):
        """Test anomaly detection with anomalous values."""
        analyzer = ConcreteAnalyzer("test")

        is_anomaly = analyzer.detect_anomalies(100, 200, threshold=0.2)

        assert is_anomaly is True

    def test_detect_anomalies_zero_expected(self):
        """Test anomaly detection with zero expected value."""
        analyzer = ConcreteAnalyzer("test")

        is_anomaly = analyzer.detect_anomalies(100, 0, threshold=0.2)

        assert is_anomaly is True  # Any non-zero current is anomaly

    def test_detect_anomalies_both_zero(self):
        """Test anomaly detection with both zero."""
        analyzer = ConcreteAnalyzer("test")

        is_anomaly = analyzer.detect_anomalies(0, 0, threshold=0.2)

        assert is_anomaly is False

    def test_categorize_confidence_high(self):
        """Test confidence categorization for high confidence."""
        analyzer = ConcreteAnalyzer("test")

        category = analyzer.categorize_confidence(0.9)

        assert category == "high"

    def test_categorize_confidence_medium(self):
        """Test confidence categorization for medium confidence."""
        analyzer = ConcreteAnalyzer("test")

        category = analyzer.categorize_confidence(0.7)

        assert category == "medium"

    def test_categorize_confidence_low(self):
        """Test confidence categorization for low confidence."""
        analyzer = ConcreteAnalyzer("test")

        category = analyzer.categorize_confidence(0.3)

        assert category == "low"

    def test_categorize_confidence_boundary_high(self):
        """Test confidence categorization at high boundary."""
        analyzer = ConcreteAnalyzer("test")

        assert analyzer.categorize_confidence(0.8) == "high"
        assert analyzer.categorize_confidence(0.79) == "medium"

    def test_categorize_confidence_boundary_medium(self):
        """Test confidence categorization at medium boundary."""
        analyzer = ConcreteAnalyzer("test")

        assert analyzer.categorize_confidence(0.6) == "medium"
        assert analyzer.categorize_confidence(0.59) == "low"


# =============================================================================
# Shared Analyzer Lifecycle Characterization
# =============================================================================


class TestAnalyzerLifecycleCharacterization:
    """Pin behavior shared by all concrete analyzers before lifecycle consolidation."""

    def test_shared_lifecycle_preserves_calculation_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = SbirEnrichmentAnalyzer()
        calls: list[str] = []
        monkeypatch.setattr(
            analyzer,
            "get_key_metrics",
            lambda _module_data: calls.append("metrics") or {},
        )
        monkeypatch.setattr(
            analyzer,
            "generate_insights",
            lambda _module_data: calls.append("insights") or [],
        )
        monkeypatch.setattr(
            analyzer,
            "_calculate_report_data_hygiene",
            lambda _module_data: calls.append("hygiene") or None,
        )
        monkeypatch.setattr(
            analyzer,
            "_calculate_report_changes_summary",
            lambda _module_data: calls.append("changes") or None,
        )
        monkeypatch.setattr(
            analyzer,
            "_get_total_records",
            lambda _module_data: calls.append("total") or 1,
        )
        monkeypatch.setattr(
            analyzer,
            "_get_processing_metrics",
            lambda _module_data, _total: calls.append("processing") or (1, 0, 0.0),
        )

        analyzer.analyze({"enriched_df": pd.DataFrame({"award_id": [1]})})

        assert calls == ["metrics", "insights", "hygiene", "changes", "total", "processing"]

    def test_missing_primary_data_short_circuits_calculations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        analyzer = SbirEnrichmentAnalyzer()

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("domain calculation should not run without primary data")

        for method_name in (
            "get_key_metrics",
            "generate_insights",
            "_calculate_report_data_hygiene",
            "_calculate_report_changes_summary",
            "_get_total_records",
            "_get_processing_metrics",
        ):
            monkeypatch.setattr(analyzer, method_name, fail_if_called)

        report = analyzer.analyze({"enriched_df": None})

        assert report.module_metrics == {"error": "No enriched DataFrame available"}

    @pytest.mark.parametrize(
        ("analyzer_cls", "primary_key", "module_name", "stage", "error_message"),
        [
            (
                SbirEnrichmentAnalyzer,
                "enriched_df",
                "sbir_enrichment",
                "enrich",
                "No enriched DataFrame available",
            ),
            (
                CetClassificationAnalyzer,
                "classified_df",
                "cet_classification",
                "transform",
                "No classified DataFrame available",
            ),
            (
                PatentAnalysisAnalyzer,
                "patent_df",
                "patent_analysis",
                "load",
                "No patent DataFrame available",
            ),
            (
                TransitionDetectionAnalyzer,
                "transitions_df",
                "transition_detection",
                "detect",
                "No transitions DataFrame available",
            ),
        ],
    )
    def test_missing_primary_data_returns_exact_empty_report(
        self,
        analyzer_cls,
        primary_key: str,
        module_name: str,
        stage: str,
        error_message: str,
    ):
        analyzer = analyzer_cls()

        report = analyzer.analyze(
            {primary_key: None, "run_context": {"run_id": "missing-primary-run"}}
        )

        assert _stable_report_dump(report) == {
            "module_name": module_name,
            "run_id": "missing-primary-run",
            "stage": stage,
            "total_records": 0,
            "records_processed": 0,
            "records_failed": 0,
            "success_rate": 0.0,
            "duration_seconds": 0.0,
            "throughput_records_per_second": 0.0,
            "data_hygiene": None,
            "changes_summary": None,
            "module_metrics": {"error": error_message},
        }

    @pytest.mark.parametrize(
        ("analyzer_cls", "primary_key", "module_name", "stage", "total_records"),
        [
            (SbirEnrichmentAnalyzer, "enriched_df", "sbir_enrichment", "enrich", 1),
            (CetClassificationAnalyzer, "classified_df", "cet_classification", "transform", 1),
            (PatentAnalysisAnalyzer, "patent_df", "patent_analysis", "load", 1),
            (
                TransitionDetectionAnalyzer,
                "transitions_df",
                "transition_detection",
                "detect",
                3,
            ),
        ],
    )
    def test_processing_metrics_default_to_successful_primary_population(
        self,
        monkeypatch: pytest.MonkeyPatch,
        analyzer_cls,
        primary_key: str,
        module_name: str,
        stage: str,
        total_records: int,
    ):
        analyzer = analyzer_cls()
        _stub_domain_analysis(monkeypatch, analyzer)
        module_data = {
            primary_key: pd.DataFrame({"record_id": [1]}),
            "run_context": {"run_id": "defaults-run"},
        }
        if analyzer_cls is TransitionDetectionAnalyzer:
            module_data["awards_df"] = pd.DataFrame({"award_id": [1, 2, 3]})

        report = analyzer.analyze(module_data)

        assert _stable_report_dump(report) == {
            "module_name": module_name,
            "run_id": "defaults-run",
            "stage": stage,
            "total_records": total_records,
            "records_processed": total_records,
            "records_failed": 0,
            "success_rate": 1.0,
            "duration_seconds": 0.0,
            "throughput_records_per_second": 0.0,
            "data_hygiene": None,
            "changes_summary": None,
            "module_metrics": {"stub_metric": 1},
        }

    @pytest.mark.parametrize(
        ("analyzer_cls", "primary_key", "module_name", "stage", "total_records"),
        [
            (SbirEnrichmentAnalyzer, "enriched_df", "sbir_enrichment", "enrich", 0),
            (CetClassificationAnalyzer, "classified_df", "cet_classification", "transform", 0),
            (PatentAnalysisAnalyzer, "patent_df", "patent_analysis", "load", 0),
            (
                TransitionDetectionAnalyzer,
                "transitions_df",
                "transition_detection",
                "detect",
                2,
            ),
        ],
    )
    def test_empty_dataframe_is_analyzed_instead_of_treated_as_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        analyzer_cls,
        primary_key: str,
        module_name: str,
        stage: str,
        total_records: int,
    ):
        analyzer = analyzer_cls()
        _stub_domain_analysis(monkeypatch, analyzer)
        module_data = {
            primary_key: pd.DataFrame({"record_id": pd.Series(dtype=int)}),
            "run_context": {"run_id": "empty-dataframe-run"},
        }
        if analyzer_cls is TransitionDetectionAnalyzer:
            module_data["awards_df"] = pd.DataFrame({"award_id": [1, 2]})

        report = analyzer.analyze(module_data)

        assert _stable_report_dump(report) == {
            "module_name": module_name,
            "run_id": "empty-dataframe-run",
            "stage": stage,
            "total_records": total_records,
            "records_processed": total_records,
            "records_failed": 0,
            "success_rate": 1.0 if total_records else 0.0,
            "duration_seconds": 0.0,
            "throughput_records_per_second": 0.0,
            "data_hygiene": None,
            "changes_summary": None,
            "module_metrics": {"stub_metric": 1},
        }


# =============================================================================
# CET Classification Analyzer Tests
# =============================================================================


class TestCetClassificationAnalyzer:
    """Tests for the CET Classification Analyzer."""

    @pytest.fixture
    def sample_classified_df(self) -> pd.DataFrame:
        """Create sample CET classified DataFrame."""
        return pd.DataFrame(
            {
                "award_id": [1, 2, 3, 4, 5],
                "primary_cet_area": [
                    "artificial_intelligence",
                    "quantum_information_science",
                    "biotechnologies",
                    "artificial_intelligence",
                    None,
                ],
                "classification_confidence": [85, 75, 90, 70, None],
                "classification_evidence": [
                    "Strong AI indicators",
                    "Quantum keywords",
                    "Biotech focus",
                    "AI patterns",
                    None,
                ],
            }
        )

    def test_initialization(self):
        """Test CET analyzer initialization."""
        analyzer = CetClassificationAnalyzer()

        assert analyzer.module_name == "cet_classification"
        assert analyzer.config == {}
        assert "min_classification_rate" in analyzer.thresholds
        assert len(analyzer.cet_areas) > 0

    def test_initialization_with_config(self):
        """Test CET analyzer initialization with custom config."""
        config = {"min_classification_rate": 0.85}
        analyzer = CetClassificationAnalyzer(config)

        assert analyzer.thresholds["min_classification_rate"] == 0.85

    def test_calculate_category_distribution(self, sample_classified_df):
        """Test calculating CET category distribution."""
        analyzer = CetClassificationAnalyzer()

        distribution = analyzer._calculate_category_distribution(sample_classified_df)

        assert "artificial_intelligence" in distribution
        assert distribution["artificial_intelligence"] == 0.4  # 2 out of 5
        assert "quantum_information_science" in distribution
        assert "biotechnologies" in distribution

    def test_calculate_category_distribution_empty(self):
        """Test category distribution with empty DataFrame."""
        analyzer = CetClassificationAnalyzer()
        empty_df = pd.DataFrame()

        distribution = analyzer._calculate_category_distribution(empty_df)

        assert distribution == {}

    def test_calculate_confidence_distribution(self, sample_classified_df):
        """Test calculating confidence score distribution."""
        analyzer = CetClassificationAnalyzer()

        dist = analyzer._calculate_confidence_distribution(sample_classified_df)

        assert "total_records_with_confidence" in dist
        assert dist["total_records_with_confidence"] == 4  # 4 non-null
        assert "average_confidence" in dist
        assert "high_confidence_count" in dist
        assert "medium_confidence_count" in dist
        assert "low_confidence_count" in dist

    def test_calculate_confidence_distribution_no_confidence(self):
        """Test confidence distribution with no confidence data."""
        analyzer = CetClassificationAnalyzer()
        df = pd.DataFrame({"award_id": [1, 2, 3]})

        dist = analyzer._calculate_confidence_distribution(df)

        assert "error" in dist

    def test_get_key_metrics(self, sample_classified_df):
        """Test extracting key metrics from CET classification data."""
        analyzer = CetClassificationAnalyzer()

        module_data = {
            "classified_df": sample_classified_df,
            "classification_results": {
                "classified_records": 4,
                "failed_records": 1,
                "duration_seconds": 5.0,
            },
            "taxonomy_data": {},
        }

        metrics = analyzer.get_key_metrics(module_data)

        assert metrics["total_records"] == 5
        assert "category_distribution" in metrics
        assert "confidence_distribution" in metrics
        assert "taxonomy_coverage" in metrics

    def test_get_key_metrics_no_dataframe(self):
        """Test key metrics with missing DataFrame."""
        analyzer = CetClassificationAnalyzer()

        module_data = {"classified_df": None}

        metrics = analyzer.get_key_metrics(module_data)

        assert "error" in metrics

    def test_generate_insights_low_classification_rate(self, sample_classified_df):
        """Test generating insights for low classification rate."""
        analyzer = CetClassificationAnalyzer()

        module_data = {
            "classified_df": sample_classified_df,
            "classification_results": {
                "classification_rate": 0.70,  # Below threshold
                "unclassified_rate": 0.30,
            },
        }

        insights = analyzer.generate_insights(module_data)

        assert len(insights) > 0
        assert any("classification rate" in i.message.lower() for i in insights)
        assert any(i.severity == "warning" for i in insights)

    def test_analyze_complete_workflow(self, sample_classified_df):
        """Test complete analysis workflow."""
        analyzer = CetClassificationAnalyzer()

        module_data = {
            "classified_df": sample_classified_df,
            "classification_results": {
                "classified_records": 4,
                "failed_records": 1,
                "duration_seconds": 5.0,
            },
            "taxonomy_data": {},
            "run_context": {"run_id": "test_run_123"},
        }

        expected_report = analyzer.create_module_report(
            run_id="test_run_123",
            stage="transform",
            total_records=5,
            records_processed=4,
            records_failed=1,
            duration_seconds=5.0,
            module_metrics=analyzer.get_key_metrics(module_data),
            data_hygiene=analyzer._calculate_data_hygiene(
                sample_classified_df, module_data["classification_results"]
            ),
            changes_summary=analyzer._calculate_changes_summary(
                sample_classified_df, module_data["classification_results"]
            ),
        )

        report = analyzer.analyze(module_data)

        assert isinstance(report, ModuleReport)
        assert report.module_name == "cet_classification"
        assert report.run_id == "test_run_123"
        assert report.total_records == 5
        assert _stable_report_dump(report) == _stable_report_dump(expected_report)

    def test_analyze_with_no_data(self):
        """Test analysis with no data."""
        analyzer = CetClassificationAnalyzer()

        module_data = {"classified_df": None, "run_context": {"run_id": "empty_run"}}

        report = analyzer.analyze(module_data)

        assert report.total_records == 0
        assert "error" in report.module_metrics

    def test_cet_areas_match_canonical_taxonomy(self):
        """Analyzer's CET areas must match the canonical config/cet/taxonomy.yaml.

        Guards against the divergent-taxonomy drift that previously left this
        analyzer with a stale 19-area list using non-canonical ids.
        """
        from pathlib import Path

        import yaml

        taxonomy_path = Path(__file__).parents[4] / "config" / "cet" / "taxonomy.yaml"
        taxonomy = yaml.safe_load(taxonomy_path.read_text())
        canonical_ids = [area["cet_id"] for area in taxonomy["cet_areas"]]

        analyzer = CetClassificationAnalyzer()

        # Ordered comparison: catches membership *and* ordering drift vs the YAML.
        assert analyzer.cet_areas == canonical_ids
        assert len(analyzer.cet_areas) == 21


# =============================================================================
# Patent Analysis Analyzer Tests
# =============================================================================


class TestPatentAnalysisAnalyzer:
    """Tests for the Patent Analysis Analyzer."""

    @pytest.fixture
    def sample_patent_df(self) -> pd.DataFrame:
        """Create sample patent DataFrame."""
        return pd.DataFrame(
            {
                "grant_doc_num": ["123456", "234567", "345678", "456789", "567890"],
                "title": [
                    "AI Method for Pattern Recognition",
                    "Quantum Computing System",
                    "Biotech Diagnostic Tool",
                    "Advanced Materials Process",
                    "Energy Storage Device",
                ],
                "grant_date": pd.to_datetime(
                    ["2020-01-15", "2020-03-20", "2020-06-10", "2020-09-05", "2020-12-12"]
                ),
                "inventor_names": [
                    "Smith, John",
                    "Doe, Jane; Brown, Bob",
                    "Lee, Alice",
                    "Chen, Wei; Kim, Min",
                    "Garcia, Maria",
                ],
                "assignee_names": ["Company A", "Company B", "Company C", "Company D", "Company E"],
                "abstract": ["Abstract 1"] * 5,
                "claims_count": [20, 15, 25, 18, 22],
                "citations_count": [10, 8, 12, 15, 9],
            }
        )

    def test_initialization(self):
        """Test patent analyzer initialization."""
        analyzer = PatentAnalysisAnalyzer()

        assert analyzer.module_name == "patent_analysis"
        assert "min_validation_pass_rate" in analyzer.thresholds
        assert len(analyzer.patent_fields) > 0
        assert len(analyzer.node_types) > 0

    def test_calculate_validation_metrics(self, sample_patent_df):
        """Test calculating patent validation metrics."""
        analyzer = PatentAnalysisAnalyzer()

        validation_results = {"valid_records": 5, "invalid_records": 0}

        metrics = analyzer._calculate_validation_metrics(sample_patent_df, validation_results)

        assert metrics["total_records"] == 5
        assert metrics["valid_records"] == 5
        assert metrics["validation_pass_rate"] == 1.0
        assert "field_validation_rates" in metrics

    def test_calculate_quality_scores(self, sample_patent_df):
        """Test calculating patent quality scores."""
        analyzer = PatentAnalysisAnalyzer()

        quality_metrics = analyzer._calculate_quality_scores(sample_patent_df, {})

        assert "average_quality_score" in quality_metrics
        assert "high_quality_records" in quality_metrics
        assert quality_metrics["total_records"] == 5
        assert 0 <= quality_metrics["average_quality_score"] <= 1.0

    def test_calculate_patent_specific_metrics(self, sample_patent_df):
        """Test calculating patent-specific metrics."""
        analyzer = PatentAnalysisAnalyzer()

        metrics = analyzer._calculate_patent_specific_metrics(sample_patent_df)

        assert "grant_date_range" in metrics
        assert "title_analysis" in metrics
        assert "inventor_analysis" in metrics
        assert "assignee_analysis" in metrics

    def test_get_key_metrics(self, sample_patent_df):
        """Test extracting key patent analysis metrics."""
        analyzer = PatentAnalysisAnalyzer()

        module_data = {
            "patent_df": sample_patent_df,
            "validation_results": {"valid_records": 5, "invalid_records": 0},
            "loading_results": {"nodes_created": 50, "relationships_created": 25},
            "neo4j_stats": {"Patent_nodes": 5},
        }

        metrics = analyzer.get_key_metrics(module_data)

        assert metrics["total_records"] == 5
        assert "validation_metrics" in metrics
        assert "loading_statistics" in metrics
        assert "quality_scores" in metrics
        assert "patent_metrics" in metrics

    def test_generate_insights_low_validation_rate(self, sample_patent_df):
        """Test generating insights for low validation rate."""
        analyzer = PatentAnalysisAnalyzer()

        module_data = {
            "patent_df": sample_patent_df,
            "validation_results": {
                "validation_pass_rate": 0.85,  # Below threshold
                "invalid_records": 15,
            },
            "loading_results": {},
        }

        insights = analyzer.generate_insights(module_data)

        assert len(insights) > 0
        assert any("validation" in i.title.lower() for i in insights)

    def test_analyze_complete_workflow(self, sample_patent_df):
        """Test complete patent analysis workflow."""
        analyzer = PatentAnalysisAnalyzer()

        module_data = {
            "patent_df": sample_patent_df,
            "validation_results": {"valid_records": 5, "invalid_records": 0},
            "loading_results": {"duration_seconds": 10.0},
            "neo4j_stats": {},
            "run_context": {"run_id": "patent_run_123"},
        }

        expected_report = analyzer.create_module_report(
            run_id="patent_run_123",
            stage="load",
            total_records=5,
            records_processed=5,
            records_failed=0,
            duration_seconds=10.0,
            module_metrics=analyzer.get_key_metrics(module_data),
            data_hygiene=analyzer._calculate_data_hygiene(
                sample_patent_df, module_data["validation_results"]
            ),
            changes_summary=analyzer._calculate_changes_summary(
                module_data["loading_results"], module_data["neo4j_stats"]
            ),
        )

        report = analyzer.analyze(module_data)

        assert isinstance(report, ModuleReport)
        assert report.module_name == "patent_analysis"
        assert report.run_id == "patent_run_123"
        assert report.stage == "load"
        assert _stable_report_dump(report) == _stable_report_dump(expected_report)

    def test_analyze_uses_validation_counts_and_loading_duration(self, sample_patent_df):
        """Patent processing counts and duration intentionally come from different sources."""
        analyzer = PatentAnalysisAnalyzer()
        module_data = {
            "patent_df": sample_patent_df,
            "validation_results": {"valid_records": 3, "invalid_records": 2},
            "loading_results": {
                "records_processed": 99,
                "records_failed": 98,
                "duration_seconds": 4.0,
            },
            "neo4j_stats": {},
            "run_context": {"run_id": "patent-split-sources"},
        }

        report = analyzer.analyze(module_data)

        assert report.total_records == 5
        assert report.records_processed == 3
        assert report.records_failed == 2
        assert report.success_rate == 0.6
        assert report.duration_seconds == 4.0
        assert report.throughput_records_per_second == 0.75


# =============================================================================
# SBIR Enrichment Analyzer Tests
# =============================================================================


class TestSbirEnrichmentAnalyzer:
    """Tests for the SBIR Enrichment Analyzer."""

    @pytest.fixture
    def sample_enriched_df(self) -> pd.DataFrame:
        """Create sample enriched SBIR DataFrame."""
        return pd.DataFrame(
            {
                "award_id": [1, 2, 3, 4, 5],
                "naics_code": ["541715", "541330", "541511", "541715", "541330"],
                "recipient_name": ["Company A", "Company B", "Company C", "Company D", "Company E"],
                "enrichment_confidence": [0.95, 0.85, 0.75, 0.90, 0.80],
                "_usaspending_match_method": [
                    "original_data",
                    "usaspending_api",
                    "fuzzy_match",
                    "original_data",
                    "agency_default",
                ],
            }
        )

    @pytest.fixture
    def sample_original_df(self) -> pd.DataFrame:
        """Create sample original SBIR DataFrame."""
        return pd.DataFrame(
            {
                "award_id": [1, 2, 3, 4, 5],
                "recipient_name": ["Company A", "Company B", "Company C", "Company D", "Company E"],
                "naics_code": [None, None, None, "541715", None],
            }
        )

    def test_initialization(self):
        """Test SBIR enrichment analyzer initialization."""
        analyzer = SbirEnrichmentAnalyzer()

        assert analyzer.module_name == "sbir_enrichment"
        assert "min_match_rate" in analyzer.thresholds
        assert len(analyzer.enrichment_fields) > 0
        assert len(analyzer.enrichment_sources) > 0

    def test_calculate_match_rates_by_source(self, sample_enriched_df):
        """Test calculating match rates by enrichment source."""
        analyzer = SbirEnrichmentAnalyzer()

        match_rates = analyzer._calculate_match_rates_by_source(sample_enriched_df)

        assert "original_data" in match_rates
        assert match_rates["original_data"] == 0.4  # 2 out of 5
        assert "usaspending_api" in match_rates
        assert "fuzzy_match" in match_rates

    def test_calculate_field_coverage(self, sample_enriched_df, sample_original_df):
        """Test calculating field coverage metrics."""
        analyzer = SbirEnrichmentAnalyzer()

        coverage = analyzer._calculate_field_coverage(sample_enriched_df, sample_original_df)

        assert "naics_code" in coverage
        assert coverage["naics_code"] == 1.0  # All enriched
        assert "naics_code_improvement" in coverage

    def test_calculate_confidence_distribution(self, sample_enriched_df):
        """Test calculating confidence distribution."""
        analyzer = SbirEnrichmentAnalyzer()

        dist = analyzer._calculate_confidence_distribution(sample_enriched_df)

        assert "high_confidence_count" in dist
        assert "medium_confidence_count" in dist
        assert "average_confidence" in dist
        assert dist["total_records_with_confidence"] == 5

    def test_get_key_metrics(self, sample_enriched_df, sample_original_df):
        """Test extracting key SBIR enrichment metrics."""
        analyzer = SbirEnrichmentAnalyzer()

        module_data = {
            "enriched_df": sample_enriched_df,
            "original_df": sample_original_df,
            "enrichment_metrics": {"overall_match_rate": 0.90},
        }

        metrics = analyzer.get_key_metrics(module_data)

        assert metrics["total_records"] == 5
        assert "match_rates_by_source" in metrics
        assert "field_coverage_metrics" in metrics
        assert "confidence_distribution" in metrics

    def test_generate_insights_low_match_rate(self, sample_enriched_df):
        """Test generating insights for low match rate."""
        analyzer = SbirEnrichmentAnalyzer()

        module_data = {
            "enriched_df": sample_enriched_df,
            "enrichment_metrics": {"overall_match_rate": 0.75},  # Below threshold
        }

        insights = analyzer.generate_insights(module_data)

        assert len(insights) > 0
        assert any("match rate" in i.message.lower() for i in insights)

    def test_analyze_complete_workflow(self, sample_enriched_df, sample_original_df):
        """Test complete SBIR enrichment analysis workflow."""
        analyzer = SbirEnrichmentAnalyzer()

        module_data = {
            "enriched_df": sample_enriched_df,
            "original_df": sample_original_df,
            "enrichment_metrics": {
                "records_processed": 5,
                "records_failed": 0,
                "duration_seconds": 8.0,
            },
            "run_context": {"run_id": "sbir_run_123"},
        }

        expected_report = analyzer.create_module_report(
            run_id="sbir_run_123",
            stage="enrich",
            total_records=5,
            records_processed=5,
            records_failed=0,
            duration_seconds=8.0,
            module_metrics=analyzer.get_key_metrics(module_data),
            data_hygiene=analyzer._calculate_data_hygiene(sample_enriched_df, sample_original_df),
            changes_summary=analyzer._calculate_changes_summary(
                sample_enriched_df, sample_original_df
            ),
        )

        report = analyzer.analyze(module_data)

        assert isinstance(report, ModuleReport)
        assert report.module_name == "sbir_enrichment"
        assert report.stage == "enrich"
        assert _stable_report_dump(report) == _stable_report_dump(expected_report)


# =============================================================================
# Transition Detection Analyzer Tests
# =============================================================================


class TestTransitionDetectionAnalyzer:
    """Tests for the Transition Detection Analyzer."""

    @pytest.fixture
    def sample_transitions_df(self) -> pd.DataFrame:
        """Create sample transitions DataFrame."""
        return pd.DataFrame(
            {
                "award_id": [1, 2, 3, 4, 5],
                "confidence": [0.85, 0.75, 0.90, 0.65, 0.70],
                "agency_score": [0.9, 0.8, 0.85, 0.7, 0.75],
                "timing_score": [0.8, 0.7, 0.9, 0.6, 0.65],
                "competition_score": [0.85, 0.75, 0.88, 0.70, 0.72],
                "patent_score": [0.7, 0.6, 0.8, 0.5, 0.55],
            }
        )

    @pytest.fixture
    def sample_awards_df(self) -> pd.DataFrame:
        """Create sample awards DataFrame."""
        return pd.DataFrame(
            {
                "award_id": list(range(1, 101)),
                "agency": ["DOD"] * 50 + ["NIH"] * 50,
                "amount": [100000] * 100,
            }
        )

    def test_initialization(self):
        """Test transition detection analyzer initialization."""
        analyzer = TransitionDetectionAnalyzer()

        assert analyzer.module_name == "transition_detection"
        assert "min_transition_rate" in analyzer.thresholds
        assert len(analyzer.confidence_bands) > 0
        assert len(analyzer.key_sectors) > 0

    def test_calculate_confidence_distribution(self, sample_transitions_df):
        """Test calculating confidence distribution."""
        analyzer = TransitionDetectionAnalyzer()

        dist = analyzer._calculate_confidence_distribution(sample_transitions_df)

        assert "high_confidence_count" in dist
        assert "likely_confidence_count" in dist
        assert "possible_confidence_count" in dist
        assert "average_confidence" in dist

    def test_calculate_signal_strength_metrics(self, sample_transitions_df):
        """Test calculating signal strength metrics."""
        analyzer = TransitionDetectionAnalyzer()

        metrics = analyzer._calculate_signal_strength_metrics(sample_transitions_df)

        assert "average_signal_strength" in metrics
        assert "median_signal_strength" in metrics
        assert "strong_signals_rate" in metrics
        assert 0 <= metrics["average_signal_strength"] <= 1.0

    def test_calculate_success_story_metrics(self, sample_transitions_df):
        """Test calculating success story metrics."""
        analyzer = TransitionDetectionAnalyzer()

        metrics = analyzer._calculate_success_story_metrics(sample_transitions_df)

        assert "total_transitions" in metrics
        assert "high_impact_transitions" in metrics
        assert "high_impact_rate" in metrics
        assert "average_success_score" in metrics

    def test_get_key_metrics(self, sample_transitions_df, sample_awards_df):
        """Test extracting key transition detection metrics."""
        analyzer = TransitionDetectionAnalyzer()

        module_data = {
            "transitions_df": sample_transitions_df,
            "awards_df": sample_awards_df,
            "detection_results": {"duration_seconds": 15.0},
        }

        metrics = analyzer.get_key_metrics(module_data)

        assert metrics["total_awards"] == 100
        assert metrics["total_transitions"] == 5
        assert "overall_transition_rate" in metrics
        assert "confidence_distribution" in metrics
        assert "signal_strength_metrics" in metrics

    def test_generate_insights_low_transition_rate(self, sample_transitions_df, sample_awards_df):
        """Test generating insights for low transition rate."""
        analyzer = TransitionDetectionAnalyzer()

        module_data = {
            "transitions_df": sample_transitions_df,
            "awards_df": sample_awards_df,
            "detection_results": {},
        }

        insights = analyzer.generate_insights(module_data)

        assert len(insights) > 0
        # With 5 transitions out of 100 awards = 5% rate, should be at threshold

    def test_analyze_complete_workflow(self, sample_transitions_df, sample_awards_df):
        """Test complete transition detection analysis workflow."""
        analyzer = TransitionDetectionAnalyzer()

        module_data = {
            "transitions_df": sample_transitions_df,
            "awards_df": sample_awards_df,
            "detection_results": {
                "awards_processed": 100,
                "detection_failed": 0,
                "duration_seconds": 20.0,
            },
            "run_context": {"run_id": "transition_run_123"},
        }

        expected_report = analyzer.create_module_report(
            run_id="transition_run_123",
            stage="detect",
            total_records=100,
            records_processed=100,
            records_failed=0,
            duration_seconds=20.0,
            module_metrics=analyzer.get_key_metrics(module_data),
            data_hygiene=analyzer._calculate_data_hygiene(sample_transitions_df, sample_awards_df),
            changes_summary=analyzer._calculate_changes_summary(
                sample_transitions_df, sample_awards_df
            ),
        )

        report = analyzer.analyze(module_data)

        assert isinstance(report, ModuleReport)
        assert report.module_name == "transition_detection"
        assert report.stage == "detect"
        assert report.total_records == 100
        assert report.records_processed == 100
        assert report.changes_summary is not None
        assert report.changes_summary.total_records == 100
        assert report.changes_summary.records_modified == 5
        assert report.changes_summary.records_unchanged == 95
        assert report.changes_summary.modification_rate == 0.05
        assert _stable_report_dump(report) == _stable_report_dump(expected_report)
