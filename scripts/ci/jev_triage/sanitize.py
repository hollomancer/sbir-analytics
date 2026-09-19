"""Build a bounded failure envelope from structured CI output."""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable

from .models import CommandFamily, FailureEnvelope


EPISTEMIC_TIER = "exploratory"

_MAX_ITEMS = 20
_MAX_JUNIT_BYTES = 2_000_000
_MAX_ID_LENGTH = 240
_MAX_EXCERPT_LENGTH = 800
_MAX_EXCERPT_LINES = 8
_REDACTED = "[REDACTED]"

_AUTHORIZATION = re.compile(
    r"(?i)(\bauthorization\s*:\s*(?:bearer\s+)?)([^\s,;]+)"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|api[_-]?key|token|secret)\s*[:=]\s*)([^\s,;]+)"
)
_CREDENTIAL_URL = re.compile(r"(?i)\b(https?://)[^/\s:@]+:[^/\s@]+@")
_TOKEN_PREFIX = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,})\b"
)


def redact_text(value: str) -> str:
    """Redact common credential forms from one diagnostic string."""

    text = _AUTHORIZATION.sub(rf"\1{_REDACTED}", value)
    text = _CREDENTIAL_ASSIGNMENT.sub(rf"\1{_REDACTED}", text)
    text = _CREDENTIAL_URL.sub(rf"\1{_REDACTED}@", text)
    return _TOKEN_PREFIX.sub(_REDACTED, text)


def _bounded_text(value: object, *, limit: int) -> str:
    text = redact_text(str(value).strip())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _bounded_unique(values: Iterable[object], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _bounded_text(value, limit=limit)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= _MAX_ITEMS:
            break
    return result


def _diagnostic_excerpt(value: str) -> str:
    lines = value.strip().splitlines()[:_MAX_EXCERPT_LINES]
    return _bounded_text("\n".join(lines), limit=_MAX_EXCERPT_LENGTH)


def failure_envelope_from_junit(
    junit_xml: str,
    *,
    check_name: str,
    exit_code: int,
    changed_path_groups: Iterable[str] = (),
    runner_os: str,
    attempt_number: int = 1,
) -> FailureEnvelope:
    """Parse failed JUnit cases into a strict, redacted failure envelope."""

    if len(junit_xml.encode("utf-8")) > _MAX_JUNIT_BYTES:
        raise ValueError("JUnit XML exceeds the 2000000-byte input limit")
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as exc:
        raise ValueError("malformed JUnit XML") from exc

    failed_test_ids: list[str] = []
    exception_types: list[str] = []
    diagnostic_excerpts: list[str] = []

    for testcase in root.iter("testcase"):
        failures = [*testcase.findall("failure"), *testcase.findall("error")]
        if not failures:
            continue
        classname = str(testcase.get("classname") or "").strip()
        name = str(testcase.get("name") or "").strip()
        test_id = f"{classname}::{name}" if classname else name
        failed_test_ids.append(test_id)
        for failure in failures:
            if failure_type := failure.get("type"):
                exception_types.append(failure_type)
            text = (failure.text or "").strip() or failure.get("message") or ""
            if text.strip():
                diagnostic_excerpts.append(_diagnostic_excerpt(text))

    return FailureEnvelope(
        check_name=_bounded_text(check_name, limit=120),
        command_family=CommandFamily.PYTEST,
        exit_code=exit_code,
        failed_test_ids=_bounded_unique(failed_test_ids, limit=_MAX_ID_LENGTH),
        exception_types=_bounded_unique(exception_types, limit=120),
        diagnostic_excerpts=_bounded_unique(
            diagnostic_excerpts,
            limit=_MAX_EXCERPT_LENGTH,
        ),
        changed_path_groups=_bounded_unique(changed_path_groups, limit=120),
        runner_os=_bounded_text(runner_os, limit=40),
        attempt_number=attempt_number,
    )
