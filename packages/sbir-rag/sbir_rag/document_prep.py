"""Document preparation: converts SBIR data records to LightRAG documents.

Each ``prepare_*`` function accepts a :class:`pandas.Series` row and returns a
``dict`` with ``content`` (text for LLM entity extraction) and ``metadata``
(structured fields preserved for cross-referencing).

Solicitation descriptions are classified into three tiers:

- **stub** (< ``min_description_length``): Boilerplate like "See attached" — skipped
- **summary** (between min and ``full_description_threshold``): Short paragraphs —
  ingested but flagged as low-value
- **full** (>= threshold): Dense technical prose — highest extraction value
"""

from __future__ import annotations

from typing import Literal

import pandas as pd


def prepare_award_document(row: pd.Series) -> dict:
    """Convert a validated_sbir_awards DataFrame row to a LightRAG document.

    Produces a text block with a structured header (agency, phase, keywords)
    followed by the award title and abstract.  The header gives the LLM
    extraction step useful context without polluting the free-text body.

    Args:
        row: A single row from the ``validated_sbir_awards`` DataFrame.

    Returns:
        ``{"content": str, "metadata": dict}`` ready for ``rag.ainsert()``.
    """
    # Build structured header
    header_parts: list[str] = []
    agency = row.get("agency")
    if pd.notna(agency) and str(agency).strip():
        header_parts.append(f"Agency: {agency}")
    phase = row.get("phase")
    if pd.notna(phase) and str(phase).strip():
        header_parts.append(f"Phase: {phase}")
    keywords = row.get("keywords")
    if pd.notna(keywords) and str(keywords).strip():
        header_parts.append(f"Keywords: {keywords}")
    header = ". ".join(header_parts) + ". " if header_parts else ""

    # Build body from title + abstract
    body_parts: list[str] = []
    for field in ("award_title", "abstract"):
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            body_parts.append(str(val).strip())
    body = " ".join(body_parts)

    return {
        "content": header + body,
        "metadata": {
            "award_id": (str(row.get("award_id")) if pd.notna(row.get("award_id")) else None),
            "agency": row.get("agency") if pd.notna(row.get("agency")) else None,
            "phase": row.get("phase") if pd.notna(row.get("phase")) else None,
            "award_year": row.get("award_year") if pd.notna(row.get("award_year")) else None,
            "company_name": (
                row.get("company_name") if pd.notna(row.get("company_name")) else None
            ),
            "document_type": "award",
        },
    }


def prepare_solicitation_document(row: pd.Series) -> dict:
    """Convert a solicitation topics DataFrame row to a LightRAG document.

    Solicitation topic descriptions are typically 500-3000 words of dense
    technical prose — far richer than award abstracts for entity extraction.

    Args:
        row: A single row from an extracted solicitation topics DataFrame.

    Returns:
        ``{"content": str, "metadata": dict}`` ready for ``rag.ainsert()``.
    """
    header_parts: list[str] = []
    topic_code = row.get("topic_code")
    if pd.notna(topic_code) and str(topic_code).strip():
        header_parts.append(f"Solicitation Topic: {topic_code}")
    agency = row.get("agency")
    if pd.notna(agency) and str(agency).strip():
        header_parts.append(f"Agency: {agency}")
    program = row.get("program")
    if pd.notna(program) and str(program).strip():
        header_parts.append(f"Program: {program}")
    header = ". ".join(header_parts) + ". " if header_parts else ""

    body_parts: list[str] = []
    for field in ("title", "description"):
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            body_parts.append(str(val).strip())
    body = " ".join(body_parts)

    return {
        "content": header + body,
        "metadata": {
            "topic_code": (str(row.get("topic_code")) if pd.notna(row.get("topic_code")) else None),
            "solicitation_number": (
                str(row.get("solicitation_number", ""))
                if pd.notna(row.get("solicitation_number"))
                else None
            ),
            "agency": row.get("agency") if pd.notna(row.get("agency")) else None,
            "year": row.get("year") if pd.notna(row.get("year")) else None,
            "document_type": "solicitation",
        },
    }


def classify_description(
    row: pd.Series,
    *,
    min_length: int = 100,
    full_threshold: int = 500,
) -> Literal["stub", "summary", "full"]:
    """Classify a solicitation description by quality tier.

    Args:
        row: Solicitation DataFrame row (must have a ``description`` field).
        min_length: Minimum chars to avoid being classified as a stub.
        full_threshold: Chars above which a description is considered full.

    Returns:
        ``"stub"``, ``"summary"``, or ``"full"``.
    """
    desc = row.get("description")
    if not pd.notna(desc) or not str(desc).strip():
        return "stub"

    length = len(str(desc).strip())
    if length < min_length:
        return "stub"
    if length < full_threshold:
        return "summary"
    return "full"
