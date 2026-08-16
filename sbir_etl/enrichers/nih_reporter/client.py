"""NIH RePORTER Projects API v2 client.

Epistemic tier: pipelines. Transport, retry, and rate limits come from
``BaseAsyncAPIClient``. Activity codes, windows, and ``appl_id`` / FY grain
stay here. No network in unit tests — inject ``http_client``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.nih_reporter.keys import (
    NIHSearchWindow,
    NIHWindowKind,
    canonicalize_nih_query_key,
    parse_refresh_window,
)
from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord, normalize_reporter_result
from sbir_etl.exceptions import APIError
from sbir_etl.utils.path_utils import ensure_dir


EPISTEMIC_TIER = "pipelines"

NIH_REPORTER_BASE_URL = "https://api.reporter.nih.gov/v2"
NIH_REPORTER_SEARCH_PATH = "/projects/search"
NIH_REPORTER_ENDPOINT = f"{NIH_REPORTER_BASE_URL}{NIH_REPORTER_SEARCH_PATH}"
NIH_REPORTER_CITATION = "https://api.reporter.nih.gov/"
NIH_ACTIVITY_CODES: tuple[str, ...] = ("R43", "R44", "R41", "R42")
NIH_PAGE_SIZE = 500
NIH_INCLUDE_FIELDS: tuple[str, ...] = (
    "ApplId",
    "FiscalYear",
    "ProjectNum",
    "CoreProjectNum",
    "ActivityCode",
    "AgencyIcAdmin",
    "Organization",
    "PrincipalInvestigators",
    "ProjectTitle",
    "AbstractText",
    "AwardAmount",
    "OpportunityNumber",
    "FullStudySection",
)


@dataclass(frozen=True)
class NIHReporterPage:
    """One validated search page plus the raw body used for hashing/cache."""

    total: int
    offset: int
    limit: int
    results: tuple[Mapping[str, Any], ...]
    raw_body: bytes
    payload_hash: str


class NIHReporterAPIClient(BaseAsyncAPIClient):
    """Async client for ``POST /v2/projects/search``."""

    api_name = "nih_reporter"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        super().__init__()
        if config is None:
            cfg = get_config()
            self.config = cfg.enrichment_refresh.nih_reporter.model_dump()
        else:
            self.config = config

        self.base_url = str(self.config.get("base_url", NIH_REPORTER_BASE_URL))
        self.timeout = self.config.get("timeout_seconds", 30)
        self.rate_limit_per_minute = int(self.config.get("rate_limit_per_minute", 30))
        cache_setting = cache_dir
        if cache_setting is None:
            cache_block = self.config.get("cache") or {}
            if isinstance(cache_block, Mapping):
                cache_setting = cache_block.get("cache_dir", "data/cache/nih_reporter")
            else:
                cache_setting = "data/cache/nih_reporter"
        self.cache_dir = Path(str(cache_setting))
        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)
        logger.info(
            f"Initialized NIHReporterAPIClient: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min"
        )

    def build_search_payload(
        self,
        *,
        offset: int,
        limit: int = NIH_PAGE_SIZE,
        project_nums: Sequence[str] | None = None,
        fiscal_years: Sequence[int] | None = None,
        window: str | NIHSearchWindow | None = None,
        activity_codes: Sequence[str] | None = NIH_ACTIVITY_CODES,
    ) -> dict[str, Any]:
        """Build a RePORTER search body. Windows become criteria, not filters."""

        if offset < 0:
            raise ValueError("NIH RePORTER offset must be >= 0")
        if limit < 1 or limit > NIH_PAGE_SIZE:
            raise ValueError(f"NIH RePORTER limit must be between 1 and {NIH_PAGE_SIZE}")

        criteria: dict[str, Any] = {}
        if activity_codes:
            criteria["activity_codes"] = list(activity_codes)
        if project_nums:
            keys = [
                key
                for key in (canonicalize_nih_query_key(item) for item in project_nums)
                if key is not None
            ]
            if not keys:
                raise ValueError("NIH RePORTER project_nums contained no usable keys")
            criteria["project_nums"] = keys
        if fiscal_years:
            criteria["fiscal_years"] = [int(year) for year in fiscal_years]

        parsed = window if isinstance(window, NIHSearchWindow) else parse_refresh_window(window)
        if parsed.kind is NIHWindowKind.FISCAL_YEARS and "fiscal_years" in criteria:
            raise ValueError("do not pass both fiscal_years and a fy: window")
        parsed.apply_to_criteria(criteria)

        return {
            "criteria": criteria,
            "include_fields": list(NIH_INCLUDE_FIELDS),
            "offset": offset,
            "limit": limit,
            "sort_field": "appl_id",
            "sort_order": "asc",
        }

    def compute_payload_hash(self, payload: Mapping[str, Any] | bytes) -> str:
        """SHA-256 of a JSON object (sorted) or of raw response bytes."""

        if isinstance(payload, bytes):
            return hashlib.sha256(payload).hexdigest()
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def fetch_page(
        self,
        *,
        offset: int,
        limit: int = NIH_PAGE_SIZE,
        project_nums: Sequence[str] | None = None,
        fiscal_years: Sequence[int] | None = None,
        window: str | NIHSearchWindow | None = None,
        activity_codes: Sequence[str] | None = NIH_ACTIVITY_CODES,
    ) -> NIHReporterPage:
        """Fetch and validate one search page."""

        body = self.build_search_payload(
            offset=offset,
            limit=limit,
            project_nums=project_nums,
            fiscal_years=fiscal_years,
            window=window,
            activity_codes=activity_codes,
        )
        response = await self._request_raw(
            "POST",
            NIH_REPORTER_SEARCH_PATH,
            params=body,
            headers={"Content-Type": "application/json"},
        )
        raw = response.content
        self._write_raw_cache(raw)
        return self.parse_page(raw, offset=offset, limit=limit)

    def parse_page(self, raw: bytes, *, offset: int, limit: int) -> NIHReporterPage:
        """Validate pagination metadata. Fail closed on inconsistency."""

        try:
            payload = json.loads(raw)
            meta = payload["meta"]
            results = payload["results"]
            total = int(meta["total"])
            response_offset = int(meta["offset"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise APIError(
                "NIH RePORTER returned an invalid response",
                api_name=self.api_name,
                endpoint=NIH_REPORTER_SEARCH_PATH,
            ) from error
        if response_offset != offset or not isinstance(results, list):
            raise APIError(
                "NIH RePORTER pagination metadata is inconsistent",
                api_name=self.api_name,
                endpoint=NIH_REPORTER_SEARCH_PATH,
            )
        if len(results) > limit or total < offset + len(results):
            raise APIError(
                "NIH RePORTER returned inconsistent result counts",
                api_name=self.api_name,
                endpoint=NIH_REPORTER_SEARCH_PATH,
            )
        if offset < total and not results:
            raise APIError(
                "NIH RePORTER pagination stopped before the declared total",
                api_name=self.api_name,
                endpoint=NIH_REPORTER_SEARCH_PATH,
            )
        return NIHReporterPage(
            total=total,
            offset=offset,
            limit=limit,
            results=tuple(results),
            raw_body=raw,
            payload_hash=self.compute_payload_hash(raw),
        )

    async def search_projects(
        self,
        *,
        project_nums: Sequence[str] | None = None,
        fiscal_years: Sequence[int] | None = None,
        window: str | NIHSearchWindow | None = None,
        activity_codes: Sequence[str] | None = NIH_ACTIVITY_CODES,
        limit: int = NIH_PAGE_SIZE,
        retrieved_at: datetime | None = None,
    ) -> list[NIHReporterRecord]:
        """Walk every page for the given criteria and normalize rows."""

        retrieved = retrieved_at or datetime.now(UTC)
        records: list[NIHReporterRecord] = []
        offset = 0
        while True:
            page = await self.fetch_page(
                offset=offset,
                limit=limit,
                project_nums=project_nums,
                fiscal_years=fiscal_years,
                window=window,
                activity_codes=activity_codes,
            )
            for result in page.results:
                if not isinstance(result, Mapping):
                    raise APIError(
                        "NIH RePORTER result is not an object",
                        api_name=self.api_name,
                        endpoint=NIH_REPORTER_SEARCH_PATH,
                    )
                records.append(
                    normalize_reporter_result(
                        result,
                        retrieved_at=retrieved,
                        payload_hash=page.payload_hash,
                    )
                )
            offset += len(page.results)
            if offset >= page.total:
                return records

    async def lookup_projects(
        self,
        project_nums: Sequence[str],
        fiscal_year: int,
        *,
        window: str | NIHSearchWindow | None = None,
        limit: int = NIH_PAGE_SIZE,
        retrieved_at: datetime | None = None,
    ) -> list[NIHReporterRecord]:
        """Exact ``project_nums`` + FY lookup, still scoped to SBIR/STTR codes.

        A date window becomes ``project_start_date`` criteria. A ``fy:`` window
        is rejected here because ``fiscal_year`` already sets ``fiscal_years``.
        """

        parsed = window if isinstance(window, NIHSearchWindow) else parse_refresh_window(window)
        if parsed.kind is NIHWindowKind.FISCAL_YEARS:
            raise ValueError("lookup_projects takes fiscal_year; do not also pass a fy: window")
        return await self.search_projects(
            project_nums=project_nums,
            fiscal_years=[fiscal_year],
            window=window if parsed.kind is NIHWindowKind.PROJECT_START_DATE else None,
            activity_codes=NIH_ACTIVITY_CODES,
            limit=limit,
            retrieved_at=retrieved_at,
        )

    def _write_raw_cache(self, raw: bytes) -> None:
        if not raw:
            return
        ensure_dir(self.cache_dir)
        digest = self.compute_payload_hash(raw)
        path = self.cache_dir / f"{digest}.json"
        if not path.exists():
            path.write_bytes(raw)
