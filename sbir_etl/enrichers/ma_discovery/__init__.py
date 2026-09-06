"""M&A discovery toolkit: query generation, verification, and press merge.

Epistemic tier: pipelines. Relocated from the paused #371 scripts.
Search backends are pluggable via ``SearchTool``. A typed snippet extractor
contract exists with a keyword adapter; the orchestrator still defaults to
``verify_acquisition``. The LLM extractor is exploratory tier and lives in
``llm_extractor.py``; import it from there, it is not re-exported here.
"""

from sbir_etl.enrichers.ma_discovery.extractor import (
    ExtractionInput,
    ExtractionVerdict,
    KeywordExtractor,
    SnippetExtractor,
)
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.press import enrich_ma_events, merge_press_signals
from sbir_etl.enrichers.ma_discovery.queries import generate_queries, query_rows_from_events
from sbir_etl.enrichers.ma_discovery.search import (
    BraveSearchTool,
    MockSearchTool,
    SearchTool,
    TavilySearchTool,
    build_search_tool,
)
from sbir_etl.enrichers.ma_discovery.verifier import VerificationResult, verify_acquisition


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "EPISTEMIC_TIER",
    "BraveSearchTool",
    "ExtractionInput",
    "ExtractionVerdict",
    "KeywordExtractor",
    "MockSearchTool",
    "SearchTool",
    "SnippetExtractor",
    "TavilySearchTool",
    "VerificationResult",
    "build_search_tool",
    "enrich_ma_events",
    "generate_queries",
    "merge_press_signals",
    "process_batch",
    "query_rows_from_events",
    "verify_acquisition",
]
