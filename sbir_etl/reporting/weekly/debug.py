"""Debug logging for the weekly awards report, toggled by the --debug CLI flag.

State lives here (not in the CLI script) so every pipeline module shares one
switch. Enable with :func:`set_debug`; helpers no-op when disabled.
"""

import sys

import httpx


_DEBUG = False


def set_debug(enabled: bool) -> None:
    """Toggle debug logging for all weekly-report modules."""
    global _DEBUG  # noqa: PLW0603
    _DEBUG = enabled


def debug_enabled() -> bool:
    return _DEBUG


def _debug(msg: str) -> None:
    """Print a debug message to stderr when debug mode is active."""
    if _DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr)


def _debug_response(label: str, resp: httpx.Response, body_preview_len: int = 500) -> None:
    """Log key details of an HTTP response in debug mode."""
    if not _DEBUG:
        return
    # Use resp.content (bytes) to avoid decoding the full body into a string.
    # Only decode the sliced prefix for the preview.
    raw = resp.content
    encoding = resp.encoding or "utf-8"
    preview = raw[:body_preview_len].decode(encoding, errors="replace")
    # Collapse newlines/control chars so the log stays on one line.
    preview = preview.replace("\r", "").replace("\n", " ").replace("\t", " ")
    if len(raw) > body_preview_len:
        preview += "..."
    _debug(f"{label} — HTTP {resp.status_code} | {len(raw)} bytes | preview: {preview}")
