#!/usr/bin/env python3
"""Compare post-Phase-II commercialization signals for NASA, Air Force, and DOE.

Epistemic tier: exploratory. Outputs are non-citable.

The firm-agency cohort is anchored on each firm's first SBIR or STTR Phase II
award. Three observed channels remain separate: federal prime contracts, SEC
Form D offerings, and unvalidated public-filing M&A candidates. A missing signal is not a
negative commercialization finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sbir_etl.capital_events.cross_enrichment import (
    CANDIDATE_STATUS,
    FORM_D_CHANNEL_AMOUNT_SOLD_MEASURE,
    evidence_sources,
    is_independent_of_form_d,
)
from sbir_etl.identity import (
    CanonicalMergePolicy,
    CompanyNameProfile,
    build_canonical_company_map,
    normalize_company_name,
)
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CUTOFF = date(2024, 12, 31)
DEFAULT_HORIZONS = (3, 5, 10)
PRIMARY_HORIZON = 5
BOOTSTRAP_ITERATIONS = 1_000
RANDOM_SEED = 42
FORM_D_START = date(2009, 1, 1)

AGENCY_LABELS = {
    "NASA": "National Aeronautics and Space Administration",
    "Air Force": "Department of Defense / Air Force",
    "DOE": "Department of Energy (including ARPA-E)",
}

EXCLUDED_FORM_D_INDUSTRIES = frozenset(
    {
        "Insurance",
        "Lodging and Conventions",
        "Other Travel",
        "Pooled Investment Fund",
        "Restaurants",
        "Retailing",
        "Tourism and Travel Services",
    }
)

PHASE_I_II_RESEARCH_MARKERS = frozenset(
    {
        "SR1",
        "SR2",
        "ST1",
        "ST2",
        "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE I ACTION",
        "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION",
        "SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE I",
        "SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE II",
    }
)

PHASE_III_RESEARCH_MARKERS = frozenset(
    {
        "SR3",
        "ST3",
        "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE III ACTION",
        "SMALL TECHNOLOGY TRANSFER RESEARCH PROGRAM PHASE III",
    }
)

_BLANK_IDENTIFIERS = frozenset({"", "NAN", "NONE", "NULL", "<NA>"})


def parse_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: object) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def normalized_name(value: object) -> str:
    return normalize_company_name(value, profile=CompanyNameProfile.ORGANIZATION_KEY_V1)


def clean_identifier(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().upper()
    return "" if text in _BLANK_IDENTIFIERS else text


def normalize_piid(value: object) -> str:
    """Dash-stripping PIID key shared with award-file vs USAspending matching."""
    text = clean_identifier(value)
    return re.sub(r"[^A-Z0-9]", "", text) if text else ""


def uei_alias(value: object) -> str:
    return normalize_uei(value) or ""


def duns_alias(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return normalize_duns(text) or ""


def first_nonblank(*values: object) -> object | None:
    for value in values:
        if value is None or pd.isna(value) or not str(value).strip():
            continue
        return value
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def agency_label(row: pd.Series) -> str | None:
    agency = str(first_nonblank(row.get("Agency")) or "").strip()
    branch = str(first_nonblank(row.get("Branch")) or "").strip()
    if agency == "National Aeronautics and Space Administration":
        return "NASA"
    if agency == "Department of Defense" and branch == "Air Force":
        return "Air Force"
    if agency == "Department of Energy":
        return "DOE"
    return None


@dataclass(frozen=True)
class CohortData:
    firms: pd.DataFrame
    phase_ii_awards: pd.DataFrame
    alias_to_firm: dict[str, str]
    phase_i_ii_contract_ids: frozenset[str]
    raw_company_names: frozenset[str]


def build_cohort(awards_path: Path, cutoff: date) -> CohortData:
    columns = [
        "Company",
        "Agency",
        "Branch",
        "Phase",
        "Program",
        "Contract",
        "Proposal Award Date",
        "Award Year",
        "Award Amount",
        "UEI",
        "Duns",
    ]
    awards = pd.read_csv(awards_path, usecols=columns, dtype="string", low_memory=False)
    awards["agency_label"] = awards.apply(agency_label, axis=1)
    awards = awards[awards["Program"].str.strip().isin({"SBIR", "STTR"})].copy()
    awards["award_date"] = awards["Proposal Award Date"].map(parse_date)
    missing_date = awards["award_date"].isna()
    awards.loc[missing_date, "award_date"] = awards.loc[missing_date, "Award Year"].map(
        lambda value: date(int(float(value)), 7, 1)
        if value is not None and not pd.isna(value) and str(value).strip()
        else None
    )
    awards = awards[awards["award_date"].map(lambda value: value is not None and value <= cutoff)]
    awards["name_alias"] = awards["Company"].map(normalized_name)
    awards["uei_alias"] = awards["UEI"].map(uei_alias)
    awards["duns_alias"] = awards["Duns"].map(duns_alias)
    awards["award_amount"] = awards["Award Amount"].map(parse_amount)
    awards["canonical_name"] = awards["Company"].map(
        lambda value: normalize_company_name(value, profile=CompanyNameProfile.MATCHING_V1)
    )
    awards = awards[awards[["uei_alias", "duns_alias", "canonical_name"]].ne("").any(axis=1)].copy()

    # Reuse the frozen repository-wide pre-load merge policy. In particular, an
    # identifier-bearing row self-matches before name matching, so equal names do
    # not collapse records carrying incompatible UEI/DUNS identities.
    identity_awards = pd.DataFrame(
        {
            "company_name": awards["Company"],
            "company_uei": awards["uei_alias"].replace("", None),
            "company_duns": awards["duns_alias"].replace("", None),
        }
    )
    canonical_map = build_canonical_company_map(
        identity_awards, policy=CanonicalMergePolicy.PRELOAD_V1
    )
    awards["firm_original_key"] = "NAME:" + awards["canonical_name"]
    has_duns = awards["duns_alias"].ne("")
    awards.loc[has_duns, "firm_original_key"] = "DUNS:" + awards.loc[has_duns, "duns_alias"]
    has_uei = awards["uei_alias"].ne("")
    awards.loc[has_uei, "firm_original_key"] = "UEI:" + awards.loc[has_uei, "uei_alias"]
    awards["firm_id"] = (
        awards["firm_original_key"].map(canonical_map).fillna(awards["firm_original_key"])
    )

    phase2 = awards[
        awards["agency_label"].notna() & (awards["Phase"].str.strip() == "Phase II")
    ].copy()
    anchors = phase2.groupby(["agency_label", "firm_id"], as_index=False).agg(
        anchor_date=("award_date", "min"),
        phase_ii_awards=("Company", "size"),
        phase_ii_dollars=("award_amount", "sum"),
        display_name=("Company", "first"),
    )
    anchors = anchors[anchors["anchor_date"] >= FORM_D_START].copy()

    cohort_firm_ids = set(anchors["firm_id"].astype(str))
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    for row in awards.itertuples(index=False):
        aliases = {
            f"uei:{row.uei_alias}" if row.uei_alias else "",
            f"duns:{row.duns_alias}" if row.duns_alias else "",
            f"name:{row.name_alias}" if row.name_alias else "",
        }
        for alias in aliases:
            if alias:
                alias_candidates[alias].add(str(row.firm_id))
    alias_to_firm: dict[str, str] = {}
    for alias, firm_ids in alias_candidates.items():
        if len(firm_ids) != 1:
            continue
        firm_id = next(iter(firm_ids))
        if firm_id in cohort_firm_ids:
            alias_to_firm[alias] = firm_id

    phase_i_ii = awards[
        awards["firm_id"].astype(str).isin(cohort_firm_ids)
        & awards["Phase"].str.strip().isin({"Phase I", "Phase II"})
    ]
    contract_ids = frozenset(
        normalize_piid(value) for value in phase_i_ii["Contract"].tolist() if normalize_piid(value)
    )
    raw_company_names = frozenset(
        str(value).strip().upper()
        for value in awards.loc[awards["firm_id"].astype(str).isin(cohort_firm_ids), "Company"]
        if value is not None and not pd.isna(value) and str(value).strip()
    )
    phase_ii_awards = phase2[["agency_label", "firm_id", "award_date", "award_amount"]].copy()
    return CohortData(
        anchors.reset_index(drop=True),
        phase_ii_awards.reset_index(drop=True),
        alias_to_firm,
        contract_ids,
        raw_company_names,
    )


def match_firm(
    *,
    uei: object = None,
    duns: object = None,
    name: object = None,
    alias_to_firm: dict[str, str],
) -> tuple[str | None, str | None]:
    candidates = (
        ("uei", uei_alias(uei)),
        ("duns", duns_alias(duns)),
        ("name", normalized_name(name)),
    )
    for basis, value in candidates:
        if value and (firm_id := alias_to_firm.get(f"{basis}:{value}")):
            return firm_id, basis
    return None, None


def is_phase_i_ii_research(value: object) -> bool:
    marker = str(first_nonblank(value) or "").strip().upper()
    return marker in PHASE_I_II_RESEARCH_MARKERS


def is_phase_iii_research(value: object) -> bool:
    marker = str(first_nonblank(value) or "").strip().upper()
    return marker in PHASE_III_RESEARCH_MARKERS


def is_excluded_phase_i_ii_action(
    research: object, piid: str, phase_i_ii_contract_ids: frozenset[str]
) -> bool:
    if is_phase_i_ii_research(research):
        return True
    return bool(piid) and piid in phase_i_ii_contract_ids and not is_phase_iii_research(research)


def load_contract_events(
    paths: Iterable[Path], cohort: CohortData, cutoff: date
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    stats: defaultdict[str, int] = defaultdict(int)
    for path in paths:
        frame = pd.read_parquet(path)
        for row in frame.to_dict("records"):
            stats["transactions_read"] += 1
            event_date = parse_date(row.get("action_date"))
            if event_date is None or event_date > cutoff:
                stats["invalid_or_after_cutoff"] += 1
                continue
            piid = normalize_piid(first_nonblank(row.get("piid"), row.get("contract_id")))
            if is_excluded_phase_i_ii_action(
                row.get("research"), piid, cohort.phase_i_ii_contract_ids
            ):
                stats["phase_i_ii_excluded"] += 1
                continue
            firm_id, basis = match_firm(
                uei=first_nonblank(row.get("vendor_uei"), row.get("recipient_uei")),
                duns=first_nonblank(row.get("vendor_duns"), row.get("recipient_unique_id")),
                name=first_nonblank(row.get("vendor_name"), row.get("recipient_name")),
                alias_to_firm=cohort.alias_to_firm,
            )
            if firm_id is None:
                stats["unmatched"] += 1
                continue
            amount = parse_amount(
                row.get("obligation_amount")
                if "obligation_amount" in row
                else row.get("federal_action_obligation")
            )
            rows.append(
                {
                    "firm_id": firm_id,
                    "event_date": event_date,
                    "amount": amount,
                    "identity_basis": basis,
                    "source_name": first_nonblank(
                        row.get("vendor_name"), row.get("recipient_name")
                    ),
                    "piid": piid,
                    "research_marker": first_nonblank(row.get("research")),
                    "awarding_agency": first_nonblank(
                        row.get("agency"), row.get("awarding_toptier_agency_name")
                    ),
                    "awarding_subagency": first_nonblank(
                        row.get("sub_agency"), row.get("awarding_subtier_agency_name")
                    ),
                    "event_key": first_nonblank(
                        row.get("transaction_unique_id"), row.get("contract_id"), piid
                    ),
                }
            )
            stats["matched"] += 1
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.drop_duplicates(subset=["event_key", "firm_id"])
    return result, dict(stats)


def form_d_cik(value: object) -> str:
    raw_cik = clean_identifier(value)
    return raw_cik.lstrip("0") or ("0" if raw_cik else "")


def offering_series_key(offering: dict[str, Any]) -> tuple[str, str, tuple[str, ...]] | None:
    cik = form_d_cik(offering.get("cik"))
    first_sale = parse_date(offering.get("date_of_first_sale"))
    securities = tuple(
        sorted(str(value).strip().lower() for value in offering.get("securities_types", []))
    )
    if not cik or first_sale is None:
        return None
    return cik, first_sale.isoformat(), securities


def quarantine_ambiguous_form_d(
    events: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop offerings whose accession or CIK is credited to more than one firm."""
    empty_audit = {
        "ambiguous_accessions_quarantined": 0,
        "ambiguous_ciks_quarantined": 0,
        "ambiguous_event_rows_dropped": 0,
    }
    if events.empty:
        return events, empty_audit
    drop = pd.Series(False, index=events.index)
    keys = events["event_key"].astype(str)
    real_accession = ~keys.str.startswith("no-accession:")
    accession_counts = (
        events.loc[real_accession].groupby("event_key", dropna=False)["firm_id"].nunique()
        if real_accession.any()
        else pd.Series(dtype="int64")
    )
    conflict_accessions = accession_counts[accession_counts > 1].index
    if len(conflict_accessions):
        drop |= events["event_key"].isin(conflict_accessions)
    ciks = events["cik"].fillna("").astype(str).str.strip()
    has_cik = ciks != ""
    cik_frame = events.loc[has_cik].assign(cik=ciks[has_cik])
    cik_counts = (
        cik_frame.groupby("cik", dropna=False)["firm_id"].nunique()
        if not cik_frame.empty
        else pd.Series(dtype="int64")
    )
    conflict_ciks = cik_counts[cik_counts > 1].index
    if len(conflict_ciks):
        drop |= ciks.isin(conflict_ciks)
    audit = {
        "ambiguous_accessions_quarantined": int(len(conflict_accessions)),
        "ambiguous_ciks_quarantined": int(len(conflict_ciks)),
        "ambiguous_event_rows_dropped": int(drop.sum()),
    }
    return events.loc[~drop].copy(), audit


def load_form_d_events(
    path: Path, cohort: CohortData, cutoff: date
) -> tuple[pd.DataFrame, dict[str, Any]]:
    events: list[dict[str, Any]] = []
    audit: defaultdict[str, float] = defaultdict(float)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            firm_id, basis = match_firm(
                name=record.get("company_name"), alias_to_firm=cohort.alias_to_firm
            )
            if firm_id is None:
                continue
            tier = str(record.get("match_confidence", {}).get("tier") or "").lower()
            if tier not in {"high", "medium"}:
                continue
            offerings = [
                item
                for item in record.get("offerings", [])
                if item.get("industry_group") not in EXCLUDED_FORM_D_INDUSTRIES
                and (
                    parse_date(item.get("date_of_first_sale"))
                    or parse_date(item.get("filing_date"))
                )
                and (
                    parse_date(item.get("date_of_first_sale"))
                    or parse_date(item.get("filing_date"))
                )
                <= cutoff
            ]
            audit["legacy_filing_count"] += len(offerings)
            audit["legacy_summed_amount_sold"] += sum(
                parse_amount(item.get("total_amount_sold")) for item in offerings
            )
            by_series: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
            standalone: list[dict[str, Any]] = []
            for offering in offerings:
                key = offering_series_key(offering)
                if key is None:
                    if offering.get("is_amendment"):
                        audit["unmatched_amendments_excluded"] += 1
                        continue
                    standalone.append(offering)
                    continue
                current = by_series.get(key)
                if current is None or str(offering.get("filing_date") or "") > str(
                    current.get("filing_date") or ""
                ):
                    by_series[key] = offering
            collapsed = list(by_series.values()) + standalone
            audit["collapsed_offering_count"] += len(collapsed)
            audit["collapsed_amount_sold"] += sum(
                parse_amount(item.get("total_amount_sold")) for item in collapsed
            )
            for offering in collapsed:
                event_date = parse_date(offering.get("date_of_first_sale")) or parse_date(
                    offering.get("filing_date")
                )
                events.append(
                    {
                        "firm_id": firm_id,
                        "event_date": event_date,
                        "amount": parse_amount(offering.get("total_amount_sold")),
                        "identity_basis": basis,
                        "confidence": tier,
                        "event_key": offering.get("accession_number"),
                        "cik": form_d_cik(offering.get("cik")),
                    }
                )
    result = pd.DataFrame(events)
    if not result.empty:
        keys = result["event_key"]
        missing = keys.isna() | keys.astype(str).str.strip().isin({"", "None", "nan", "NaN"})
        if missing.any():
            result.loc[missing, "event_key"] = [
                f"no-accession:{index}" for index in result.index[missing]
            ]
        result = result.drop_duplicates(subset=["firm_id", "event_key"])
        result, quarantined = quarantine_ambiguous_form_d(result)
        audit.update(quarantined)
    return result, dict(audit)


def ma_provenance_audit_bucket(sources: Iterable[str]) -> str:
    """Split Form-D-only rows from rows with no recognized underlying source."""

    source_set = {str(source) for source in sources if source}
    if "form_d" in source_set and all(source == "form_d" for source in source_set):
        return "form_d_only"
    if not source_set:
        return "unclassified"
    return "independent_of_form_d"


def load_ma_events(
    path: Path, cohort: CohortData, cutoff: date
) -> tuple[pd.DataFrame, dict[str, int]]:
    events: list[dict[str, Any]] = []
    stats: defaultdict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            event_date = parse_date(record.get("event_date"))
            if event_date is None or event_date > cutoff:
                stats["invalid_or_after_cutoff"] += 1
                continue
            confidence = str(record.get("confidence") or "").lower()
            if confidence not in {"high", "medium"}:
                stats["low_confidence_excluded"] += 1
                continue
            firm_id, basis = match_firm(
                name=record.get("company_name"), alias_to_firm=cohort.alias_to_firm
            )
            if firm_id is None:
                stats["unmatched"] += 1
                continue
            cross_enrichment = record.get("cross_enrichment") or {}
            sources = cross_enrichment.get("evidence_sources") or evidence_sources(record)
            independent = cross_enrichment.get("independent_of_form_d")
            if independent is None:
                independent = is_independent_of_form_d(record)
            stats[ma_provenance_audit_bucket(sources)] += 1
            events.append(
                {
                    "firm_id": firm_id,
                    "event_date": event_date,
                    "amount": 0.0,
                    "identity_basis": basis,
                    "confidence": confidence,
                    "acquirer": record.get("acquirer"),
                    "evidence_sources": ",".join(sorted(sources)),
                    "independent_of_form_d": bool(independent),
                    "relationship_id": cross_enrichment.get("relationship_id"),
                }
            )
            stats["matched"] += 1
    frame = pd.DataFrame(events)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["firm_id", "event_date", "acquirer"])
    return frame, dict(stats)


def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def bootstrap_ratio(firm_rows: pd.DataFrame, *, iterations: int, seed: int) -> tuple[float, float]:
    if firm_rows.empty or firm_rows["phase_ii_dollars"].sum() <= 0:
        return math.nan, math.nan
    raised = firm_rows["observed_dollars"].to_numpy(dtype=float)
    sbir = firm_rows["phase_ii_dollars"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    estimates = np.empty(iterations)
    for index in range(iterations):
        sample = rng.integers(0, len(firm_rows), len(firm_rows))
        denominator = sbir[sample].sum()
        estimates[index] = raised[sample].sum() / denominator if denominator > 0 else math.nan
    return float(np.nanpercentile(estimates, 2.5)), float(np.nanpercentile(estimates, 97.5))


def same_agency_contract_mask(events: pd.DataFrame, agency: str) -> pd.Series:
    top = events.get("awarding_agency", pd.Series("", index=events.index)).fillna("").astype(str)
    sub = events.get("awarding_subagency", pd.Series("", index=events.index)).fillna("").astype(str)
    if agency == "NASA":
        return top.str.contains("National Aeronautics", case=False, regex=False)
    if agency == "DOE":
        return top.str.contains("Department of Energy", case=False, regex=False)
    return top.str.contains("Department of Defense", case=False, regex=False) & sub.str.contains(
        "Air Force", case=False, regex=False
    )


def summarize_channel(
    eligible: pd.DataFrame,
    events: pd.DataFrame,
    *,
    agency: str,
    horizon: int,
    channel: str,
    confidence_filter: str,
    cutoff: date,
) -> tuple[dict[str, Any], pd.DataFrame]:
    per_firm: list[dict[str, Any]] = []
    empty_events = events.iloc[0:0] if not events.empty else events
    events_by_firm: dict[Any, pd.DataFrame] = {}
    if not events.empty:
        for firm_id, group in events.groupby("firm_id", sort=False):
            events_by_firm[firm_id] = group
    for row in eligible.itertuples(index=False):
        horizon_end = min(add_years(row.anchor_date, horizon), cutoff)
        firm_events = events_by_firm.get(row.firm_id, empty_events)
        matched = (
            firm_events[
                (firm_events["event_date"] > row.anchor_date)
                & (firm_events["event_date"] <= horizon_end)
            ]
            if not firm_events.empty
            else firm_events
        )
        if confidence_filter == "high" and not matched.empty and "confidence" in matched:
            matched = matched[matched["confidence"] == "high"]
        observed_dollars = max(float(matched["amount"].sum()), 0.0) if not matched.empty else 0.0
        same_agency_dollars = 0.0
        if channel == "federal_contract" and not matched.empty:
            same_net = float(
                matched.loc[same_agency_contract_mask(matched, agency), "amount"].sum()
            )
            same_agency_dollars = min(max(same_net, 0.0), observed_dollars)
        if channel in {"federal_contract", "form_d"}:
            has_signal = observed_dollars > 0
            positive_events = matched[matched["amount"] > 0] if not matched.empty else matched
            first_date = positive_events["event_date"].min() if has_signal else None
        else:
            has_signal = not matched.empty
            first_date = matched["event_date"].min() if has_signal else None
        independent_signal = has_signal
        if channel == "ma" and has_signal:
            independent_signal = bool(
                matched.get("independent_of_form_d", pd.Series(False, index=matched.index)).any()
            )
        per_firm.append(
            {
                "agency": agency,
                "horizon_years": horizon,
                "channel": channel,
                "confidence_filter": confidence_filter,
                "firm_id": row.firm_id,
                "anchor_date": row.anchor_date,
                "phase_ii_dollars": float(row.phase_ii_dollars),
                "has_signal": has_signal,
                "independent_signal": independent_signal,
                "observed_dollars": observed_dollars,
                "same_agency_dollars": same_agency_dollars,
                "first_event_date": first_date,
                "latency_days": (first_date - row.anchor_date).days if first_date else None,
            }
        )
    firm_frame = pd.DataFrame(per_firm)
    successes = int(firm_frame["has_signal"].sum()) if not firm_frame.empty else 0
    denominator = len(firm_frame)
    ci_low, ci_high = wilson_interval(successes, denominator)
    total_sbir = float(firm_frame["phase_ii_dollars"].sum()) if denominator else 0.0
    total_observed = float(firm_frame["observed_dollars"].sum()) if denominator else 0.0
    same_agency_dollars = (
        float(firm_frame["same_agency_dollars"].sum())
        if denominator and "same_agency_dollars" in firm_frame
        else 0.0
    )
    positive = firm_frame[firm_frame["observed_dollars"] > 0] if denominator else firm_frame
    boot_low, boot_high = bootstrap_ratio(
        firm_frame,
        iterations=BOOTSTRAP_ITERATIONS,
        seed=RANDOM_SEED + horizon + sum(ord(char) for char in agency + channel),
    )
    record = {
        "agency": agency,
        "agency_definition": AGENCY_LABELS[agency],
        "horizon_years": horizon,
        "channel": channel,
        "confidence_filter": confidence_filter,
        "eligible_firms": denominator,
        "firms_with_signal": successes,
        "firms_with_independent_signal": int(firm_frame["independent_signal"].sum())
        if denominator
        else 0,
        "rate": successes / denominator if denominator else math.nan,
        "rate_ci_low": ci_low,
        "rate_ci_high": ci_high,
        "phase_ii_dollars": total_sbir,
        "observed_dollars": total_observed,
        "same_agency_observed_dollars": same_agency_dollars,
        "same_agency_dollar_share": same_agency_dollars / total_observed
        if total_observed
        else math.nan,
        "dollars_per_phase_ii_dollar": total_observed / total_sbir if total_sbir else math.nan,
        "leverage_ci_low": boot_low,
        "leverage_ci_high": boot_high,
        "conditional_firm_median_dollars": float(positive["observed_dollars"].median())
        if not positive.empty
        else 0.0,
        "median_latency_years": float(
            firm_frame.loc[firm_frame["has_signal"], "latency_days"].median() / 365.25
        )
        if successes
        else math.nan,
    }
    return record, firm_frame


def build_channel_overlap(firm_frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize independent five-year pathways without double-counting Form D-derived M&A."""

    primary = firm_frame[
        (firm_frame["horizon_years"] == PRIMARY_HORIZON)
        & (
            (firm_frame["channel"] == "federal_contract")
            | (firm_frame["confidence_filter"] == "high")
        )
    ]
    overlap = primary.pivot_table(
        index=["agency", "firm_id"],
        columns="channel",
        values="has_signal",
        aggfunc="max",
        fill_value=False,
    ).reset_index()
    for channel in ("federal_contract", "form_d", "ma"):
        if channel not in overlap:
            overlap[channel] = False
    ma_primary = primary[primary["channel"] == "ma"]
    if ma_primary.empty:
        ma_independent = pd.DataFrame(columns=["agency", "firm_id", "ma_independent"])
    else:
        ma_independent = (
            ma_primary.pivot_table(
                index=["agency", "firm_id"],
                values="independent_signal",
                aggfunc="max",
                fill_value=False,
            )
            .rename(columns={"independent_signal": "ma_independent"})
            .reset_index()
        )
    overlap = overlap.merge(ma_independent, on=["agency", "firm_id"], how="left")
    overlap["ma_independent"] = overlap["ma_independent"].fillna(False).astype(bool)
    overlap["ma_any_signal"] = overlap["ma"].astype(bool)
    overlap["ma_same_source_only"] = overlap["ma_any_signal"] & ~overlap["ma_independent"]
    overlap["pathway"] = overlap.apply(
        lambda row: "+".join(
            channel
            for channel in ("federal_contract", "form_d", "ma")
            if row[channel if channel != "ma" else "ma_independent"]
        )
        or "no_observed_signal",
        axis=1,
    )
    overlap_summary = overlap.groupby(["agency", "pathway"], as_index=False).agg(
        firms=("firm_id", "size"),
        ma_any_signal_firms=("ma_any_signal", "sum"),
        ma_same_source_only_firms=("ma_same_source_only", "sum"),
    )
    return overlap_summary


def build_outputs(
    cohort: CohortData,
    contracts: pd.DataFrame,
    form_d: pd.DataFrame,
    ma: pd.DataFrame,
    *,
    cutoff: date,
    horizons: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summaries: list[dict[str, Any]] = []
    firm_results: list[pd.DataFrame] = []
    for agency in AGENCY_LABELS:
        agency_cohort = cohort.firms[cohort.firms["agency_label"] == agency]
        for horizon in horizons:
            eligible = agency_cohort[
                agency_cohort["anchor_date"].map(
                    lambda value, years=horizon: add_years(value, years) <= cutoff
                )
            ].copy()
            eligible = eligible.drop(columns=["phase_ii_dollars"], errors="ignore")
            phase_ii_awards = cohort.phase_ii_awards[
                cohort.phase_ii_awards["agency_label"] == agency
            ].merge(
                eligible[["firm_id", "anchor_date"]],
                on="firm_id",
                how="inner",
                validate="many_to_one",
            )
            phase_ii_awards = phase_ii_awards[
                phase_ii_awards.apply(
                    lambda row, years=horizon: row["award_date"]
                    <= add_years(row["anchor_date"], years),
                    axis=1,
                )
            ]
            horizon_dollars = phase_ii_awards.groupby("firm_id")["award_amount"].sum()
            eligible["phase_ii_dollars"] = eligible["firm_id"].map(horizon_dollars).fillna(0.0)
            channel_specs = (
                ("federal_contract", contracts, "all"),
                ("form_d", form_d, "high"),
                ("form_d", form_d, "high_medium"),
                ("ma", ma, "high"),
                ("ma", ma, "high_medium"),
            )
            for channel, events, confidence_filter in channel_specs:
                summary, firms = summarize_channel(
                    eligible,
                    events,
                    agency=agency,
                    horizon=horizon,
                    channel=channel,
                    confidence_filter=confidence_filter,
                    cutoff=cutoff,
                )
                summaries.append(summary)
                firm_results.append(firms)
    summary_frame = pd.DataFrame(summaries)
    firm_frame = pd.concat(firm_results, ignore_index=True)
    return summary_frame, firm_frame, build_channel_overlap(firm_frame)


def build_vintage_diagnostics(firm_results: pd.DataFrame) -> pd.DataFrame:
    primary = firm_results[
        (firm_results["channel"] == "federal_contract")
        | (firm_results["confidence_filter"] == "high")
    ].copy()
    primary["anchor_year"] = primary["anchor_date"].map(lambda value: value.year)
    records = []
    for keys, group in primary.groupby(
        ["agency", "horizon_years", "channel", "confidence_filter", "anchor_year"]
    ):
        agency, horizon, channel, confidence, anchor_year = keys
        denominator = len(group)
        successes = int(group["has_signal"].sum())
        phase_ii_dollars = float(group["phase_ii_dollars"].sum())
        observed_dollars = float(group["observed_dollars"].sum())
        records.append(
            {
                "agency": agency,
                "horizon_years": horizon,
                "channel": channel,
                "confidence_filter": confidence,
                "anchor_year": anchor_year,
                "eligible_firms": denominator,
                "firms_with_signal": successes,
                "rate": successes / denominator if denominator else math.nan,
                "phase_ii_dollars": phase_ii_dollars,
                "observed_dollars": observed_dollars,
                "dollars_per_phase_ii_dollar": observed_dollars / phase_ii_dollars
                if phase_ii_dollars
                else math.nan,
            }
        )
    return pd.DataFrame(records)


def build_air_force_era_diagnostics(firm_results: pd.DataFrame) -> pd.DataFrame:
    frame = firm_results[
        (firm_results["agency"] == "Air Force")
        & (
            (firm_results["channel"] == "federal_contract")
            | (firm_results["confidence_filter"] == "high")
        )
    ].copy()
    frame["era"] = frame["anchor_date"].map(
        lambda value: "2009-2016" if value.year < 2017 else "2017+"
    )
    return (
        frame.groupby(["horizon_years", "channel", "confidence_filter", "era"], as_index=False)
        .agg(
            eligible_firms=("firm_id", "size"),
            firms_with_signal=("has_signal", "sum"),
            phase_ii_dollars=("phase_ii_dollars", "sum"),
            observed_dollars=("observed_dollars", "sum"),
        )
        .assign(
            rate=lambda value: value["firms_with_signal"] / value["eligible_firms"],
            dollars_per_phase_ii_dollar=lambda value: value["observed_dollars"]
            / value["phase_ii_dollars"],
        )
    )


def build_linkage_audit(
    contracts: pd.DataFrame, form_d: pd.DataFrame, ma: pd.DataFrame
) -> pd.DataFrame:
    frames = []
    for channel, events in (("federal_contract", contracts), ("form_d", form_d), ("ma", ma)):
        if events.empty:
            continue
        grouped = (
            events.assign(channel=channel)
            .groupby(["channel", "identity_basis"], as_index=False)
            .agg(event_rows=("firm_id", "size"), matched_firms=("firm_id", "nunique"))
        )
        frames.append(grouped)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def write_markdown(summary: pd.DataFrame, cohort: pd.DataFrame, path: Path, cutoff: date) -> None:
    headline = summary[
        (summary["horizon_years"] == PRIMARY_HORIZON)
        & ((summary["channel"] == "federal_contract") | (summary["confidence_filter"] == "high"))
    ].copy()
    headline["rate_display"] = headline["rate"].map(lambda value: f"{100 * value:.1f}%")
    headline["independent_rate_display"] = [
        f"{100 * row.firms_with_independent_signal / row.eligible_firms:.1f}%"
        if row.eligible_firms
        else "n/a"
        for row in headline.itertuples()
    ]
    headline["leverage_display"] = headline["dollars_per_phase_ii_dollar"].map(
        lambda value: f"{value:.2f}x"
    )
    pivot_rate = headline.pivot(index="agency", columns="channel", values="rate_display")
    pivot_independent_rate = headline.pivot(
        index="agency", columns="channel", values="independent_rate_display"
    )
    pivot_leverage = headline.pivot(index="agency", columns="channel", values="leverage_display")
    lines = [
        "# NASA, Air Force, and DOE SBIR/STTR commercialization outcomes",
        "",
        "**Status:** exploratory — non-citable  ",
        f"**Observation cutoff:** {cutoff.isoformat()}  ",
        "**Primary estimand:** observed firm-level signals within five years of first Phase II",
        "",
        "## Executive scorecard",
        "",
        "A zero means no signal was observed in these public-data channels; it does not mean the firm did not commercialize.",
        "",
        "| Agency | Eligible firms | Contract rate | Form D rate (high) | M&A candidate rate (high) | M&A candidate independent of Form D | Contract $ / Phase II $ | Form D $ / Phase II $ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for agency in AGENCY_LABELS:
        eligible = int(
            headline[(headline["agency"] == agency) & (headline["channel"] == "federal_contract")][
                "eligible_firms"
            ].iloc[0]
        )
        lines.append(
            f"| {agency} | {eligible:,} | {pivot_rate.loc[agency, 'federal_contract']} | "
            f"{pivot_rate.loc[agency, 'form_d']} | {pivot_rate.loc[agency, 'ma']} | "
            f"{pivot_independent_rate.loc[agency, 'ma']} | "
            f"{pivot_leverage.loc[agency, 'federal_contract']} | {pivot_leverage.loc[agency, 'form_d']} |"
        )
    lines.extend(
        [
            "",
            "## Reading the comparison",
            "",
            "- Contract activity measures subsequent federal-market participation, not proven lineage from a particular Phase II technology.",
            "- Form D captures disclosed Regulation D financing only. Amount sold measures exempt securities sold; it is not company, enterprise, or exit value. High-confidence matches are the headline; medium-confidence matches remain a sensitivity.",
            "- M&A rows are unvalidated public-record candidates, not verified legal exits. Coverage is incomplete and identity or classification errors are possible, so the direction of net bias is unknown. Independent-pathway counts exclude candidates derived only from the same Form D filing.",
            "- Firms may appear in more than one agency cohort; each agency clock begins at that agency's first Phase II award.",
            "",
            "## Cohort and methods",
            "",
            f"The analysis includes SBIR and STTR Phase II cohorts first observed from 2009 through {cutoff.year}. "
            "NASA is the full NASA portfolio; Air Force is the Air Force branch of DoD; DOE includes ARPA-E. "
            "The five-year result includes only firms with a fully observable five-year follow-up period.",
            "",
            "Federal contract dollars are signed net obligations from any awarding agency. Phase I and II SBIR/STTR actions are excluded by research marker or by a dash-stripped PIID match unless the action is coded Phase III. Form D amounts use actual exempt securities sold, collapse amendments into offering series, and quarantine accessions or CIKs matched to more than one firm. A business-combination flag does not convert that amount into deal value.",
            "",
            "## Limitations",
            "",
            "This is a descriptive portfolio comparison, not a causal evaluation. Agency portfolios differ in technology, mission, firm age, and selection. Identity resolution is strongest for UEI/DUNS-linked contracts and weaker for name-keyed SEC signals. Form D and M&A have both false-negative and false-positive risk, so neither is a one-sided bound. M&A candidates require transaction-level review of identity, closing status, and source terms before they can be described as exits.",
            "",
            "Detailed 3-, 5-, and 10-year estimates, confidence intervals, linkage diagnostics, and channel overlap are in the companion CSV artifacts.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, action="append", required=True)
    parser.add_argument("--form-d", type=Path, default=REPO_ROOT / "data/form_d_details.jsonl")
    parser.add_argument("--ma", type=Path, default=REPO_ROOT / "data/sbir_ma_events.jsonl")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data/reports/three_agency_commercialization",
    )
    parser.add_argument("--cutoff", type=date.fromisoformat, default=DEFAULT_CUTOFF)
    parser.add_argument("--horizons", type=int, nargs="+", default=list(DEFAULT_HORIZONS))
    args = parser.parse_args(argv)

    input_paths = [args.awards, *args.contracts, args.form_d, args.ma]
    missing = [path for path in input_paths if not path.is_file()]
    if missing:
        parser.error("missing input(s): " + ", ".join(str(path) for path in missing))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cohort = build_cohort(args.awards, args.cutoff)
    contracts, contract_audit = load_contract_events(args.contracts, cohort, args.cutoff)
    form_d, form_d_audit = load_form_d_events(args.form_d, cohort, args.cutoff)
    ma, ma_audit = load_ma_events(args.ma, cohort, args.cutoff)
    summary, firm_results, overlap = build_outputs(
        cohort,
        contracts,
        form_d,
        ma,
        cutoff=args.cutoff,
        horizons=tuple(sorted(set(args.horizons))),
    )
    vintage = build_vintage_diagnostics(firm_results)
    air_force_era = build_air_force_era_diagnostics(firm_results)
    linkage = build_linkage_audit(contracts, form_d, ma)

    cohort.firms.to_csv(args.output_dir / "cohort.csv", index=False)
    summary.to_csv(args.output_dir / "agency_horizon_outcomes.csv", index=False)
    firm_results.to_csv(args.output_dir / "firm_channel_outcomes.csv", index=False)
    overlap.to_csv(args.output_dir / "channel_overlap.csv", index=False)
    vintage.to_csv(args.output_dir / "annual_vintage_outcomes.csv", index=False)
    air_force_era.to_csv(args.output_dir / "air_force_era_outcomes.csv", index=False)
    linkage.to_csv(args.output_dir / "linkage_audit.csv", index=False)
    contracts.to_csv(args.output_dir / "matched_contract_events.csv", index=False)
    write_markdown(summary, cohort.firms, args.output_dir / "policy_memo.md", args.cutoff)

    manifest = {
        "epistemic_tier": "exploratory",
        "citable": False,
        "ma_candidate_status": CANDIDATE_STATUS,
        "measure_definitions": {
            "form_d_amount_sold": FORM_D_CHANNEL_AMOUNT_SOLD_MEASURE,
            "form_d_amount_sold_is_deal_value": False,
            "ma_legal_event_validated": False,
            "ma_deal_terms_captured": False,
            "ma_enterprise_value_observed": False,
        },
        "cutoff": args.cutoff.isoformat(),
        "horizons_years": sorted(set(args.horizons)),
        "primary_horizon_years": PRIMARY_HORIZON,
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        "random_seed": RANDOM_SEED,
        "canonical_identity_policy": CanonicalMergePolicy.PRELOAD_V1.value,
        "inputs": [
            {
                "path": str(path.resolve()),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in input_paths
        ],
        "cohort_rows": len(cohort.firms),
        "cohort_firms_by_agency": cohort.firms.groupby("agency_label")["firm_id"]
        .nunique()
        .to_dict(),
        "audits": {
            "contracts": contract_audit,
            "form_d": form_d_audit,
            "ma": ma_audit,
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(summary.to_string(index=False))
    print(f"\nWrote exploratory outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
