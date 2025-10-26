#!/usr/bin/env python3
"""
sbir-etl/scripts/openspec/fetch_provider_docs.py

Fetch provider documentation pages listed in an openspec providers.json file,
attempt to discover authoritative rate-limit and auth information, and annotate
the providers.json entries with discovery metadata.

This is a best-effort automated annotator — it performs HTTP GETs against the
providers' docs_url and api_docs_url (when present) and performs lightweight
heuristics on headers and text content to find mentions of rate limits,
auth model hints, and delta/cursor support.

Usage:
    python sbir-etl/scripts/openspec/fetch_provider_docs.py \
        --providers-file sbir-etl/openspec/changes/add-iterative-api-enrichment/providers.json \
        --output-file sbir-etl/openspec/changes/add-iterative-api-enrichment/providers.json

Notes:
- This script does NOT authenticate to any provider; it only fetches public docs.
- It is intentionally conservative: it records findings but does not assume they
  are authoritative. After running, inspect the updated providers.json and
  manually verify any discovered values before changing connector behavior.
- The script uses only standard library modules, so it should be runnable in
  constrained environments.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import ssl
import tempfile
import time
from datetime import datetime
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Reasonable defaults
USER_AGENT = "sbir-etl-docs-fetcher/1.0 (+https://github.com/your-org/sbir-etl)"
DEFAULT_TIMEOUT = 15  # seconds
RATE_LIMIT_HEADER_CANDIDATES = [
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "retry-after",
]

# Lightweight regexes to discover human-readable rate-limit mentions in docs HTML/text
RATE_LIMIT_PATTERNS = [
    re.compile(r"(\d+)\s*requests?/\s*(second|sec|s)\b", re.IGNORECASE),
    re.compile(r"(\d+)\s*requests?/\s*(minute|min|m)\b", re.IGNORECASE),
    re.compile(r"rate[-\s]*limit", re.IGNORECASE),
    re.compile(r"rate[-\s]*limit.*?(\d+)", re.IGNORECASE),
    re.compile(r"requests? per (second|minute|hour)", re.IGNORECASE),
    re.compile(r"throttl", re.IGNORECASE),
    re.compile(r"ETag", re.IGNORECASE),  # ETag/If-Modified-Since mention
    re.compile(r"If-Modified-Since", re.IGNORECASE),
    re.compile(r"If-None-Match", re.IGNORECASE),
]


def http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> Tuple[int, Dict[str, str], str]:
    """
    Perform a simple HTTP GET and return (status_code, headers, body_text).

    Uses a simple User-Agent and verifies SSL by default. Returns body decoded
    as utf-8 with errors replaced.
    """
    ctx = ssl.create_default_context()
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            # Headers: convert to dict with lower-case keys
            raw_headers = getattr(resp, "headers", None)
            headers = {}
            if raw_headers:
                for k, v in raw_headers.items():
                    headers[k.lower()] = v.strip()
            raw = resp.read()
            try:
                text = raw.decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            return int(status), headers, text
    except HTTPError as he:
        # Try to read body from error response if available
        try:
            body = he.read().decode("utf-8", errors="replace") if hasattr(he, "read") else ""
        except Exception:
            body = ""
        return he.code if getattr(he, "code", None) else 0, {}, body
    except URLError as ue:
        raise
    except Exception:
        raise


def extract_rate_limit_from_headers(headers: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Inspect headers for common rate-limit / retry headers and return a small dict
    if found.
    """
    found = {}
    for h in RATE_LIMIT_HEADER_CANDIDATES:
        if h in headers:
            found[h] = headers[h]
    return found if found else None


def extract_rate_limit_from_text(text: str) -> Optional[str]:
    """
    Search the text for human-readable rate-limit mentions using heuristics.
    Return the first matched snippet or None.
    """
    for pat in RATE_LIMIT_PATTERNS:
        m = pat.search(text)
        if m:
            # return a short context snippet
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            snippet = text[start:end].replace("\n", " ").strip()
            return snippet
    return None


def annotate_provider(provider: Dict, url_key: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    """
    Attempt to fetch and analyze a single URL (docs or api_docs) for the given provider.
    Annotates provider['discovery'][url_key] with findings.
    """
    url = provider.get(url_key)
    discovery = provider.setdefault("discovery", {})
    entry = discovery.setdefault(url_key, {})
    if not url:
        entry.update({"status": "no_url", "checked_at": now_iso(), "note": "No URL provided"})
        return

    # Normalize URL: only proceed for http/https
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        entry.update(
            {
                "status": "unsupported_scheme",
                "checked_at": now_iso(),
                "note": f"Unsupported URL scheme: {parsed.scheme}",
            }
        )
        return

    entry["checked_at"] = now_iso()
    entry["url"] = url
    entry["attempts"] = entry.get("attempts", 0) + 1

    try:
        status, headers, text = http_get(url, timeout=timeout)
    except URLError as e:
        entry["status"] = "error"
        entry["error"] = f"URLError: {e}"
        return
    except Exception as e:
        entry["status"] = "error"
        entry["error"] = f"Exception: {e}"
        return

    entry["http_status"] = int(status)
    # Record a subset of headers for brevity
    useful_headers = {}
    for k in ("content-type", "cache-control", "last-modified", "etag"):
        if k in headers:
            useful_headers[k] = headers[k]
    # record any rate-limit headers discovered
    rl_headers = extract_rate_limit_from_headers(headers)
    if rl_headers:
        entry["rate_limit_headers"] = rl_headers
    if useful_headers:
        entry["headers"] = useful_headers

    # search text for rate-limit patterns
    rl_text = extract_rate_limit_from_text(text)
    if rl_text:
        entry["rate_limit_text_snippet"] = rl_text

    # Search for ETag/If-Modified/If-None-Match mentions (delta support hints)
    etag_hit = bool(re.search(r"If-None-Match|If-Modified-Since|ETag", text, re.IGNORECASE))
    entry["delta_support_hint"] = etag_hit

    # Auth hints in the docs text: look for words like "api key", "oauth", "bearer"
    auth_hint = None
    m = re.search(r"(api key|api_key|apikey|oauth2|oauth|bearer token|bearer)", text, re.IGNORECASE)
    if m:
        auth_hint = m.group(1)
        entry["auth_hint"] = auth_hint

    entry["status"] = "fetched"
    entry["sample_snippet"] = text[:1024].replace("\n", " ")


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def load_providers(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


def safe_write_json(path: str, data: Dict) -> None:
    # Write to temp and atomically move
    dirpath = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix="providers.", dir=dirpath, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False, ensure_ascii=False)
        # atomic replace
        shutil.move(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def find_and_annotate(
    providers_obj: Dict, timeout: int = DEFAULT_TIMEOUT, single_id: Optional[str] = None
) -> None:
    providers = providers_obj.get("providers", [])
    for p in providers:
        pid = p.get("id")
        if single_id and pid != single_id:
            continue
        logging.info("Processing provider: %s (%s)", p.get("name"), pid)
        # Try docs_url first
        annotate_provider(p, "docs_url", timeout=timeout)
        # Then api_docs_url if present
        annotate_provider(p, "api_docs_url", timeout=timeout)
        # small delay between fetches to be polite
        time.sleep(0.25)


def summarize_findings(providers_obj: Dict) -> None:
    providers = providers_obj.get("providers", [])
    for p in providers:
        pid = p.get("id")
        disc = p.get("discovery", {})
        docs = disc.get("docs_url", {})
        api = disc.get("api_docs_url", {})
        found = []
        if docs.get("status") == "fetched" and (
            docs.get("rate_limit_headers") or docs.get("rate_limit_text_snippet")
        ):
            found.append("docs-rate-limit")
        if api.get("status") == "fetched" and (
            api.get("rate_limit_headers") or api.get("rate_limit_text_snippet")
        ):
            found.append("api-rate-limit")
        if docs.get("delta_support_hint") or api.get("delta_support_hint"):
            found.append("delta-hint")
        logging.info(
            "Provider %s (%s) discoveries: %s", p.get("name"), pid, ", ".join(found) or "none"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch provider docs and annotate providers.json with findings."
    )
    parser.add_argument(
        "--providers-file",
        "-i",
        default="sbir-etl/openspec/changes/add-iterative-api-enrichment/providers.json",
        help="Path to providers.json to read and update",
    )
    parser.add_argument(
        "--output-file",
        "-o",
        default="",
        help="Output path for updated providers.json (defaults to providers-file)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--provider-id",
        "-p",
        default="",
        help="Optional single provider id to process (defaults to all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s - %(message)s",
    )
    providers_file = args.providers_file
    output_file = args.output_file or providers_file

    if not os.path.isfile(providers_file):
        logging.error("Providers file not found: %s", providers_file)
        return 2

    try:
        providers_obj = load_providers(providers_file)
    except Exception as e:
        logging.exception("Failed to load providers file: %s", e)
        return 3

    logging.info("Loaded providers file: %s", providers_file)
    try:
        find_and_annotate(providers_obj, timeout=args.timeout, single_id=args.provider_id or None)
        summarize_findings(providers_obj)
        # update top-level metadata
        meta = providers_obj.setdefault("auto_discovery", {})
        meta["last_run_at"] = now_iso()
        meta["runner"] = "fetch_provider_docs.py"
        # Persist updated file
        safe_write_json(output_file, providers_obj)
        logging.info("Wrote updated providers file to: %s", output_file)
    except Exception as e:
        logging.exception("Error during discovery: %s", e)
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
