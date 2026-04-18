"""Shared helpers for lightweight script reporting output.

These utilities are intentionally minimal and dependency-light so that
standalone scripts under ``scripts/data`` can share formatting and I/O
behavior without duplicating helper logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def serialize_dagster_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Convert Dagster metadata values to JSON-serializable plain values."""
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        # Dagster metadata values expose the real value via a `.value` attribute.
        result[key] = value.value if hasattr(value, "value") else value
    return result


def _escape_md_cell(value: Any) -> str:
    """Escape markdown table cell content."""
    return str(value).replace("|", "\\|")


def render_metric_table(title: str, rows: list[tuple[str, Any]]) -> str:
    """Render a standard markdown metric table section."""
    lines = [
        f"# {title}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for metric, value in rows:
        lines.append(f"| {_escape_md_cell(metric)} | {_escape_md_cell(value)} |")
    return "\n".join(lines)


def write_gha_outputs(gha_output: Path | None, outputs: Mapping[str, Any]) -> None:
    """Append key-value outputs to a GitHub Actions output file."""
    if gha_output is None:
        return
    with gha_output.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")
