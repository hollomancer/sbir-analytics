"""Exact project-number recovery through the official NIH RePORTER API."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from .identity import IdentityRecoveryError
from .source_keys import NIH_CORE_PROJECT_ADAPTER, NIH_PROJECT_ADAPTER


NIH_REPORTER_ENDPOINT = "https://api.reporter.nih.gov/v2/projects/search"
_NIH_ADAPTERS = frozenset({NIH_PROJECT_ADAPTER, NIH_CORE_PROJECT_ADAPTER})
_REQUIRED_ATTEMPT_COLUMNS = frozenset(
    {
        "adapter",
        "award_year_key",
        "source_award_key",
    }
)
_INCLUDE_FIELDS = (
    "ApplId",
    "FiscalYear",
    "ProjectNum",
    "CoreProjectNum",
    "Organization",
)


def canonicalize_nih_query_key(value: Any) -> str | None:
    """Format an SBIR source key for an exact NIH project-number query."""

    if value is None or value is pd.NA:
        return None
    text = str(value).strip(" ,").upper()
    if not text or text in {"<NA>", "NAN", "NONE", "NULL", r"\N"}:
        return None
    return "".join(text.split()) or None


def _chunks(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for position in range(0, len(values), size):
        yield values[position : position + size]


class NIHReporterExtractor:
    """Retrieve exact requested project keys and retain raw-response provenance."""

    def __init__(
        self,
        attempts: pd.DataFrame,
        *,
        requester: Callable[[dict[str, Any]], bytes] | None = None,
        retrieval_time: datetime | None = None,
    ) -> None:
        if missing := sorted(_REQUIRED_ATTEMPT_COLUMNS - set(attempts.columns)):
            raise IdentityRecoveryError(f"NIH attempts missing columns: {missing}")
        selected = attempts.loc[attempts["adapter"].isin(_NIH_ADAPTERS)].copy()
        if selected.empty:
            raise IdentityRecoveryError("No NIH exact-key attempts were supplied")
        selected["query_key"] = selected["source_award_key"].map(canonicalize_nih_query_key)
        selected = selected.loc[selected["query_key"].notna()]
        if selected.empty:
            raise IdentityRecoveryError("NIH attempts contain no usable project query keys")
        if not selected["award_year_key"].astype(str).str.fullmatch(r"\d{4}").all():
            raise IdentityRecoveryError("NIH attempts require four-digit fiscal years")

        self.query_keys_by_year = {
            int(year): tuple(sorted(set(group["query_key"].astype(str))))
            for year, group in selected.groupby("award_year_key", sort=True)
        }
        self.requester = requester or self._request
        self.retrieval_time = retrieval_time or datetime.now(UTC)
        self.response_digests: list[str] = []
        self.raw_responses: list[bytes] = []
        self.request_count = 0
        self.provenance: dict[str, Any] = {}

    @staticmethod
    def _request(payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload, separators=(",", ":")).encode()
        last_error: BaseException | None = None
        for attempt in range(3):
            request = urllib.request.Request(
                NIH_REPORTER_ENDPOINT,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                # The request URL is the fixed official HTTPS endpoint above; callers
                # can replace the requester but cannot supply a URL to this method.
                with urllib.request.urlopen(request, timeout=180) as response:  # nosec B310
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code not in {408, 425, 429, 500, 502, 503, 504}:
                    raise IdentityRecoveryError(
                        f"NIH RePORTER request failed with HTTP {error.code}"
                    ) from error
                last_error = error
            except urllib.error.URLError as error:
                last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
        raise IdentityRecoveryError("NIH RePORTER request failed after retries") from last_error

    def _page(
        self,
        project_numbers: Sequence[str],
        fiscal_year: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        payload = {
            "criteria": {
                "project_nums": list(project_numbers),
                "fiscal_years": [fiscal_year],
            },
            "include_fields": list(_INCLUDE_FIELDS),
            "offset": offset,
            "limit": 50,
            "sort_field": "appl_id",
            "sort_order": "asc",
        }
        body = self.requester(payload)
        self.request_count += 1
        self.raw_responses.append(body)
        self.response_digests.append(hashlib.sha256(body).hexdigest())
        try:
            response = json.loads(body)
            meta = response["meta"]
            results = response["results"]
            total = int(meta["total"])
            response_offset = int(meta["offset"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise IdentityRecoveryError("NIH RePORTER returned an invalid response") from error
        if response_offset != offset or not isinstance(results, list):
            raise IdentityRecoveryError("NIH RePORTER pagination metadata is inconsistent")
        if len(results) > 50 or total < offset + len(results):
            raise IdentityRecoveryError("NIH RePORTER returned inconsistent result counts")
        return total, results

    @staticmethod
    def _identifier_rows(result: dict[str, Any]) -> Iterator[dict[str, Any]]:
        try:
            record_id = str(result["appl_id"])
            fiscal_year = int(result["fiscal_year"])
            organization = result.get("organization") or {}
        except (KeyError, TypeError, ValueError) as error:
            raise IdentityRecoveryError("NIH project lacks record ID or fiscal year") from error
        ueis = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in (organization.get("org_ueis") or [organization.get("primary_uei")])
                    if value is not None and str(value).strip()
                }
            )
        )
        duns_values = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in (
                        organization.get("org_duns") or [organization.get("primary_duns")]
                    )
                    if value is not None and str(value).strip()
                }
            )
        )
        pairs = (
            [(uei, duns) for uei in ueis for duns in duns_values]
            if ueis and duns_values
            else [(uei, None) for uei in ueis]
            if ueis
            else [(None, duns) for duns in duns_values]
            if duns_values
            else [(None, None)]
        )
        for uei, duns in pairs:
            yield {
                "official_record_id": record_id,
                "project_num": result.get("project_num"),
                "core_project_num": result.get("core_project_num"),
                "fiscal_year": fiscal_year,
                "recipient_uei": uei,
                "recipient_duns": duns,
            }

    def extract(self) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for year, query_keys in self.query_keys_by_year.items():
            for batch in _chunks(query_keys, 25):
                offset = 0
                while True:
                    total, results = self._page(batch, year, offset)
                    for result in results:
                        records.extend(self._identifier_rows(result))
                    offset += len(results)
                    if offset >= total:
                        break
                    if not results:
                        raise IdentityRecoveryError(
                            "NIH RePORTER pagination stopped before the declared total"
                        )

        retrieval = self.retrieval_time.astimezone(UTC).isoformat()
        combined_digest = hashlib.sha256(
            json.dumps(self.response_digests, separators=(",", ":")).encode()
        ).hexdigest()
        self.provenance = {
            "endpoint": NIH_REPORTER_ENDPOINT,
            "retrieved_at": retrieval,
            "request_count": self.request_count,
            "response_sha256": tuple(self.response_digests),
            "source_digest": combined_digest,
            "query_keys_sha256": hashlib.sha256(
                json.dumps(self.query_keys_by_year, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        return pd.DataFrame.from_records(
            records,
            columns=[
                "official_record_id",
                "project_num",
                "core_project_num",
                "fiscal_year",
                "recipient_uei",
                "recipient_duns",
            ],
        )
