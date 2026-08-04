"""Immutable USAspending prime-transaction snapshots for resolved NSF awardees."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

import pandas as pd
from loguru import logger

from sbir_etl.enrichers.usaspending.client import USAspendingAPIClient
from sbir_etl.exceptions import APIError

USASPENDING_API_BASE = "https://api.usaspending.gov/api/v2"
USASPENDING_API_DOCUMENTATION = "https://api.usaspending.gov/docs/endpoints"
USASPENDING_PRIME_SCHEMA_VERSION = "USASPENDING-NSF-PRIME-2026Q3"
USASPENDING_EARLIEST_SEARCH_DATE = date(2007, 10, 1)
DOD_AGENCY_NAME = "Department of Defense"
DOD_CGAC_CODE = "097"
DOD_USASPENDING_AGENCY_ID = 1173

AWARD_TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "procurement": ("A", "B", "C", "D"),
    "grant_assistance": ("02", "03", "04", "05", "F001", "F002"),
    "direct_assistance": ("06", "10", "F006", "F007"),
    "other_assistance": ("09", "11", "-1", "F005", "F008", "F009", "F010"),
}
AGENCY_SCOPES = ("awarding", "funding")
AWARD_FIELDS = [
    "generated_internal_id",
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Award Amount",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "awarding_agency_id",
    "Awarding Sub Agency",
    "Funding Agency",
    "Funding Sub Agency",
    "Description",
    "naics_code",
    "product_or_service_code",
    "Assistance Listing",
]

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _clean_uei(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    cleaned = _NON_ALNUM.sub("", str(value).upper())
    return cleaned if len(cleaned) == 12 else None


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"immutable USAspending snapshot would change: {path}")
        return
    with path.open("xb") as handle:
        handle.write(content)


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n")
    temporary.replace(path)


def _request_hash(payload: object) -> str:
    return _sha256(_canonical(payload))[:12]


def _fiscal_year(value: object) -> int | None:
    timestamp = pd.to_datetime(str(value), errors="coerce", utc=True)
    if pd.isna(timestamp):
        return None
    return int(timestamp.year + (timestamp.month >= 10))


def _request_spec(
    ueis: list[str], start_date: date, end_date: date, batch_size: int
) -> dict[str, object]:
    return {
        "schema_version": USASPENDING_PRIME_SCHEMA_VERSION,
        "recipient_ueis": ueis,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "batch_size": batch_size,
        "award_type_groups": {key: list(value) for key, value in AWARD_TYPE_GROUPS.items()},
        "agency_scopes": list(AGENCY_SCOPES),
        "dod_agency": {
            "name": DOD_AGENCY_NAME,
            "cgac_code": DOD_CGAC_CODE,
            "usaspending_agency_id": DOD_USASPENDING_AGENCY_ID,
        },
    }


async def _load_or_call(
    path: Path,
    *,
    request: dict[str, Any],
    call: Callable[[], Awaitable[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, object]]:
    if path.is_file():
        content = path.read_bytes()
        wrapper = json.loads(content)
        if wrapper.get("request") != request:
            raise FileExistsError(f"saved USAspending page has a different request: {path}")
        response = wrapper.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"saved USAspending page has no response object: {path}")
        return response, {
            "relative_path": str(path),
            "sha256": _sha256(content),
            "bytes": len(content),
            "retrieved_at": wrapper.get("retrieved_at"),
            "reused": True,
        }
    response = await call()
    wrapper = {
        "request": request,
        "response": response,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    content = _canonical(wrapper)
    _write_immutable(path, content)
    return response, {
        "relative_path": str(path),
        "sha256": _sha256(content),
        "bytes": len(content),
        "retrieved_at": wrapper["retrieved_at"],
        "reused": False,
    }


def _validated_awardees(awardees: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    required = {"nsf_organization_id", "nsf_awardee_uei"}
    if missing := sorted(required - set(awardees.columns)):
        raise ValueError(f"NSF awardees are missing required columns: {missing}")
    usable = awardees[["nsf_organization_id", "nsf_awardee_uei"]].copy()
    usable["uei"] = usable["nsf_awardee_uei"].map(_clean_uei)
    usable = usable.dropna(subset=["uei", "nsf_organization_id"]).drop_duplicates()
    if usable["uei"].duplicated().any():
        raise ValueError("one recipient UEI resolves to multiple NSF organization IDs")
    mapping = usable.set_index("uei")["nsf_organization_id"].astype(str).to_dict()
    return sorted(mapping), mapping


def _validate_agency_reference(payload: dict[str, Any]) -> dict[str, object]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise APIError("USAspending top-tier agency reference returned no results list")
    matches = [
        item
        for item in results
        if isinstance(item, dict)
        and item.get("agency_name") == DOD_AGENCY_NAME
        and str(item.get("toptier_code")) == DOD_CGAC_CODE
    ]
    if len(matches) != 1:
        raise APIError(f"expected one authoritative DoD agency reference; found {len(matches)}")
    match = matches[0]
    if int(match.get("agency_id", -1)) != DOD_USASPENDING_AGENCY_ID:
        raise APIError(
            "USAspending DoD agency identifier changed: "
            f"expected {DOD_USASPENDING_AGENCY_ID}, got {match.get('agency_id')}"
        )
    return {
        "agency_id": int(match["agency_id"]),
        "toptier_code": str(match["toptier_code"]),
        "agency_name": str(match["agency_name"]),
        "abbreviation": match.get("abbreviation"),
        "agency_slug": match.get("agency_slug"),
    }


def _award_identity(record: dict[str, Any]) -> str:
    generated = str(record.get("generated_internal_id") or "").strip()
    if not generated:
        raise APIError("USAspending award result has no generated_internal_id")
    return generated


async def fetch_usaspending_prime_snapshot(
    awardees: pd.DataFrame,
    snapshot_dir: Path | str,
    *,
    start_date: date = USASPENDING_EARLIEST_SEARCH_DATE,
    end_date: date,
    client: USAspendingAPIClient | None = None,
    batch_size: int = 20,
    max_concurrency: int = 8,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Fetch exact-UEI DoD prime awards and their source-grain transactions."""

    if start_date < USASPENDING_EARLIEST_SEARCH_DATE:
        raise ValueError(
            f"USAspending search start date cannot precede {USASPENDING_EARLIEST_SEARCH_DATE}"
        )
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")
    if batch_size < 1 or batch_size > 50:
        raise ValueError("batch_size must be between 1 and 50")
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least one")
    ueis, organization_by_uei = _validated_awardees(awardees)
    if not ueis:
        raise ValueError("no verified NSF awardee UEIs are available for prime funding lookup")
    directory = Path(snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    spec = _request_spec(ueis, start_date, end_date, batch_size)
    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest.get("request_spec") != spec:
            raise FileExistsError("USAspending prime manifest exists for a different request")
        return existing_manifest

    owned_client = client is None
    active_client = client or USAspendingAPIClient(
        config={
            "timeout_seconds": 60,
            "rate_limit_per_minute": 120,
            "state_file": str(directory / "client_state.json"),
            "usaspending_api": {"base_url": USASPENDING_API_BASE},
        }
    )
    semaphore = asyncio.Semaphore(max_concurrency)
    file_entries: list[dict[str, object]] = []
    failures: dict[str, str] = {}
    try:
        agency_request = {"endpoint": "/references/toptier_agencies/"}
        async with semaphore:
            agency_payload, agency_file = await _load_or_call(
                directory / "agency_reference.json",
                request=agency_request,
                call=active_client.get_toptier_agencies,
            )
        agency_file["kind"] = "agency_reference"
        file_entries.append(agency_file)
        agency_reference = _validate_agency_reference(agency_payload)

        batches = [ueis[index : index + batch_size] for index in range(0, len(ueis), batch_size)]
        logger.info(
            "USAspending prime snapshot: {} UEIs, {} search batches, {} type/scope queries",
            len(ueis),
            len(batches),
            len(batches) * len(AWARD_TYPE_GROUPS) * len(AGENCY_SCOPES),
        )

        async def search_batch(
            group: str, codes: tuple[str, ...], scope: str, index: int, batch: list[str]
        ) -> list[dict[str, Any]]:
            found: list[dict[str, Any]] = []
            page = 1
            batch_key = f"{index:05d}-{_request_hash(batch)}"
            while True:
                filters = {
                    "time_period": [
                        {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                    ],
                    "agencies": [{"type": scope, "tier": "toptier", "name": DOD_AGENCY_NAME}],
                    "recipient_search_text": batch,
                    "award_type_codes": list(codes),
                }
                request = {
                    "endpoint": "/search/spending_by_award/",
                    "filters": filters,
                    "fields": AWARD_FIELDS,
                    "page": page,
                    "limit": 100,
                    "sort": "Award ID",
                    "order": "asc",
                }
                path = (
                    directory / "award_search" / group / scope / batch_key / f"page-{page:05d}.json"
                )
                async with semaphore:
                    payload, entry = await _load_or_call(
                        path,
                        request=request,
                        call=partial(
                            active_client.search_awards,
                            filters=filters,
                            fields=AWARD_FIELDS,
                            page=page,
                            limit=100,
                            sort="Award ID",
                            order="asc",
                        ),
                    )
                entry.update(kind="award_search", instrument_group=group, agency_scope=scope)
                file_entries.append(entry)
                results = payload.get("results")
                if not isinstance(results, list):
                    raise APIError(f"USAspending award search returned no results list: {path}")
                for raw_record in results:
                    if not isinstance(raw_record, dict):
                        continue
                    recipient_uei = _clean_uei(raw_record.get("Recipient UEI"))
                    if recipient_uei not in organization_by_uei:
                        continue
                    record = dict(raw_record)
                    record["_instrument_query_group"] = group
                    record["_agency_query_scope"] = scope
                    record["_matched_nsf_organization_id"] = organization_by_uei[recipient_uei]
                    record["_search_source_path"] = str(path)
                    record["_search_source_sha256"] = entry["sha256"]
                    record["_search_retrieved_at"] = entry["retrieved_at"]
                    found.append(record)
                metadata = payload.get("page_metadata")
                has_next = isinstance(metadata, dict) and bool(
                    metadata.get("hasNext") or metadata.get("next")
                )
                if not has_next:
                    return found
                page += 1
                if page > 10_000:
                    raise APIError("USAspending award search exceeded 10,000 pages")

        search_tasks = [
            asyncio.create_task(search_batch(group, codes, scope, index, batch))
            for group, codes in AWARD_TYPE_GROUPS.items()
            for scope in AGENCY_SCOPES
            for index, batch in enumerate(batches)
        ]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        raw_awards: list[dict[str, Any]] = []
        for index, result in enumerate(search_results):
            if isinstance(result, BaseException):
                failures[f"award_search_{index}"] = f"{type(result).__name__}: {result}"
            else:
                raw_awards.extend(result)

        awards: dict[str, dict[str, Any]] = {}
        for record in raw_awards:
            generated_id = _award_identity(record)
            existing = awards.get(generated_id)
            if existing is None:
                record["_agency_query_scopes"] = [record.pop("_agency_query_scope")]
                awards[generated_id] = record
                continue
            if _clean_uei(existing.get("Recipient UEI")) != _clean_uei(record.get("Recipient UEI")):
                raise APIError(f"USAspending award {generated_id} returned conflicting recipients")
            scope = record.get("_agency_query_scope")
            if scope not in existing["_agency_query_scopes"]:
                existing["_agency_query_scopes"].append(scope)
                existing["_agency_query_scopes"].sort()
        award_index = [awards[key] for key in sorted(awards)]
        award_index_content = _canonical(award_index)
        award_index_path = directory / "award_index.json"
        award_index_reused = award_index_path.exists()
        _write_immutable(award_index_path, award_index_content)
        file_entries.append(
            {
                "kind": "award_index",
                "relative_path": str(award_index_path),
                "sha256": _sha256(award_index_content),
                "bytes": len(award_index_content),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "reused": award_index_reused,
            }
        )

        async def transactions_for_award(award: dict[str, Any]) -> list[dict[str, Any]]:
            generated_id = _award_identity(award)
            award_hash = _request_hash(generated_id)
            page = 1
            rows: list[dict[str, Any]] = []
            while True:
                request = {
                    "endpoint": "/transactions/",
                    "award_id": generated_id,
                    "page": page,
                    "limit": 5000,
                    "sort": "action_date",
                    "order": "asc",
                }
                path = directory / "transactions" / award_hash / f"page-{page:05d}.json"
                async with semaphore:
                    payload, entry = await _load_or_call(
                        path,
                        request=request,
                        call=partial(
                            active_client.get_award_transactions,
                            generated_id,
                            page=page,
                            limit=5000,
                        ),
                    )
                entry.update(kind="award_transactions", generated_award_id=generated_id)
                file_entries.append(entry)
                results = payload.get("results")
                if not isinstance(results, list):
                    raise APIError(f"USAspending transactions returned no results list: {path}")
                for raw_transaction in results:
                    if not isinstance(raw_transaction, dict):
                        continue
                    transaction = dict(raw_transaction)
                    transaction["_award"] = award
                    transaction["_transaction_source_path"] = str(path)
                    transaction["_transaction_source_sha256"] = entry["sha256"]
                    transaction["_transaction_retrieved_at"] = entry["retrieved_at"]
                    rows.append(transaction)
                metadata = payload.get("page_metadata")
                has_next = isinstance(metadata, dict) and bool(
                    metadata.get("hasNext") or metadata.get("next")
                )
                if not has_next:
                    return rows
                page += 1
                if page > 10_000:
                    raise APIError(f"USAspending award {generated_id} exceeded 10,000 pages")

        transaction_tasks = [
            asyncio.create_task(transactions_for_award(award)) for award in award_index
        ]
        transaction_results = await asyncio.gather(*transaction_tasks, return_exceptions=True)
        raw_transactions: list[dict[str, Any]] = []
        for index, result in enumerate(transaction_results):
            if isinstance(result, BaseException):
                failures[f"award_transactions_{index}"] = f"{type(result).__name__}: {result}"
            else:
                raw_transactions.extend(result)
        normalized_source = [
            _normalize_transaction(item, agency_reference) for item in raw_transactions
        ]
        normalized: list[dict[str, object]] = []
        for transaction in normalized_source:
            action_date = pd.to_datetime(
                str(transaction.get("action_date")), errors="coerce", utc=True
            )
            if pd.isna(action_date):
                raise APIError(
                    f"USAspending transaction {transaction.get('prime_transaction_id')} "
                    "has no usable action date"
                )
            if start_date <= action_date.date() <= end_date:
                normalized.append(transaction)
        out_of_window_transaction_count = len(normalized_source) - len(normalized)
        transaction_ids = [str(item["prime_transaction_id"]) for item in normalized]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise APIError("USAspending prime transaction IDs are not unique")
        transaction_content = _canonical(normalized)
        transaction_index_path = directory / "prime_transaction_index.json"
        transaction_index_reused = transaction_index_path.exists()
        _write_immutable(transaction_index_path, transaction_content)
        file_entries.append(
            {
                "kind": "prime_transaction_index",
                "relative_path": str(transaction_index_path),
                "sha256": _sha256(transaction_content),
                "bytes": len(transaction_content),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "reused": transaction_index_reused,
            }
        )
    finally:
        if owned_client:
            await active_client.aclose()

    relative_entries = []
    for entry in file_entries:
        normalized_entry = dict(entry)
        path = Path(str(normalized_entry["relative_path"]))
        normalized_entry["relative_path"] = str(path.relative_to(directory))
        relative_entries.append(normalized_entry)
    manifest: dict[str, Any] = {
        "schema_version": USASPENDING_PRIME_SCHEMA_VERSION,
        "source_system": "USAspending API",
        "source_documentation": USASPENDING_API_DOCUMENTATION,
        "snapshot_created_at": datetime.now(UTC).isoformat(),
        "request_spec": spec,
        "agency_reference": agency_reference,
        "verified_recipient_uei_count": len(ueis),
        "matched_prime_award_count": len(award_index),
        "source_transaction_count": len(normalized_source),
        "prime_transaction_count": len(normalized),
        "out_of_window_transaction_count": out_of_window_transaction_count,
        "negative_transaction_count": sum(
            float(cast(Any, item.get("signed_obligation_amount") or 0)) < 0 for item in normalized
        ),
        "zero_transaction_count": sum(
            float(cast(Any, item.get("signed_obligation_amount") or 0)) == 0 for item in normalized
        ),
        "failed_request_count": len(failures),
        "retrieval_complete": not failures,
        "files": sorted(relative_entries, key=lambda item: str(item["relative_path"])),
        "failures": failures,
        "coverage_limitations": [
            "Advanced Search begins 2007-10-01; older transactions require bulk archives",
            "award transaction histories are clipped to the requested action-date window",
            "FPDS Other Transaction codes O/R are not accepted by Advanced Search and are loaded separately",
            "only exact UEI matches enter verified prime totals",
        ],
    }
    _write_json_atomic(directory / "manifest.partial.json", manifest)
    if failures and not allow_partial:
        raise APIError(
            f"USAspending prime snapshot has {len(failures)} failed requests; "
            f"sample={dict(sorted(failures.items())[:5])}"
        )
    if not failures:
        _write_immutable(
            manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
        )
    return manifest


def _normalize_transaction(
    transaction: dict[str, Any], agency_reference: dict[str, object]
) -> dict[str, object]:
    award = transaction.get("_award")
    if not isinstance(award, dict):
        raise APIError("USAspending transaction has no award context")
    transaction_id = str(transaction.get("id") or "").strip()
    if not transaction_id:
        raise APIError("USAspending transaction has no source transaction ID")
    group = str(award.get("_instrument_query_group") or "")
    obligation = pd.to_numeric(
        pd.Series([transaction.get("federal_action_obligation")]), errors="coerce"
    ).iloc[0]
    amount = None if pd.isna(obligation) else float(obligation)
    recipient_uei = _clean_uei(award.get("Recipient UEI"))
    return {
        "prime_transaction_id": transaction_id,
        "dod_award_generated_id": _award_identity(award),
        "dod_award_id": award.get("Award ID"),
        "nsf_organization_id": award.get("_matched_nsf_organization_id"),
        "recipient_name_source": award.get("Recipient Name"),
        "recipient_uei_source": recipient_uei,
        "recipient_match_method": "exact_uei",
        "recipient_match_confidence": "verified_identifier",
        "funding_mode": "prime",
        "instrument_group": "prime_procurement" if group == "procurement" else "prime_assistance",
        "instrument_query_group": group,
        "award_type_code": transaction.get("type"),
        "award_type_description": transaction.get("type_description"),
        "signed_obligation_amount": amount,
        "is_deobligation": amount is not None and amount < 0,
        "is_zero_obligation": amount == 0 if amount is not None else False,
        "action_date": transaction.get("action_date"),
        "fiscal_year": _fiscal_year(transaction.get("action_date")),
        "action_type_code": transaction.get("action_type"),
        "action_type_description": transaction.get("action_type_description"),
        "modification_number": transaction.get("modification_number"),
        "transaction_description": transaction.get("description"),
        "award_description": award.get("Description"),
        "award_start_date": award.get("Start Date"),
        "award_end_date": award.get("End Date"),
        "award_current_amount": award.get("Award Amount"),
        "awarding_agency_name": award.get("Awarding Agency"),
        "awarding_agency_id": award.get("awarding_agency_id"),
        "awarding_subagency_name": award.get("Awarding Sub Agency"),
        "funding_agency_name": award.get("Funding Agency"),
        "funding_subagency_name": award.get("Funding Sub Agency"),
        "dod_toptier_cgac_code": agency_reference["toptier_code"],
        "dod_usaspending_agency_id": agency_reference["agency_id"],
        "agency_query_scopes": json.dumps(award.get("_agency_query_scopes", [])),
        "naics_code": award.get("naics_code"),
        "product_or_service_code": award.get("product_or_service_code"),
        "assistance_listing": award.get("Assistance Listing"),
        "source_system": "USAspending API",
        "source_kind": (
            "FPDS prime transaction" if group == "procurement" else "FABS prime transaction"
        ),
        "source_endpoint": f"{USASPENDING_API_BASE}/transactions/",
        "source_transaction_path": transaction.get("_transaction_source_path"),
        "source_transaction_sha256": transaction.get("_transaction_source_sha256"),
        "source_retrieved_at": transaction.get("_transaction_retrieved_at"),
        "source_award_search_path": award.get("_search_source_path"),
        "source_award_search_sha256": award.get("_search_source_sha256"),
        "source_schema_version": USASPENDING_PRIME_SCHEMA_VERSION,
    }


def load_usaspending_prime_snapshot(
    snapshot_dir: Path | str, *, require_complete: bool = True
) -> pd.DataFrame:
    """Checksum-verify and load a saved prime transaction index."""

    directory = Path(snapshot_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = directory / "manifest.partial.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"USAspending prime manifest not found: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if require_complete and not manifest.get("retrieval_complete"):
        raise ValueError("USAspending prime snapshot is incomplete")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("USAspending prime manifest has no files list")
    transaction_path: Path | None = None
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = directory / str(entry.get("relative_path"))
        actual = _sha256(path.read_bytes())
        if actual != entry.get("sha256"):
            raise ValueError(f"USAspending prime snapshot checksum mismatch: {path}")
        if entry.get("kind") == "prime_transaction_index":
            transaction_path = path
    if transaction_path is None:
        raise ValueError("USAspending prime snapshot has no transaction index")
    rows = json.loads(transaction_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if frame["prime_transaction_id"].duplicated().any():
        raise ValueError("USAspending prime transaction IDs are not unique")
    for column in ("action_date", "award_start_date", "award_end_date", "source_retrieved_at"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    frame["signed_obligation_amount"] = pd.to_numeric(
        frame["signed_obligation_amount"], errors="coerce"
    )
    return frame.sort_values(["fiscal_year", "prime_transaction_id"]).reset_index(drop=True)


def run_usaspending_prime_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Synchronous wrapper for scripts and orchestration assets."""

    return cast(dict[str, Any], asyncio.run(fetch_usaspending_prime_snapshot(*args, **kwargs)))


__all__ = [
    "AGENCY_SCOPES",
    "AWARD_TYPE_GROUPS",
    "DOD_AGENCY_NAME",
    "DOD_CGAC_CODE",
    "DOD_USASPENDING_AGENCY_ID",
    "USASPENDING_EARLIEST_SEARCH_DATE",
    "USASPENDING_PRIME_SCHEMA_VERSION",
    "fetch_usaspending_prime_snapshot",
    "load_usaspending_prime_snapshot",
    "run_usaspending_prime_snapshot",
]
