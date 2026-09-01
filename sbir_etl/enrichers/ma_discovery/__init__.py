"""M&A discovery toolkit: query generation, verification, and press merge.

Epistemic tier: pipelines. Relocated from the paused #371 scripts.
Search backends are pluggable via ``SearchTool``. A typed snippet extractor
exists (keyword adapter plus optional LLM JSON client); the orchestrator
still defaults to ``verify_acquisition``.
"""

from sbir_etl.enrichers.ma_discovery.collision import CollisionResult, apply_c3
from sbir_etl.enrichers.ma_discovery.confidence import assign_confidence
from sbir_etl.enrichers.ma_discovery.extractor import (
    ExtractionInput,
    ExtractionVerdict,
    FrozenLlmExtractor,
    KeywordExtractor,
    LlmExtractor,
    RecordingLlmExtractor,
    SnippetExtractor,
    build_llm_extractor,
    pair_names_match,
)
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.press import enrich_ma_events, merge_press_signals
from sbir_etl.enrichers.ma_discovery.queries import generate_queries, query_rows_from_events
from sbir_etl.enrichers.ma_discovery.search import (
    BraveSearchTool,
    MockSearchTool,
    SearchTool,
    SnippetSearchTool,
    TavilySearchTool,
    build_search_tool,
)
from sbir_etl.enrichers.ma_discovery.verifier import VerificationResult, verify_acquisition


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "EPISTEMIC_TIER",
    "BraveSearchTool",
    "CollisionResult",
    "ExtractionInput",
    "ExtractionVerdict",
    "FrozenLlmExtractor",
    "KeywordExtractor",
    "LlmExtractor",
    "RecordingLlmExtractor",
    "MockSearchTool",
    "SearchTool",
    "SnippetExtractor",
    "SnippetSearchTool",
    "TavilySearchTool",
    "VerificationResult",
    "apply_c3",
    "assign_confidence",
    "build_llm_extractor",
    "build_search_tool",
    "pair_names_match",
    "enrich_ma_events",
    "generate_queries",
    "merge_press_signals",
    "process_batch",
    "query_rows_from_events",
    "verify_acquisition",
]
