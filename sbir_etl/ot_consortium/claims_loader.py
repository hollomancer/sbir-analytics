"""Pluggable loader for firm-reported covered-sales claims (audit mode).

Accepts a pandas DataFrame, a CSV/Parquet path, or a list of dict rows and
normalizes them into :class:`CoveredSalesClaim` objects. The schema is treated
as not-yet-final: a column-alias map absorbs common header variants, and unknown
columns are preserved in ``metadata``.

Attributability rule: a claim that cites no PIID, no parent PIID, and no
firm-internal reference is an aggregated covered-sales total that cannot be tied
to a specific award. It is flagged ``is_attributable = False`` so the classifier
skips it and the magnitude report counts its dollars in a separate
non-attributable bucket — never folded into a tier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
from loguru import logger

from .models import CoveredSalesClaim, FirmUEISource

# Maps canonical CoveredSalesClaim fields to accepted source-column aliases.
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "claim_id": ("claim_id", "id", "row_id"),
    "firm_name": ("firm_name", "company", "company_name", "recipient_name", "vendor_name"),
    "firm_uei": ("firm_uei", "uei", "recipient_uei"),
    "firm_internal_ref": ("firm_internal_ref", "internal_ref", "project_id", "internal_id"),
    "firm_duns": ("firm_duns", "duns"),
    "claimed_award_piid": ("claimed_award_piid", "piid", "award_piid", "contract_id"),
    "claimed_parent_piid": ("claimed_parent_piid", "parent_piid", "parent_award_id", "idv_piid"),
    "cmf_name": ("cmf_name", "consortium", "consortium_manager", "cmf"),
    "claimed_obligation_usd": (
        "claimed_obligation_usd",
        "obligation",
        "obligated_amount",
        "covered_sales",
        "amount",
    ),
    "agency": ("agency", "awarding_agency", "awarding_agency_name"),
    "fiscal_year": ("fiscal_year", "fy", "year"),
    "source_document": ("source_document", "source", "provenance"),
}


def _first_present(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in row and not _is_blank(row[alias]):
            return row[alias]
    return None


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _to_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if _is_blank(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if _is_blank(value):
        return None
    return str(value).strip()


def _coerce_rows(source: Any) -> list[dict[str, Any]]:
    """Coerce any supported source into a list of dict rows."""
    if isinstance(source, pd.DataFrame):
        return cast("list[dict[str, Any]]", source.to_dict("records"))
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() == ".parquet":
            return cast("list[dict[str, Any]]", pd.read_parquet(path).to_dict("records"))
        return cast("list[dict[str, Any]]", pd.read_csv(path, dtype=str).to_dict("records"))
    if isinstance(source, list):
        return [dict(r) for r in source]
    raise TypeError(f"Unsupported claims source type: {type(source)!r}")


def load_claims(source: Any) -> list[CoveredSalesClaim]:
    """Load and normalize covered-sales claims from a pluggable source.

    Args:
        source: A DataFrame, a path to a ``.csv``/``.parquet`` file, or a list of
            dict rows.

    Returns:
        A list of validated :class:`CoveredSalesClaim` objects.
    """
    rows = _coerce_rows(source)
    claims: list[CoveredSalesClaim] = []
    known_aliases = {a for aliases in _COLUMN_ALIASES.values() for a in aliases}

    for idx, row in enumerate(rows):
        vals: dict[str, Any] = {
            field: _first_present(row, al) for field, al in _COLUMN_ALIASES.items()
        }

        firm_uei = _to_str(vals["firm_uei"])
        piid = _to_str(vals["claimed_award_piid"])
        parent = _to_str(vals["claimed_parent_piid"])
        internal = _to_str(vals["firm_internal_ref"])

        # Aggregated total with no award handle → not attributable to one award.
        is_attributable = bool(piid or parent or internal)

        extras = {k: v for k, v in row.items() if k not in known_aliases and not _is_blank(v)}

        claim = CoveredSalesClaim(
            claim_id=_to_str(vals["claim_id"]) or f"claim_{idx}",
            firm_name=_to_str(vals["firm_name"]) or "",
            firm_uei=firm_uei,
            firm_uei_source=FirmUEISource.PROVIDED if firm_uei else FirmUEISource.UNRESOLVED,
            firm_internal_ref=internal,
            firm_duns=_to_str(vals["firm_duns"]),
            claimed_award_piid=piid,
            claimed_parent_piid=parent,
            cmf_name=_to_str(vals["cmf_name"]),
            claimed_obligation_usd=_to_float(vals["claimed_obligation_usd"]),
            agency=_to_str(vals["agency"]),
            fiscal_year=_to_int(vals["fiscal_year"]),
            is_attributable=is_attributable,
            source_document=_to_str(vals["source_document"]),
            metadata=extras,
        )
        claims.append(claim)

    n_agg = sum(1 for c in claims if not c.is_attributable)
    logger.info(
        "Loaded {} covered-sales claims ({} non-attributable aggregates)", len(claims), n_agg
    )
    return claims
