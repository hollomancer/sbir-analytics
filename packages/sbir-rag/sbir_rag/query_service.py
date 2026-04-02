"""Semantic search and natural language query interface over SBIR data.

Wraps LightRAG's four retrieval modes into a domain-specific service:

- **naive**: Pure vector similarity search (fastest, no graph context)
- **local**: Entity-centric retrieval with neighborhood context
- **global**: Community-based thematic summarization
- **hybrid**: Combined local + global (recommended default)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from sbir_rag.config import LightRAGConfig


class SBIRQueryService:
    """Semantic search and NL query interface over SBIR awards.

    Provides four retrieval modes that map directly to LightRAG's
    internal modes, with SBIR-specific result formatting.

    Args:
        config: LightRAG configuration.
    """

    def __init__(self, config: LightRAGConfig):
        self._config = config
        self._rag = None

    async def _get_rag(self):
        """Lazily create the LightRAG instance."""
        if self._rag is None:
            from sbir_rag.factory import create_lightrag_instance

            self._rag = await create_lightrag_instance(self._config)
        return self._rag

    async def semantic_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Vector-only similarity search (naive mode).

        Fastest mode — returns documents ranked by embedding similarity
        without graph context.  Good for finding specific awards matching
        a technical query.

        Args:
            query: Natural language search query.
            top_k: Number of results (defaults to config.retrieval_top_k).

        Returns:
            List of result dicts with content and metadata.
        """
        rag = await self._get_rag()
        top_k = top_k or self._config.retrieval_top_k

        result = await rag.aquery(
            query,
            param={"mode": "naive", "top_k": top_k},
        )

        return self._format_results(result, mode="naive")

    async def entity_neighborhood(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Entity-centric retrieval with graph context (local mode).

        Finds relevant entities and traverses their graph neighborhood
        to provide rich context about related awards, companies, and
        technologies.

        Args:
            query: Natural language search query.
            top_k: Number of results.

        Returns:
            List of result dicts with entity context.
        """
        rag = await self._get_rag()
        top_k = top_k or self._config.retrieval_top_k

        result = await rag.aquery(
            query,
            param={"mode": "local", "top_k": top_k},
        )

        return self._format_results(result, mode="local")

    async def thematic_summary(self, query: str) -> str:
        """Community-based thematic summarization (global mode).

        Uses Leiden community summaries to produce a high-level thematic
        overview.  Best for broad questions like "what are the main
        research themes in quantum computing SBIR awards?"

        Args:
            query: Natural language query.

        Returns:
            Synthesized thematic summary string.
        """
        rag = await self._get_rag()

        result = await rag.aquery(
            query,
            param={"mode": "global"},
        )

        # Global mode returns a synthesized text summary
        if isinstance(result, str):
            return result
        return str(result)

    async def hybrid_query(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Combined local + global retrieval (hybrid mode).

        Recommended default — combines entity-level precision with
        community-level thematic context.

        Args:
            query: Natural language query.
            top_k: Number of results for the local component.

        Returns:
            Dict with both local results and global summary.
        """
        rag = await self._get_rag()
        top_k = top_k or self._config.retrieval_top_k

        result = await rag.aquery(
            query,
            param={"mode": "hybrid", "top_k": top_k},
        )

        return {
            "mode": "hybrid",
            "query": query,
            "result": result if isinstance(result, str) else str(result),
        }

    async def query(
        self,
        query: str,
        *,
        mode: str | None = None,
        top_k: int | None = None,
    ) -> Any:
        """Unified query entry point that dispatches to the appropriate mode.

        Args:
            query: Natural language search query.
            mode: Retrieval mode (naive, local, global, hybrid).
                  Defaults to config.default_retrieval_mode.
            top_k: Number of results.

        Returns:
            Results in the format of the selected mode.
        """
        mode = mode or self._config.default_retrieval_mode

        dispatch = {
            "naive": lambda: self.semantic_search(query, top_k=top_k),
            "local": lambda: self.entity_neighborhood(query, top_k=top_k),
            "global": lambda: self.thematic_summary(query),
            "hybrid": lambda: self.hybrid_query(query, top_k=top_k),
        }

        handler = dispatch.get(mode)
        if handler is None:
            raise ValueError(
                f"Unknown retrieval mode: {mode!r}. "
                f"Must be one of: {', '.join(dispatch)}"
            )

        logger.debug(f"RAG query mode={mode} top_k={top_k}: {query[:100]}")
        return await handler()

    @staticmethod
    def _format_results(
        result: Any,
        *,
        mode: str,
    ) -> list[dict[str, Any]]:
        """Format LightRAG results into a consistent list of dicts."""
        if isinstance(result, str):
            return [{"content": result, "mode": mode}]
        if isinstance(result, list):
            return [
                {"content": item, "mode": mode} if isinstance(item, str)
                else {**item, "mode": mode} if isinstance(item, dict)
                else {"content": str(item), "mode": mode}
                for item in result
            ]
        return [{"content": str(result), "mode": mode}]
