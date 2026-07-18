#!/usr/bin/env python3
"""Hydrate SAM.gov descriptions for bounded, evidence-gated opportunity targets."""

import argparse
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.exceptions import APIError, RateLimitError
from sbir_etl.extractors.sam_gov_opportunities import SamGovOpportunitiesExtractor


_NOTICE_TYPES = frozenset({"u", "s", "p", "o", "k", "r"})
_NOTICE_TYPE_NAMES = {
    "presolicitation": "p",
    "pre-solicitation": "p",
    "sources sought": "r",
    "special notice": "s",
    "solicitation": "o",
    "combined synopsis/solicitation": "k",
    "justification (j&a)": "u",
}


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "<na>"} else None


def _needs_description(description: Any, title: Any) -> bool:
    description_text = _text(description)
    title_text = _text(title)
    if description_text is None:
        return True
    normalized_description = " ".join(description_text.lower().split())
    normalized_title = " ".join(title_text.lower().split()) if title_text else None
    return normalized_description == normalized_title


def _ordered_target_ids(candidates: pd.DataFrame) -> list[str]:
    if candidates.empty or "target_id" not in candidates:
        return []
    ranked = candidates.copy()
    confidence = ranked.get("is_high_confidence", pd.Series(False, index=ranked.index))
    ranked["_high"] = confidence.map(
        lambda value: (_text(value) or "").lower() in {"true", "1", "yes"}
    )
    ranked["_score"] = pd.to_numeric(
        ranked.get("candidate_score", pd.Series(index=ranked.index, dtype="float64")),
        errors="coerce",
    ).fillna(-1.0)
    ranked = ranked.sort_values(["_high", "_score"], ascending=False, kind="stable")
    return list(dict.fromkeys(value for value in ranked["target_id"].map(_text) if value))


def _normalized(value: Any) -> str | None:
    text = _text(value)
    return " ".join(text.upper().split()) if text else None


def _field(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name]
    return pd.Series([None] * len(frame), index=frame.index, dtype="object")


def _pre_screen_target_ids(awards: pd.DataFrame, opportunities: pd.DataFrame) -> list[str]:
    """Select description targets using identity, organization, and code gates only."""

    if awards.empty or opportunities.empty:
        return []
    award_ueis = set(_field(awards, "uei", "recipient_uei").map(_normalized).dropna())
    award_agencies = set(_field(awards, "agency").map(_normalized).dropna())
    award_sub_tiers = set(_field(awards, "branch", "sub_agency").map(_normalized).dropna())
    award_offices = set(_field(awards, "office").map(_normalized).dropna())
    award_naics = set(_field(awards, "naics_code", "naics").map(_normalized).dropna())
    award_psc = set(_field(awards, "psc_code", "product_or_service_code").map(_normalized).dropna())
    award_agency = _field(awards, "agency").map(_normalized)
    missing_codes = (
        _field(awards, "naics_code", "naics").map(_text).isna()
        & _field(awards, "psc_code", "product_or_service_code").map(_text).isna()
    )
    missing_code_agencies = set(award_agency.loc[missing_codes].dropna())

    ranked: list[tuple[int, str]] = []
    today = pd.Timestamp.now(tz="UTC").normalize()
    for _, row in opportunities.iterrows():
        target_id = _text(row.get("notice_id"))
        if target_id is None:
            continue
        active = (_text(row.get("active")) or "").lower()
        if active not in {"true", "1", "yes", "active"}:
            continue
        notice_type = (_text(row.get("notice_type_code")) or "").lower()
        if not notice_type:
            notice_type = _NOTICE_TYPE_NAMES.get((_text(row.get("notice_type")) or "").lower(), "")
        if notice_type not in _NOTICE_TYPES:
            continue
        deadline_text = _text(row.get("response_deadline"))
        deadline = (
            pd.to_datetime(deadline_text, errors="coerce", utc=True) if deadline_text else None
        )
        if pd.notna(deadline) and deadline < today:
            continue

        agency = _normalized(row.get("agency"))
        sub_tier = _normalized(row.get("sub_tier"))
        office = _normalized(row.get("office"))
        agency_match = bool(agency and agency in award_agencies)
        sub_tier_match = bool(sub_tier and sub_tier in award_sub_tiers)
        office_match = bool(office and office in award_offices)
        organization_match = agency_match or sub_tier_match or office_match
        exact_uei = bool((uei := _normalized(row.get("awardee_uei"))) and uei in award_ueis)
        naics_match = bool((naics := _normalized(row.get("naics_code"))) and naics in award_naics)
        psc_match = bool((psc := _normalized(row.get("psc_code"))) and psc in award_psc)
        missing_code_fallback = bool(agency and agency in missing_code_agencies)
        if not organization_match or not (
            exact_uei or naics_match or psc_match or missing_code_fallback
        ):
            continue

        priority = (
            (100 if exact_uei else 0)
            + (30 if office_match else 20 if sub_tier_match else 10)
            + (20 if naics_match else 0)
            + (20 if psc_match else 0)
            + (5 if notice_type in {"u", "s", "p"} else 0)
        )
        ranked.append((priority, target_id))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return list(dict.fromkeys(target_id for _priority, target_id in ranked))


def hydrate_candidate_descriptions(
    opportunities: pd.DataFrame,
    candidates: pd.DataFrame,
    fetch_description: Callable[[str | None], str | None],
    *,
    awards: pd.DataFrame | None = None,
    max_records: int = 500,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return opportunities with bounded description hydration and audit counts."""

    if max_records < 0:
        raise ValueError("max_records must be non-negative")
    out = opportunities.copy()
    if "description" not in out:
        out["description"] = None
    if "description_source" not in out:
        out["description_source"] = None

    stats = {
        "candidate_targets": 0,
        "pre_screen_targets": 0,
        "selected_targets": 0,
        "already_substantive": 0,
        "fetch_attempts": 0,
        "hydrated": 0,
        "missing_opportunity": 0,
        "missing_description_url": 0,
        "empty_response": 0,
        "api_failures": 0,
        "rate_limited": 0,
        "cap_reached": 0,
    }
    if "notice_id" not in out:
        stats["missing_opportunity"] = len(_ordered_target_ids(candidates))
        return out, stats

    notice_ids = out["notice_id"].map(_text)
    candidate_target_ids = _ordered_target_ids(candidates)
    pre_screen_target_ids = _pre_screen_target_ids(
        awards if awards is not None else pd.DataFrame(), out
    )
    target_ids = list(dict.fromkeys([*candidate_target_ids, *pre_screen_target_ids]))
    stats["candidate_targets"] = len(candidate_target_ids)
    stats["pre_screen_targets"] = len(pre_screen_target_ids)
    stats["selected_targets"] = len(target_ids)
    for target_id in target_ids:
        matches = out.index[notice_ids == target_id]
        if len(matches) == 0:
            stats["missing_opportunity"] += 1
            continue
        index = matches[0]
        title = out.at[index, "title"] if "title" in out else None
        if not _needs_description(out.at[index, "description"], title):
            stats["already_substantive"] += 1
            continue
        description_url = (
            _text(out.at[index, "description_url"]) if "description_url" in out else None
        )
        if description_url is None:
            stats["missing_description_url"] += 1
            continue
        if stats["fetch_attempts"] >= max_records:
            stats["cap_reached"] = 1
            break
        stats["fetch_attempts"] += 1
        try:
            description = fetch_description(description_url)
        except RateLimitError:
            stats["rate_limited"] = 1
            break
        except APIError:
            stats["api_failures"] += 1
            continue
        if _needs_description(description, title):
            stats["empty_response"] += 1
            continue
        out.loc[matches, "description"] = description
        out.loc[matches, "description_source"] = "sam.gov description endpoint"
        hydrated_at = datetime.now(UTC).isoformat()
        out.loc[matches, "description_retrieved_at"] = hydrated_at
        out.loc[matches, "description_content_hash"] = hashlib.sha256(
            str(description).encode()
        ).hexdigest()
        stats["hydrated"] += 1
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--stats-output", type=Path)
    parser.add_argument("--max-records", type=int, default=500)
    args = parser.parse_args()

    opportunities = _read(args.opportunities)
    awards = _read(args.awards)
    candidates = _read(args.candidates) if args.candidates else pd.DataFrame()
    with SamGovOpportunitiesExtractor() as extractor:
        hydrated, stats = hydrate_candidate_descriptions(
            opportunities,
            candidates,
            extractor.fetch_description,
            awards=awards,
            max_records=args.max_records,
        )
    output = args.output or args.opportunities
    _write(hydrated, output)
    payload = {"output": str(output), **stats}
    stats_output = args.stats_output or output.with_suffix(".hydration.json")
    stats_output.parent.mkdir(parents=True, exist_ok=True)
    stats_output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
