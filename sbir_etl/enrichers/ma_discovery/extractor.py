"""Typed snippet extractors for M&A discovery.

Epistemic tier: pipelines. Structured verdict plumbing only — fixture
rankings and any live-model comparison are exploratory and non-citable.

``KeywordExtractor`` adapts the existing ``verify_acquisition`` heuristic.
``LlmExtractor`` asks a chat callable for JSON matching the design schema.
The orchestrator does not default to the LLM path.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition
from sbir_etl.enrichers.openai_client import DEFAULT_MODEL, OpenAIClient


EPISTEMIC_TIER = "pipelines"

UNKNOWN_DATE = "Unknown"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"

EXTRACTOR_SYSTEM_PROMPT = """\
You extract whether a text snippet confirms that one named company was acquired \
by a named acquirer.

Return ONLY a JSON object with this schema:
{
  "confirmed": bool,
  "matched_company": string or null,
  "matched_acquirer": string or null,
  "acquisition_date": "YYYY-MM-DD" or null,
  "value_usd": number or null,
  "citation_url": string or null,
  "reason": string
}

Rules:
- confirmed=true only when the snippet states a completed acquisition, merger, \
or purchase of the target by the acquirer. Legal suffix and letter-case \
differences do not block a match.
- confirmed=false for rumors, talks, approaches, teaming, supplier \
relationships, same-industry news, or a different pair of firms.
- Do not invent a date or value. Use null when the snippet does not state one.
- acquisition_date must be ISO YYYY-MM-DD when a calendar date is present.
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

ChatFn = Callable[[str, str], str | None]


class ChatClient(Protocol):
    """Minimal chat surface implemented by ``OpenAIClient``."""

    def chat(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> str | None: ...


class SnippetExtractor(Protocol):
    """Shared extractor surface for keyword and LLM adapters."""

    def extract(self, item: ExtractionInput) -> ExtractionVerdict: ...


@dataclass(frozen=True)
class ExtractionInput:
    """One snippet to score against a named (company, acquirer) pair."""

    company: str
    acquirer: str
    snippet: str
    source_url: str | None = None


@dataclass(frozen=True)
class ExtractionVerdict:
    """Structured acquisition verdict for one snippet.

    Field names match the design schema plus ``confirmed`` and ``reason``.
    """

    confirmed: bool
    reason: str
    matched_company: str | None = None
    matched_acquirer: str | None = None
    acquisition_date: str | None = None
    value_usd: float | None = None
    citation_url: str | None = None


def is_filled_date(value: str | None) -> bool:
    """True when ``value`` is a real date, not the keyword heuristic's placeholder."""
    if value is None:
        return False
    stripped = value.strip()
    return bool(stripped) and stripped.casefold() != UNKNOWN_DATE.casefold()


def is_filled_value(value: float | None) -> bool:
    """True when a numeric deal value was extracted."""
    return value is not None


def build_user_prompt(item: ExtractionInput) -> str:
    """Render the user message for the structured JSON prompt."""
    url = item.source_url or ""
    return (
        f"Company: {item.company}\n"
        f"Acquirer: {item.acquirer}\n"
        f"Source URL: {url}\n"
        f"Snippet:\n{item.snippet}\n"
    )


def parse_llm_payload(raw: str | None) -> dict[str, Any] | None:
    """Parse a JSON object from a model response, including fenced blocks."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    else:
        obj = _JSON_OBJECT.search(text)
        if obj:
            text = obj.group(0)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def verdict_from_payload(
    payload: dict[str, Any] | None,
    *,
    citation_fallback: str | None = None,
    parse_failure_reason: str = "Unparseable LLM response",
) -> ExtractionVerdict:
    """Map a parsed JSON object onto ``ExtractionVerdict``.

    Missing or malformed payloads are unconfirmed; they are never guessed.
    """
    if payload is None:
        return ExtractionVerdict(confirmed=False, reason=parse_failure_reason)

    confirmed = payload.get("confirmed")
    if not isinstance(confirmed, bool):
        return ExtractionVerdict(
            confirmed=False,
            reason="LLM JSON missing boolean 'confirmed'",
        )

    return ExtractionVerdict(
        confirmed=confirmed,
        reason=_as_optional_str(payload.get("reason")) or "LLM structured verdict",
        matched_company=_as_optional_str(payload.get("matched_company")),
        matched_acquirer=_as_optional_str(payload.get("matched_acquirer")),
        acquisition_date=_parse_iso_date(payload.get("acquisition_date")),
        value_usd=_parse_value_usd(payload.get("value_usd")),
        citation_url=_as_optional_str(payload.get("citation_url")) or citation_fallback,
    )


class KeywordExtractor:
    """Adapter around ``verify_acquisition``. Does not change the heuristic."""

    name = "keyword"

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        result = verify_acquisition(item.company, item.acquirer, item.snippet)
        confirmed = bool(result["confirmed"])
        raw_date = result["date"]
        date = raw_date if is_filled_date(raw_date) else None
        return ExtractionVerdict(
            confirmed=confirmed,
            reason=result["reason"],
            matched_company=item.company if confirmed else None,
            matched_acquirer=item.acquirer if confirmed else None,
            acquisition_date=date,
            value_usd=result["value"],
            citation_url=item.source_url,
        )


class LlmExtractor:
    """JSON-schema extractor over an injected chat callable or ``OpenAIClient``.

    Callers must inject the client. Use ``build_llm_extractor`` when an API
    key is present. Tests inject a mock that returns JSON and never hit the
    network.
    """

    name = "llm"

    def __init__(
        self,
        client: ChatClient | ChatFn,
        *,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._chat = _bind_chat(client, model=model, temperature=temperature)

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        raw = self._chat(EXTRACTOR_SYSTEM_PROMPT, build_user_prompt(item))
        return verdict_from_payload(parse_llm_payload(raw), citation_fallback=item.source_url)


def build_llm_extractor(
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> LlmExtractor | None:
    """Return an ``LlmExtractor`` over ``OpenAIClient`` when a key exists.

    Looks at ``api_key`` then ``OPENAI_API_KEY``. Returns ``None`` otherwise.
    Does not change the orchestrator default.
    """
    key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
    if not key:
        return None
    return LlmExtractor(OpenAIClient(api_key=key), model=model)


def _bind_chat(
    client: ChatClient | ChatFn,
    *,
    model: str,
    temperature: float,
) -> ChatFn:
    chat = getattr(client, "chat", None)
    if callable(chat):

        def _from_client(system: str, user: str) -> str | None:
            return chat(system, user, model=model, temperature=temperature)

        return _from_client
    if callable(client):
        return client
    raise TypeError("LlmExtractor client must be a chat callable or expose chat()")


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _parse_iso_date(value: Any) -> str | None:
    """Accept only canonical ISO ``YYYY-MM-DD``. Invalid dates become null."""
    text = _as_optional_str(value)
    if text is None or not is_filled_date(text):
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    canonical = parsed.isoformat()
    return canonical if canonical == text else None


def _parse_value_usd(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    parsed: float | None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed
