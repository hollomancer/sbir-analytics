"""OpenAI API client with retry, concurrency control, and token tracking.

Provides a thin wrapper around the OpenAI Chat Completions and Responses
APIs with:

- Exponential-backoff retry on 429 and 5xx errors
- Configurable concurrency semaphore for thread-pool safety
- Token usage logging via loguru

Usage::

    from sbir_etl.enrichers.openai_client import OpenAIClient

    client = OpenAIClient(api_key="sk-...")
    text = client.chat("You are helpful.", "Summarize this award.")

    research = client.web_search("Find info about Acme Corp SBIR recipient")
    if research:
        print(research.summary, research.source_urls)

    client.close()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_DILIGENCE_MODEL = "gpt-4.1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


@dataclass
class WebSearchResult:
    """Result from an OpenAI web search query."""

    summary: str
    source_urls: list[str] = field(default_factory=list)


class OpenAIClient:
    """Synchronous OpenAI API client with retry and concurrency control.

    Args:
        api_key: OpenAI API key.
        max_concurrent: Maximum concurrent requests across threads.
            Controls the semaphore size. Default 4.
        timeout: HTTP request timeout in seconds.
        model: Default model for chat and web search.
    """

    def __init__(
        self,
        api_key: str,
        max_concurrent: int = 4,
        timeout: int = 120,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._semaphore = threading.Semaphore(max_concurrent)
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpenAIClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any],
        timeout: int | None = None,
    ) -> httpx.Response | None:
        """Make an API request with semaphore + retry."""
        effective_timeout = timeout or self._timeout
        model_name = payload.get("model", "unknown")

        for attempt in range(MAX_RETRIES + 1):
            self._semaphore.acquire()
            try:
                resp = self._client.request(
                    method, url, headers=self._headers(), json=payload,
                    timeout=effective_timeout,
                )
            finally:
                self._semaphore.release()

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.debug(
                        f"OpenAI {model_name} returned {resp.status_code}, "
                        f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue

            try:
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                if attempt < MAX_RETRIES:
                    continue
                logger.warning(
                    f"OpenAI API error after {MAX_RETRIES} retries: {resp.status_code}"
                )
                return None

        return None

    def chat(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> str | None:
        """Call the Chat Completions API.

        Args:
            system: System message content.
            user: User message content.
            model: Model override (defaults to client's model).
            temperature: Sampling temperature.

        Returns:
            Assistant message text, or ``None`` on failure.
        """
        payload = {
            "model": model or self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = self._request("POST", OPENAI_CHAT_URL, payload)
        if resp is None:
            return None

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            logger.debug(
                f"OpenAI chat: {len(content)} chars | "
                f"tokens: prompt={usage.get('prompt_tokens', '?')} "
                f"completion={usage.get('completion_tokens', '?')} "
                f"total={usage.get('total_tokens', '?')}"
            )
            return content
        except (KeyError, IndexError) as e:
            logger.warning(f"OpenAI Chat unexpected response: {e}")
            return None

    def web_search(
        self,
        query: str,
        instructions: str | None = None,
        model: str | None = None,
    ) -> WebSearchResult | None:
        """Call the Responses API with web_search_preview tool.

        Args:
            query: The search query / input text.
            instructions: System-level instructions for the search.
            model: Model override.

        Returns:
            :class:`WebSearchResult` with summary and source URLs, or ``None``.
        """
        default_instructions = (
            "You are a research assistant gathering public information about "
            "companies that receive SBIR/STTR federal awards. Provide a concise "
            "2-3 sentence summary covering: what the company does, its size/stage, "
            "notable products or contracts, and any previous SBIR/STTR history. "
            "Cite your sources."
        )
        payload = {
            "model": model or self._model,
            "tools": [{"type": "web_search_preview"}],
            "instructions": instructions or default_instructions,
            "input": query,
        }
        resp = self._request("POST", OPENAI_RESPONSES_URL, payload, timeout=60)
        if resp is None:
            return None

        data = resp.json()
        summary_text = ""
        source_urls: list[str] = []

        for output_item in data.get("output", []):
            if output_item.get("type") == "message":
                for content_block in output_item.get("content", []):
                    if content_block.get("type") == "output_text":
                        summary_text = content_block.get("text", "")
                        for annotation in content_block.get("annotations", []):
                            url = annotation.get("url", "")
                            if url and url not in source_urls:
                                source_urls.append(url)

        if not summary_text:
            return None

        return WebSearchResult(summary=summary_text, source_urls=source_urls)
