"""Direct NSF award extraction with immutable, checksummed source snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import zipfile
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_etl.exceptions import APIError

NSF_AWARDS_API_BASE = "https://api.nsf.gov/services/v1/awards"
NSF_AWARDS_API_DOCUMENTATION = "https://resources.research.gov/common/webapi/awardapisearch-v1.htm"
NSF_ANNUAL_DOWNLOAD_PAGE = "https://www.nsf.gov/awardsearch/download-awards"
NSF_DIRECT_SCHEMA_VERSION = "NSF-DIRECT-2026Q3"


def normalize_nsf_award_id(value: object) -> str | None:
    """Return NSF's seven-digit display identifier when usable."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if value.is_integer():
            value = str(int(value))
    cleaned = str(value).strip()
    match = re.fullmatch(r"(\d+)(?:\.0+)?", cleaned)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) > 9 or not digits.strip("0"):
        return None
    return digits.zfill(7) if len(digits) <= 7 else digits


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _clean_text(value: object) -> str | None:
    if value is None or value is pd.NA:
        return None
    cleaned = str(value).strip()
    return None if cleaned.upper() in {"", "NAN", "NONE", "NULL", "<NA>"} else cleaned


def _number(value: object) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    cleaned = (_clean_text(value) or "").lower()
    if cleaned in {"true", "t", "yes", "y", "1"}:
        return True
    if cleaned in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _json_field(value: object) -> str:
    if value is None or value is pd.NA:
        return "[]"
    if isinstance(value, str):
        if not value.strip():
            return "[]"
        value = [part.strip() for part in value.split(",") if part.strip()]
    elif not isinstance(value, list | tuple):
        value = [value]
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _program(record: dict[str, Any], title: str | None) -> tuple[str | None, str | None]:
    name = _clean_text(record.get("fundProgramName"))
    if name is None and isinstance(record.get("pgm_ele"), list):
        names = [
            _clean_text(item.get("pgm_ele_name"))
            for item in record["pgm_ele"]
            if isinstance(item, dict)
        ]
        name = "; ".join(item for item in names if item) or None
    searchable = " ".join(item for item in (name, title) if item).upper()
    program = "STTR" if "STTR" in searchable else "SBIR" if "SBIR" in searchable else None
    return program, name


def _phase(record: dict[str, Any], title: str | None) -> str | None:
    searchable = " ".join(
        item for item in (_clean_text(record.get("fundProgramName")), title) if item
    ).upper()
    for phase, token in (("III", "PHASE III"), ("II", "PHASE II"), ("I", "PHASE I")):
        if token in searchable:
            return phase
    return None


def _records(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if isinstance(response, dict):
        if response.get("serviceNotification"):
            raise APIError(
                "NSF Award Search API service notification: "
                + json.dumps(response["serviceNotification"], sort_keys=True)
            )
        values = response.get("award") or []
        return [item for item in values if isinstance(item, dict)]
    for key in ("awards", "award", "results", "data"):
        values = payload.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
        if isinstance(values, dict):
            return [values]
    return [payload] if any(key in payload for key in ("id", "awd_id")) else []


@dataclass(frozen=True)
class NSFAwardFetch:
    requested_award_id: str
    resolved_award_id: str | None
    source_url: str
    retrieved_at: str
    content: bytes
    found: bool


class NSFAwardAPIClient:
    """Synchronous client for exact direct-NSF award lookups."""

    def __init__(
        self,
        *,
        base_url: str = NSF_AWARDS_API_BASE,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client
        self._lock = threading.Lock()

    @property
    def client(self) -> httpx.Client:
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(
                    timeout=self.timeout,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                    headers={"User-Agent": "sbir-analytics/NSF-award-reconciliation"},
                )
            return self._client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        retry=retry_if_exception_type(
            (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)
        ),
        reraise=True,
    )
    def fetch_award(self, award_id: object) -> NSFAwardFetch:
        normalized = normalize_nsf_award_id(award_id)
        if normalized is None:
            raise ValueError(f"invalid NSF award identifier: {award_id!r}")
        url = f"{self.base_url}/{normalized}.json"
        response = self.client.get(url)
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        if response.status_code != 200:
            raise APIError(
                f"NSF Award Search API returned {response.status_code} for {normalized}",
                http_status=response.status_code,
            )
        try:
            awards = _records(response.json())
        except ValueError as exc:
            raise APIError(f"NSF Award Search API returned invalid JSON for {normalized}") from exc
        if len(awards) > 1:
            raise APIError(f"NSF lookup {normalized} returned {len(awards)} records")
        resolved = normalize_nsf_award_id(awards[0].get("id")) if awards else None
        if resolved is not None and resolved != normalized:
            raise APIError(f"NSF lookup {normalized} returned mismatched identifier {resolved}")
        return NSFAwardFetch(
            normalized,
            resolved,
            url,
            datetime.now(UTC).isoformat(),
            response.content,
            bool(awards),
        )


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"immutable NSF snapshot would change: {path}")
        return
    with path.open("xb") as handle:
        handle.write(content)


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def fetch_nsf_award_snapshots(
    award_ids: Iterable[object],
    snapshot_dir: Path | str,
    *,
    client: NSFAwardAPIClient | None = None,
    max_workers: int = 8,
    allow_partial: bool = False,
) -> dict[str, Any]:
    """Fetch a restartable immutable API snapshot and checksum manifest."""

    identifiers = sorted(
        {normalized for value in award_ids if (normalized := normalize_nsf_award_id(value))}
    )
    if not identifiers:
        raise ValueError("no usable NSF award identifiers were provided")
    if max_workers < 1:
        raise ValueError("max_workers must be at least one")
    directory = Path(snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("requested_award_ids") != identifiers:
            raise FileExistsError("NSF snapshot manifest exists for a different identifier set")
        return manifest

    active_client = client or NSFAwardAPIClient()
    owned_client = client is None
    entries: dict[str, dict[str, object]] = {}
    failures: dict[str, str] = {}
    missing: list[str] = []
    for award_id in identifiers:
        path = directory / f"{award_id}.json"
        if not path.exists():
            missing.append(award_id)
            continue
        content = path.read_bytes()
        records = _records(json.loads(content))
        entries[award_id] = {
            "requested_award_id": award_id,
            "resolved_award_id": normalize_nsf_award_id(records[0].get("id")) if records else None,
            "source_url": f"{NSF_AWARDS_API_BASE}/{award_id}.json",
            "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            "relative_path": path.name,
            "sha256": _sha256(content),
            "bytes": len(content),
            "found": bool(records),
            "reused": True,
        }

    def fetch_one(award_id: str) -> dict[str, object]:
        fetched = active_client.fetch_award(award_id)
        path = directory / f"{award_id}.json"
        _write_immutable(path, fetched.content)
        entry = asdict(fetched)
        entry.pop("content")
        entry.update(
            relative_path=path.name,
            sha256=_sha256(fetched.content),
            bytes=len(fetched.content),
            reused=False,
        )
        return entry

    logger.info(
        "NSF direct snapshot: {} requested, {} reused, {} to fetch",
        len(identifiers),
        len(entries),
        len(missing),
    )
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, award_id): award_id for award_id in missing}
            for completed, future in enumerate(as_completed(futures), start=len(entries) + 1):
                award_id = futures[future]
                try:
                    entries[award_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - manifest each failed identifier
                    failures[award_id] = f"{type(exc).__name__}: {exc}"
                if completed % 500 == 0 or completed == len(identifiers):
                    logger.info(
                        "NSF snapshot progress: {}/{} ({} failures)",
                        completed,
                        len(identifiers),
                        len(failures),
                    )
    finally:
        if owned_client:
            active_client.close()

    manifest: dict[str, Any] = {
        "schema_version": NSF_DIRECT_SCHEMA_VERSION,
        "source_system": "NSF Award Search API",
        "source_documentation": NSF_AWARDS_API_DOCUMENTATION,
        "source_base_url": NSF_AWARDS_API_BASE,
        "snapshot_created_at": datetime.now(UTC).isoformat(),
        "requested_award_ids": identifiers,
        "requested_award_count": len(identifiers),
        "retrieved_record_count": len(entries),
        "found_award_count": sum(bool(item["found"]) for item in entries.values()),
        "not_found_award_count": sum(not bool(item["found"]) for item in entries.values()),
        "failed_award_count": len(failures),
        "retrieval_complete": not failures and len(entries) == len(identifiers),
        "entries": [entries[key] for key in sorted(entries)],
        "failures": failures,
    }
    _write_json_atomic(directory / "manifest.partial.json", manifest)
    if failures and not allow_partial:
        raise APIError(
            f"NSF snapshot has {len(failures)} failed lookups; "
            f"sample={dict(sorted(failures.items())[:5])}"
        )
    if manifest["retrieval_complete"]:
        _write_immutable(
            manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        )
    return manifest


def load_nsf_snapshot_index(snapshot_dir: Path | str) -> pd.DataFrame:
    """Load and checksum-verify one lookup-provenance row per requested identifier."""

    directory = Path(snapshot_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = directory / "manifest.partial.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"NSF snapshot manifest not found: {directory}")
    content = manifest_path.read_bytes()
    manifest = json.loads(content)
    entries = {str(item["requested_award_id"]): item for item in manifest.get("entries", [])}
    failures = manifest.get("failures", {})
    rows: list[dict[str, object]] = []
    for raw_id in manifest.get("requested_award_ids", []):
        award_id = normalize_nsf_award_id(raw_id)
        if award_id is None:
            raise ValueError(f"invalid requested ID in NSF manifest: {raw_id!r}")
        entry = entries.get(award_id)
        if entry is None:
            rows.append(
                {
                    "nsf_lookup_requested_award_id": award_id,
                    "nsf_lookup_status": "failed"
                    if award_id in failures
                    else "missing_manifest_entry",
                    "nsf_lookup_failure": failures.get(award_id),
                    "nsf_lookup_snapshot_manifest_path": str(manifest_path),
                    "nsf_lookup_snapshot_manifest_sha256": _sha256(content),
                }
            )
            continue
        source_path = directory / str(entry["relative_path"])
        actual_sha = _sha256(source_path.read_bytes())
        if actual_sha != entry.get("sha256"):
            raise ValueError(f"NSF snapshot checksum mismatch for {award_id}")
        found = bool(entry.get("found"))
        rows.append(
            {
                "nsf_lookup_requested_award_id": award_id,
                "nsf_lookup_resolved_award_id": normalize_nsf_award_id(
                    entry.get("resolved_award_id")
                ),
                "nsf_lookup_status": "found" if found else "not_found",
                "nsf_lookup_found": found,
                "nsf_lookup_failure": None,
                "nsf_lookup_source_url": entry.get("source_url"),
                "nsf_lookup_source_path": str(source_path),
                "nsf_lookup_source_sha256": actual_sha,
                "nsf_lookup_retrieved_at": pd.to_datetime(
                    entry.get("retrieved_at"), errors="coerce", utc=True
                ),
                "nsf_lookup_snapshot_manifest_path": str(manifest_path),
                "nsf_lookup_snapshot_manifest_sha256": _sha256(content),
            }
        )
    return pd.DataFrame(rows).sort_values("nsf_lookup_requested_award_id").reset_index(drop=True)


def _iter_documents(path: Path) -> Iterator[tuple[object, str, str, datetime]]:
    if path.is_dir():
        for child in sorted(path.glob("*.json")):
            if child.name.startswith("manifest"):
                continue
            content = child.read_bytes()
            yield (
                json.loads(content),
                str(child),
                _sha256(content),
                datetime.fromtimestamp(child.stat().st_mtime, tz=UTC),
            )
        return
    if path.suffix.lower() == ".zip":
        retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if member.lower().endswith(".json"):
                    content = archive.read(member)
                    yield json.loads(content), f"{path}!{member}", _sha256(content), retrieved_at
        return
    content = path.read_bytes()
    yield (
        json.loads(content),
        str(path),
        _sha256(content),
        datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
    )


def normalize_nsf_award_record(
    record: dict[str, Any],
    *,
    source_path: str,
    source_sha256: str,
    source_retrieved_at: datetime,
) -> dict[str, object]:
    """Normalize Award Search API and annual JSON schemas to one award grain."""

    api = "id" in record
    award_id = normalize_nsf_award_id(record.get("id") if api else record.get("awd_id"))
    if award_id is None:
        raise ValueError(f"direct NSF record has no usable award id: {source_path}")
    institution = record.get("inst") if isinstance(record.get("inst"), dict) else {}
    title = _clean_text(record.get("title") if api else record.get("awd_titl_txt"))
    program, program_name = _program(record, title)
    return {
        "nsf_award_id": award_id,
        "nsf_award_title": title,
        "nsf_award_abstract": _clean_text(
            record.get("abstractText") if api else record.get("awd_abstract_narration")
        ),
        "nsf_program": program,
        "nsf_phase": _phase(record, title),
        "nsf_fund_program_name": program_name,
        "nsf_transaction_type": _clean_text(
            record.get("transType") if api else record.get("tran_type")
        ),
        "nsf_award_date": _clean_text(
            record.get("date") if api else record.get("awd_min_amd_letter_date")
        ),
        "nsf_start_date": _clean_text(
            record.get("startDate") if api else record.get("awd_eff_date")
        ),
        "nsf_end_date": _clean_text(record.get("expDate") if api else record.get("awd_exp_date")),
        "nsf_latest_amendment_date": _clean_text(
            record.get("latestAmendmentDate") if api else record.get("awd_max_amd_letter_date")
        ),
        "nsf_obligated_amount": _number(
            record.get("fundsObligatedAmt") if api else record.get("awd_amount")
        ),
        "nsf_estimated_total_amount": _number(
            record.get("estimatedTotalAmt") if api else record.get("tot_intn_awd_amt")
        ),
        "nsf_source_active_award": _boolean(record.get("activeAwd")) if api else None,
        "nsf_source_historical_award": _boolean(record.get("histAwd")) if api else None,
        "nsf_awardee_name": _clean_text(
            record.get("awardeeName") if api else institution.get("inst_name")
        ),
        "nsf_awardee_legal_business_name": _clean_text(
            record.get("awardee") if api else institution.get("org_lgl_bus_name")
        ),
        "nsf_awardee_uei": _clean_text(
            record.get("ueiNumber") if api else institution.get("org_uei_num")
        ),
        "nsf_awardee_parent_uei": _clean_text(
            record.get("parentUeiNumber") if api else institution.get("org_prnt_uei_num")
        ),
        "nsf_awardee_city": _clean_text(
            record.get("awardeeCity") if api else institution.get("inst_city_name")
        ),
        "nsf_awardee_state": _clean_text(
            record.get("awardeeStateCode") if api else institution.get("inst_state_code")
        ),
        "nsf_awardee_zip": _clean_text(
            record.get("awardeeZipCode") if api else institution.get("inst_zip_code")
        ),
        "nsf_award_agency_code": _clean_text(
            record.get("awardAgencyCode") if api else record.get("awd_agcy_code")
        ),
        "nsf_funding_agency_code": _clean_text(
            record.get("fundAgencyCode") if api else record.get("fund_agcy_code")
        ),
        "nsf_directorate_abbreviation": _clean_text(
            record.get("dirAbbr") if api else record.get("dir_abbr")
        ),
        "nsf_division_abbreviation": _clean_text(
            record.get("divAbbr") if api else record.get("div_abbr")
        ),
        "nsf_cfda_number": _clean_text(record.get("cfdaNumber") if api else record.get("cfda_num")),
        "nsf_program_element_codes_json": _json_field(
            record.get("progEleCode") if api else record.get("pgm_ele")
        ),
        "nsf_program_reference_codes_json": _json_field(
            record.get("progRefCode") if api else record.get("pgm_ref")
        ),
        "nsf_fiscal_year_obligations_json": _json_field(
            record.get("fundsObligated") if api else record.get("oblg_fy")
        ),
        "source_system": "National Science Foundation",
        "source_kind": "nsf_award_search_api" if api else "nsf_annual_award_json",
        "source_url": (
            f"{NSF_AWARDS_API_BASE}/{award_id}.json" if api else NSF_ANNUAL_DOWNLOAD_PAGE
        ),
        "source_path": source_path,
        "source_record_sha256": source_sha256,
        "source_retrieved_at": source_retrieved_at.astimezone(UTC).isoformat(),
        "source_schema_version": NSF_DIRECT_SCHEMA_VERSION,
    }


def load_nsf_awards(paths: Iterable[Path | str]) -> pd.DataFrame:
    """Load and deduplicate direct NSF JSON sources at one-row-per-award grain."""

    rows: list[dict[str, object]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"NSF direct source not found: {path}")
        for payload, source_path, source_sha, retrieved_at in _iter_documents(path):
            rows.extend(
                normalize_nsf_award_record(
                    record,
                    source_path=source_path,
                    source_sha256=source_sha,
                    source_retrieved_at=retrieved_at,
                )
                for record in _records(payload)
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for column in (
        "nsf_award_date",
        "nsf_start_date",
        "nsf_end_date",
        "nsf_latest_amendment_date",
        "source_retrieved_at",
    ):
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    frame["_source_priority"] = frame["source_kind"].eq("nsf_award_search_api").astype(int)
    frame = frame.sort_values(
        ["nsf_award_id", "_source_priority", "source_retrieved_at"], na_position="first"
    )
    frame["direct_source_record_count"] = frame.groupby("nsf_award_id")["nsf_award_id"].transform(
        "size"
    )
    return (
        frame.drop_duplicates("nsf_award_id", keep="last")
        .drop(columns="_source_priority")
        .sort_values("nsf_award_id")
        .reset_index(drop=True)
    )


__all__ = [
    "NSF_ANNUAL_DOWNLOAD_PAGE",
    "NSF_AWARDS_API_BASE",
    "NSF_AWARDS_API_DOCUMENTATION",
    "NSF_DIRECT_SCHEMA_VERSION",
    "NSFAwardAPIClient",
    "NSFAwardFetch",
    "fetch_nsf_award_snapshots",
    "load_nsf_awards",
    "load_nsf_snapshot_index",
    "normalize_nsf_award_id",
    "normalize_nsf_award_record",
]
