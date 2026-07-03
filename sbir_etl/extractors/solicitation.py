"""SBIR.gov Solicitations API client — topic titles/descriptions for the weekly report.

Rebuilds ``SolicitationExtractor``, which
:mod:`sbir_etl.reporting.weekly.enrichment` depends on for solicitation topic
metadata but which was absent from the tree — it never existed anywhere in
this repo's git history (confirmed via ``git log --all``), so the weekly
report's ``fetch_solicitation_topics()`` degraded to a warning-and-skip
whenever it tried to import this module.

Mirrors :class:`sbir_etl.extractors.sbir_gov_api.SbirGovClient`: httpx +
tenacity retry, no authentication, same API family
(https://api.www.sbir.gov/public/api). API docs: https://www.sbir.gov/api.

This sandbox has no outbound network access to ``api.www.sbir.gov`` (blocked
by the environment's network policy) to capture a live response sample, so
field extraction below is defensive — it tries every documented naming
variant (camelCase and snake_case) for each key rather than assuming one
shape. Before the first production run, capture one real response (e.g.
``curl 'https://api.www.sbir.gov/public/api/solicitations?rows=1'``) and, if
the real field names differ from every variant tried here, add the missing
variant to the ``_*_KEYS`` tuples below — the extraction logic itself does
not need to change.
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError
from .sbir_gov_api import SBIR_GOV_API_BASE


# Field-name variants seen across SBIR.gov API response shapes. See the
# module docstring: unverified against a live response in this sandbox.
_TOPIC_CODE_KEYS = ("topic_number", "topic_code", "topicCode")
_TITLE_KEYS = ("topic_title", "topicTitle", "title")
_DESC_KEYS = ("topic_description", "topicDescription", "description")
_AGENCY_KEYS = ("agency", "branch")
_PROGRAM_KEYS = ("program",)
_SOL_NUMBER_KEYS = ("solicitation_number", "solicitationNumber")

_TOPIC_COLUMNS = ["topic_code", "title", "description", "agency", "program", "solicitation_number"]


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-empty value found under any of ``keys``."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


class SolicitationExtractor:
    """Client for the SBIR.gov Solicitations API.

    Used by :func:`sbir_etl.reporting.weekly.enrichment.fetch_solicitation_topics`
    to look up solicitation topic titles/descriptions for weekly-report awards.
    """

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

    # ------------------------------------------------------------------
    # HTTP + parsing
    # ------------------------------------------------------------------

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
            return data
        if isinstance(data, dict):
            return data.get("results") or data.get("data") or []
        return []

    @staticmethod
    def _flatten_to_topics(solicitations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flatten a solicitations API response into one row per topic.

        Each solicitation typically nests a list of topics; a record with no
        nested list but its own topic code is treated as a single topic.
        """
        rows: list[dict[str, Any]] = []
        for sol in solicitations:
            sol_number = _first(sol, _SOL_NUMBER_KEYS) or ""
            sol_agency = _first(sol, _AGENCY_KEYS)
            sol_program = _first(sol, _PROGRAM_KEYS)

            topics = sol.get("solicitation_topics") or sol.get("topics") or []
            if not topics:
                if _first(sol, _TOPIC_CODE_KEYS):
                    topics = [sol]
                else:
                    continue

            for t in topics:
                tc = _first(t, _TOPIC_CODE_KEYS)
                if not tc:
                    continue
                rows.append(
                    {
                        "topic_code": str(tc).strip(),
                        "title": _first(t, _TITLE_KEYS) or "",
                        "description": _first(t, _DESC_KEYS),
                        "agency": _first(t, _AGENCY_KEYS) or sol_agency,
                        "program": _first(t, _PROGRAM_KEYS) or sol_program,
                        "solicitation_number": sol_number,
                    }
                )
        return rows

    # ------------------------------------------------------------------
    # Public API — matches the contract fetch_solicitation_topics() calls
    # ------------------------------------------------------------------

    def extract_topics(
        self, *, year: int, max_results: int = 1000, page_size: int = 100
    ) -> pd.DataFrame:
        """Fetch all solicitation topics for a given solicitation year.

        Returns a DataFrame with a ``topic_code`` column plus
        title/description/agency/program/solicitation_number.
        """
        all_rows: list[dict[str, Any]] = []
        start = 0
        while start < max_results:
            page = self._get_solicitations({"year": year, "start": start, "rows": page_size})
            if not page:
                break
            all_rows.extend(self._flatten_to_topics(page))
            if len(page) < page_size:
                break
            start += page_size

        if not all_rows:
            return pd.DataFrame(columns=_TOPIC_COLUMNS)
        return pd.DataFrame(all_rows)

    @staticmethod
    def deduplicate_topics(df: pd.DataFrame) -> pd.DataFrame:
        """Drop duplicate ``topic_code`` rows, preferring the most complete record."""
        if df.empty or "topic_code" not in df.columns:
            return df
        df = df.copy()
        has_desc = df["description"].notna() if "description" in df.columns else False
        df["_has_desc"] = has_desc
        df = df.sort_values("_has_desc", ascending=False)
        df = df.drop_duplicates(subset=["topic_code"], keep="first")
        return df.drop(columns=["_has_desc"]).reset_index(drop=True)

    def query_by_keyword(self, keyword: str, *, rows: int = 20) -> list[dict[str, Any]]:
        """Keyword search across solicitations; returns one dict per matched topic."""
        page = self._get_solicitations({"keyword": keyword, "rows": rows})
        return self._flatten_to_topics(page)

    def query_awards_for_topic(self, topic_code: str) -> dict[str, Any] | None:
        """Best-effort fallback: find an award that used this topic code and
        reconstruct a topic summary from its title/abstract/agency/program.

        Every SBIR.gov award record carries its own Topic Code, so an award
        matching ``topic_code`` stands in for an unfindable solicitation-topic
        record. This is the last of three lookups
        :func:`~sbir_etl.reporting.weekly.enrichment.fetch_solicitation_topics`
        tries per topic, so a miss here means "no topic info available" —
        returns ``None`` on any failure (network error, no match, unexpected
        response shape) rather than raising.
        """
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
