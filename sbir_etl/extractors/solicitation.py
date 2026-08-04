"""SBIR.gov solicitation client and lossless source normalization.

The weekly report historically consumed a six-column, topic-only view from
``SolicitationExtractor``.  That interface remains available, while the normalized
interface preserves every source record, the documented solicitation fields, and the
topic/subtopic hierarchy for research use.

Official source contract: https://www.sbir.gov/api/solicitation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError
from .sbir_gov_api import SBIR_GOV_API_BASE


SBIR_GOV_SOLICITATION_SOURCE = "sbir_gov"
SBIR_GOV_SOLICITATION_SCHEMA_VERSION = "sbir-gov-solicitations-v1"
SBIR_GOV_SOLICITATION_DOCS_URL = "https://www.sbir.gov/api/solicitation"
SBIR_GOV_SOLICITATION_MAX_PAGE_SIZE = 50

_SOLICITATION_KEYS: dict[str, tuple[str, ...]] = {
    "solicitation_title": ("solicitation_title", "solicitationTitle"),
    "solicitation_number": ("solicitation_number", "solicitationNumber"),
    "program": ("program",),
    "phase": ("phase",),
    "agency": ("agency",),
    "branch": ("branch",),
    "solicitation_year": ("solicitation_year", "solicitationYear", "year"),
    "release_date": ("release_date", "releaseDate"),
    "open_date": ("open_date", "openDate"),
    "close_date": ("close_date", "closeDate"),
    "application_due_dates": (
        "application_due_date",
        "application_due_dates",
        "applicationDueDate",
        "applicationDueDates",
    ),
    "occurrence_number": ("occurrence_number", "occurrenceNumber"),
    "solicitation_agency_url": ("solicitation_agency_url", "solicitationAgencyUrl"),
    "current_status": ("current_status", "currentStatus"),
    "solicitation_topics": ("solicitation_topics", "solicitationTopics", "topics"),
}

_TOPIC_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("topic_title", "topicTitle", "title"),
    "branch": ("branch",),
    "topic_code": ("topic_number", "topic_code", "topicNumber", "topicCode"),
    "description": ("topic_description", "topicDescription", "description"),
    "sbir_topic_link": ("sbir_topic_link", "sbirTopicLink"),
    "subtopics": ("subtopics", "subTopics"),
}

_SUBTOPIC_KEYS: dict[str, tuple[str, ...]] = {
    "title": ("subtopic_title", "subtopicTitle", "title"),
    "branch": ("branch",),
    "topic_code": (
        "subtopic_number",
        "subtopic_code",
        "subtopicNumber",
        "subtopicCode",
    ),
    "description": ("subtopic_description", "subtopicDescription", "description"),
}

SOLICITATION_VERSION_COLUMNS = [
    "solicitation_version_id",
    "solicitation_id",
    "source_system",
    "source_schema_version",
    "source_record_sha256",
    "source_record_json",
    "source_url",
    "source_query_json",
    "retrieved_at",
    "solicitation_title",
    "solicitation_number",
    "program",
    "phase",
    "agency",
    "branch",
    "solicitation_year",
    "release_date",
    "open_date",
    "close_date",
    "application_due_dates",
    "occurrence_number",
    "solicitation_agency_url",
    "current_status",
]

SOLICITATION_TOPIC_COLUMNS = [
    "topic_id",
    "solicitation_version_id",
    "solicitation_id",
    "parent_topic_id",
    "topic_level",
    "topic_ordinal",
    "subtopic_ordinal",
    "source_path",
    "topic_code",
    "parent_topic_code",
    "title",
    "description",
    "agency",
    "branch",
    "program",
    "solicitation_number",
    "sbir_topic_link",
    "source_system",
    "source_schema_version",
    "source_record_sha256",
    "source_record_json",
    "source_url",
    "source_query_json",
    "retrieved_at",
]

LEGACY_TOPIC_COLUMNS = [
    "topic_code",
    "title",
    "description",
    "agency",
    "program",
    "solicitation_number",
]

_DOCUMENTED_FIELD_RETENTION = {
    "solicitation.solicitation_title": "solicitation_versions.solicitation_title",
    "solicitation.solicitation_number": "solicitation_versions.solicitation_number",
    "solicitation.program": "solicitation_versions.program",
    "solicitation.phase": "solicitation_versions.phase",
    "solicitation.agency": "solicitation_versions.agency",
    "solicitation.branch": "solicitation_versions.branch",
    "solicitation.solicitation_year": "solicitation_versions.solicitation_year",
    "solicitation.release_date": "solicitation_versions.release_date",
    "solicitation.open_date": "solicitation_versions.open_date",
    "solicitation.close_date": "solicitation_versions.close_date",
    "solicitation.application_due_date": "solicitation_versions.application_due_dates",
    "solicitation.occurrence_number": "solicitation_versions.occurrence_number",
    "solicitation.solicitation_agency_url": ("solicitation_versions.solicitation_agency_url"),
    "solicitation.current_status": "solicitation_versions.current_status",
    "solicitation.solicitation_topics": "topics.solicitation_version_id",
    "topic.topic_title": "topics.title",
    "topic.branch": "topics.branch",
    "topic.topic_number": "topics.topic_code",
    "topic.topic_description": "topics.description",
    "topic.sbir_topic_link": "topics.sbir_topic_link",
    "topic.subtopics": "topics.parent_topic_id",
    "subtopic.subtopic_title": "topics.title",
    "subtopic.branch": "topics.branch",
    "subtopic.subtopic_number": "topics.topic_code",
    "subtopic.subtopic_description": "topics.description",
}


@dataclass(frozen=True)
class SolicitationTables:
    """Normalized tables at solicitation-version and topic/subtopic grain."""

    solicitation_versions: pd.DataFrame
    topics: pd.DataFrame


def _first(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-empty value found under any supported source key."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    material = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _identity_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).casefold()


def _clean_code(value: Any) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _record_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _due_dates(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_solicitations(
    solicitations: list[dict[str, Any]],
    *,
    source_url: str | None = None,
    source_query: dict[str, Any] | None = None,
    retrieved_at: str | None = None,
) -> SolicitationTables:
    """Normalize source records without discarding their original JSON.

    ``source_record_json`` is a canonical JSON representation of the source object,
    and ``source_record_sha256`` hashes that exact representation.  The normalized
    columns are query-oriented; the canonical record is the lossless fallback for
    source fields added after this schema version.
    """

    version_rows: list[dict[str, Any]] = []
    topic_rows: list[dict[str, Any]] = []
    seen_versions: set[str] = set()
    query_json = _canonical_json(source_query) if source_query is not None else None

    for solicitation in solicitations:
        if not isinstance(solicitation, dict):
            raise TypeError("each solicitation source record must be a dictionary")

        source_record_json = _canonical_json(solicitation)
        source_record_sha256 = hashlib.sha256(source_record_json.encode("utf-8")).hexdigest()
        values = {
            field: _first(solicitation, keys)
            for field, keys in _SOLICITATION_KEYS.items()
            if field != "solicitation_topics"
        }
        solicitation_number = _clean_code(values["solicitation_number"])
        solicitation_id = _stable_id(
            "sbir_gov_solicitation",
            _identity_text(values["agency"]),
            _identity_text(solicitation_number) or source_record_sha256,
        )
        solicitation_version_id = _stable_id(
            "sbir_gov_solicitation_version",
            solicitation_id,
            _identity_text(values["occurrence_number"]),
            source_record_sha256,
        )

        if solicitation_version_id in seen_versions:
            continue
        seen_versions.add(solicitation_version_id)

        version_rows.append(
            {
                "solicitation_version_id": solicitation_version_id,
                "solicitation_id": solicitation_id,
                "source_system": SBIR_GOV_SOLICITATION_SOURCE,
                "source_schema_version": SBIR_GOV_SOLICITATION_SCHEMA_VERSION,
                "source_record_sha256": source_record_sha256,
                "source_record_json": source_record_json,
                "source_url": source_url,
                "source_query_json": query_json,
                "retrieved_at": retrieved_at,
                "solicitation_title": values["solicitation_title"],
                "solicitation_number": solicitation_number,
                "program": values["program"],
                "phase": values["phase"],
                "agency": values["agency"],
                "branch": values["branch"],
                "solicitation_year": values["solicitation_year"],
                "release_date": values["release_date"],
                "open_date": values["open_date"],
                "close_date": values["close_date"],
                "application_due_dates": _due_dates(values["application_due_dates"]),
                "occurrence_number": values["occurrence_number"],
                "solicitation_agency_url": values["solicitation_agency_url"],
                "current_status": values["current_status"],
            }
        )

        nested_value = _first(solicitation, _SOLICITATION_KEYS["solicitation_topics"])
        topics = _record_list(nested_value)
        flat_topic = False
        if not topics and _first(solicitation, _TOPIC_KEYS["topic_code"]) is not None:
            topics = [solicitation]
            flat_topic = True

        for topic_ordinal, topic in enumerate(topics):
            topic_code = _clean_code(_first(topic, _TOPIC_KEYS["topic_code"]))
            topic_record_json = _canonical_json(topic)
            topic_record_sha256 = hashlib.sha256(topic_record_json.encode("utf-8")).hexdigest()
            source_path = "$" if flat_topic else f"$.solicitation_topics[{topic_ordinal}]"
            topic_id = _stable_id(
                "sbir_gov_topic",
                solicitation_version_id,
                source_path,
                _identity_text(topic_code) or topic_record_sha256,
            )
            topic_branch = _first(topic, _TOPIC_KEYS["branch"])
            topic_link = _first(topic, _TOPIC_KEYS["sbir_topic_link"])

            common = {
                "solicitation_version_id": solicitation_version_id,
                "solicitation_id": solicitation_id,
                "agency": values["agency"],
                "program": values["program"],
                "solicitation_number": solicitation_number,
                "source_system": SBIR_GOV_SOLICITATION_SOURCE,
                "source_schema_version": SBIR_GOV_SOLICITATION_SCHEMA_VERSION,
                "source_url": source_url,
                "source_query_json": query_json,
                "retrieved_at": retrieved_at,
            }
            topic_rows.append(
                {
                    "topic_id": topic_id,
                    **common,
                    "parent_topic_id": None,
                    "topic_level": "topic",
                    "topic_ordinal": topic_ordinal,
                    "subtopic_ordinal": None,
                    "source_path": source_path,
                    "topic_code": topic_code,
                    "parent_topic_code": None,
                    "title": _first(topic, _TOPIC_KEYS["title"]),
                    "description": _first(topic, _TOPIC_KEYS["description"]),
                    "branch": topic_branch,
                    "sbir_topic_link": topic_link,
                    "source_record_sha256": topic_record_sha256,
                    "source_record_json": topic_record_json,
                }
            )

            subtopics = _record_list(_first(topic, _TOPIC_KEYS["subtopics"]))
            for subtopic_ordinal, subtopic in enumerate(subtopics):
                subtopic_code = _clean_code(_first(subtopic, _SUBTOPIC_KEYS["topic_code"]))
                subtopic_record_json = _canonical_json(subtopic)
                subtopic_record_sha256 = hashlib.sha256(
                    subtopic_record_json.encode("utf-8")
                ).hexdigest()
                subtopic_path = f"{source_path}.subtopics[{subtopic_ordinal}]"
                subtopic_id = _stable_id(
                    "sbir_gov_subtopic",
                    topic_id,
                    subtopic_path,
                    _identity_text(subtopic_code) or subtopic_record_sha256,
                )
                topic_rows.append(
                    {
                        "topic_id": subtopic_id,
                        **common,
                        "parent_topic_id": topic_id,
                        "topic_level": "subtopic",
                        "topic_ordinal": topic_ordinal,
                        "subtopic_ordinal": subtopic_ordinal,
                        "source_path": subtopic_path,
                        "topic_code": subtopic_code,
                        "parent_topic_code": topic_code,
                        "title": _first(subtopic, _SUBTOPIC_KEYS["title"]),
                        "description": _first(subtopic, _SUBTOPIC_KEYS["description"]),
                        "branch": _first(subtopic, _SUBTOPIC_KEYS["branch"]),
                        "sbir_topic_link": None,
                        "source_record_sha256": subtopic_record_sha256,
                        "source_record_json": subtopic_record_json,
                    }
                )

    return SolicitationTables(
        solicitation_versions=pd.DataFrame(version_rows, columns=SOLICITATION_VERSION_COLUMNS),
        topics=pd.DataFrame(topic_rows, columns=SOLICITATION_TOPIC_COLUMNS),
    )


def _field_presence(
    records: list[dict[str, Any]], field_keys: dict[str, tuple[str, ...]]
) -> dict[str, dict[str, int]]:
    return {
        field: {
            "present_records": sum(any(key in record for key in keys) for record in records),
            "populated_records": sum(_first(record, keys) is not None for record in records),
        }
        for field, keys in field_keys.items()
    }


def _all_aliases(field_keys: dict[str, tuple[str, ...]]) -> set[str]:
    return {alias for aliases in field_keys.values() for alias in aliases}


def audit_solicitation_schema(solicitations: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure documented field presence, retention, drift, hierarchy, and duplicates."""

    topic_records: list[dict[str, Any]] = []
    subtopic_records: list[dict[str, Any]] = []
    malformed_topics = 0
    malformed_subtopics = 0

    for solicitation in solicitations:
        nested_value = _first(solicitation, _SOLICITATION_KEYS["solicitation_topics"])
        if nested_value is not None and not isinstance(nested_value, (dict, list)):
            malformed_topics += 1
        topics = _record_list(nested_value)
        if not topics and _first(solicitation, _TOPIC_KEYS["topic_code"]) is not None:
            topics = [solicitation]
        topic_records.extend(topics)

        for topic in topics:
            subtopic_value = _first(topic, _TOPIC_KEYS["subtopics"])
            if subtopic_value is not None and not isinstance(subtopic_value, (dict, list)):
                malformed_subtopics += 1
            subtopic_records.extend(_record_list(subtopic_value))

    normalized = normalize_solicitations(solicitations)
    available_targets = {
        *(f"solicitation_versions.{column}" for column in SOLICITATION_VERSION_COLUMNS),
        *(f"topics.{column}" for column in SOLICITATION_TOPIC_COLUMNS),
    }
    retained = {
        field: target
        for field, target in _DOCUMENTED_FIELD_RETENTION.items()
        if target in available_targets
    }
    documented_count = len(_DOCUMENTED_FIELD_RETENTION)
    unique_source_hashes = {_record_hash(record) for record in solicitations}

    top_level_aliases = _all_aliases(_SOLICITATION_KEYS) | _all_aliases(_TOPIC_KEYS)
    topic_aliases = _all_aliases(_TOPIC_KEYS)
    subtopic_aliases = _all_aliases(_SUBTOPIC_KEYS)

    return {
        "schema_version": SBIR_GOV_SOLICITATION_SCHEMA_VERSION,
        "source_record_count": len(solicitations),
        "unique_source_record_count": len(unique_source_hashes),
        "duplicate_source_record_count": len(solicitations) - len(unique_source_hashes),
        "topic_record_count": len(topic_records),
        "subtopic_record_count": len(subtopic_records),
        "normalized_solicitation_version_count": len(normalized.solicitation_versions),
        "normalized_topic_row_count": len(normalized.topics),
        "documented_field_count": documented_count,
        "retained_documented_field_count": len(retained),
        "retention_rate": len(retained) / documented_count,
        "retention_map": retained,
        "field_presence": {
            "solicitation": _field_presence(solicitations, _SOLICITATION_KEYS),
            "topic": _field_presence(topic_records, _TOPIC_KEYS),
            "subtopic": _field_presence(subtopic_records, _SUBTOPIC_KEYS),
        },
        "unknown_fields": {
            "solicitation": sorted(
                {key for record in solicitations for key in record} - top_level_aliases
            ),
            "topic": sorted({key for record in topic_records for key in record} - topic_aliases),
            "subtopic": sorted(
                {key for record in subtopic_records for key in record} - subtopic_aliases
            ),
        },
        "malformed_nested_values": {
            "solicitation_topics": malformed_topics,
            "subtopics": malformed_subtopics,
        },
    }


def _legacy_topic_rows(topics: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in topics.to_dict(orient="records"):
        if row.get("topic_level") != "topic":
            continue
        topic_code = _clean_code(row.get("topic_code"))
        if topic_code is None:
            continue
        legacy_agency = row.get("agency")
        if row.get("source_path") != "$":
            legacy_agency = row.get("branch") or legacy_agency
        rows.append(
            {
                "topic_code": topic_code,
                "title": row.get("title") or "",
                "description": row.get("description"),
                "agency": legacy_agency,
                "program": row.get("program"),
                "solicitation_number": row.get("solicitation_number") or "",
            }
        )
    return rows


class SolicitationExtractor:
    """Client for SBIR.gov solicitations and the weekly-report compatibility view."""

    def __init__(
        self,
        *,
        base_url: str = SBIR_GOV_API_BASE,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> SolicitationExtractor:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    )
    def _get_solicitations(self, params: dict[str, str | int]) -> list[dict[str, Any]]:
        url = f"{self.base_url}/solicitations"
        logger.debug(f"SBIR.gov solicitations API request: {url} params={params}")

        response = self.client.get(url, params=params)
        if response.status_code != 200:
            raise APIError(
                f"SBIR.gov solicitations API returned {response.status_code}: "
                f"{response.text[:200]}",
                api_name="sbir_gov_solicitations",
                http_status=response.status_code,
            )

        data = response.json()
        if isinstance(data, list):
            return [record for record in data if isinstance(record, dict)]
        if isinstance(data, dict):
            records = data.get("results") or data.get("data") or []
            return _record_list(records)
        return []

    @staticmethod
    def _page_size(page_size: int) -> int:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        return min(page_size, SBIR_GOV_SOLICITATION_MAX_PAGE_SIZE)

    def _collect_solicitations(
        self,
        *,
        params: dict[str, str | int],
        max_results: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        if max_results <= 0:
            return []

        bounded_page_size = self._page_size(page_size)
        records: list[dict[str, Any]] = []
        start = 0
        while len(records) < max_results:
            rows = min(bounded_page_size, max_results - len(records))
            page = self._get_solicitations({**params, "start": start, "rows": rows})
            if not page:
                break
            records.extend(page[: max_results - len(records)])
            start += len(page)
            if len(page) < rows:
                break
        return records

    @staticmethod
    def _flatten_to_topics(solicitations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return the historical six-column view used by weekly reporting."""
        return _legacy_topic_rows(normalize_solicitations(solicitations).topics)

    def extract_solicitation_tables(
        self, *, year: int, max_results: int = 1000, page_size: int = 50
    ) -> SolicitationTables:
        """Fetch and normalize solicitation versions plus their topic hierarchy."""
        bounded_page_size = self._page_size(page_size)
        records = self._collect_solicitations(
            params={"year": year},
            max_results=max_results,
            page_size=bounded_page_size,
        )
        return normalize_solicitations(
            records,
            source_url=f"{self.base_url}/solicitations",
            source_query={
                "year": year,
                "max_results": max_results,
                "page_size": bounded_page_size,
            },
            retrieved_at=datetime.now(UTC).isoformat(),
        )

    def extract_topics(
        self, *, year: int, max_results: int = 1000, page_size: int = 50
    ) -> pd.DataFrame:
        """Fetch the historical topic view without changing weekly-report behavior."""
        tables = self.extract_solicitation_tables(
            year=year,
            max_results=max_results,
            page_size=page_size,
        )
        rows = _legacy_topic_rows(tables.topics)
        return pd.DataFrame(rows, columns=LEGACY_TOPIC_COLUMNS)

    @staticmethod
    def deduplicate_topics(df: pd.DataFrame) -> pd.DataFrame:
        """Drop duplicate topic codes, preferring the most complete record."""
        if df.empty or "topic_code" not in df.columns:
            return df
        df = df.copy()
        has_desc = df["description"].notna() if "description" in df.columns else False
        df["_has_desc"] = has_desc
        df = df.sort_values("_has_desc", ascending=False)
        df = df.drop_duplicates(subset=["topic_code"], keep="first")
        return df.drop(columns=["_has_desc"]).reset_index(drop=True)

    def query_by_keyword(self, keyword: str, *, rows: int = 20) -> list[dict[str, Any]]:
        """Keyword search returning the historical six-column topic view."""
        bounded_rows = self._page_size(rows)
        page = self._get_solicitations({"keyword": keyword, "rows": bounded_rows})
        return self._flatten_to_topics(page)

    def query_awards_for_topic(self, topic_code: str) -> dict[str, Any] | None:
        """Best-effort award fallback for a topic missing from solicitation results."""
        try:
            response = self.client.get(
                f"{self.base_url}/awards",
                params={"topic_code": topic_code, "rows": 1},
            )
            if response.status_code != 200:
                return None
            data = response.json()
            awards = (
                data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
            )
        except (httpx.TransportError, httpx.TimeoutException, ValueError):
            return None

        if not awards:
            return None

        award = awards[0]
        return {
            "title": award.get("award_title") or award.get("title") or "",
            "description": award.get("abstract") or award.get("description"),
            "agency": award.get("agency"),
            "program": award.get("program"),
        }


__all__ = [
    "LEGACY_TOPIC_COLUMNS",
    "SBIR_GOV_SOLICITATION_DOCS_URL",
    "SBIR_GOV_SOLICITATION_MAX_PAGE_SIZE",
    "SBIR_GOV_SOLICITATION_SCHEMA_VERSION",
    "SBIR_GOV_SOLICITATION_SOURCE",
    "SOLICITATION_TOPIC_COLUMNS",
    "SOLICITATION_VERSION_COLUMNS",
    "SolicitationExtractor",
    "SolicitationTables",
    "audit_solicitation_schema",
    "normalize_solicitations",
]
