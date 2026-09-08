"""Normalized NIH RePORTER project record.

Epistemic tier: pipelines. ``appl_id`` is the official row id. Award-level
upsert uses ``(canonical project_num, fy)``. Multiple ``appl_id``s or
organization identifiers for one upsert key are retained, not collapsed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sbir_etl.enrichers.nih_reporter.keys import canonicalize_nih_query_key


EPISTEMIC_TIER = "pipelines"

NIH_SOURCE_ID = "nih_reporter"


@dataclass(frozen=True)
class NIHReporterRecord:
    """One RePORTER project row after field extraction.

    ``org_uei`` / ``org_duns`` are the primary identifiers when present.
    ``org_ueis`` / ``org_duns_values`` keep the full official sets so a later
    identity consumer can expand pairs without a second fetch.
    """

    appl_id: str
    fy: int
    project_num: str | None = None
    core_project_num: str | None = None
    activity_code: str | None = None
    agency_ic_admin: str | None = None
    org_name: str | None = None
    org_uei: str | None = None
    org_duns: str | None = None
    org_ueis: tuple[str, ...] = ()
    org_duns_values: tuple[str, ...] = ()
    pi_names: tuple[str, ...] = ()
    project_title: str | None = None
    abstract_text: str | None = None
    award_amount: float | None = None
    foa_number: str | None = None
    study_section: str | None = None
    source: str = NIH_SOURCE_ID
    last_refreshed_at: datetime | None = None
    payload_hash: str | None = None

    def upsert_key(self) -> tuple[str, int] | None:
        """Award-level key, or ``None`` when the project number is unusable."""

        canonical = canonicalize_nih_query_key(self.project_num)
        if canonical is None:
            return None
        return (canonical, self.fy)

    def to_mapping(self) -> dict[str, Any]:
        """JSON/Parquet-friendly record."""

        return {
            "appl_id": self.appl_id,
            "fy": self.fy,
            "project_num": self.project_num,
            "core_project_num": self.core_project_num,
            "activity_code": self.activity_code,
            "agency_ic_admin": self.agency_ic_admin,
            "org_name": self.org_name,
            "org_uei": self.org_uei,
            "org_duns": self.org_duns,
            "org_ueis": list(self.org_ueis),
            "org_duns_values": list(self.org_duns_values),
            "pi_names": list(self.pi_names),
            "project_title": self.project_title,
            "abstract_text": self.abstract_text,
            "award_amount": self.award_amount,
            "foa_number": self.foa_number,
            "study_section": self.study_section,
            "source": self.source,
            "last_refreshed_at": (
                self.last_refreshed_at.isoformat() if self.last_refreshed_at else None
            ),
            "payload_hash": self.payload_hash,
        }


def normalize_reporter_result(
    result: Mapping[str, Any],
    *,
    retrieved_at: datetime | None = None,
    payload_hash: str | None = None,
) -> NIHReporterRecord:
    """Extract a typed record from one RePORTER ``results[]`` object.

    Raises:
        ValueError: If ``appl_id`` or ``fiscal_year`` is missing or unusable.
    """

    try:
        appl_id = str(result["appl_id"]).strip()
        fy = int(result["fiscal_year"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("NIH RePORTER project lacks appl_id or fiscal_year") from error
    if not appl_id:
        raise ValueError("NIH RePORTER project lacks appl_id or fiscal_year")

    raw_org = result.get("organization")
    organization = raw_org if isinstance(raw_org, Mapping) else {}
    ueis = _identifier_values(organization, "org_ueis", "primary_uei")
    duns_values = _identifier_values(organization, "org_duns", "primary_duns")
    return NIHReporterRecord(
        appl_id=appl_id,
        fy=fy,
        project_num=_optional_str(result.get("project_num")),
        core_project_num=_optional_str(result.get("core_project_num")),
        activity_code=_optional_str(result.get("activity_code")),
        agency_ic_admin=_optional_str(result.get("agency_ic_admin")),
        org_name=_optional_str(organization.get("org_name")),
        org_uei=ueis[0] if ueis else None,
        org_duns=duns_values[0] if duns_values else None,
        org_ueis=ueis,
        org_duns_values=duns_values,
        pi_names=_pi_names(result.get("principal_investigators")),
        project_title=_optional_str(result.get("project_title")),
        abstract_text=_optional_str(result.get("abstract_text")),
        award_amount=_optional_float(result.get("award_amount")),
        foa_number=_opportunity_number(result.get("opportunity_number")),
        study_section=_study_section(result.get("full_study_section")),
        last_refreshed_at=retrieved_at,
        payload_hash=payload_hash,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _identifier_values(
    organization: Mapping[str, Any],
    plural_key: str,
    primary_key: str,
) -> tuple[str, ...]:
    raw = organization.get(plural_key)
    values: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = str(item).strip() if item is not None else ""
            if text:
                values.append(text)
    primary = _optional_str(organization.get(primary_key))
    if primary and primary not in values:
        values.insert(0, primary)
    return tuple(dict.fromkeys(values))


def _pi_names(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for investigator in raw:
        if not isinstance(investigator, Mapping):
            continue
        full = _optional_str(investigator.get("full_name"))
        if full:
            names.append(full)
            continue
        first = _optional_str(investigator.get("first_name")) or ""
        last = _optional_str(investigator.get("last_name")) or ""
        joined = " ".join(part for part in (first, last) if part)
        if joined:
            names.append(joined)
    return tuple(names)


def _opportunity_number(raw: Any) -> str | None:
    if isinstance(raw, list):
        for item in raw:
            text = _optional_str(item)
            if text:
                return text
        return None
    return _optional_str(raw)


def _study_section(raw: Any) -> str | None:
    if isinstance(raw, Mapping):
        for key in ("srg_code", "name", "srg_name"):
            text = _optional_str(raw.get(key))
            if text:
                return text
        return None
    return _optional_str(raw)
