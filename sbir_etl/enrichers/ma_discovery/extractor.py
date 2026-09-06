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
from pathlib import Path
from typing import Any, Protocol

from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition
from sbir_etl.enrichers.openai_client import OpenAIClient
from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "pipelines"

UNKNOWN_DATE = "Unknown"
XAI_API_KEY_ENV = "XAI_API_KEY"
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_XAI_MODEL = "grok-4.6"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_GROK_MODEL = "x-ai/grok-4.6"
OPENROUTER_KEY_PREFIX = "sk-or-"

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
        max_tokens: int | None = None,
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


def pair_names_match(requested: str | None, returned: str | None) -> bool:
    """True when both names normalize equal under ``RECIPIENT_V1``.

    Empty normalization on either side is a mismatch. Legal-suffix and case
    differences are ignored so extractor and query generator share identity.
    """
    left = normalize_company_name(requested or "", profile=CompanyNameProfile.RECIPIENT_V1)
    right = normalize_company_name(returned or "", profile=CompanyNameProfile.RECIPIENT_V1)
    return bool(left) and bool(right) and left == right


def verdict_from_payload(
    payload: dict[str, Any] | None,
    *,
    item: ExtractionInput,
    parse_failure_reason: str = "Unparseable LLM response",
) -> ExtractionVerdict:
    """Map a parsed JSON object onto ``ExtractionVerdict``.

    Missing or malformed payloads are unconfirmed; they are never guessed.
    ``confirmed=true`` fails closed unless both returned names match ``item``
    under ``RECIPIENT_V1``. ``item.source_url`` is the citation; the model
    cannot replace it.
    """
    if payload is None:
        return ExtractionVerdict(confirmed=False, reason=parse_failure_reason)

    confirmed = payload.get("confirmed")
    if not isinstance(confirmed, bool):
        return ExtractionVerdict(
            confirmed=False,
            reason="LLM JSON missing boolean 'confirmed'",
        )

    matched_company = _as_optional_str(payload.get("matched_company"))
    matched_acquirer = _as_optional_str(payload.get("matched_acquirer"))
    reason = _as_optional_str(payload.get("reason")) or "LLM structured verdict"
    if confirmed and (
        not pair_names_match(item.company, matched_company)
        or not pair_names_match(item.acquirer, matched_acquirer)
    ):
        confirmed = False
        reason = "LLM pair does not match requested company/acquirer"

    return ExtractionVerdict(
        confirmed=confirmed,
        reason=reason,
        matched_company=matched_company,
        matched_acquirer=matched_acquirer,
        acquisition_date=_parse_iso_date(payload.get("acquisition_date")),
        value_usd=_parse_value_usd(payload.get("value_usd")),
        citation_url=item.source_url,
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


def _response_key(item: ExtractionInput) -> tuple[str, str, str]:
    return (item.company, item.acquirer, item.source_url or "")


class FrozenLlmExtractor:
    """Replay frozen chat responses. No network.

    JSONL rows: ``company``, ``acquirer``, ``source_url``, ``raw_response``.
    Missing rows are unconfirmed.
    """

    name = "frozen_llm"

    def __init__(self, path: Path) -> None:
        self.path = path
        self._raw: dict[tuple[str, str, str], str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            key = (
                str(record.get("company") or ""),
                str(record.get("acquirer") or ""),
                str(record.get("source_url") or ""),
            )
            raw = record.get("raw_response")
            if isinstance(raw, str) and raw:
                self._raw[key] = raw

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        raw = self._raw.get(_response_key(item))
        if raw is None:
            return ExtractionVerdict(
                confirmed=False,
                reason="No frozen LLM response for this snippet",
            )
        return verdict_from_payload(parse_llm_payload(raw), item=item)


class RecordingLlmExtractor:
    """Wrap ``LlmExtractor``, append frozen responses, and resume from ``path``."""

    name = "recording_llm"

    def __init__(
        self,
        inner: LlmExtractor,
        sink: list[dict[str, Any]],
        *,
        path: Path | None = None,
    ) -> None:
        self.inner = inner
        self._sink = sink
        self._path = path
        self._seen: dict[tuple[str, str, str], str | None] = {}
        if path is not None and path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                key = (
                    str(record.get("company") or ""),
                    str(record.get("acquirer") or ""),
                    str(record.get("source_url") or ""),
                )
                raw = record.get("raw_response")
                self._seen[key] = raw if isinstance(raw, str) else None
                self._sink.append(record)

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        key = _response_key(item)
        raw = self._seen.get(key)
        if isinstance(raw, str) and raw.strip():
            return verdict_from_payload(parse_llm_payload(raw), item=item)
        raw = self.inner._chat(EXTRACTOR_SYSTEM_PROMPT, build_user_prompt(item))
        record = {
            "company": item.company,
            "acquirer": item.acquirer,
            "source_url": item.source_url,
            "snippet": item.snippet,
            "model": self.inner.model,
            "raw_response": raw,
        }
        self._sink.append(record)
        self._seen[key] = raw
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        return verdict_from_payload(parse_llm_payload(raw), item=item)


class LlmExtractor:
    """JSON-schema extractor over an injected chat callable or xAI chat.

    Callers must inject the client. Use ``build_llm_extractor`` when
    ``OPENROUTER_API_KEY`` or ``XAI_API_KEY`` is present. Tests inject a
    mock that returns JSON and never hit the network.
    """

    name = "llm"

    def __init__(
        self,
        client: ChatClient | ChatFn,
        *,
        model: str = DEFAULT_XAI_MODEL,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._chat = _bind_chat(client, model=model, temperature=temperature)

    def extract(self, item: ExtractionInput) -> ExtractionVerdict:
        raw = self._chat(EXTRACTOR_SYSTEM_PROMPT, build_user_prompt(item))
        return verdict_from_payload(parse_llm_payload(raw), item=item)


def build_llm_extractor(
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LlmExtractor | None:
    """Return an ``LlmExtractor`` over OpenRouter or xAI chat when a key exists.

    Prefers ``api_key``, then ``OPENROUTER_API_KEY``, then ``XAI_API_KEY``.
    Keys starting with ``sk-or-`` use OpenRouter and model ``x-ai/grok-4.6``.
    Direct xAI keys use ``grok-4.6``. Does not change the orchestrator default.
    """
    key = (
        (api_key.strip() if isinstance(api_key, str) and api_key.strip() else "")
        or (os.environ.get(OPENROUTER_API_KEY_ENV) or "").strip()
        or (os.environ.get(XAI_API_KEY_ENV) or "").strip()
    )
    if not key:
        return None
    if key.startswith(OPENROUTER_KEY_PREFIX):
        chosen_model = model or OPENROUTER_GROK_MODEL
        client = OpenAIClient(
            api_key=key,
            model=chosen_model,
            timeout=300,
            chat_url=OPENROUTER_CHAT_URL,
            extra_headers={
                "HTTP-Referer": "https://github.com/hollomancer/sbir-analytics",
                "X-Title": "sbir-analytics ma-discovery",
            },
        )
        return LlmExtractor(client, model=chosen_model)
    chosen_model = model or DEFAULT_XAI_MODEL
    client = OpenAIClient(
        api_key=key,
        model=chosen_model,
        chat_url=XAI_CHAT_URL,
    )
    return LlmExtractor(client, model=chosen_model)


def _bind_chat(
    client: ChatClient | ChatFn,
    *,
    model: str,
    temperature: float,
) -> ChatFn:
    chat = getattr(client, "chat", None)
    if callable(chat):

        def _from_client(system: str, user: str) -> str | None:
            return chat(
                system,
                user,
                model=model,
                temperature=temperature,
                max_tokens=2048,
            )

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
