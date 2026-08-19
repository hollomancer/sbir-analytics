"""M&A discovery toolkit: query generation, verification, and press merge.

Epistemic tier: pipelines. Relocated from the paused #371 scripts.
Search backends are pluggable via ``SearchTool``; the LLM extractor is
still out of scope.
"""

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
    "MockSearchTool",
    "SearchTool",
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
