"""Deterministic CET-area agreement facts from the NSTC taxonomy keyword lists."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from sbir_etl.config.yaml_io import read_yaml_mapping
from sbir_etl.exceptions import ConfigurationError
from sbir_etl.utils.procurement_text import find_lineage_phrases


DEFAULT_TAXONOMY_PATH = Path("config/cet/taxonomy.yaml")


@lru_cache(maxsize=4)
def load_cet_vocabulary(path: str | None = None) -> dict[str, tuple[str, ...]]:
    """Map lowercased CET-area display name → keyword phrases.

    Returns an empty mapping when the taxonomy file is missing or unreadable —
    the packet degrades to no CET fact rather than failing.
    """

    taxonomy_path = Path(path) if path is not None else DEFAULT_TAXONOMY_PATH
    try:
        data = read_yaml_mapping(
            taxonomy_path,
            description="CET taxonomy",
            allow_empty=True,
        )
    except ConfigurationError:
        return {}
    vocabulary: dict[str, tuple[str, ...]] = {}
    for area in data.get("cet_areas", []):
        name = str(area.get("name", "")).strip()
        keywords = tuple(str(keyword).strip() for keyword in area.get("keywords", []) if keyword)
        if name and keywords:
            vocabulary[name.lower()] = keywords
    return vocabulary


def cet_agreement_fact(
    award_cet: Any,
    opportunity_text: Any,
    *,
    taxonomy_path: str | None = None,
) -> str | None:
    """State that the notice text matches the award's critical-technology area.

    Verifiable: the quoted keywords appear verbatim in the notice text. Returns
    None when the award has no CET label, the label is not a taxonomy area, or
    no area keyword occurs in the text.
    """

    label = str(award_cet).strip() if award_cet is not None else ""
    if not label or label.lower() in {"nan", "none", "<na>"}:
        return None
    keywords = load_cet_vocabulary(taxonomy_path).get(label.lower())
    if not keywords:
        return None
    hits = find_lineage_phrases(opportunity_text, phrases=keywords)
    if not hits:
        return None
    quoted = [f"“{hit}”" for hit in hits[:3]]
    listed = (
        " and ".join(quoted) if len(quoted) <= 2 else f"{', '.join(quoted[:-1])}, and {quoted[-1]}"
    )
    return f"Both fall in the {label} critical-technology area — the notice mentions {listed}."


__all__ = ["cet_agreement_fact", "load_cet_vocabulary"]
