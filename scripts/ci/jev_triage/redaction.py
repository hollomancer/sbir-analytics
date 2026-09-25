"""Credential redaction shared by all Jev triage envelope constructors."""

import re


EPISTEMIC_TIER = "exploratory"

REDACTED = "[REDACTED]"

_AUTHORIZATION = re.compile(
    r"(?i)(\bauthorization\s*:\s*(?:bearer\s+)?)([^\s,;]+)"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r'''(?ix)
    (\b(?:password|passwd|api[_-]?key|token|secret)\s*[:=]\s*)
    (?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)
    '''
)
_CREDENTIAL_URL = re.compile(r"(?i)\b(https?://)[^/\s:@]+:[^/\s@]+@")
_TOKEN_PREFIX = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,})\b"
)


def redact_text(value: str) -> str:
    """Redact common credential forms from one string."""

    text = _AUTHORIZATION.sub(rf"\1{REDACTED}", value)
    text = _CREDENTIAL_ASSIGNMENT.sub(rf"\1{REDACTED}", text)
    text = _CREDENTIAL_URL.sub(rf"\1{REDACTED}@", text)
    return _TOKEN_PREFIX.sub(REDACTED, text)
