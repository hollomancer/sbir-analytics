"""Adapter: USAspending/FPDS records → :class:`OTAward`.

This isolates the messy, source-shaped column handling from the tier logic. It
tolerates the column-name variance seen across the USAspending dump, the contract
extractor output, and ad-hoc samples (mirroring the tolerant ``.get`` style used
by the transition scoring asset).

The DoD ~90-day FPDS reporting lag is recorded here so callers can stamp it onto
output metadata: recent fiscal years undercount OT actions, and the newer
``Consortia`` / ``Primary Consortia Member UEI`` fields are more sparsely
populated the closer to the present you look.
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd

from .models import OTAward

#: DoD Other Transaction actions typically post to FPDS/USAspending ~90 days after
#: execution. Surfaced in asset metadata as a completeness caveat.
FPDS_REPORTING_LAG_DAYS = 90

# Column-name candidates, in priority order, for each OTAward field.
_COL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "award_id": ("award_id", "contract_id", "piid", "PIID"),
    "piid": ("piid", "PIID", "contract_id", "award_id"),
    "parent_piid": ("parent_piid", "parent_idv_piid", "parent_award_id", "parent_award_piid"),
    "recipient_uei": ("recipient_uei", "vendor_uei", "contractor_uei", "uei", "UEI"),
    "recipient_name": ("recipient_name", "vendor_name", "contractor_name", "recipient_legal_name"),
    "obligation_amount": (
        "obligation_amount",
        "obligated_amount",
        "total_obligation",
        "federal_action_obligation",
    ),
    "agency": (
        "awarding_sub_agency_name",
        "awarding_agency_name",
        "awarding_agency_code",
        "agency",
    ),
    "fiscal_year": ("fiscal_year", "action_date_fiscal_year", "fy"),
}

# Truthy/falsey spellings of the DoD "Consortia" Y/N field. Anything else (blank,
# null, unknown) maps to None — never silently to "No".
_CONSORTIA_YES = {"y", "yes", "true", "t", "1"}
_CONSORTIA_NO = {"n", "no", "false", "f", "0"}

# award_type / idv_type substrings indicating an Other Transaction instrument.
_OT_TYPE_HINTS = ("other transaction", "ot ", "ota", "11", "transaction")


def _get(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    for col in candidates:
        if col in row and not _blank(row[col]):
            return row[col]
    return None


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _to_float(value: Any) -> float | None:
    if _blank(value):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if _blank(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if _blank(value):
        return None
    return str(value).strip()


def parse_consortia_flag(value: Any) -> bool | None:
    """Parse the DoD Consortia Y/N field. Unknown/blank → None (not False)."""
    if _blank(value):
        return None
    token = str(value).strip().lower()
    if token in _CONSORTIA_YES:
        return True
    if token in _CONSORTIA_NO:
        return False
    return None


def detect_modification(row: dict[str, Any]) -> bool | None:
    """Detect a modification-based row (T3 signal).

    A non-zero modification number, or an explicit modification award type, marks
    the row as a modification to a base agreement. Returns None when no relevant
    field is present (unknown, not "not a modification").
    """
    mod_num = _get(
        row, ("modification_number", "mod_number", "award_modification_amendment_number")
    )
    if not _blank(mod_num):
        token = str(mod_num).strip().upper()
        # Base awards use "0", "00", "P00000", or "ORIGINAL".
        if token in {"0", "00", "000", "P00000", "ORIGINAL", "BASE"}:
            return False
        return True
    award_type = _to_str(_get(row, ("award_type", "contract_award_type", "type_description")))
    if award_type and "modification" in award_type.lower():
        return True
    return None


def is_ot_record(row: dict[str, Any]) -> bool:
    """Heuristic: does this record represent an Other Transaction instrument?"""
    indicator = _get(row, ("is_ot", "ot_indicator", "other_transaction"))
    if not _blank(indicator):
        token = str(indicator).strip().lower()
        if token in _CONSORTIA_YES:
            return True
        if token in _CONSORTIA_NO:
            return False
    for field in (
        "award_type",
        "idv_type",
        "contract_award_type",
        "type_description",
        "pricing_type",
    ):
        val = _to_str(row.get(field))
        if val and any(hint in val.lower() for hint in _OT_TYPE_HINTS):
            return True
    # Presence of consortia metadata is itself an OT signal.
    if not _blank(_get(row, ("consortia", "Consortia", "consortia_flag"))):
        return True
    return False


def build_ot_award(row: dict[str, Any], *, found_in_federal_data: bool = True) -> OTAward:
    """Map one source record dict to an :class:`OTAward`."""
    award_id = _to_str(_get(row, _COL_CANDIDATES["award_id"])) or ""
    return OTAward(
        award_id=award_id,
        piid=_to_str(_get(row, _COL_CANDIDATES["piid"])),
        parent_piid=_to_str(_get(row, _COL_CANDIDATES["parent_piid"])),
        recipient_uei=_to_str(_get(row, _COL_CANDIDATES["recipient_uei"])),
        recipient_name=_to_str(_get(row, _COL_CANDIDATES["recipient_name"])),
        consortia_flag=parse_consortia_flag(
            _get(row, ("consortia", "Consortia", "consortia_flag"))
        ),
        primary_consortia_member_uei=_to_str(
            _get(
                row,
                (
                    "primary_consortia_member_uei",
                    "Primary Consortia Member UEI",
                    "consortia_member_uei",
                    "member_uei",
                ),
            )
        ),
        is_modification=detect_modification(row),
        obligation_amount=_to_float(_get(row, _COL_CANDIDATES["obligation_amount"])),
        agency=_to_str(_get(row, _COL_CANDIDATES["agency"])),
        fiscal_year=_to_int(_get(row, _COL_CANDIDATES["fiscal_year"])),
        base_recipient_uei=_to_str(
            _get(row, ("base_recipient_uei", "parent_recipient_uei", "parent_uei"))
        ),
        base_recipient_name=_to_str(_get(row, ("base_recipient_name", "parent_recipient_name"))),
        found_in_federal_data=found_in_federal_data,
    )


def build_ot_awards(df: pd.DataFrame, *, ot_only: bool = True) -> list[OTAward]:
    """Build OTAwards from a DataFrame of federal records.

    Args:
        df: Contracts/USAspending records with named columns.
        ot_only: When True, keep only records that look like OT instruments.
    """
    if df is None or df.empty:
        return []
    awards: list[OTAward] = []
    for row in cast("list[dict[str, Any]]", df.to_dict("records")):
        if ot_only and not is_ot_record(row):
            continue
        awards.append(build_ot_award(row))
    return awards
