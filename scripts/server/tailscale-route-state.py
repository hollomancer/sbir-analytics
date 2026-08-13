#!/usr/bin/env python3
"""Classify ownership of one Tailscale Serve route."""

from __future__ import annotations

import json
import sys
from typing import Any


def _matches_port(value: str, port: str) -> bool:
    return value == port or value.rsplit(":", 1)[-1] == port


def _references_port(value: Any, port: str) -> bool:
    if isinstance(value, dict):
        return any(
            _matches_port(str(key), port) or _references_port(item, port)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_references_port(item, port) for item in value)
    return False


def classify(config: dict[str, Any], port: str, target: str, tls_host: str | None = None) -> str:
    tcp = config.get("TCP", {})
    web = config.get("Web", {})
    funnel = config.get("AllowFunnel", {})
    foreground = config.get("Foreground", {})
    if not all(isinstance(section, dict) for section in (tcp, web, funnel)):
        return "occupied"

    tcp_entry = tcp.get(port)
    web_entries = {key: value for key, value in web.items() if _matches_port(str(key), port)}
    funnel_entries = {key: value for key, value in funnel.items() if _matches_port(str(key), port)}
    foreground_uses_port = _references_port(foreground, port)

    if tls_host is None:
        expected_handlers = {"Handlers": {"/": {"Proxy": target}}}
        owned = (
            tcp_entry == {"HTTPS": True}
            and len(web_entries) == 1
            and next(iter(web_entries.values())) == expected_handlers
            and not any(bool(value) for value in funnel_entries.values())
            and not foreground_uses_port
        )
    else:
        owned = (
            tcp_entry == {"TCPForward": target, "TerminateTLS": tls_host}
            and not web_entries
            and not any(bool(value) for value in funnel_entries.values())
            and not foreground_uses_port
        )
    if owned:
        return "owned"

    if tcp_entry is None and not web_entries and not funnel_entries and not foreground_uses_port:
        return "free"
    return "occupied"


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print("usage: tailscale-route-state.py PORT TARGET [TLS_HOST]", file=sys.stderr)
        return 2
    try:
        config = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"invalid Tailscale Serve JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("invalid Tailscale Serve JSON: expected an object", file=sys.stderr)
        return 2
    tls_host = sys.argv[3] if len(sys.argv) == 4 else None
    print(classify(config, sys.argv[1], sys.argv[2], tls_host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
