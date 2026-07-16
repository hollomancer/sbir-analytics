"""Public SAM.gov Opportunities API client with bounded pagination."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_etl.exceptions import APIError, RateLimitError
from sbir_etl.models.opportunity import Opportunity, OpportunityContact


OPPORTUNITIES_URL = "https://api.sam.gov/opportunities/v2/search"
NOTICE_TYPE_CODES = {
    "Justification (J&A)": "u",
    "Pre-solicitation": "p",
    "Presolicitation": "p",
    "Award Notice": "a",
    "Sources Sought": "r",
    "Special Notice": "s",
    "Solicitation": "o",
    "Sale of Surplus Property": "g",
    "Combined Synopsis/Solicitation": "k",
    "Intent to Bundle Requirements": "i",
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _parse_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed.date()


def _parse_datetime(value: Any) -> datetime | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed.to_pydatetime()


class SamGovOpportunitiesExtractor:
    """Retrieve and normalize public opportunity records without silent truncation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = OPPORTUNITIES_URL,
        page_size: int = 1000,
        max_pages: int = 100,
        max_records: int = 100_000,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SAM_GOV_API_KEY", "")
        if not self.api_key:
            raise ValueError("SAM_GOV_API_KEY is required for the public Opportunities API")
        self.base_url = base_url
        self.page_size = page_size
        self.max_pages = max_pages
        self.max_records = max_records
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    )
    def _get(self, url: str, *, params: dict[str, Any]) -> httpx.Response:
        response = self._client.get(url, params=params)
        if response.status_code == 429:
            raise RateLimitError("SAM.gov Opportunities API quota exceeded", api_name="sam.gov")
        if response.status_code >= 400:
            raise APIError(
                f"SAM.gov Opportunities API returned HTTP {response.status_code}",
                api_name="sam.gov",
                endpoint=url,
                http_status=response.status_code,
            )
        return response

    def search_page(
        self,
        *,
        posted_from: date,
        posted_to: date,
        offset: int = 0,
        notice_types: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if posted_to < posted_from or (posted_to - posted_from).days > 365:
            raise ValueError("SAM.gov posted date window must be ordered and at most 365 days")
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "postedFrom": posted_from.strftime("%m/%d/%Y"),
            "postedTo": posted_to.strftime("%m/%d/%Y"),
            "limit": self.page_size,
            "offset": offset,
        }
        if notice_types:
            params["ptype"] = list(notice_types)
        data = self._get(self.base_url, params=params).json()
        if not isinstance(data, dict):
            raise APIError("SAM.gov Opportunities API returned a non-object response")
        return data

    def iter_raw_records(
        self,
        *,
        posted_from: date,
        posted_to: date,
        notice_types: Sequence[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        offset = 0
        emitted = 0
        for _page in range(self.max_pages):
            payload = self.search_page(
                posted_from=posted_from,
                posted_to=posted_to,
                offset=offset,
                notice_types=notice_types,
            )
            rows = payload.get("opportunitiesData") or []
            if not isinstance(rows, list):
                raise APIError("SAM.gov Opportunities response has invalid opportunitiesData")
            for row in rows:
                if emitted >= self.max_records:
                    raise APIError(
                        "SAM.gov opportunity record cap reached; refusing partial output"
                    )
                if isinstance(row, dict):
                    emitted += 1
                    yield row
            total = int(payload.get("totalRecords") or emitted)
            if not rows or emitted >= total:
                return
            offset += len(rows)
        raise APIError("SAM.gov opportunity page cap reached; refusing partial output")

    def fetch_description(self, url: str | None) -> str | None:
        if not url or url.lower() == "null":
            return None
        response = self._get(url, params={"api_key": self.api_key})
        try:
            value = response.json()
            if isinstance(value, dict):
                return _text(value.get("description") or value.get("content"))
        except ValueError:
            pass
        return _text(response.text)

    def normalize_record(
        self, row: dict[str, Any], *, fetch_description: bool = False
    ) -> Opportunity:
        type_name = _text(row.get("type")) or "Unknown"
        type_code = NOTICE_TYPE_CODES.get(type_name) or _text(row.get("typeCode"))
        path_names = (_text(row.get("fullParentPathName")) or "").split(".")
        path_codes = (_text(row.get("fullParentPathCode")) or "").split(".")
        award = row.get("award") or {}
        awardee = award.get("awardee") or {}
        description_url = _text(row.get("description"))
        description = self.fetch_description(description_url) if fetch_description else None
        description = description or _text(row.get("title"))
        contacts = [
            OpportunityContact(
                contact_type=_text(c.get("type")),
                name=_text(c.get("fullName") or c.get("fullname")),
                title=_text(c.get("title")),
                email=_text(c.get("email")),
                phone=_text(c.get("phone")),
            )
            for c in (row.get("pointOfContact") or [])
            if isinstance(c, dict)
        ]
        canonical = {
            "notice_id": _text(row.get("noticeId")) or "",
            "notice_type": type_name,
            "notice_type_code": type_code,
            "title": _text(row.get("title")) or "Untitled opportunity",
            "posted_date": _text(row.get("postedDate")),
            "response_deadline": _text(row.get("responseDeadLine") or row.get("reponseDeadLine")),
            "full_parent_path_code": _text(row.get("fullParentPathCode")),
            "naics_code": _text(row.get("naicsCode")),
            "classification_code": _text(row.get("classificationCode")),
            "active": row.get("active"),
            "description": description,
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        return Opportunity(
            notice_id=canonical["notice_id"],
            notice_type=type_name,
            notice_type_code=type_code,
            base_notice_type=_text(row.get("baseType")),
            solicitation_number=_text(row.get("solicitationNumber")),
            title=canonical["title"],
            description=description,
            active=str(row.get("active", "")).strip().lower() in {"yes", "true", "1", "active"},
            status=_text(row.get("status")),
            posted_date=_parse_date(row.get("postedDate")),
            response_deadline=_parse_datetime(
                row.get("responseDeadLine") or row.get("reponseDeadLine")
            ),
            archive_date=_parse_date(row.get("archiveDate")),
            agency=_text(row.get("department")) or (path_names[0] if path_names else None),
            agency_code=path_codes[0] if path_codes else None,
            sub_tier=_text(row.get("subTier")) or (path_names[1] if len(path_names) > 1 else None),
            sub_tier_code=path_codes[1] if len(path_codes) > 1 else None,
            office=_text(row.get("office")) or (path_names[2] if len(path_names) > 2 else None),
            office_code=path_codes[2] if len(path_codes) > 2 else None,
            full_parent_path_name=_text(row.get("fullParentPathName")),
            full_parent_path_code=_text(row.get("fullParentPathCode")),
            naics_code=_text(row.get("naicsCode")),
            classification_code=_text(row.get("classificationCode")),
            psc_code=_text(row.get("classificationCode")),
            set_aside_code=_text(row.get("typeOfSetAside")),
            set_aside_description=_text(row.get("typeOfSetAsideDescription")),
            awardee_uei=_text(awardee.get("ueiSAM")),
            awardee_name=_text(awardee.get("name")),
            contacts=contacts,
            description_url=description_url,
            ui_url=_text(row.get("uiLink")),
            additional_info_url=_text(row.get("additionalInfoLink")),
            resource_urls=[str(v) for v in (row.get("resourceLinks") or []) if v],
            source_url=_text(row.get("uiLink")) or description_url,
            retrieved_at=datetime.now(UTC),
            content_hash=digest,
        )

    def fetch_opportunities(
        self,
        *,
        posted_from: date,
        posted_to: date,
        notice_types: Sequence[str] | None = None,
        include_descriptions: bool = True,
    ) -> list[Opportunity]:
        return [
            self.normalize_record(row, fetch_description=include_descriptions)
            for row in self.iter_raw_records(
                posted_from=posted_from, posted_to=posted_to, notice_types=notice_types
            )
        ]


__all__ = ["NOTICE_TYPE_CODES", "OPPORTUNITIES_URL", "SamGovOpportunitiesExtractor"]
