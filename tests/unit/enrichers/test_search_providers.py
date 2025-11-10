"""Unit tests for search provider modules.

Tests for search provider base classes, scoring utilities, and mock provider:
- Base classes: ProviderError, ProviderResult, ProviderResponse
- BaseSearchProvider: Abstract base with utilities (latency, retry, normalization)
- Scoring utilities: URL normalization, text similarity, citation scoring
- Scoring dataclasses: FieldMatchScore, ResultScore
- Metrics: precision@k, recall@k, F1, aggregation
- MockSearxngProvider: Fixture loading, synthesis, latency simulation
"""

import json
import time

import pytest

from src.enrichers.search_providers.base import (
    BaseSearchProvider,
    ProviderError,
    ProviderResponse,
    ProviderResult,
    make_mock_response,
)
from src.enrichers.search_providers.mock_searxng import MockSearxngProvider, make_mock_searxng
from src.enrichers.search_providers.scoring import (
    FieldMatchScore,
    ResultScore,
    domain_of_url,
    f1_from_precision_recall,
    jaccard_similarity,
    normalize_url,
    precision_at_k,
    recall_at_k,
    score_citation,
    score_result_against_truth,
    sequence_similarity,
    text_similarity,
    tokenize_text,
)


pytestmark = pytest.mark.fast


# =============================================================================
# Base Classes Tests
# =============================================================================


class TestProviderError:
    """Tests for ProviderError exception."""

    def test_provider_error_creation(self):
        """Test creating a provider error."""
        error = ProviderError("Test error message")

        assert isinstance(error, RuntimeError)
        assert str(error) == "Test error message"


class TestProviderResult:
    """Tests for ProviderResult dataclass."""

    def test_result_creation_full(self):
        """Test creating a result with all fields."""
        result = ProviderResult(
            title="Test Title",
            snippet="Test snippet text",
            url="https://example.com",
            source="test_provider",
            score=0.95,
            metadata={"rank": 1},
        )

        assert result.title == "Test Title"
        assert result.snippet == "Test snippet text"
        assert result.url == "https://example.com"
        assert result.source == "test_provider"
        assert result.score == 0.95
        assert result.metadata == {"rank": 1}

    def test_result_creation_minimal(self):
        """Test creating a result with minimal fields."""
        result = ProviderResult(title=None, snippet=None, url=None)

        assert result.title is None
        assert result.snippet is None
        assert result.url is None
        assert result.source is None
        assert result.score is None
        assert result.metadata == {}

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ProviderResult(title="Test", snippet="Content", url="https://test.com", score=0.9)

        result_dict = result.to_dict()

        assert result_dict["title"] == "Test"
        assert result_dict["snippet"] == "Content"
        assert result_dict["url"] == "https://test.com"
        assert result_dict["score"] == 0.9


class TestProviderResponse:
    """Tests for ProviderResponse dataclass."""

    def test_response_creation_full(self):
        """Test creating a response with all fields."""
        results = [ProviderResult(title="Test", snippet="Content", url="https://test.com")]
        response = ProviderResponse(
            provider="test",
            query="test query",
            results=results,
            citations=[{"url": "https://cite.com"}],
            raw={"data": "value"},
            latency_ms=150.5,
            cost_usd=0.001,
            metadata={"request_id": "123"},
        )

        assert response.provider == "test"
        assert response.query == "test query"
        assert len(response.results) == 1
        assert response.latency_ms == 150.5
        assert response.cost_usd == 0.001

    def test_response_creation_minimal(self):
        """Test creating a response with minimal fields."""
        response = ProviderResponse(provider="test", query="query", results=[])

        assert response.provider == "test"
        assert response.query == "query"
        assert response.results == []
        assert response.citations == []
        assert response.raw is None
        assert response.latency_ms is None
        assert response.cost_usd is None
        assert response.metadata == {}

    def test_response_to_dict(self):
        """Test converting response to dictionary."""
        results = [ProviderResult(title="Test", snippet="Content", url="https://test.com")]
        response = ProviderResponse(provider="test", query="query", results=results)

        response_dict = response.to_dict()

        assert response_dict["provider"] == "test"
        assert response_dict["query"] == "query"
        assert len(response_dict["results"]) == 1
        assert isinstance(response_dict["results"][0], dict)


# =============================================================================
# BaseSearchProvider Tests
# =============================================================================


class ConcreteProvider(BaseSearchProvider):
    """Concrete implementation for testing."""

    def search(self, query: str, context: dict | None = None) -> ProviderResponse:
        return ProviderResponse(provider=self.name, query=query, results=[])


class TestBaseSearchProvider:
    """Tests for BaseSearchProvider abstract class."""

    def test_initialization_default(self):
        """Test provider initialization with defaults."""
        provider = ConcreteProvider("test_provider")

        assert provider.name == "test_provider"
        assert provider.config == {}
        assert provider.default_timeout == 10.0
        assert provider.max_retries == 3
        assert provider.backoff_base == 2.0

    def test_initialization_with_config(self):
        """Test provider initialization with custom config."""
        config = {"timeout_seconds": 30.0, "max_retries": 5, "backoff_base": 1.5}
        provider = ConcreteProvider("test", config)

        assert provider.default_timeout == 30.0
        assert provider.max_retries == 5
        assert provider.backoff_base == 1.5

    def test_measure_latency(self):
        """Test latency measurement utility."""
        provider = ConcreteProvider("test")

        def slow_function():
            time.sleep(0.01)  # 10ms
            return "result"

        result, latency_ms = provider.measure_latency(slow_function)

        assert result == "result"
        assert latency_ms >= 10.0  # At least 10ms

    def test_backoff_retry_success_first_try(self):
        """Test retry logic succeeds on first try."""
        provider = ConcreteProvider("test")

        def always_succeed():
            return "success"

        result = provider.backoff_retry(always_succeed)

        assert result == "success"

    def test_backoff_retry_success_after_retries(self):
        """Test retry logic succeeds after failures."""
        provider = ConcreteProvider("test")
        attempts = []

        def fail_then_succeed():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("Not yet")
            return "success"

        result = provider.backoff_retry(fail_then_succeed, max_retries=5)

        assert result == "success"
        assert len(attempts) == 3

    def test_backoff_retry_exhausted(self):
        """Test retry logic exhausts all retries."""
        provider = ConcreteProvider("test")

        def always_fail():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            provider.backoff_retry(always_fail, max_retries=2)

    def test_backoff_retry_with_specific_exceptions(self):
        """Test retry only on specific exception types."""
        provider = ConcreteProvider("test")

        def raise_runtime_error():
            raise RuntimeError("Runtime error")

        # Should not retry RuntimeError when only ValueError is retriable
        with pytest.raises(RuntimeError):
            provider.backoff_retry(
                raise_runtime_error, max_retries=3, retriable_exceptions=(ValueError,)
            )

    def test_normalize_snippet_basic(self):
        """Test snippet normalization."""
        snippet = "  Multiple   whitespace   collapse  "

        normalized = BaseSearchProvider.normalize_snippet(snippet)

        assert normalized == "Multiple whitespace collapse"

    def test_normalize_snippet_truncate(self):
        """Test snippet truncation."""
        long_snippet = "a" * 2000

        normalized = BaseSearchProvider.normalize_snippet(long_snippet, max_length=100)

        assert len(normalized) <= 100
        assert normalized.endswith("…")

    def test_normalize_snippet_none(self):
        """Test normalizing None snippet."""
        assert BaseSearchProvider.normalize_snippet(None) is None
        assert BaseSearchProvider.normalize_snippet("") is None

    def test_pick_top_results_by_score(self):
        """Test picking top results by score."""
        results = [
            ProviderResult(title="A", snippet="a", url=None, score=0.9),
            ProviderResult(title="B", snippet="b", url=None, score=0.5),
            ProviderResult(title="C", snippet="c", url=None, score=0.8),
        ]

        top = BaseSearchProvider.pick_top_results(results, top_k=2)

        assert len(top) == 2
        assert top[0].title == "A"  # Highest score
        assert top[1].title == "C"  # Second highest

    def test_pick_top_results_no_scores(self):
        """Test picking top results when no scores present."""
        results = [
            ProviderResult(title="A", snippet="a", url=None),
            ProviderResult(title="B", snippet="b", url=None),
            ProviderResult(title="C", snippet="c", url=None),
        ]

        top = BaseSearchProvider.pick_top_results(results, top_k=2)

        assert len(top) == 2
        assert top[0].title == "A"  # Original order preserved
        assert top[1].title == "B"

    def test_extract_urls_from_results(self):
        """Test extracting URLs from results."""
        results = [
            ProviderResult(title="A", snippet="a", url="https://a.com"),
            ProviderResult(title="B", snippet="b", url=None),
            ProviderResult(title="C", snippet="c", url="https://c.com"),
        ]

        urls = BaseSearchProvider.extract_urls_from_results(results)

        assert urls == ["https://a.com", "https://c.com"]

    def test_estimate_request_cost(self):
        """Test request cost estimation."""
        provider = ConcreteProvider("test", {"unit_cost_usd": 0.005})

        cost = provider.estimate_request_cost()

        assert cost == 0.005


class TestMakeMockResponse:
    """Tests for make_mock_response helper."""

    def test_make_mock_response_basic(self):
        """Test creating a mock response."""
        snippets = ["First result", "Second result"]
        urls = ["https://first.com", "https://second.com"]

        response = make_mock_response("mock", "test query", snippets, urls)

        assert response.provider == "mock"
        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.results[0].snippet == "First result"
        assert response.results[0].url == "https://first.com"

    def test_make_mock_response_no_urls(self):
        """Test creating a mock response without URLs."""
        snippets = ["Result 1", "Result 2"]

        response = make_mock_response("mock", "query", snippets)

        assert len(response.results) == 2
        assert response.results[0].url is None


# =============================================================================
# Scoring Utilities Tests
# =============================================================================


class TestURLUtilities:
    """Tests for URL normalization and domain extraction."""

    def test_normalize_url_basic(self):
        """Test basic URL normalization."""
        url = "HTTPS://EXAMPLE.COM/Path"

        normalized = normalize_url(url)

        assert normalized == "https://example.com/Path"

    def test_normalize_url_strip_query(self):
        """Test URL normalization strips query and fragment."""
        url = "https://example.com/path?query=1#fragment"

        normalized = normalize_url(url)

        assert normalized == "https://example.com/path"

    def test_normalize_url_add_scheme(self):
        """Test URL normalization adds missing scheme."""
        url = "example.com/path"

        normalized = normalize_url(url)

        assert normalized == "http://example.com/path"

    def test_normalize_url_none(self):
        """Test normalizing None URL."""
        assert normalize_url(None) is None
        assert normalize_url("") is None

    def test_domain_of_url(self):
        """Test extracting domain from URL."""
        url = "https://www.example.com/path"

        domain = domain_of_url(url)

        assert domain == "www.example.com"

    def test_domain_of_url_none(self):
        """Test domain extraction from None."""
        assert domain_of_url(None) is None


class TestTextUtilities:
    """Tests for text tokenization and similarity."""

    def test_tokenize_text_basic(self):
        """Test basic text tokenization."""
        text = "Hello world! This is a test."

        tokens = tokenize_text(text)

        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_tokenize_text_filters_short(self):
        """Test tokenization filters short tokens."""
        text = "a ab abc"

        tokens = tokenize_text(text)

        assert "a" not in tokens  # Too short
        assert "ab" in tokens
        assert "abc" in tokens

    def test_tokenize_text_none(self):
        """Test tokenizing None."""
        assert tokenize_text(None) == []

    def test_jaccard_similarity_identical(self):
        """Test Jaccard similarity for identical sets."""
        a = ["hello", "world"]
        b = ["hello", "world"]

        sim = jaccard_similarity(a, b)

        assert sim == 1.0

    def test_jaccard_similarity_disjoint(self):
        """Test Jaccard similarity for disjoint sets."""
        a = ["hello", "world"]
        b = ["foo", "bar"]

        sim = jaccard_similarity(a, b)

        assert sim == 0.0

    def test_jaccard_similarity_partial(self):
        """Test Jaccard similarity for partial overlap."""
        a = ["hello", "world", "test"]
        b = ["hello", "foo", "bar"]

        sim = jaccard_similarity(a, b)

        assert 0.0 < sim < 1.0  # Partial overlap

    def test_sequence_similarity_identical(self):
        """Test sequence similarity for identical strings."""
        sim = sequence_similarity("hello world", "hello world")

        assert sim == 1.0

    def test_sequence_similarity_different(self):
        """Test sequence similarity for different strings."""
        sim = sequence_similarity("hello", "world")

        assert sim < 0.5

    def test_text_similarity_identical(self):
        """Test combined text similarity for identical texts."""
        sim = text_similarity("hello world test", "hello world test")

        assert sim == 1.0

    def test_text_similarity_both_empty(self):
        """Test text similarity for empty strings."""
        sim = text_similarity("", "")

        assert sim == 1.0

    def test_text_similarity_one_empty(self):
        """Test text similarity when one string is empty."""
        sim = text_similarity("hello", "")

        assert sim == 0.0


# =============================================================================
# Scoring Dataclasses Tests
# =============================================================================


class TestFieldMatchScore:
    """Tests for FieldMatchScore dataclass."""

    def test_field_match_score_creation(self):
        """Test creating a field match score."""
        score = FieldMatchScore(
            field="name", truth="Acme Corp", candidate="Acme Corporation", similarity=0.85
        )

        assert score.field == "name"
        assert score.truth == "Acme Corp"
        assert score.candidate == "Acme Corporation"
        assert score.similarity == 0.85


class TestResultScore:
    """Tests for ResultScore dataclass."""

    def test_result_score_creation(self):
        """Test creating a result score."""
        field_scores = [FieldMatchScore("name", "Acme", "Acme Corp", 0.9)]
        score = ResultScore(
            provider="test",
            query="acme",
            rank=1,
            url="https://acme.com",
            title="Acme Corporation",
            snippet="Leader in widgets",
            text_similarity=0.85,
            field_scores=field_scores,
            citation_score=1.0,
            latency_ms=50.0,
        )

        assert score.provider == "test"
        assert score.rank == 1
        assert score.text_similarity == 0.85
        assert score.citation_score == 1.0

    def test_result_score_to_dict(self):
        """Test converting result score to dictionary."""
        field_scores = [FieldMatchScore("name", "A", "B", 0.5)]
        score = ResultScore(
            provider="test",
            query="q",
            rank=1,
            url="https://test.com",
            title="Test",
            snippet="Snippet",
            text_similarity=0.7,
            field_scores=field_scores,
            citation_score=0.8,
        )

        score_dict = score.to_dict()

        assert score_dict["provider"] == "test"
        assert score_dict["rank"] == 1
        assert isinstance(score_dict["field_scores"], list)
        assert isinstance(score_dict["field_scores"][0], dict)


# =============================================================================
# Citation and Result Scoring Tests
# =============================================================================


class TestScoreCitation:
    """Tests for citation scoring."""

    def test_score_citation_exact_match(self):
        """Test citation scoring for exact URL match."""
        score = score_citation("https://example.com/path", "https://example.com/path")

        assert score == 1.0

    def test_score_citation_same_domain(self):
        """Test citation scoring for same domain."""
        score = score_citation("https://example.com/path1", "https://example.com/path2")

        assert score == 0.8

    def test_score_citation_different_domain(self):
        """Test citation scoring for different domains."""
        score = score_citation("https://example.com", "https://other.com")

        assert score == 0.0

    def test_score_citation_none_truth(self):
        """Test citation scoring with None truth URL."""
        score = score_citation("https://example.com", None)

        assert score == 0.0


class TestScoreResultAgainstTruth:
    """Tests for scoring results against truth."""

    def test_score_result_basic(self):
        """Test basic result scoring."""
        result = ProviderResult(
            title="Acme Corporation", snippet="Leading widget manufacturer", url="https://acme.com"
        )
        truth = {"name": "Acme Corp", "website": "https://acme.com"}

        score = score_result_against_truth(result, truth)

        assert score.text_similarity > 0.0
        assert score.citation_score == 1.0  # Exact website match


# =============================================================================
# Metrics Tests
# =============================================================================


class TestPrecisionRecallMetrics:
    """Tests for precision and recall metrics."""

    def test_precision_at_k_all_positive(self):
        """Test precision@k when all results are positive."""
        results = [
            ResultScore(
                "test",
                "q",
                1,
                None,
                "T1",
                "S1",
                text_similarity=0.8,
                field_scores=[],
                citation_score=0.6,
            ),
            ResultScore(
                "test",
                "q",
                2,
                None,
                "T2",
                "S2",
                text_similarity=0.9,
                field_scores=[],
                citation_score=0.7,
            ),
        ]

        precision = precision_at_k(results, k=2, threshold=0.5)

        assert precision == 1.0

    def test_precision_at_k_partial(self):
        """Test precision@k with partial positive results."""
        results = [
            ResultScore(
                "test",
                "q",
                1,
                None,
                "T1",
                "S1",
                text_similarity=0.8,
                field_scores=[],
                citation_score=0.0,
            ),
            ResultScore(
                "test",
                "q",
                2,
                None,
                "T2",
                "S2",
                text_similarity=0.2,
                field_scores=[],
                citation_score=0.0,
            ),
        ]

        precision = precision_at_k(results, k=2, threshold=0.5)

        assert precision == 0.5

    def test_recall_at_k_found(self):
        """Test recall@k when target is found."""
        results = [
            ResultScore(
                "test",
                "q",
                1,
                None,
                "T1",
                "S1",
                text_similarity=0.8,
                field_scores=[],
                citation_score=0.0,
            ),
        ]

        recall = recall_at_k(results, k=1, threshold=0.5)

        assert recall == 1.0

    def test_recall_at_k_not_found(self):
        """Test recall@k when target is not found."""
        results = [
            ResultScore(
                "test",
                "q",
                1,
                None,
                "T1",
                "S1",
                text_similarity=0.2,
                field_scores=[],
                citation_score=0.0,
            ),
        ]

        recall = recall_at_k(results, k=1, threshold=0.5)

        assert recall == 0.0

    def test_f1_from_precision_recall(self):
        """Test F1 score calculation."""
        f1 = f1_from_precision_recall(0.8, 0.6)

        assert 0.6 < f1 < 0.8  # Harmonic mean


# =============================================================================
# MockSearxngProvider Tests
# =============================================================================


class TestMockSearxngProvider:
    """Tests for MockSearxngProvider."""

    def test_initialization_defaults(self):
        """Test mock provider initialization with defaults."""
        provider = MockSearxngProvider()

        assert provider.name == "searxng-mock"
        assert provider.config["result_count"] == 5
        assert provider.config["simulated_latency_ms"] == 20.0

    def test_initialization_custom_config(self):
        """Test mock provider initialization with custom config."""
        config = {"result_count": 3, "simulated_latency_ms": 50.0, "seed": 42}
        provider = MockSearxngProvider(config=config)

        assert provider.config["result_count"] == 3
        assert provider.config["simulated_latency_ms"] == 50.0

    def test_search_synthesize_results(self):
        """Test search with synthesized results."""
        provider = MockSearxngProvider(config={"result_count": 3, "seed": 42})

        response = provider.search("test query")

        assert response.provider == "searxng-mock"
        assert response.query == "test query"
        assert len(response.results) == 3
        assert all("test query" in r.snippet.lower() for r in response.results)

    def test_search_latency_simulation(self):
        """Test search simulates latency."""
        provider = MockSearxngProvider(config={"simulated_latency_ms": 10.0, "jitter_ms": 0.0})

        start = time.time()
        response = provider.search("query")
        elapsed_ms = (time.time() - start) * 1000.0

        assert elapsed_ms >= 10.0
        assert response.latency_ms >= 10.0

    def test_search_with_fixture(self, tmp_path):
        """Test search with fixture file."""
        fixture_data = [
            {"title": "Result 1", "snippet": "Test snippet 1", "url": "https://test1.com"},
            {"title": "Result 2", "snippet": "Test snippet 2", "url": "https://test2.com"},
        ]
        fixture_path = tmp_path / "fixture.json"
        with fixture_path.open("w") as f:
            json.dump(fixture_data, f)

        provider = MockSearxngProvider(
            config={"fixture_path": str(fixture_path), "result_count": 2}
        )

        response = provider.search("query")

        assert len(response.results) <= 2
        assert response.metadata["fixture_used"] is True

    def test_make_mock_searxng_factory(self):
        """Test factory function."""
        provider = make_mock_searxng({"result_count": 2})

        assert isinstance(provider, MockSearxngProvider)
        assert provider.config["result_count"] == 2
