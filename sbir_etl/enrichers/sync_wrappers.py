"""Synchronous wrappers for async enricher API clients.

Provides thin sync facades around the async API clients so that scripts
and notebooks that don't run inside an async event loop can still leverage
the shared rate-limiting, retry, and error-handling infrastructure.

Each method delegates to the async original via
:func:`sbir_etl.utils.async_tools.run_sync`. Close/context-manager
plumbing is provided by :class:`_SyncFacade`.

Usage::

    from sbir_etl.enrichers.sync_wrappers import (
        SyncUSAspendingClient,
        SyncSAMGovClient,
        SyncSemanticScholarClient,
    )

    with SyncUSAspendingClient() as usa:
        recipient = usa.autocomplete_recipient("Acme Corp")

    with SyncSAMGovClient() as sam:
        entity = sam.get_entity_by_uei("ABC123DEF456")

    with SyncSemanticScholarClient() as s2:
        record = s2.lookup_author("Jane Smith")
"""

from __future__ import annotations

from typing import Any

from ..utils.async_tools import run_sync
from .fpds_atom import FPDSAtomClient, FPDSRecord
from .lens_patents import LensPatentClient, LensPatentRecord
from .opencorporates import CorporateRecord, Officer, OpenCorporatesClient
from .orcid_client import ORCIDClient, ORCIDRecord
from .press_wire import PressRelease, PressWireClient
from .rate_limiting import RateLimiter
from .sam_gov.client import SAMGovAPIClient
from .semantic_scholar import PublicationRecord, SemanticScholarClient
from .usaspending.client import USAspendingAPIClient


class _SyncFacade:
    """Base class for sync facades over async API clients.

    Subclasses set ``self._client`` to any object exposing an ``aclose()``
    coroutine. This base provides sync ``close()`` and context-manager
    plumbing so each concrete facade only defines the domain methods.
    """

    _client: Any

    def close(self) -> None:
        run_sync(self._client.aclose())

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class SyncUSAspendingClient(_SyncFacade):
    """Synchronous facade for :class:`USAspendingAPIClient`."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._client = USAspendingAPIClient(config=config)

    def get_recipient_by_uei(self, uei: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_recipient_by_uei(uei))

    def get_recipient_by_duns(self, duns: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_recipient_by_duns(duns))

    def get_recipient_by_cage(self, cage: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_recipient_by_cage(cage))

    def get_award_by_piid(self, piid: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_award_by_piid(piid))

    def autocomplete_recipient(
        self, search_text: str, limit: int = 5
    ) -> dict[str, Any]:
        return run_sync(self._client.autocomplete_recipient(search_text, limit))

    def search_transactions(
        self,
        filters: dict[str, Any],
        fields: list[str],
        page: int = 1,
        limit: int = 100,
        sort: str | None = "Transaction Amount",
        order: str | None = "desc",
    ) -> dict[str, Any]:
        return run_sync(
            self._client.search_transactions(
                filters, fields, page=page, limit=limit, sort=sort, order=order
            )
        )

    def search_awards(
        self,
        filters: dict[str, Any],
        fields: list[str],
        page: int = 1,
        limit: int = 100,
        sort: str | None = "Award Amount",
        order: str | None = "desc",
    ) -> dict[str, Any]:
        return run_sync(
            self._client.search_awards(
                filters, fields, page=page, limit=limit, sort=sort, order=order
            )
        )

    def search_recipients(
        self, keyword: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        return run_sync(self._client.search_recipients(keyword, limit))

    def get_recipient_profile(
        self, recipient_id: str, year: str = "all"
    ) -> dict[str, Any] | None:
        return run_sync(self._client.get_recipient_profile(recipient_id, year))

    def fetch_award_details(self, award_id: str) -> dict[str, Any] | None:
        return run_sync(self._client.fetch_award_details(award_id))


class SyncSAMGovClient(_SyncFacade):
    """Synchronous facade for :class:`SAMGovAPIClient`."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._client = SAMGovAPIClient(config=config)

    def get_entity_by_uei(self, uei: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_entity_by_uei(uei))

    def get_entity_by_cage(self, cage: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_entity_by_cage(cage))

    def search_entities(
        self,
        *,
        legal_business_name: str | None = None,
        duns: str | None = None,
        registration_status: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return run_sync(
            self._client.search_entities(
                legal_business_name=legal_business_name,
                duns=duns,
                registration_status=registration_status,
                limit=limit,
            )
        )


class SyncSemanticScholarClient(_SyncFacade):
    """Synchronous facade for :class:`SemanticScholarClient`.

    Supports ``shared_limiter`` for sharing a global rate budget across
    worker threads.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = 100,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = SemanticScholarClient(
            api_key=api_key,
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    def search_author(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        return run_sync(self._client.search_author(name, limit))

    def get_author_details(self, author_id: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_author_details(author_id))

    def lookup_author(self, name: str) -> PublicationRecord | None:
        return run_sync(self._client.lookup_author(name))


class SyncFPDSAtomClient(_SyncFacade):
    """Synchronous facade for :class:`FPDSAtomClient`.

    Supports ``shared_limiter`` for sharing a global FPDS rate budget
    across worker threads.
    """

    def __init__(
        self,
        *,
        timeout: int = 30,
        rate_limit_per_minute: int = 60,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = FPDSAtomClient(
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    def search_by_piid(self, piid: str) -> FPDSRecord | None:
        return run_sync(self._client.search_by_piid(piid))

    def search_by_vendor(
        self,
        name: str | None = None,
        uei: str | None = None,
        limit: int = 10,
    ) -> list[FPDSRecord]:
        return run_sync(self._client.search_by_vendor(name=name, uei=uei, limit=limit))

    def get_description(self, piid: str) -> str | None:
        return run_sync(self._client.get_description(piid))

    def get_research_code(self, piid: str) -> str | None:
        return run_sync(self._client.get_research_code(piid))

    def get_descriptions(self, piids: list[str]) -> dict[str, str]:
        return run_sync(self._client.get_descriptions(piids))


class SyncORCIDClient(_SyncFacade):
    """Synchronous facade for :class:`ORCIDClient`.

    Supports ``shared_limiter`` for sharing a global rate budget across
    worker threads.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = 60,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = ORCIDClient(
            access_token=access_token,
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    def search(
        self,
        family_name: str,
        given_names: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return run_sync(self._client.search(family_name, given_names, limit))

    def get_profile(self, orcid_id: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_profile(orcid_id))

    def lookup(self, name: str) -> ORCIDRecord | None:
        return run_sync(self._client.lookup(name))


class SyncOpenCorporatesClient(_SyncFacade):
    """Synchronous facade for :class:`OpenCorporatesClient`.

    Supports ``shared_limiter`` for sharing a global rate budget across
    worker threads (the ``weekly_awards_report`` job uses a 30/min shared
    limiter to stay under the free-tier quota).
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = 30,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = OpenCorporatesClient(
            api_token=api_token,
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    def search_companies(
        self,
        name: str,
        jurisdiction: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        return run_sync(
            self._client.search_companies(name, jurisdiction, limit)
        )

    def get_company(
        self, jurisdiction: str, company_number: str
    ) -> dict[str, Any] | None:
        return run_sync(self._client.get_company(jurisdiction, company_number))

    def get_officers(
        self, jurisdiction: str, company_number: str
    ) -> list[Officer]:
        return run_sync(self._client.get_officers(jurisdiction, company_number))

    def get_corporate_grouping(
        self, jurisdiction: str, company_number: str
    ) -> tuple[str | None, str | None]:
        return run_sync(
            self._client.get_corporate_grouping(jurisdiction, company_number)
        )

    def lookup_company(
        self,
        name: str,
        jurisdiction: str | None = None,
    ) -> CorporateRecord | None:
        return run_sync(self._client.lookup_company(name, jurisdiction))


class SyncPressWireClient(_SyncFacade):
    """Synchronous facade for :class:`PressWireClient`.

    Exposes the watchlist / poll / reset_seen API synchronously. The
    watchlist and dedup cache are stateful on the underlying async
    client; the facade just routes polling calls through
    :func:`run_sync`.
    """

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        *,
        timeout: int = 30,
        rate_limit_per_minute: int = 30,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = PressWireClient(
            feeds=feeds,
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    # Watchlist management is pure Python — no need to route through run_sync
    def set_watchlist(self, company_names: list[str]) -> None:
        self._client.set_watchlist(company_names)

    def add_to_watchlist(self, company_name: str) -> None:
        self._client.add_to_watchlist(company_name)

    def reset_seen(self) -> None:
        self._client.reset_seen()

    # Polling is async on the underlying client — route through run_sync
    def poll(self) -> list[PressRelease]:
        return run_sync(self._client.poll())

    def poll_all_unfiltered(self) -> list[PressRelease]:
        return run_sync(self._client.poll_all_unfiltered())


class SyncLensPatentClient(_SyncFacade):
    """Synchronous facade for :class:`LensPatentClient`."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        timeout: int = 30,
        rate_limit_per_minute: int = 50,
        shared_limiter: RateLimiter | None = None,
    ) -> None:
        self._client = LensPatentClient(
            api_token=api_token,
            timeout=timeout,
            rate_limit_per_minute=rate_limit_per_minute,
            shared_limiter=shared_limiter,
        )

    def search_patents_by_assignee(
        self, company_name: str, max_results: int = 100
    ) -> list[LensPatentRecord]:
        return run_sync(
            self._client.search_patents_by_assignee(company_name, max_results)
        )

    def search_patents_by_inventor(
        self, inventor_name: str, max_results: int = 50
    ) -> list[LensPatentRecord]:
        return run_sync(
            self._client.search_patents_by_inventor(inventor_name, max_results)
        )
