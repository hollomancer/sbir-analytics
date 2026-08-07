"""Normalize DoD funding observed for directly validated NSF SBIR/STTR awardees.

The outputs in this module are funding observations at their source grain.  They
do not assert that a DoD transaction used a particular NSF-funded capability or
that an awardee is a critical supply-chain dependency.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

import pandas as pd

from sbir_etl.utils.text_normalization import normalize_name

DEFENSE_FUNDING_SCHEMA_VERSION = "NSF-DEFENSE-FUNDING-2026Q3"
DOD_SOURCE_AGENCY_NAME = "Department of Defense"
DOD_FPDS_AGENCY_CODE = "9700"

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_DOD_AWARD_CODE = re.compile(r"(?:^|_)9700(?:_|$)")
_OTHER_TRANSACTION_CODES = {"O", "R", "IDV-O", "IDV-R"}


def _missing(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        return bool(pd.isna(cast(Any, value)))
    except (TypeError, ValueError):
        return False


def _text(value: object) -> str | None:
    if _missing(value):
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    return None if cleaned.upper() in {"", "NAN", "NONE", "NULL", "<NA>"} else cleaned


def _identifier(value: object) -> str | None:
    cleaned = _text(value)
    return _NON_ALNUM.sub("", cleaned.upper()) or None if cleaned else None


def _uei(value: object) -> str | None:
    cleaned = _identifier(value)
    return cleaned if cleaned and len(cleaned) == 12 else None


def _duns(value: object) -> str | None:
    cleaned = _identifier(value)
    return cleaned if cleaned and len(cleaned) == 9 and cleaned.isdigit() else None


def _name(value: object) -> str | None:
    cleaned = _text(value)
    if cleaned is None:
        return None
    normalized = normalize_name(cleaned, remove_suffixes=True)
    return normalized if len(normalized) >= 4 else None


def _first(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    for column in aliases:
        if column in frame.columns:
            return frame[column]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_values(values: object) -> list[str]:
    if _missing(values):
        return []
    if isinstance(values, list):
        return sorted({text for value in values if (text := _text(value)) is not None})
    if isinstance(values, str):
        try:
            parsed = json.loads(values)
        except json.JSONDecodeError:
            parsed = [values]
        if isinstance(parsed, list):
            return sorted({text for value in parsed if (text := _text(value)) is not None})
    return []


def _json_unique(values: pd.Series) -> str:
    items: set[str] = set()
    for value in values:
        items.update(_json_values(value))
        text = _text(value)
        if text and not text.startswith("["):
            items.add(text)
    return json.dumps(sorted(items), separators=(",", ":"))


def _fiscal_year(value: object) -> int | None:
    timestamp = pd.to_datetime(str(value), errors="coerce", utc=True)
    if pd.isna(timestamp):
        return None
    return int(timestamp.year + (timestamp.month >= 10))


def build_nsf_identity_registry(
    awardees: pd.DataFrame,
    reconciliation: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build one legal-entity row with all usable NSF/SBIR.gov identity aliases.

    Exact UEI or legacy-DUNS collisions fail closed.  Shared normalized names are
    retained in the registry but excluded from the name-candidate lookup map.
    """

    if "nsf_organization_id" not in awardees.columns:
        raise ValueError("NSF awardees are missing required column: nsf_organization_id")

    organizations: dict[str, dict[str, Any]] = {}

    def bucket(organization_id: object) -> dict[str, Any] | None:
        identifier = _text(organization_id)
        if identifier is None:
            return None
        return organizations.setdefault(
            identifier,
            {
                "ueis": set(),
                "duns": set(),
                "names": set(),
                "source_names": set(),
                "preferred_uei": None,
                "preferred_duns": None,
                "preferred_name": None,
                "resolution_method": None,
                "resolution_confidence": None,
                "awardee_status": None,
            },
        )

    for _, row in awardees.iterrows():
        item = bucket(row.get("nsf_organization_id"))
        if item is None:
            continue
        legal_name = _text(row.get("nsf_awardee_legal_business_name"))
        source_name = legal_name or _text(row.get("nsf_awardee_name"))
        recipient_uei = _uei(row.get("nsf_awardee_uei"))
        recipient_duns = _duns(row.get("nsf_awardee_duns"))
        if recipient_uei:
            item["ueis"].add(recipient_uei)
            item["preferred_uei"] = recipient_uei
        if recipient_duns:
            item["duns"].add(recipient_duns)
            item["preferred_duns"] = recipient_duns
        if source_name:
            item["source_names"].add(source_name)
            normalized = _name(source_name)
            if normalized:
                item["names"].add(normalized)
                item["preferred_name"] = normalized
        organization_id = _text(row.get("nsf_organization_id")) or ""
        if organization_id.startswith("uei:"):
            derived_uei = _uei(organization_id.removeprefix("uei:"))
            if derived_uei:
                item["ueis"].add(derived_uei)
        elif organization_id.startswith("duns:"):
            derived_duns = _duns(organization_id.removeprefix("duns:"))
            if derived_duns:
                item["duns"].add(derived_duns)
        item["resolution_method"] = _text(row.get("organization_resolution_method"))
        item["resolution_confidence"] = _text(row.get("organization_resolution_confidence"))
        item["awardee_status"] = _text(row.get("nsf_awardee_status"))

    if reconciliation is not None and not reconciliation.empty:
        for _, row in reconciliation.iterrows():
            item = bucket(row.get("nsf_organization_id"))
            if item is None:
                continue
            for column in ("nsf_awardee_uei", "sbir_gov_uei"):
                value = _uei(row.get(column))
                if value:
                    item["ueis"].add(value)
            value = _duns(row.get("sbir_gov_duns"))
            if value:
                item["duns"].add(value)
                item["preferred_duns"] = item["preferred_duns"] or value
            for column in (
                "nsf_awardee_legal_business_name",
                "nsf_awardee_name",
                "sbir_gov_company_name",
            ):
                source_name = _text(row.get(column))
                normalized = _name(source_name)
                if source_name:
                    item["source_names"].add(source_name)
                if normalized:
                    item["names"].add(normalized)
                    item["preferred_name"] = item["preferred_name"] or normalized

    exact_owners: dict[tuple[str, str], set[str]] = {}
    for organization_id, item in organizations.items():
        for kind in ("ueis", "duns"):
            for value in item[kind]:
                exact_owners.setdefault((kind, value), set()).add(organization_id)
    conflicts = {
        f"{kind}:{value}": sorted(owners)
        for (kind, value), owners in exact_owners.items()
        if len(owners) > 1
    }
    if conflicts:
        sample = dict(sorted(conflicts.items())[:5])
        raise ValueError(f"exact NSF identity aliases map to multiple organizations: {sample}")

    rows: list[dict[str, object]] = []
    for organization_id in sorted(organizations):
        item = organizations[organization_id]
        ueis = sorted(item["ueis"])
        duns_values = sorted(item["duns"])
        names = sorted(item["names"])
        source_names = sorted(item["source_names"])
        rows.append(
            {
                "nsf_organization_id": organization_id,
                "nsf_awardee_name": source_names[0] if source_names else None,
                "recipient_uei": item["preferred_uei"] or (ueis[0] if ueis else None),
                "recipient_duns": item["preferred_duns"]
                or (duns_values[0] if duns_values else None),
                "normalized_name": item["preferred_name"] or (names[0] if names else None),
                "recipient_uei_aliases": json.dumps(ueis, separators=(",", ":")),
                "recipient_duns_aliases": json.dumps(duns_values, separators=(",", ":")),
                "normalized_name_aliases": json.dumps(names, separators=(",", ":")),
                "source_name_aliases": json.dumps(source_names, separators=(",", ":")),
                "organization_resolution_method": item["resolution_method"],
                "organization_resolution_confidence": item["resolution_confidence"],
                "nsf_awardee_status": item["awardee_status"],
                "identity_uei_count": len(ueis),
                "identity_duns_count": len(duns_values),
                "identity_name_count": len(names),
            }
        )
    return pd.DataFrame(rows)


def _registry_maps(
    registry: pd.DataFrame,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    required = {
        "nsf_organization_id",
        "recipient_uei_aliases",
        "recipient_duns_aliases",
        "normalized_name_aliases",
    }
    if missing := sorted(required - set(registry.columns)):
        raise ValueError(f"NSF identity registry is missing required columns: {missing}")
    owners: dict[str, dict[str, set[str]]] = {"uei": {}, "duns": {}, "name": {}}
    for _, row in registry.iterrows():
        organization_id = str(row["nsf_organization_id"])
        for key, column in (
            ("uei", "recipient_uei_aliases"),
            ("duns", "recipient_duns_aliases"),
            ("name", "normalized_name_aliases"),
        ):
            for value in _json_values(row[column]):
                owners[key].setdefault(value, set()).add(organization_id)
    if conflicts := {
        f"{kind}:{value}": sorted(ids)
        for kind in ("uei", "duns")
        for value, ids in owners[kind].items()
        if len(ids) > 1
    }:
        raise ValueError(
            f"exact identity aliases are ambiguous: {dict(sorted(conflicts.items())[:5])}"
        )
    maps = []
    for kind in ("uei", "duns", "name"):
        maps.append(
            {value: next(iter(ids)) for value, ids in owners[kind].items() if len(ids) == 1}
        )
    return cast(tuple[dict[str, str], dict[str, str], dict[str, str]], tuple(maps))


def _resolve_recipients(
    frame: pd.DataFrame,
    registry: pd.DataFrame,
    *,
    uei_column: str,
    duns_column: str,
    name_column: str,
    include_name_candidates: bool,
) -> pd.DataFrame:
    working = frame.copy()
    uei_map, duns_map, name_map = _registry_maps(registry)
    working["_recipient_uei"] = working[uei_column].map(_uei)
    working["_recipient_duns"] = working[duns_column].map(_duns)
    working["_recipient_normalized_name"] = working[name_column].map(_name)
    working["_uei_match"] = working["_recipient_uei"].map(uei_map)
    working["_duns_match"] = working["_recipient_duns"].map(duns_map)
    working["_name_match"] = (
        working["_recipient_normalized_name"].map(name_map) if include_name_candidates else pd.NA
    )
    conflicts = (
        working["_uei_match"].notna()
        & working["_duns_match"].notna()
        & working["_uei_match"].ne(working["_duns_match"])
    )
    if conflicts.any():
        raise ValueError("source rows contain conflicting exact UEI and DUNS organization matches")
    working["nsf_organization_id"] = (
        working["_uei_match"].fillna(working["_duns_match"]).fillna(working["_name_match"])
    )
    working = working.dropna(subset=["nsf_organization_id"]).copy()
    working["recipient_match_method"] = "exact_normalized_name"
    working["recipient_match_confidence"] = "candidate_name"
    working.loc[working["_duns_match"].notna(), "recipient_match_method"] = "exact_duns"
    working.loc[working["_duns_match"].notna(), "recipient_match_confidence"] = (
        "verified_legacy_identifier"
    )
    working.loc[working["_uei_match"].notna(), "recipient_match_method"] = "exact_uei"
    working.loc[working["_uei_match"].notna(), "recipient_match_confidence"] = "verified_identifier"
    working["recipient_match_evidence"] = working.apply(
        lambda row: json.dumps(
            {
                "source_uei": row["_recipient_uei"],
                "source_duns": row["_recipient_duns"],
                "source_normalized_name": row["_recipient_normalized_name"],
                "uei_match": row["_uei_match"],
                "duns_match": row["_duns_match"],
                "name_candidate_match": row["_name_match"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        axis=1,
    )
    return working


def _metadata(frame: pd.DataFrame, key: str) -> pd.Series:
    if "metadata" not in frame.columns:
        return pd.Series(pd.NA, index=frame.index, dtype="object")

    def value(item: object) -> object:
        if isinstance(item, dict):
            return item.get(key)
        if isinstance(item, str):
            try:
                parsed = json.loads(item)
            except json.JSONDecodeError:
                return None
            return parsed.get(key) if isinstance(parsed, dict) else None
        return None

    return frame["metadata"].map(value)


def normalize_prime_api_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize a loaded exact-UEI USAspending API snapshot."""

    required = {
        "prime_transaction_id",
        "dod_award_generated_id",
        "nsf_organization_id",
        "recipient_match_method",
        "recipient_match_confidence",
        "instrument_group",
        "signed_obligation_amount",
        "action_date",
    }
    if missing := sorted(required - set(frame.columns)):
        raise ValueError(f"USAspending API prime transactions are missing columns: {missing}")
    output = frame.copy()
    output["prime_transaction_id"] = output["prime_transaction_id"].map(_text)
    if output["prime_transaction_id"].isna().any():
        raise ValueError("USAspending API prime transactions contain missing source IDs")
    if output["prime_transaction_id"].duplicated().any():
        raise ValueError("USAspending API prime transaction IDs are not unique")
    output["signed_obligation_amount"] = pd.to_numeric(
        output["signed_obligation_amount"], errors="coerce"
    )
    if output["signed_obligation_amount"].isna().any():
        raise ValueError("USAspending API prime transactions contain missing obligations")
    output["action_date"] = pd.to_datetime(output["action_date"], errors="coerce", utc=True)
    if output["action_date"].isna().any():
        raise ValueError("USAspending API prime transactions contain missing action dates")
    output["fiscal_year"] = output["action_date"].map(_fiscal_year).astype("Int64")
    output["funding_mode"] = "prime"
    output["is_deobligation"] = output["signed_obligation_amount"].lt(0)
    output["is_zero_obligation"] = output["signed_obligation_amount"].eq(0)
    output["source_record_id"] = output["prime_transaction_id"]
    output["source_schema_version"] = output.get(
        "source_schema_version", DEFENSE_FUNDING_SCHEMA_VERSION
    )
    output["dod_agency_filter_method"] = "authoritative_toptier_agency_reference"
    return output.sort_values(["fiscal_year", "prime_transaction_id"]).reset_index(drop=True)


def normalize_prime_archive_transactions(
    frame: pd.DataFrame,
    registry: pd.DataFrame,
    *,
    source_path: Path | str | None = None,
    source_sha256: str | None = None,
    include_name_candidates: bool = True,
    ot_only: bool = False,
) -> pd.DataFrame:
    """Normalize recipient-filtered FPDS archive rows to signed prime transactions."""

    required = {
        "transaction_unique_id",
        "generated_unique_award_id",
        "vendor_name",
        "vendor_uei",
        "vendor_duns",
        "action_date",
        "obligation_amount",
        "contract_award_type",
    }
    if missing := sorted(required - set(frame.columns)):
        raise ValueError(f"USAspending contract archive is missing columns: {missing}")
    working = frame.copy()
    awarding_name = _first(working, ("agency", "awarding_toptier_agency_name"))
    funding_name = _metadata(working, "funding_agency")
    generated_id = working["generated_unique_award_id"].fillna("").astype(str)
    exact_name = awarding_name.fillna("").astype(str).str.casefold().eq(
        DOD_SOURCE_AGENCY_NAME.casefold()
    ) | funding_name.fillna("").astype(str).str.casefold().eq(DOD_SOURCE_AGENCY_NAME.casefold())
    source_code = generated_id.str.upper().str.contains(_DOD_AWARD_CODE)
    working["_dod_name_filter"] = exact_name
    working["_dod_code_filter"] = source_code
    working = working.loc[exact_name | source_code].copy()
    working["dod_agency_filter_method"] = "source_toptier_name"
    working.loc[working["_dod_code_filter"], "dod_agency_filter_method"] = (
        "generated_award_agency_code_9700"
    )
    working.loc[
        working["_dod_code_filter"] & working["_dod_name_filter"],
        "dod_agency_filter_method",
    ] = "source_toptier_name_and_generated_award_agency_code_9700"
    working = _resolve_recipients(
        working,
        registry,
        uei_column="vendor_uei",
        duns_column="vendor_duns",
        name_column="vendor_name",
        include_name_candidates=include_name_candidates,
    )
    award_type = working["contract_award_type"].fillna("").astype(str).str.strip().str.upper()
    is_ot = award_type.isin(_OTHER_TRANSACTION_CODES) | award_type.str.contains(
        "OTHER TRANSACTION", regex=False
    )
    working["instrument_group"] = "prime_procurement"
    working.loc[is_ot, "instrument_group"] = "prime_other_transaction"
    if ot_only:
        working = working.loc[working["instrument_group"].eq("prime_other_transaction")].copy()
    working["prime_transaction_id"] = working["transaction_unique_id"].map(_text)
    if working["prime_transaction_id"].isna().any():
        raise ValueError("matched archive prime transactions contain missing source IDs")
    if working["prime_transaction_id"].duplicated().any():
        raise ValueError("matched archive prime transaction IDs are not unique")
    working["signed_obligation_amount"] = pd.to_numeric(
        working["obligation_amount"], errors="coerce"
    )
    if working["signed_obligation_amount"].isna().any():
        raise ValueError("matched archive prime transactions contain missing obligations")
    working["action_date"] = pd.to_datetime(working["action_date"], errors="coerce", utc=True)
    if working["action_date"].isna().any():
        raise ValueError("matched archive prime transactions contain missing action dates")
    working["fiscal_year"] = working["action_date"].map(_fiscal_year).astype("Int64")
    working["funding_mode"] = "prime"
    working["is_deobligation"] = working["signed_obligation_amount"].lt(0)
    working["is_zero_obligation"] = working["signed_obligation_amount"].eq(0)
    working["dod_award_generated_id"] = working["generated_unique_award_id"].map(_text)
    working["dod_award_id"] = _first(working, ("piid", "contract_id")).map(_text)
    working["recipient_name_source"] = working["vendor_name"].map(_text)
    working["recipient_uei_source"] = working["vendor_uei"].map(_uei)
    working["recipient_duns_source"] = working["vendor_duns"].map(_duns)
    working["award_type_code"] = working["contract_award_type"].map(_text)
    working["transaction_description"] = _first(working, ("description", "transaction_description"))
    working["award_description"] = working["transaction_description"]
    working["award_start_date"] = pd.to_datetime(
        _first(working, ("start_date", "period_of_performance_start_date")),
        errors="coerce",
        utc=True,
    )
    working["award_end_date"] = pd.to_datetime(
        _first(working, ("end_date", "period_of_performance_current_end_date")),
        errors="coerce",
        utc=True,
    )
    working["awarding_agency_name"] = awarding_name.loc[working.index]
    working["funding_agency_name"] = funding_name.loc[working.index]
    working["awarding_subagency_name"] = _first(working, ("sub_agency",))
    working["naics_code"] = _first(working, ("naics_code",))
    working["product_or_service_code"] = _first(working, ("product_or_service_code",))
    source = Path(source_path) if source_path is not None else None
    source_hash = source_sha256 or (_file_sha256(source) if source and source.is_file() else None)
    working["source_system"] = "USAspending Award Data Archive (FPDS)"
    working["source_kind"] = "FPDS prime transaction"
    working["source_record_id"] = working["prime_transaction_id"]
    working["source_transaction_path"] = str(source) if source else None
    working["source_transaction_sha256"] = source_hash
    working["source_schema_version"] = DEFENSE_FUNDING_SCHEMA_VERSION
    output_columns = [
        "prime_transaction_id",
        "dod_award_generated_id",
        "dod_award_id",
        "nsf_organization_id",
        "recipient_name_source",
        "recipient_uei_source",
        "recipient_duns_source",
        "recipient_match_method",
        "recipient_match_confidence",
        "recipient_match_evidence",
        "funding_mode",
        "instrument_group",
        "award_type_code",
        "signed_obligation_amount",
        "is_deobligation",
        "is_zero_obligation",
        "action_date",
        "fiscal_year",
        "transaction_description",
        "award_description",
        "award_start_date",
        "award_end_date",
        "awarding_agency_name",
        "awarding_subagency_name",
        "funding_agency_name",
        "dod_agency_filter_method",
        "naics_code",
        "product_or_service_code",
        "source_system",
        "source_kind",
        "source_record_id",
        "source_transaction_path",
        "source_transaction_sha256",
        "source_schema_version",
    ]
    return (
        working[output_columns]
        .sort_values(["fiscal_year", "prime_transaction_id"])
        .reset_index(drop=True)
    )


def combine_prime_transactions(*frames: pd.DataFrame) -> pd.DataFrame:
    """Combine pre-partitioned prime sources and reject duplicate source transaction IDs."""

    usable = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return pd.DataFrame()
    combined = pd.concat(usable, ignore_index=True, sort=False)
    if combined["prime_transaction_id"].isna().any():
        raise ValueError("combined prime transactions contain missing source IDs")
    if combined["prime_transaction_id"].duplicated().any():
        duplicate = combined.loc[
            combined["prime_transaction_id"].duplicated(keep=False), "prime_transaction_id"
        ].iloc[0]
        raise ValueError(
            "prime sources overlap on a duplicate source transaction ID; check repeated inputs "
            f"for transaction {duplicate}"
        )
    return combined.sort_values(["fiscal_year", "prime_transaction_id"]).reset_index(drop=True)


def normalize_subaward_transactions(facts: pd.DataFrame) -> pd.DataFrame:
    """Project matched USAspending/FSRS subaward facts into the funding ledger."""

    required = {
        "subaward_fact_id",
        "sbir_organization_id",
        "match_method",
        "evidence_grade",
        "prime_award_unique_key",
        "prime_award_piid",
        "subaward_amount",
        "subaward_action_date",
        "subawardee_name",
    }
    if missing := sorted(required - set(facts.columns)):
        raise ValueError(f"matched subaward facts are missing columns: {missing}")
    output = pd.DataFrame(index=facts.index)
    output["subaward_transaction_id"] = facts["subaward_fact_id"].map(_text)
    output["dod_award_generated_id"] = facts["prime_award_unique_key"].map(_text)
    output["dod_award_id"] = facts["prime_award_piid"].map(_text)
    output["nsf_organization_id"] = facts["sbir_organization_id"].map(_text)
    output["recipient_name_source"] = facts["subawardee_name"].map(_text)
    output["recipient_uei_source"] = _first(facts, ("subawardee_uei",)).map(_uei)
    output["recipient_duns_source"] = _first(facts, ("subawardee_duns",)).map(_duns)
    output["recipient_match_method"] = facts["match_method"].astype("string")
    output["recipient_match_confidence"] = "candidate_name"
    output.loc[facts["evidence_grade"].eq("verified_identifier"), "recipient_match_confidence"] = (
        "verified_identifier"
    )
    output["recipient_match_evidence"] = facts.apply(
        lambda row: json.dumps(
            {
                "match_method": _text(row.get("match_method")),
                "evidence_grade": _text(row.get("evidence_grade")),
                "source_uei": _uei(row.get("subawardee_uei")),
                "source_duns": _duns(row.get("subawardee_duns")),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        axis=1,
    )
    output["funding_mode"] = "reported_subaward"
    award_keys = output["dod_award_generated_id"].fillna("").astype(str).str.upper()
    output["instrument_group"] = "reported_subaward_unknown"
    output.loc[award_keys.str.startswith("CONT_"), "instrument_group"] = "contract_subaward"
    output.loc[award_keys.str.startswith("ASST_"), "instrument_group"] = "assistance_subaward"
    output["signed_obligation_amount"] = pd.to_numeric(facts["subaward_amount"], errors="coerce")
    if output["signed_obligation_amount"].isna().any():
        raise ValueError("matched subaward transactions contain missing obligations")
    output["is_deobligation"] = output["signed_obligation_amount"].lt(0)
    output["is_zero_obligation"] = output["signed_obligation_amount"].eq(0)
    output["action_date"] = pd.to_datetime(facts["subaward_action_date"], errors="coerce", utc=True)
    if output["action_date"].isna().any():
        raise ValueError("matched subaward transactions contain missing action dates")
    output["fiscal_year"] = output["action_date"].map(_fiscal_year).astype("Int64")
    output["prime_recipient_name"] = _first(facts, ("prime_name",))
    output["prime_recipient_uei"] = _first(facts, ("prime_uei",)).map(_uei)
    output["prime_parent_name"] = _first(facts, ("prime_parent_name",))
    output["subaward_number"] = _first(facts, ("subaward_number",))
    output["subaward_sam_report_id"] = _first(facts, ("subaward_sam_report_id",))
    output["transaction_description"] = _first(facts, ("subaward_description",))
    output["award_description"] = _first(facts, ("prime_award_description",))
    output["naics_code"] = _first(facts, ("prime_naics_code",))
    output["awarding_agency_name"] = DOD_SOURCE_AGENCY_NAME
    output["dod_agency_filter_method"] = "input_is_dod_scoped_subaward_archive"
    output["source_system"] = _first(facts, ("source_system",)).fillna(
        "USAspending.gov subaward data (SAM.gov/FSRS)"
    )
    output["source_kind"] = "reported first-tier subaward"
    output["source_record_id"] = output["subaward_transaction_id"]
    output["source_url"] = _first(facts, ("source_url",))
    output["source_last_modified"] = pd.to_datetime(
        _first(facts, ("source_last_modified",)), errors="coerce", utc=True
    )
    output["source_transaction_path"] = _first(facts, ("source_input_path",))
    output["source_transaction_sha256"] = _first(facts, ("source_input_sha256",))
    output["source_schema_version"] = DEFENSE_FUNDING_SCHEMA_VERSION
    if output["subaward_transaction_id"].isna().any():
        raise ValueError("matched subaward transactions contain missing source IDs")
    if output["subaward_transaction_id"].duplicated().any():
        raise ValueError("matched subaward transaction IDs are not unique")
    return output.sort_values(["fiscal_year", "subaward_transaction_id"]).reset_index(drop=True)


def _verified(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[
        frame["recipient_match_confidence"].isin(
            ["verified_identifier", "verified_legacy_identifier"]
        )
    ].copy()


def build_defense_funding_summary(
    prime_transactions: pd.DataFrame,
    subaward_transactions: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate verified signed flows without mixing funding modes or instruments."""

    frames: list[pd.DataFrame] = []
    for frame, identifier in (
        (prime_transactions, "prime_transaction_id"),
        (subaward_transactions, "subaward_transaction_id"),
    ):
        if frame.empty:
            continue
        source = _verified(frame)
        source = source.copy()
        source["_source_transaction_id"] = source[identifier].astype(str)
        source["_positive_amount"] = source["signed_obligation_amount"].clip(lower=0)
        source["_negative_amount"] = source["signed_obligation_amount"].clip(upper=0)
        frames.append(source)
    if not frames:
        return pd.DataFrame()
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keys = ["nsf_organization_id", "fiscal_year", "funding_mode", "instrument_group"]
    summary = ledger.groupby(keys, as_index=False, dropna=False).agg(
        signed_obligation_total=("signed_obligation_amount", "sum"),
        positive_obligation_total=("_positive_amount", "sum"),
        deobligation_total=("_negative_amount", "sum"),
        source_transaction_count=("_source_transaction_id", "nunique"),
        positive_transaction_count=(
            "signed_obligation_amount",
            lambda values: int(values.gt(0).sum()),
        ),
        negative_transaction_count=(
            "signed_obligation_amount",
            lambda values: int(values.lt(0).sum()),
        ),
        zero_transaction_count=("signed_obligation_amount", lambda values: int(values.eq(0).sum())),
        dod_award_count=("dod_award_generated_id", "nunique"),
        first_observed_funding_date=("action_date", "min"),
        last_observed_funding_date=("action_date", "max"),
        recipient_match_methods=("recipient_match_method", _json_unique),
        recipient_match_confidences=("recipient_match_confidence", _json_unique),
        source_transaction_ids=("_source_transaction_id", _json_unique),
        source_award_ids=("dod_award_generated_id", _json_unique),
        source_systems=("source_system", _json_unique),
    )
    summary["observed_fiscal_year_count"] = summary.groupby(
        ["nsf_organization_id", "funding_mode", "instrument_group"], dropna=False
    )["fiscal_year"].transform("nunique")
    summary["verified_totals_only"] = True
    summary["funding_interpretation"] = (
        "Observed signed DoD funding to the legal entity; no specific NSF-award use is established"
    )
    return summary.sort_values(keys).reset_index(drop=True)


def _temporal_association(row: pd.Series) -> str:
    nsf_start = pd.to_datetime(str(row.get("nsf_start_date")), errors="coerce", utc=True)
    nsf_end = pd.to_datetime(str(row.get("nsf_end_date")), errors="coerce", utc=True)
    dod_first = pd.to_datetime(str(row.get("dod_first_action_date")), errors="coerce", utc=True)
    dod_last = pd.to_datetime(str(row.get("dod_last_action_date")), errors="coerce", utc=True)
    if any(pd.isna(value) for value in (nsf_start, nsf_end, dod_first, dod_last)):
        return "indeterminate"
    nsf_start_timestamp = cast(pd.Timestamp, nsf_start)
    nsf_end_timestamp = cast(pd.Timestamp, nsf_end)
    dod_first_timestamp = cast(pd.Timestamp, dod_first)
    dod_last_timestamp = cast(pd.Timestamp, dod_last)
    if dod_last_timestamp < nsf_start_timestamp:
        return "before_nsf_performance_period"
    if dod_first_timestamp > nsf_end_timestamp:
        return "after_nsf_performance_period"
    return "overlaps_nsf_performance_period"


def build_nsf_award_defense_evidence(
    direct_awards: pd.DataFrame,
    prime_transactions: pd.DataFrame,
    subaward_transactions: pd.DataFrame,
    *,
    award_screen: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Emit award-to-award review assertions without inferring capability use."""

    if "nsf_award_id" not in direct_awards.columns or "nsf_organization_id" not in direct_awards:
        raise ValueError("direct NSF awards are missing award or organization identifiers")
    sources: list[pd.DataFrame] = []
    for frame, identifier in (
        (prime_transactions, "prime_transaction_id"),
        (subaward_transactions, "subaward_transaction_id"),
    ):
        if frame.empty:
            continue
        source = frame.copy()
        source["_source_transaction_id"] = source[identifier].astype(str)
        for column in (
            "source_transaction_path",
            "source_transaction_sha256",
            "source_url",
            "source_kind",
            "award_description",
            "transaction_description",
            "product_or_service_code",
            "naics_code",
        ):
            if column not in source.columns:
                source[column] = pd.NA
        sources.append(source)
    if not sources:
        return pd.DataFrame()
    transactions = pd.concat(sources, ignore_index=True, sort=False)
    transactions["_dod_award_key"] = transactions["dod_award_generated_id"].fillna(
        transactions["dod_award_id"]
    )
    transactions = transactions.dropna(subset=["_dod_award_key"])
    award_keys = [
        "nsf_organization_id",
        "_dod_award_key",
        "funding_mode",
        "instrument_group",
        "recipient_match_method",
        "recipient_match_confidence",
    ]
    dod_awards = transactions.groupby(award_keys, as_index=False, dropna=False).agg(
        dod_award_generated_id=("dod_award_generated_id", "first"),
        dod_award_id=("dod_award_id", "first"),
        dod_first_action_date=("action_date", "min"),
        dod_last_action_date=("action_date", "max"),
        signed_obligation_total=("signed_obligation_amount", "sum"),
        source_transaction_count=("_source_transaction_id", "nunique"),
        source_transaction_ids=("_source_transaction_id", _json_unique),
        source_systems=("source_system", _json_unique),
        source_paths=("source_transaction_path", _json_unique),
        source_sha256s=("source_transaction_sha256", _json_unique),
        source_urls=("source_url", _json_unique),
        source_record_kinds=("source_kind", _json_unique),
        review_award_descriptions=("award_description", _json_unique),
        review_transaction_descriptions=("transaction_description", _json_unique),
        review_product_service_codes=("product_or_service_code", _json_unique),
        review_naics_codes=("naics_code", _json_unique),
    )
    nsf_columns = [
        "nsf_award_id",
        "nsf_organization_id",
        "nsf_program",
        "nsf_phase",
        "nsf_award_title",
        "nsf_start_date",
        "nsf_end_date",
        "nsf_award_performance_status",
        "analysis_date",
        "source_url",
        "source_path",
        "source_record_sha256",
    ]
    nsf = direct_awards.copy()
    for column in nsf_columns:
        if column not in nsf.columns:
            nsf[column] = pd.NA
    evidence = nsf[nsf_columns].merge(
        dod_awards,
        on="nsf_organization_id",
        how="inner",
        validate="many_to_many",
        suffixes=("_nsf", "_dod"),
    )
    evidence["temporal_association"] = evidence.apply(_temporal_association, axis=1)
    evidence["temporal_association_is_causal_evidence"] = False
    evidence["evidence_method"] = "legal_entity_cooccurrence_and_timing"
    evidence["specific_award_usage_status"] = "not_established"
    evidence["critical_supply_chain_status"] = "not_assessed"
    evidence["evidence_limitation"] = (
        "Shared legal-entity identity and timing do not establish use of NSF-funded work"
    )
    if award_screen is not None:
        if "nsf_award_id" not in award_screen.columns:
            raise ValueError("NSF award screen is missing nsf_award_id")
        if award_screen["nsf_award_id"].duplicated().any():
            raise ValueError("NSF award screen IDs are not unique")
        screen_columns = [
            "nsf_award_id",
            "primary_cet",
            "primary_cet_score",
            "supporting_cets",
            "cet_evidence",
            "cet_taxonomy_version",
            "cet_classifier_version",
            "verified_dod_funding_observed",
            "critical_supply_chain_review_candidate",
            "critical_supply_chain_screen_basis",
            "defense_policy_mapping_status",
            "defense_policy_mapping_version",
            "screen_version",
        ]
        available = [column for column in screen_columns if column in award_screen.columns]
        evidence = evidence.merge(
            award_screen[available],
            on="nsf_award_id",
            how="left",
            validate="many_to_one",
        )
    evidence["evidence_assertion_id"] = evidence.apply(
        lambda row: "nsf-dod-evidence:"
        + hashlib.sha256(
            json.dumps(
                [
                    _text(row.get("nsf_award_id")),
                    _text(row.get("_dod_award_key")),
                    _text(row.get("funding_mode")),
                    _text(row.get("instrument_group")),
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:20],
        axis=1,
    )
    return evidence.sort_values(
        ["nsf_award_id", "dod_first_action_date", "_dod_award_key"]
    ).reset_index(drop=True)


def evaluate_defense_funding_quality(
    prime_transactions: pd.DataFrame,
    subaward_transactions: pd.DataFrame,
    summary: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    award_screen: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Evaluate fail-closed funding and evidence invariants."""

    prime_ids_unique = bool(
        prime_transactions.empty
        or (
            prime_transactions["prime_transaction_id"].notna().all()
            and ~prime_transactions["prime_transaction_id"].duplicated().any()
        )
    )
    subaward_ids_unique = bool(
        subaward_transactions.empty
        or (
            subaward_transactions["subaward_transaction_id"].notna().all()
            and ~subaward_transactions["subaward_transaction_id"].duplicated().any()
        )
    )

    def flags_are_consistent(frame: pd.DataFrame) -> bool:
        return bool(
            frame.empty
            or (
                frame["is_deobligation"].eq(frame["signed_obligation_amount"].lt(0)).all()
                and frame["is_zero_obligation"].eq(frame["signed_obligation_amount"].eq(0)).all()
            )
        )

    verified_total = sum(
        float(_verified(frame)["signed_obligation_amount"].sum())
        for frame in (prime_transactions, subaward_transactions)
        if not frame.empty
    )
    summary_total = float(summary["signed_obligation_total"].sum()) if not summary.empty else 0.0
    traceability = True
    if not summary.empty:
        traceability = bool(
            summary.apply(
                lambda row: len(_json_values(row["source_transaction_ids"]))
                == int(row["source_transaction_count"]),
                axis=1,
            ).all()
        )
    candidate_excluded = bool(
        summary.empty
        or summary["recipient_match_confidences"]
        .map(lambda value: "candidate_name" not in _json_values(value))
        .all()
    )
    modes_separate = bool(
        (prime_transactions.empty or prime_transactions["funding_mode"].eq("prime").all())
        and (
            subaward_transactions.empty
            or subaward_transactions["funding_mode"].eq("reported_subaward").all()
        )
    )
    evidence_gated = bool(
        evidence.empty
        or (
            evidence["specific_award_usage_status"].eq("not_established").all()
            and evidence["critical_supply_chain_status"].eq("not_assessed").all()
            and ~evidence["temporal_association_is_causal_evidence"].any()
        )
    )
    screen_versions_complete = bool(
        award_screen is None
        or award_screen.empty
        or award_screen[["cet_taxonomy_version", "cet_classifier_version"]].notna().all(axis=None)
    )
    policy_mapping_deferred = bool(
        award_screen is None
        or award_screen.empty
        or award_screen["defense_policy_mapping_status"]
        .eq("deferred_no_authoritative_dod14_or_ndis8_mapping")
        .all()
    )
    award_screen_gated = bool(
        award_screen is None
        or award_screen.empty
        or (
            award_screen["critical_supply_chain_status"].eq("not_assessed").all()
            and award_screen["specific_award_usage_status"].eq("not_established").all()
        )
    )
    gates = {
        "prime_transaction_ids_unique": prime_ids_unique,
        "subaward_transaction_ids_unique": subaward_ids_unique,
        "signed_obligation_totals_reconcile": abs(verified_total - summary_total) <= 0.005,
        "negative_and_zero_transactions_preserved": flags_are_consistent(prime_transactions)
        and flags_are_consistent(subaward_transactions),
        "prime_and_subaward_modes_separate": modes_separate,
        "weak_name_candidates_excluded_from_verified_summary": candidate_excluded,
        "aggregate_source_ids_traceable": traceability,
        "specific_award_and_criticality_evidence_gated": evidence_gated,
        "cet_classifier_versions_complete": screen_versions_complete,
        "dod14_ndis8_policy_mapping_deferred": policy_mapping_deferred,
        "award_screen_conclusions_evidence_gated": award_screen_gated,
    }
    return {
        "schema_version": DEFENSE_FUNDING_SCHEMA_VERSION,
        "prime_transaction_count": int(len(prime_transactions)),
        "subaward_transaction_count": int(len(subaward_transactions)),
        "verified_prime_transaction_count": int(len(_verified(prime_transactions)))
        if not prime_transactions.empty
        else 0,
        "verified_subaward_transaction_count": int(len(_verified(subaward_transactions)))
        if not subaward_transactions.empty
        else 0,
        "prime_negative_transaction_count": int(
            prime_transactions["signed_obligation_amount"].lt(0).sum()
        )
        if not prime_transactions.empty
        else 0,
        "subaward_negative_transaction_count": int(
            subaward_transactions["signed_obligation_amount"].lt(0).sum()
        )
        if not subaward_transactions.empty
        else 0,
        "verified_signed_obligation_total": verified_total,
        "summary_signed_obligation_total": summary_total,
        "evidence_assertion_count": int(len(evidence)),
        "award_screen_count": int(len(award_screen)) if award_screen is not None else 0,
        "quality_gates": gates,
        "quality_gates_passed": bool(all(gates.values())),
    }


__all__ = [
    "DEFENSE_FUNDING_SCHEMA_VERSION",
    "DOD_FPDS_AGENCY_CODE",
    "DOD_SOURCE_AGENCY_NAME",
    "build_defense_funding_summary",
    "build_nsf_award_defense_evidence",
    "build_nsf_identity_registry",
    "combine_prime_transactions",
    "evaluate_defense_funding_quality",
    "normalize_prime_api_transactions",
    "normalize_prime_archive_transactions",
    "normalize_subaward_transactions",
]
