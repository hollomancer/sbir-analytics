"""Tests for keyword and LLM snippet extractors.

The keyword cases that fail are the eval, not bugs to "fix" here.
LLM tests inject a mock chat callable and never call a network API.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sbir_etl.enrichers.ma_discovery.extractor import (
    EXTRACTOR_SYSTEM_PROMPT,
    ExtractionInput,
    KeywordExtractor,
    LlmExtractor,
    build_llm_extractor,
    build_user_prompt,
    verdict_from_payload,
)
from sbir_etl.enrichers.ma_discovery.extractor_eval import load_fixtures


pytestmark = pytest.mark.fast


def _by_id():
    return {item.id: item for item in load_fixtures()}


def _extract(extractor, fixture):
    return extractor.extract(fixture.as_input())


def test_keyword_confirms_slam_dunk_names_and_verb() -> None:
    fixture = _by_id()["slam_dunk_date_value"]
    verdict = _extract(KeywordExtractor(), fixture)
    assert verdict.confirmed is True
    assert verdict.acquisition_date is None  # heuristic cannot fill a date
    assert verdict.value_usd is None
    assert verdict.matched_company == fixture.company
    assert verdict.citation_url == fixture.source_url


def test_keyword_rejects_same_industry_negative() -> None:
    verdict = _extract(KeywordExtractor(), _by_id()["negative_same_industry"])
    assert verdict.confirmed is False
    assert verdict.matched_company is None


def test_keyword_false_positive_on_exploring_merger() -> None:
    """Keyword treats substring 'merger' as confirmation even for talks-only."""
    verdict = _extract(KeywordExtractor(), _by_id()["rumor_exploring_merger"])
    assert verdict.confirmed is True


def test_keyword_false_positive_on_potential_acquisition() -> None:
    verdict = _extract(KeywordExtractor(), _by_id()["rumor_potential_acquisition"])
    assert verdict.confirmed is True


def test_keyword_misses_suffix_stripped_names() -> None:
    """Query names keep Inc/LLC; snippet does not, so substring match fails."""
    verdict = _extract(KeywordExtractor(), _by_id()["suffix_mismatch"])
    assert verdict.confirmed is False


def test_keyword_case_fold_still_confirms() -> None:
    verdict = _extract(KeywordExtractor(), _by_id()["case_variant"])
    assert verdict.confirmed is True


def test_keyword_talks_to_acquire_escapes_the_verb_list() -> None:
    """'acquire' is not in the keyword list; this rumor is a true negative."""
    verdict = _extract(KeywordExtractor(), _by_id()["rumor_talks_to_acquire"])
    assert verdict.confirmed is False


def test_llm_parses_schema_from_plain_json() -> None:
    payload = {
        "confirmed": True,
        "matched_company": "Aether Photonics",
        "matched_acquirer": "Helios Defense",
        "acquisition_date": "2024-03-12",
        "value_usd": 42_000_000,
        "citation_url": "https://example.com/press/helios-aether-2024",
        "reason": "Press release states a completed acquisition.",
    }
    extractor = LlmExtractor(lambda _system, _user: json.dumps(payload))
    verdict = extractor.extract(
        ExtractionInput(
            company="Aether Photonics",
            acquirer="Helios Defense",
            snippet="Helios Defense acquired Aether Photonics.",
            source_url="https://example.com/unused",
        )
    )
    assert verdict.confirmed is True
    assert verdict.matched_company == "Aether Photonics"
    assert verdict.matched_acquirer == "Helios Defense"
    assert verdict.acquisition_date == "2024-03-12"
    assert verdict.value_usd == 42_000_000
    assert verdict.citation_url == "https://example.com/press/helios-aether-2024"


def test_llm_rejects_talks_only_when_mock_says_so() -> None:
    payload = {
        "confirmed": False,
        "matched_company": None,
        "matched_acquirer": None,
        "acquisition_date": None,
        "value_usd": None,
        "citation_url": "https://example.com/rumor/vertex-lumen",
        "reason": "Snippet is talks-only; no completed deal.",
    }
    fixture = _by_id()["rumor_talks_to_acquire"]
    extractor = LlmExtractor(lambda _system, _user: json.dumps(payload))
    verdict = _extract(extractor, fixture)
    assert verdict.confirmed is False
    assert "talks-only" in verdict.reason


def test_llm_parses_fenced_json_and_uses_source_fallback() -> None:
    raw = """Here you go:
```json
{"confirmed": true, "matched_company": "Cedar Micro",
 "matched_acquirer": "Summit Partners", "acquisition_date": "2022-06-04",
 "value_usd": null, "citation_url": null, "reason": "Bought language."}
```
"""
    extractor = LlmExtractor(lambda _system, _user: raw)
    verdict = extractor.extract(
        ExtractionInput(
            company="Cedar Micro",
            acquirer="Summit Partners",
            snippet="Summit Partners bought Cedar Micro.",
            source_url="https://example.com/press/summit-cedar",
        )
    )
    assert verdict.confirmed is True
    assert verdict.acquisition_date == "2022-06-04"
    assert verdict.citation_url == "https://example.com/press/summit-cedar"


def test_llm_unparseable_response_is_unconfirmed() -> None:
    extractor = LlmExtractor(lambda _system, _user: "I think they bought them.")
    verdict = extractor.extract(ExtractionInput(company="A", acquirer="B", snippet="maybe"))
    assert verdict.confirmed is False
    assert "Unparseable" in verdict.reason


def test_llm_prompt_asks_for_schema_and_pair() -> None:
    captured: dict[str, str] = {}

    def _chat(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return json.dumps({"confirmed": False, "reason": "no"})

    item = ExtractionInput(
        company="Aether Photonics",
        acquirer="Helios Defense",
        snippet="not a deal",
        source_url="https://example.com/x",
    )
    LlmExtractor(_chat).extract(item)
    assert "acquisition_date" in captured["system"]
    assert "value_usd" in captured["system"]
    assert "talks" in captured["system"]
    assert captured["system"] == EXTRACTOR_SYSTEM_PROMPT
    assert captured["user"] == build_user_prompt(item)
    assert "Aether Photonics" in captured["user"]


def test_llm_accepts_openai_client_shape() -> None:
    payload = {"confirmed": False, "reason": "client-shape mock"}
    client = SimpleNamespace(
        chat=lambda system, user, model=None, temperature=0.3: json.dumps(payload)
    )
    verdict = LlmExtractor(client, model="gpt-4.1-mini").extract(
        ExtractionInput(company="A", acquirer="B", snippet="no")
    )
    assert verdict.confirmed is False
    assert verdict.reason == "client-shape mock"


def test_verdict_from_payload_rejects_non_bool_confirmed() -> None:
    verdict = verdict_from_payload({"confirmed": "yes", "reason": "bad"})
    assert verdict.confirmed is False
    assert "boolean" in verdict.reason


def test_parse_llm_payload_ignores_unknown_placeholder_date() -> None:
    verdict = verdict_from_payload(
        {
            "confirmed": True,
            "acquisition_date": "Unknown",
            "reason": "keyword-shaped",
        }
    )
    assert verdict.confirmed is True
    assert verdict.acquisition_date is None


def test_build_llm_extractor_returns_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_llm_extractor() is None


def test_build_llm_extractor_uses_openai_client_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    extractor = build_llm_extractor()
    assert isinstance(extractor, LlmExtractor)
    assert extractor.model == "gpt-4.1-mini"
