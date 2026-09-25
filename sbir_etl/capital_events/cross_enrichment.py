"""Bidirectional, provenance-aware Form D and M&A-candidate cross-enrichment.

The source files remain immutable.  This module annotates M&A records with
matching Form D evidence and emits a relationship/crosswalk layer for downstream
analysis.  A composite M&A row is an unvalidated public-record candidate, not a
verified legal exit.  It is not itself counted as an independent source; only
the underlying Form D, EFTS, press, or discovery evidence is.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


DEFAULT_LINK_WINDOW_DAYS = 366
CANDIDATE_STATUS = "unvalidated_public_record_candidate"
HIGH_FORM_D_MATCH_TIER = "high"
FORM_D_CHANNEL_AMOUNT_SOLD_MEASURE = "exempt_securities_sold"
FORM_D_AMOUNT_SOLD_MEASURE = "business_combination_associated_exempt_securities_sold"


def organization_key(value: object) -> str:
    """Return the repository's versioned organization identity key."""

    return normalize_company_name(value, profile=CompanyNameProfile.ORGANIZATION_KEY_V1)


def parse_iso_date(value: object) -> date | None:
    """Parse a leading ISO date without guessing other date formats."""

    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _amount(value: object) -> float:
    if not isinstance(value, (str, int, float)):
        return 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _relationship_id(target_key: str, event_date: object, acquirer: object) -> str:
    material = "|".join((target_key, str(event_date or ""), organization_key(acquirer)))
    return "ma_" + hashlib.sha256(material.encode()).hexdigest()[:20]


_SOURCE_CLASS_TOKENS = frozenset({"form_d", "efts", "press", "discovery"})


def _signals(record: dict[str, Any]) -> dict[str, Any]:
    signals = record.get("signals") or {}
    return signals if isinstance(signals, dict) else {}


def _has_discovery_evidence(record: dict[str, Any], signals: dict[str, Any]) -> bool:
    """Recognize both the local discovery payload and the #699 row shape."""

    if (
        signals.get("discovery_confirmed")
        or record.get("discovery_evidence")
        or record.get("source_url")
    ):
        return True
    source = str(record.get("source") or "").strip()
    if not source or not record.get("evidence"):
        return False
    return source.lower() not in _SOURCE_CLASS_TOKENS


def _has_confirmed_press(record: dict[str, Any], signals: dict[str, Any]) -> bool:
    """Count confirmed press evidence only; ignore raw press-wire hit lists."""

    if signals.get("press_confirmed"):
        return True
    evidence = record.get("press_evidence")
    return bool(evidence) and not isinstance(evidence, list)


def evidence_sources(record: dict[str, Any]) -> list[str]:
    """Return underlying source classes for a composite M&A-candidate row."""

    sources: set[str] = set()
    signals = _signals(record)
    if signals.get("form_d_business_combination") or record.get("form_d_detail"):
        sources.add("form_d")
    if record.get("efts_detail") or any(
        value for key, value in signals.items() if str(key).startswith("efts_")
    ):
        sources.add("efts")
    if _has_confirmed_press(record, signals):
        sources.add("press")
    if _has_discovery_evidence(record, signals):
        sources.add("discovery")
    return sorted(sources)


def is_independent_of_form_d(record: dict[str, Any]) -> bool:
    """Whether an M&A candidate has evidence beyond the Form D filing it may reuse."""

    return any(source != "form_d" for source in evidence_sources(record))


def _match_tier(record: dict[str, Any]) -> str:
    return str((record.get("match_confidence") or {}).get("tier") or "").strip().lower()


def _form_d_detail(record: dict[str, Any]) -> dict[str, Any]:
    detail = record.get("form_d_detail")
    return detail if isinstance(detail, dict) else {}


def _originating_accession(detail: dict[str, Any]) -> str:
    for key in ("accession_number", "accession"):
        value = str(detail.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_originating_offering(
    offering: dict[str, Any],
    *,
    originating_accession: str,
    originating_date: date | None,
) -> bool:
    if originating_accession:
        return offering["accession_number"] == originating_accession
    return originating_date is not None and offering["event_date"] == originating_date


def independent_source_count(sources: Iterable[str]) -> int:
    """Count source classes other than Form D."""

    return sum(1 for source in sources if source and source != "form_d")


def relationship_source_classes(row: dict[str, Any]) -> list[str]:
    """Return source classes, including Form D linked during cross-enrichment."""

    sources = {str(source) for source in row.get("evidence_sources") or [] if source}
    accessions = row.get("form_d_accession_numbers") or []
    if accessions or int(row.get("matched_form_d_combination_count") or 0):
        sources.add("form_d")
    return sorted(sources)


def _form_d_offerings(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    offerings: list[dict[str, Any]] = []
    for record in records:
        if _match_tier(record) != HIGH_FORM_D_MATCH_TIER:
            continue
        target_name = str(record.get("company_name") or "").strip()
        target_key = organization_key(target_name)
        if not target_key:
            continue
        record_cik = str(record.get("form_d_cik") or "").lstrip("0")
        match_tier = HIGH_FORM_D_MATCH_TIER
        for offering in record.get("offerings") or []:
            event_date = parse_iso_date(offering.get("filing_date")) or parse_iso_date(
                offering.get("date_of_first_sale")
            )
            offerings.append(
                {
                    "target_name": target_name,
                    "target_key": target_key,
                    "event_date": event_date,
                    "accession_number": str(offering.get("accession_number") or "").strip(),
                    "cik": str(offering.get("cik") or record_cik).lstrip("0"),
                    "amount_sold": _amount(offering.get("total_amount_sold")),
                    "is_business_combination": bool(offering.get("is_business_combination")),
                    "is_amendment": bool(offering.get("is_amendment")),
                    "match_tier": match_tier,
                }
            )
    return offerings


def _within_window(left: date | None, right: date | None, days: int) -> bool:
    return left is not None and right is not None and abs((left - right).days) <= days


def enrich_form_d_and_ma(
    form_d_records: Iterable[dict[str, Any]],
    ma_records: Iterable[dict[str, Any]],
    *,
    link_window_days: int = DEFAULT_LINK_WINDOW_DAYS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return enriched M&A candidates, candidate relationships, and Form D links."""

    offerings = _form_d_offerings(form_d_records)
    by_target: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for offering in offerings:
        by_target[offering["target_key"]].append(offering)

    enriched: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    linked_accessions: set[str] = set()

    for raw_record in ma_records:
        record = dict(raw_record)
        target_name = str(record.get("company_name") or "").strip()
        target_key = organization_key(target_name)
        if not target_key:
            enriched.append(record)
            continue
        event_date = parse_iso_date(record.get("event_date"))
        acquirer = str(record.get("acquirer") or "").strip() or None
        relationship_id = _relationship_id(target_key, record.get("event_date"), acquirer)
        target_offerings = by_target.get(target_key, [])
        sources = evidence_sources(record)
        independent = any(source != "form_d" for source in sources)
        form_d_detail = _form_d_detail(record)
        originating_accession = _originating_accession(form_d_detail)
        originating_date = parse_iso_date(form_d_detail.get("filing_date"))
        allow_window = "form_d" not in sources
        matched_combinations: list[tuple[dict[str, Any], bool]] = []
        seen_accessions: set[str] = set()
        for offering in target_offerings:
            accession = offering["accession_number"]
            if (
                not offering["is_business_combination"]
                or not accession
                or accession in seen_accessions
            ):
                continue
            originating = _is_originating_offering(
                offering,
                originating_accession=originating_accession,
                originating_date=originating_date,
            )
            window_match = allow_window and _within_window(
                offering["event_date"], event_date, link_window_days
            )
            if originating or window_match:
                seen_accessions.add(accession)
                matched_combinations.append((offering, originating))
        after_event = [
            offering
            for offering in target_offerings
            if event_date is not None
            and offering["event_date"] is not None
            and offering["event_date"] > event_date
        ]
        acquirer_offerings = (
            [
                offering
                for offering in by_target.get(organization_key(acquirer), [])
                if event_date is not None
                and offering["event_date"] is not None
                and offering["event_date"] >= event_date
            ]
            if acquirer
            else []
        )

        provenance = {
            "relationship_id": relationship_id,
            "target_key": target_key,
            "candidate_status": CANDIDATE_STATUS,
            "legal_event_validated": False,
            "deal_terms_captured": False,
            "enterprise_value_observed": False,
            "form_d_amount_sold_measure": FORM_D_AMOUNT_SOLD_MEASURE,
            "form_d_amount_sold_is_deal_value": False,
            "evidence_sources": sources,
            "source_class_count": len(sources),
            "independent_source_count": independent_source_count(sources),
            "independent_of_form_d": independent,
            "same_source_only": sources == ["form_d"],
            "form_d_accession_numbers": sorted(
                {item["accession_number"] for item, _ in matched_combinations}
            ),
            "form_d_ciks": sorted({item["cik"] for item, _ in matched_combinations if item["cik"]}),
            "matched_form_d_combination_count": len(matched_combinations),
            "post_event_target_form_d_raw_filing_count": len(after_event),
            "post_event_target_form_d_raw_amount_sum": sum(
                item["amount_sold"] for item in after_event
            ),
            "acquirer_form_d_accession_numbers": sorted(
                {
                    item["accession_number"]
                    for item in acquirer_offerings
                    if item["accession_number"]
                }
            ),
            "acquirer_alias_candidate": {
                "name": acquirer,
                "relationship": "candidate_acquired_by",
                "valid_from": event_date.isoformat() if event_date else None,
                "auto_merge": False,
            }
            if acquirer
            else None,
        }
        record["cross_enrichment"] = provenance
        enriched.append(record)
        relationships.append(
            {
                "relationship_id": relationship_id,
                "target_name": target_name,
                "target_key": target_key,
                "acquirer_name": acquirer,
                "acquirer_key": organization_key(acquirer),
                "event_date": event_date.isoformat() if event_date else None,
                "relationship_type": (
                    "candidate_acquired_by" if acquirer else "candidate_business_combination"
                ),
                "confidence": record.get("confidence"),
                **provenance,
            }
        )
        for offering, originating in matched_combinations:
            accession = offering["accession_number"]
            linked_accessions.add(accession)
            crosswalk.append(
                {
                    "accession_number": accession,
                    "form_d_cik": offering["cik"],
                    "target_name": target_name,
                    "relationship_id": relationship_id,
                    "acquirer_name": acquirer,
                    "link_status": "linked",
                    "legal_event_validated": False,
                    "evidence_role": "originating_evidence"
                    if originating
                    else "independent_corroboration",
                    "confidence_credit": not originating,
                    "match_tier": offering["match_tier"],
                    "date_distance_days": abs((offering["event_date"] - event_date).days)
                    if offering["event_date"] and event_date
                    else None,
                }
            )

    for offering in offerings:
        accession = offering["accession_number"]
        if offering["is_business_combination"] and accession and accession not in linked_accessions:
            crosswalk.append(
                {
                    "accession_number": accession,
                    "form_d_cik": offering["cik"],
                    "target_name": offering["target_name"],
                    "relationship_id": None,
                    "acquirer_name": None,
                    "link_status": "unlinked",
                    "legal_event_validated": False,
                    "evidence_role": "form_d_only",
                    "confidence_credit": False,
                    "match_tier": offering["match_tier"],
                    "date_distance_days": None,
                }
            )
    relationship_by_id: dict[str, dict[str, Any]] = {}
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    for relationship in relationships:
        relationship_id = relationship["relationship_id"]
        current = relationship_by_id.get(relationship_id)
        if current is None:
            relationship_by_id[relationship_id] = relationship
            continue
        sources = sorted(set(current["evidence_sources"]) | set(relationship["evidence_sources"]))
        current["evidence_sources"] = sources
        current["source_class_count"] = len(sources)
        current["independent_source_count"] = independent_source_count(sources)
        current["independent_of_form_d"] = any(source != "form_d" for source in sources)
        current["same_source_only"] = sources == ["form_d"]
        for field_name in (
            "form_d_accession_numbers",
            "form_d_ciks",
            "acquirer_form_d_accession_numbers",
        ):
            current[field_name] = sorted(set(current[field_name]) | set(relationship[field_name]))
        current["matched_form_d_combination_count"] = len(current["form_d_accession_numbers"])
        current["post_event_target_form_d_raw_filing_count"] = max(
            current["post_event_target_form_d_raw_filing_count"],
            relationship["post_event_target_form_d_raw_filing_count"],
        )
        current["post_event_target_form_d_raw_amount_sum"] = max(
            current["post_event_target_form_d_raw_amount_sum"],
            relationship["post_event_target_form_d_raw_amount_sum"],
        )
        if confidence_rank.get(str(relationship.get("confidence")), -1) > confidence_rank.get(
            str(current.get("confidence")), -1
        ):
            current["confidence"] = relationship.get("confidence")

    crosswalk_by_key: dict[tuple[str, str | None], dict[str, Any]] = {}
    for link in crosswalk:
        crosswalk_key = (link["accession_number"], link["relationship_id"])
        current_link = crosswalk_by_key.get(crosswalk_key)
        if current_link is None or link["confidence_credit"]:
            crosswalk_by_key[crosswalk_key] = link
    return enriched, list(relationship_by_id.values()), list(crosswalk_by_key.values())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read nonblank JSONL records."""

    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write JSONL deterministically and return the row count."""

    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in materialized:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return len(materialized)


def iter_relationship_alias_candidates(
    relationships: Iterable[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Yield review-only candidate relationships; never imply a verified acquisition."""

    for relationship in relationships:
        candidate = relationship.get("acquirer_alias_candidate")
        if candidate:
            yield {
                "relationship_id": relationship["relationship_id"],
                "target_key": relationship["target_key"],
                **candidate,
            }
