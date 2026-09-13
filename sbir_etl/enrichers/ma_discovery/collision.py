"""C3 collision join between discovery rows and existing M&A events.

Epistemic tier: pipelines. Deterministic join and promotion table from
``specs/ma-discovery-integration/design.md``. Does not call search or an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


EPISTEMIC_TIER = "pipelines"
COLLISION_WINDOW = timedelta(days=30)
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class CollisionResult:
    """Merged event set plus the discovery-side mutations."""

    rows: list[dict[str, Any]]
    inserted: list[dict[str, Any]] = field(default_factory=list)
    promoted: list[dict[str, Any]] = field(default_factory=list)
    confirmed_existing: list[dict[str, Any]] = field(default_factory=list)
    applied_hits: list[dict[str, Any]] = field(default_factory=list)


def name_key(value: str | None) -> str:
    """Suffix-stripping recipient key used by query generation."""
    return normalize_company_name(value or "", profile=CompanyNameProfile.RECIPIENT_V1)


def parse_event_date(value: object) -> date | None:
    """Parse ISO ``YYYY-MM-DD``; anything else is missing."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def dates_collide(existing: object, discovered: object) -> bool:
    """True when dates match within ±30 days, or both are missing."""
    left = parse_event_date(existing)
    right = parse_event_date(discovered)
    if left is None or right is None:
        return left is None and right is None
    delta = left - right
    if delta < timedelta(0):
        delta = -delta
    return delta <= COLLISION_WINDOW


def _has_form_d(row: dict[str, Any]) -> bool:
    if row.get("form_d_detail"):
        return True
    signals = row.get("signals") or {}
    return bool(isinstance(signals, dict) and signals.get("form_d_business_combination"))


def _rank(confidence: object) -> int:
    if isinstance(confidence, str):
        return _CONFIDENCE_RANK.get(confidence, -1)
    return -1


def _with_signal(row: dict[str, Any], **updates: Any) -> dict[str, Any]:
    merged = dict(row)
    signals = dict(merged.get("signals") or {})
    extra = updates.pop("signals", None)
    if isinstance(extra, dict):
        signals.update(extra)
    merged["signals"] = signals
    merged.update(updates)
    return merged


def apply_c3(
    existing: list[dict[str, Any]],
    discovered: list[dict[str, Any]],
) -> CollisionResult:
    """Join discovered rows onto existing events under rule C3.

    Discovery never lowers confidence and never overwrites a Form D acquirer.
    """
    rows = [dict(row) for row in existing]
    inserted: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    confirmed_existing: list[dict[str, Any]] = []
    applied_hits: list[dict[str, Any]] = []

    for hit in discovered:
        company_key = name_key(str(hit.get("company_name") or ""))
        if not company_key:
            continue
        hit_date = hit.get("event_date") or hit.get("date")
        match_idx: int | None = None
        dateless_idx: int | None = None
        for idx, row in enumerate(rows):
            if name_key(str(row.get("company_name") or "")) != company_key:
                continue
            existing_date = row.get("event_date")
            if parse_event_date(existing_date) is None:
                if dateless_idx is None:
                    dateless_idx = idx
                continue
            if dates_collide(existing_date, hit_date):
                match_idx = idx
                break
        if match_idx is None:
            match_idx = dateless_idx

        if match_idx is None:
            inserted_row = _discovered_as_event(hit)
            rows.append(inserted_row)
            inserted.append(inserted_row)
            applied_hits.append(hit)
            continue

        current = rows[match_idx]
        signals: dict[str, Any] = {"discovery_confirmed": True}
        if _has_form_d(current):
            existing_acq = str(current.get("acquirer") or "")
            discovered_acq = str(hit.get("acquirer") or "")
            if (
                existing_acq
                and discovered_acq
                and name_key(existing_acq) != name_key(discovered_acq)
            ):
                signals["discovered_acquirer_disagrees"] = discovered_acq
            updated = _with_signal(current, signals=signals)
            rows[match_idx] = updated
            confirmed_existing.append(updated)
            continue

        current_rank = _rank(current.get("confidence"))
        if current_rank >= _rank("high"):
            updated = _with_signal(current, signals=signals)
            rows[match_idx] = updated
            confirmed_existing.append(updated)
            continue
        if current_rank >= _rank("medium"):
            updated = _with_signal(current, confidence="high", signals=signals)
            rows[match_idx] = updated
            promoted.append(updated)
            applied_hits.append(hit)
            continue
        updated = _with_signal(current, confidence="medium", signals=signals)
        rows[match_idx] = updated
        promoted.append(updated)
        applied_hits.append(hit)

    return CollisionResult(
        rows=rows,
        inserted=inserted,
        promoted=promoted,
        confirmed_existing=confirmed_existing,
        applied_hits=applied_hits,
    )


def _discovered_as_event(hit: dict[str, Any]) -> dict[str, Any]:
    event_date = hit.get("event_date") or hit.get("date")
    if event_date == "Unknown":
        event_date = None
    confidence = hit.get("confidence") or "low"
    return {
        "company_name": hit.get("company_name"),
        "acquirer": hit.get("acquirer"),
        "event_date": event_date,
        "confidence": confidence,
        "signals": {
            "discovery_confirmed": True,
            **(hit.get("signals") or {}),
        },
        "form_d_detail": None,
        "source": hit.get("source"),
        "evidence": hit.get("evidence"),
        "value": hit.get("value"),
    }
