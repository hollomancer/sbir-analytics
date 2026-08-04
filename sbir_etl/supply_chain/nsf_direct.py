"""Reconcile the SBIR.gov NSF baseline to authoritative direct NSF awards."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pandas as pd

from sbir_etl.extractors.nsf_awards import normalize_nsf_award_id
from sbir_etl.utils.text_normalization import normalize_name


class NSFAwardPerformanceStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UPCOMING = "upcoming"
    INDETERMINATE = "indeterminate"


class NSFAwardeeStatus(StrEnum):
    CURRENT = "current"
    FORMER = "former"
    UPCOMING_ONLY = "upcoming_only"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class NSFReconciliationResult:
    direct_awards: pd.DataFrame
    reconciliation: pd.DataFrame
    awardees: pd.DataFrame
    quality: dict[str, Any]


_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_WHITESPACE = re.compile(r"\s+")


def _first(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    for column in aliases:
        if column in frame.columns:
            return frame[column]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _text(value: object) -> str | None:
    if value is None or value is pd.NA or pd.isna(cast(Any, value)):
        return None
    cleaned = _WHITESPACE.sub(" ", str(value).strip())
    return None if cleaned.upper() in {"", "NAN", "NONE", "NULL", "<NA>"} else cleaned


def _identifier(value: object) -> str | None:
    cleaned = _text(value)
    return _NON_ALNUM.sub("", cleaned.upper()) or None if cleaned else None


def _name(value: object) -> str | None:
    cleaned = _text(value)
    if cleaned is None:
        return None
    normalized = normalize_name(cleaned, remove_suffixes=True)
    return normalized if len(normalized) >= 4 else None


def _program(value: object) -> str | None:
    cleaned = (_text(value) or "").upper()
    return cleaned if cleaned in {"SBIR", "STTR"} else None


def _phase(value: object) -> str | None:
    cleaned = (_text(value) or "").upper().replace("PHASE", "").strip()
    cleaned = {"1": "I", "2": "II", "3": "III"}.get(cleaned, cleaned)
    return cleaned if cleaned in {"I", "II", "III"} else None


def _analysis_timestamp(value: str | date | datetime | pd.Timestamp) -> pd.Timestamp:
    result = pd.Timestamp(value)
    result = result.tz_localize(UTC) if result.tzinfo is None else result.tz_convert(UTC)
    return result.normalize()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_record_ids(frame: pd.DataFrame) -> pd.Series:
    columns = [
        "sbir_gov_company_name",
        "sbir_gov_nsf_award_id",
        "sbir_gov_contract_number_source",
        "sbir_gov_agency_tracking_number_source",
        "sbir_gov_award_title",
        "sbir_gov_award_year",
        "sbir_gov_award_amount",
    ]

    def digest(row: pd.Series) -> str:
        values = ["" if pd.isna(row[column]) else str(row[column]) for column in columns]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()[:20]

    digests = frame.apply(digest, axis=1)
    occurrences = digests.groupby(digests).cumcount().add(1)
    return pd.Series(
        [
            f"sbir-gov:{item}:{occurrence}"
            for item, occurrence in zip(digests, occurrences, strict=True)
        ],
        index=frame.index,
    )


def build_nsf_sbir_baseline(
    awards: pd.DataFrame,
    *,
    include_sttr: bool = True,
    source_path: str | None = None,
    source_sha256: str | None = None,
) -> pd.DataFrame:
    """Normalize NSF SBIR/STTR rows while preserving SBIR.gov source values."""

    agencies = _first(awards, ("Agency", "agency", "funding_agency"))
    programs = _first(awards, ("Program", "program")).map(_program)
    allowed = {"SBIR", "STTR"} if include_sttr else {"SBIR"}
    selected = awards.loc[
        agencies.map(
            lambda value: (_text(value) or "").upper() in {"NSF", "NATIONAL SCIENCE FOUNDATION"}
        )
        & programs.isin(allowed)
    ].copy()
    if selected.empty:
        return pd.DataFrame()
    names = _first(selected, ("Company", "company_name", "organization_name"))
    contract_source = _first(selected, ("Contract", "contract"))
    tracking_source = _first(selected, ("Agency Tracking Number", "agency_tracking_number"))
    contract_ids = contract_source.map(normalize_nsf_award_id)
    tracking_ids = tracking_source.map(normalize_nsf_award_id)
    ueis = _first(selected, ("UEI", "uei", "company_uei"))
    duns = _first(selected, ("Duns", "DUNS", "duns", "company_duns"))
    baseline = pd.DataFrame(
        {
            "sbir_gov_company_name": names.map(_text),
            "sbir_gov_normalized_name": names.map(_name),
            "sbir_gov_uei_source": ueis,
            "sbir_gov_uei": ueis.map(_identifier),
            "sbir_gov_duns_source": duns,
            "sbir_gov_duns": duns.map(_identifier),
            "sbir_gov_program": programs.loc[selected.index],
            "sbir_gov_phase": _first(selected, ("Phase", "phase")).map(_phase),
            "sbir_gov_award_title": _first(selected, ("Award Title", "award_title", "title")).map(
                _text
            ),
            "sbir_gov_abstract": _first(selected, ("Abstract", "abstract")).map(_text),
            "sbir_gov_topic_code": _first(selected, ("Topic Code", "topic_code")).map(_text),
            "sbir_gov_award_year": pd.to_numeric(
                _first(selected, ("Award Year", "award_year")), errors="coerce"
            ).astype("Int64"),
            "sbir_gov_award_amount": pd.to_numeric(
                _first(selected, ("Award Amount", "award_amount"))
                .astype("string")
                .str.replace(r"[$,]", "", regex=True),
                errors="coerce",
            ),
            "sbir_gov_proposal_award_date": pd.to_datetime(
                _first(selected, ("Proposal Award Date", "proposal_award_date")),
                errors="coerce",
                utc=True,
            ),
            "sbir_gov_contract_end_date": pd.to_datetime(
                _first(selected, ("Contract End Date", "contract_end_date")),
                errors="coerce",
                utc=True,
            ),
            "sbir_gov_contract_number_source": contract_source.map(_text),
            "sbir_gov_contract_award_id": contract_ids,
            "sbir_gov_agency_tracking_number_source": tracking_source.map(_text),
            "sbir_gov_tracking_award_id": tracking_ids,
            "sbir_gov_nsf_award_id": contract_ids.fillna(tracking_ids),
            "sbir_gov_solicitation_number": _first(
                selected, ("Solicitation Number", "solicitation_number")
            ).map(_text),
        },
        index=selected.index,
    ).reset_index(drop=True)
    baseline["sbir_gov_award_id_source"] = "agency_tracking_number"
    baseline.loc[baseline["sbir_gov_contract_award_id"].notna(), "sbir_gov_award_id_source"] = (
        "contract_number"
    )
    baseline.loc[baseline["sbir_gov_nsf_award_id"].isna(), "sbir_gov_award_id_source"] = "unusable"
    baseline["sbir_gov_award_id_conflict"] = (
        baseline["sbir_gov_contract_award_id"].notna()
        & baseline["sbir_gov_tracking_award_id"].notna()
        & baseline["sbir_gov_contract_award_id"].ne(baseline["sbir_gov_tracking_award_id"])
    )
    baseline["sbir_gov_source_system"] = "SBIR.gov bulk award_data.csv"
    baseline["sbir_gov_source_path"] = source_path
    baseline["sbir_gov_source_sha256"] = source_sha256
    baseline["sbir_gov_record_id"] = _stable_record_ids(baseline)
    baseline["sbir_gov_record_count_for_award_id"] = baseline.groupby(
        "sbir_gov_nsf_award_id", dropna=False
    )["sbir_gov_record_id"].transform("size")
    return baseline.sort_values(
        ["sbir_gov_nsf_award_id", "sbir_gov_record_id"], na_position="last"
    ).reset_index(drop=True)


def load_nsf_sbir_baseline(path: Path | str, *, include_sttr: bool = True) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"SBIR.gov award baseline not found: {source}")
    return build_nsf_sbir_baseline(
        pd.read_csv(source, dtype=str, low_memory=False),
        include_sttr=include_sttr,
        source_path=str(source),
        source_sha256=_file_sha256(source),
    )


def requested_nsf_award_ids(baseline: pd.DataFrame) -> list[str]:
    if "sbir_gov_nsf_award_id" not in baseline.columns:
        raise ValueError("NSF baseline is missing sbir_gov_nsf_award_id")
    return sorted(baseline["sbir_gov_nsf_award_id"].dropna().astype(str).unique().tolist())


def classify_nsf_award_status(
    start_date: object,
    end_date: object,
    analysis_date: str | date | datetime | pd.Timestamp,
) -> str:
    """Classify one direct award from performance dates, never award year."""

    analysis = _analysis_timestamp(analysis_date)
    start = pd.to_datetime(str(start_date), errors="coerce", utc=True)
    end = pd.to_datetime(str(end_date), errors="coerce", utc=True)
    if pd.notna(start) and start > analysis:
        return NSFAwardPerformanceStatus.UPCOMING.value
    if pd.notna(end) and end < analysis:
        return NSFAwardPerformanceStatus.EXPIRED.value
    if pd.notna(start) and pd.notna(end):
        return NSFAwardPerformanceStatus.ACTIVE.value
    return NSFAwardPerformanceStatus.INDETERMINATE.value


def _organization(row: pd.Series) -> pd.Series:
    direct_uei = _identifier(row.get("nsf_awardee_uei"))
    baseline_uei = _identifier(row.get("sbir_gov_uei"))
    baseline_duns = _identifier(row.get("sbir_gov_duns"))
    legal_name = _text(row.get("nsf_awardee_legal_business_name"))
    direct_name = _name(legal_name if legal_name else row.get("nsf_awardee_name"))
    baseline_name = _name(row.get("sbir_gov_company_name"))
    if direct_uei:
        organization_id, method, confidence = (
            f"uei:{direct_uei}",
            "direct_nsf_uei",
            "verified_identifier",
        )
    elif baseline_uei:
        organization_id, method, confidence = (
            f"uei:{baseline_uei}",
            "sbir_gov_uei",
            "verified_identifier",
        )
    elif baseline_duns:
        organization_id, method, confidence = (
            f"duns:{baseline_duns}",
            "sbir_gov_legacy_duns",
            "verified_legacy_identifier",
        )
    elif direct_name or baseline_name:
        organization_id, method, confidence = (
            f"name_candidate:{direct_name or baseline_name}",
            "normalized_name_candidate",
            "candidate_name",
        )
    else:
        organization_id, method, confidence = None, "unresolved", "none"
    if direct_uei and baseline_uei:
        match_method = "exact_uei" if direct_uei == baseline_uei else "conflicting_uei"
    elif direct_uei:
        match_method = "direct_nsf_uei_only"
    elif baseline_uei:
        match_method = "sbir_gov_uei_only"
    elif direct_name and baseline_name:
        match_method = (
            "exact_normalized_name_candidate"
            if direct_name == baseline_name
            else "conflicting_normalized_name"
        )
    elif baseline_duns:
        match_method = "sbir_gov_legacy_duns_only"
    elif direct_name or baseline_name:
        match_method = "single_source_normalized_name_candidate"
    else:
        match_method = "unresolved"
    evidence = {
        "direct_nsf_uei": direct_uei,
        "sbir_gov_uei": baseline_uei,
        "sbir_gov_duns": baseline_duns,
        "direct_normalized_name": direct_name,
        "sbir_gov_normalized_name": baseline_name,
    }
    return pd.Series(
        {
            "nsf_organization_id": organization_id,
            "organization_resolution_method": method,
            "organization_resolution_confidence": confidence,
            "organization_match_method": match_method,
            "organization_match_evidence": json.dumps(
                evidence, sort_keys=True, separators=(",", ":")
            ),
        }
    )


def _date_value(value: object) -> str | None:
    parsed = pd.to_datetime(str(value), errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _different(left: object, right: object, kind: str) -> bool:
    if kind == "date":
        return _date_value(left) != _date_value(right)
    if kind == "number":
        values = pd.to_numeric(pd.Series([left, right]), errors="coerce")
        if values.isna().all():
            return False
        if values.isna().any():
            return True
        return abs(float(values.iloc[0]) - float(values.iloc[1])) > 0.01
    left_text, right_text = _text(left), _text(right)
    return (left_text.casefold() if left_text else None) != (
        right_text.casefold() if right_text else None
    )


_COMPARISONS = (
    ("title", "sbir_gov_award_title", "nsf_award_title", "text"),
    ("abstract", "sbir_gov_abstract", "nsf_award_abstract", "text"),
    ("program", "sbir_gov_program", "nsf_program", "text"),
    ("phase", "sbir_gov_phase", "nsf_phase", "text"),
    ("award_amount", "sbir_gov_award_amount", "nsf_comparison_amount", "number"),
    ("award_date", "sbir_gov_proposal_award_date", "nsf_award_date", "date"),
    ("end_date", "sbir_gov_contract_end_date", "nsf_end_date", "date"),
    ("organization_uei", "sbir_gov_uei", "nsf_awardee_uei", "text"),
    ("organization_name", "sbir_gov_company_name", "nsf_awardee_name", "text"),
)


def _findings(row: pd.Series) -> pd.Series:
    fields = []
    if row.get("reconciliation_disposition") == "matched":
        fields = [
            field
            for field, left, right, kind in _COMPARISONS
            if _different(row.get(left), row.get(right), kind)
        ]
    return pd.Series(
        {
            "reconciliation_discrepancy_count": len(fields),
            "reconciliation_discrepancy_fields": json.dumps(fields, separators=(",", ":")),
        }
    )


def _rollup_awardees(direct: pd.DataFrame, analysis: pd.Timestamp) -> pd.DataFrame:
    working = direct.dropna(subset=["nsf_organization_id"]).copy()
    if working.empty:
        return pd.DataFrame()
    for status in NSFAwardPerformanceStatus:
        working[f"_{status.value}"] = working["nsf_award_performance_status"].eq(status.value)
    working["_sbir"] = working["nsf_program"].eq("SBIR")
    working["_sttr"] = working["nsf_program"].eq("STTR")
    awardees = working.groupby("nsf_organization_id", as_index=False).agg(
        nsf_awardee_name=("nsf_awardee_name", "first"),
        nsf_awardee_legal_business_name=("nsf_awardee_legal_business_name", "first"),
        nsf_awardee_uei=("nsf_awardee_uei", "first"),
        organization_resolution_method=("organization_resolution_method", "first"),
        organization_resolution_confidence=("organization_resolution_confidence", "first"),
        nsf_direct_award_count=("nsf_award_id", "nunique"),
        nsf_sbir_award_count=("_sbir", "sum"),
        nsf_sttr_award_count=("_sttr", "sum"),
        nsf_active_award_count=("_active", "sum"),
        nsf_expired_award_count=("_expired", "sum"),
        nsf_upcoming_award_count=("_upcoming", "sum"),
        nsf_indeterminate_award_count=("_indeterminate", "sum"),
        nsf_first_award_start_date=("nsf_start_date", "min"),
        nsf_latest_award_end_date=("nsf_end_date", "max"),
    )
    awardees["nsf_awardee_status"] = NSFAwardeeStatus.INDETERMINATE.value
    awardees.loc[awardees["nsf_upcoming_award_count"].gt(0), "nsf_awardee_status"] = (
        NSFAwardeeStatus.UPCOMING_ONLY.value
    )
    awardees.loc[awardees["nsf_expired_award_count"].gt(0), "nsf_awardee_status"] = (
        NSFAwardeeStatus.FORMER.value
    )
    awardees.loc[awardees["nsf_active_award_count"].gt(0), "nsf_awardee_status"] = (
        NSFAwardeeStatus.CURRENT.value
    )
    awardees["nsf_awardee_status_basis"] = "direct_nsf_performance_periods"
    awardees["analysis_date"] = analysis
    return awardees.sort_values("nsf_organization_id").reset_index(drop=True)


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.fillna("missing").value_counts().sort_index().items()
    }


def reconcile_nsf_sbir_awards(
    baseline: pd.DataFrame,
    direct_awards: pd.DataFrame,
    *,
    analysis_date: str | date | datetime | pd.Timestamp,
    direct_lookup: pd.DataFrame | None = None,
) -> NSFReconciliationResult:
    """Reconcile exact NSF IDs and derive current/former from authoritative dates."""

    required_baseline = {"sbir_gov_record_id", "sbir_gov_nsf_award_id"}
    if missing := sorted(required_baseline - set(baseline.columns)):
        raise ValueError(f"NSF baseline is missing required columns: {missing}")
    required_direct = {
        "nsf_award_id",
        "nsf_program",
        "nsf_start_date",
        "nsf_end_date",
        "source_kind",
        "source_path",
        "source_record_sha256",
    }
    if missing := sorted(required_direct - set(direct_awards.columns)):
        raise ValueError(f"direct NSF awards are missing required columns: {missing}")
    analysis = _analysis_timestamp(analysis_date)
    direct = direct_awards.copy()
    direct["nsf_award_id"] = direct["nsf_award_id"].map(normalize_nsf_award_id)
    if direct["nsf_award_id"].isna().any():
        raise ValueError("direct NSF awards contain unusable IDs")
    if direct["nsf_award_id"].duplicated().any():
        raise ValueError("direct NSF award IDs are not unique")
    for column in ("nsf_award_date", "nsf_start_date", "nsf_end_date"):
        if column not in direct.columns:
            direct[column] = pd.NaT
        direct[column] = pd.to_datetime(direct[column], errors="coerce", utc=True)
    baseline_ids = set(baseline["sbir_gov_nsf_award_id"].dropna().astype(str))
    direct_program = direct["nsf_program"].isin(["SBIR", "STTR"])
    direct["direct_scope_basis"] = "direct_nsf_sbir_sttr_program"
    direct.loc[~direct_program, "direct_scope_basis"] = "matched_sbir_gov_baseline"
    direct = direct.loc[direct_program | direct["nsf_award_id"].isin(baseline_ids)].copy()
    direct["nsf_award_performance_status"] = direct.apply(
        lambda row: classify_nsf_award_status(row["nsf_start_date"], row["nsf_end_date"], analysis),
        axis=1,
    )
    direct["analysis_date"] = analysis
    direct["nsf_comparison_amount"] = direct.get(
        "nsf_estimated_total_amount", pd.Series(pd.NA, index=direct.index)
    ).fillna(direct.get("nsf_obligated_amount", pd.Series(pd.NA, index=direct.index)))

    lookup_provided = direct_lookup is not None
    if direct_lookup is None:
        lookup = pd.DataFrame(
            {
                "nsf_lookup_requested_award_id": direct["nsf_award_id"],
                "nsf_lookup_resolved_award_id": direct["nsf_award_id"],
                "nsf_lookup_status": "found",
                "nsf_lookup_found": True,
                "nsf_lookup_source_url": direct.get("source_url"),
                "nsf_lookup_source_path": direct["source_path"],
                "nsf_lookup_source_sha256": direct["source_record_sha256"],
                "nsf_lookup_retrieved_at": direct.get("source_retrieved_at"),
                "nsf_lookup_snapshot_manifest_path": None,
                "nsf_lookup_snapshot_manifest_sha256": None,
            }
        )
    else:
        lookup = direct_lookup.copy()
    required_lookup = {"nsf_lookup_requested_award_id", "nsf_lookup_status"}
    if missing := sorted(required_lookup - set(lookup.columns)):
        raise ValueError(f"direct NSF lookup index is missing columns: {missing}")
    lookup["nsf_lookup_requested_award_id"] = lookup["nsf_lookup_requested_award_id"].map(
        normalize_nsf_award_id
    )
    if (
        lookup["nsf_lookup_requested_award_id"].isna().any()
        or lookup["nsf_lookup_requested_award_id"].duplicated().any()
    ):
        raise ValueError("direct NSF lookup index has invalid or duplicate requested IDs")
    lookup_columns = [
        "nsf_lookup_requested_award_id",
        "nsf_lookup_resolved_award_id",
        "nsf_lookup_status",
        "nsf_lookup_found",
        "nsf_lookup_failure",
        "nsf_lookup_source_url",
        "nsf_lookup_source_path",
        "nsf_lookup_source_sha256",
        "nsf_lookup_retrieved_at",
        "nsf_lookup_snapshot_manifest_path",
        "nsf_lookup_snapshot_manifest_sha256",
    ]
    for column in lookup_columns:
        if column not in lookup.columns:
            lookup[column] = pd.NA
    lookup = lookup[lookup_columns]
    direct = direct.merge(
        lookup,
        left_on="nsf_award_id",
        right_on="nsf_lookup_requested_award_id",
        how="left",
        validate="one_to_one",
    )
    reconciliation = baseline.merge(
        direct,
        left_on="sbir_gov_nsf_award_id",
        right_on="nsf_award_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    lookup_by_id = lookup.set_index("nsf_lookup_requested_award_id")
    for column in lookup_columns[1:]:
        mapped = reconciliation["sbir_gov_nsf_award_id"].map(lookup_by_id[column])
        reconciliation[column] = reconciliation[column].where(
            reconciliation[column].notna(), mapped
        )
    reconciliation["nsf_lookup_requested_award_id"] = reconciliation[
        "nsf_lookup_requested_award_id"
    ].fillna(reconciliation["sbir_gov_nsf_award_id"])
    matched = reconciliation["_merge"].eq("both")
    reconciliation["reconciliation_disposition"] = "no_direct_record"
    reconciliation.loc[matched, "reconciliation_disposition"] = "matched"
    reconciliation["match_method"] = "no_direct_match"
    reconciliation.loc[
        matched & reconciliation["sbir_gov_award_id_source"].eq("contract_number"),
        "match_method",
    ] = "exact_contract_award_id"
    reconciliation.loc[
        matched & reconciliation["sbir_gov_award_id_source"].eq("agency_tracking_number"),
        "match_method",
    ] = "exact_agency_tracking_award_id"
    reconciliation["match_confidence"] = "none"
    reconciliation.loc[matched, "match_confidence"] = "high"
    reconciliation["match_evidence"] = reconciliation.apply(
        lambda row: json.dumps(
            {
                "nsf_direct_award_id": _text(row.get("nsf_award_id")),
                "sbir_gov_selected_award_id": _text(row.get("sbir_gov_nsf_award_id")),
                "sbir_gov_contract_award_id": _text(row.get("sbir_gov_contract_award_id")),
                "sbir_gov_tracking_award_id": _text(row.get("sbir_gov_tracking_award_id")),
                "nsf_direct_lookup_status": _text(row.get("nsf_lookup_status")),
                "nsf_direct_lookup_source_sha256": _text(row.get("nsf_lookup_source_sha256")),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        axis=1,
    )
    matched_ids = set(reconciliation.loc[matched, "nsf_award_id"].dropna().astype(str))
    direct_only = direct.loc[~direct["nsf_award_id"].isin(matched_ids)].copy()
    if not direct_only.empty:
        empty_baseline = pd.DataFrame(index=direct_only.index, columns=baseline.columns)
        rows = pd.concat(
            [empty_baseline.reset_index(drop=True), direct_only.reset_index(drop=True)], axis=1
        )
        rows["_merge"] = "right_only"
        rows["reconciliation_disposition"] = "direct_only"
        rows["match_method"] = "no_sbir_gov_match"
        rows["match_confidence"] = "none"
        rows["match_evidence"] = rows["nsf_award_id"].map(
            lambda value: json.dumps({"nsf_direct_award_id": value}, separators=(",", ":"))
        )
        reconciliation = pd.concat([reconciliation, rows], ignore_index=True)
    reconciliation = pd.concat(
        [reconciliation, reconciliation.apply(_organization, axis=1)], axis=1
    )
    reconciliation = pd.concat([reconciliation, reconciliation.apply(_findings, axis=1)], axis=1)
    reconciliation = reconciliation.drop(columns="_merge")

    resolution = reconciliation.loc[
        reconciliation["nsf_award_id"].notna(),
        [
            "nsf_award_id",
            "nsf_organization_id",
            "organization_resolution_method",
            "organization_resolution_confidence",
        ],
    ].drop_duplicates("nsf_award_id")
    direct = direct.merge(resolution, on="nsf_award_id", how="left", validate="one_to_one")
    matched_counts = (
        reconciliation.loc[reconciliation["reconciliation_disposition"].eq("matched")]
        .groupby("nsf_award_id")["sbir_gov_record_id"]
        .count()
    )
    direct["direct_reconciliation_disposition"] = "direct_only"
    direct.loc[
        direct["nsf_award_id"].isin(matched_counts.index), "direct_reconciliation_disposition"
    ] = "matched_sbir_gov"
    direct.loc[
        direct["nsf_award_id"].isin(matched_counts[matched_counts.gt(1)].index),
        "direct_reconciliation_disposition",
    ] = "matched_multiple_sbir_gov_records"
    awardees = _rollup_awardees(direct, analysis)
    if not awardees.empty:
        statuses = awardees[
            ["nsf_organization_id", "nsf_awardee_status", "nsf_awardee_status_basis"]
        ]
        direct = direct.merge(statuses, on="nsf_organization_id", how="left")
        reconciliation = reconciliation.merge(statuses, on="nsf_organization_id", how="left")
    reconciliation["nsf_awardee_status"] = reconciliation["nsf_awardee_status"].fillna(
        "indeterminate_no_direct_dates"
    )
    reconciliation["nsf_awardee_status_basis"] = reconciliation["nsf_awardee_status_basis"].fillna(
        "no_direct_nsf_performance_period"
    )
    reconciliation["analysis_date"] = analysis

    discrepancy_counts: dict[str, int] = {}
    for value in reconciliation["reconciliation_discrepancy_fields"]:
        for field in json.loads(value):
            discrepancy_counts[field] = discrepancy_counts.get(field, 0) + 1
    baseline_with_ids = reconciliation["sbir_gov_nsf_award_id"].notna()
    lookup_coverage = bool(reconciliation.loc[baseline_with_ids, "nsf_lookup_status"].notna().all())
    lookup_provenance = bool(
        reconciliation.loc[
            baseline_with_ids,
            [
                "nsf_lookup_source_url",
                "nsf_lookup_source_path",
                "nsf_lookup_source_sha256",
                "nsf_lookup_snapshot_manifest_path",
                "nsf_lookup_snapshot_manifest_sha256",
            ],
        ]
        .notna()
        .all(axis=None)
    )
    gates = {
        "direct_award_ids_unique": bool(~direct["nsf_award_id"].duplicated().any()),
        "every_direct_record_has_reconciliation_disposition": bool(
            direct["direct_reconciliation_disposition"].notna().all()
        ),
        "analysis_date_consistent": bool(
            direct["analysis_date"].eq(analysis).all()
            and reconciliation["analysis_date"].eq(analysis).all()
        ),
        "statuses_use_direct_performance_dates": True,
        "direct_source_provenance_complete": bool(
            direct[["source_kind", "source_path", "source_record_sha256"]].notna().all(axis=None)
        ),
        "direct_lookup_coverage_complete": lookup_coverage if lookup_provided else True,
        "direct_lookup_snapshot_provenance_complete": (
            lookup_provenance if lookup_provided else True
        ),
    }
    quality = {
        "analysis_date": analysis.date().isoformat(),
        "baseline_record_count": int(len(baseline)),
        "baseline_unique_usable_award_ids": int(baseline["sbir_gov_nsf_award_id"].nunique()),
        "baseline_unusable_award_id_count": int(baseline["sbir_gov_nsf_award_id"].isna().sum()),
        "baseline_award_id_conflict_count": int(baseline["sbir_gov_award_id_conflict"].sum()),
        "direct_in_scope_award_count": int(len(direct)),
        "reconciliation_record_count": int(len(reconciliation)),
        "baseline_matched_record_count": int(matched.sum()),
        "baseline_no_direct_record_count": int((~matched).sum()),
        "direct_matched_award_count": int(len(matched_ids)),
        "direct_only_award_count": int(len(direct_only)),
        "direct_lookup_status_counts": _counts(lookup["nsf_lookup_status"]),
        "match_method_counts": _counts(reconciliation["match_method"]),
        "organization_resolution_method_counts": _counts(
            reconciliation["organization_resolution_method"]
        ),
        "award_performance_status_counts": _counts(direct["nsf_award_performance_status"]),
        "awardee_status_counts": _counts(awardees["nsf_awardee_status"])
        if not awardees.empty
        else {},
        "discrepancy_field_counts": dict(sorted(discrepancy_counts.items())),
        "quality_gates": gates,
        "quality_gates_passed": bool(all(gates.values())),
    }
    return NSFReconciliationResult(
        direct.sort_values("nsf_award_id").reset_index(drop=True),
        reconciliation.sort_values(
            ["nsf_award_id", "sbir_gov_record_id"], na_position="last"
        ).reset_index(drop=True),
        awardees,
        quality,
    )


__all__ = [
    "NSFAwardPerformanceStatus",
    "NSFAwardeeStatus",
    "NSFReconciliationResult",
    "build_nsf_sbir_baseline",
    "classify_nsf_award_status",
    "load_nsf_sbir_baseline",
    "reconcile_nsf_sbir_awards",
    "requested_nsf_award_ids",
]
