"""Deterministic plain-language checks for representative-facing packet text."""

from __future__ import annotations

import re
from typing import Any

# Internal vocabulary that must not reach representative-facing text.
# Each entry: (pattern, label, replacement guidance).
JARGON_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (r"\bcohort\b", "cohort", 'say "awards in this packet"'),
    (
        r"\bcomposite\s+(?:score|rank|[0-9])",
        "composite score",
        "say how many screening checks passed",
    ),
    (r"\bsignal class\b", "signal class", 'say "screening path"'),
    (r"\btopical similarity\b", "topical similarity", "name the shared technical terms"),
    (r"\blineage language\b", "lineage language", "quote the phrase found in the notice"),
    (r"\bwatchlist\b", "watchlist", 'say "needs more evidence"'),
    (r"\btriage\b", "triage", 'say "review priority"'),
    (r"\bhigh[- ]confidence\b", "high-confidence", 'say "priority lead"'),
)

MAX_SENTENCE_WORDS = 30

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_FORMATTING = re.compile(r"\*\*|\\(.)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:https?://)[^)\s]*\)")


def _strip_formatting(line: str) -> str:
    line = _LINK.sub(r"\1", line)
    return _FORMATTING.sub(lambda match: match.group(1) or "", line)


def check_plain_language(
    markdown: str, *, max_sentence_words: int = MAX_SENTENCE_WORDS
) -> dict[str, Any]:
    """Check generated packet text for jargon and hard-to-read sentences.

    Blockquotes and table rows are excluded: they quote public records, and the
    check targets the text this pipeline writes, not source material.
    """

    own_lines: list[str] = []  # headings + narrative — scanned for jargon
    narrative_lines: list[str] = []  # prose only — scanned for sentence length
    for raw in markdown.split("\n"):
        line = raw.strip()
        if not line or line.startswith((">", "|")):
            continue
        if line.startswith("#"):
            own_lines.append(_strip_formatting(line.lstrip("# ")))
            continue
        if line.startswith("- "):
            line = line[2:]
        cleaned = _strip_formatting(line)
        own_lines.append(cleaned)
        narrative_lines.append(cleaned)

    jargon: list[dict[str, Any]] = []
    haystack = "\n".join(own_lines).lower()
    for pattern, label, suggestion in JARGON_PATTERNS:
        count = len(re.findall(pattern, haystack))
        if count:
            jargon.append({"term": label, "count": count, "suggestion": suggestion})

    long_sentences: list[dict[str, Any]] = []
    sentence_count = 0
    word_count = 0
    for line in narrative_lines:
        for sentence in _SENTENCE_END.split(line):
            stripped = sentence.strip()
            if not stripped:
                continue
            words = len(stripped.split())
            sentence_count += 1
            word_count += words
            if words > max_sentence_words:
                excerpt = stripped if len(stripped) <= 120 else stripped[:119] + "…"
                long_sentences.append({"words": words, "text": excerpt})

    return {
        "passed": not jargon and not long_sentences,
        "jargon": jargon,
        "long_sentences": long_sentences,
        "sentences": sentence_count,
        "words": word_count,
        "average_sentence_length": (
            round(word_count / sentence_count, 1) if sentence_count else 0.0
        ),
    }


__all__ = ["JARGON_PATTERNS", "MAX_SENTENCE_WORDS", "check_plain_language"]
