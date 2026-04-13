"""Synchronous wrappers for async enricher API clients.

Provides thin sync facades around :class:`USAspendingAPIClient`,
:class:`SAMGovAPIClient`, and :class:`SemanticScholarClient` so that
scripts and notebooks that don't run inside an async event loop can
still leverage the shared rate-limiting, retry, and error-handling
infrastructure.

Each method delegates to the async original via
:func:`sbir_etl.utils.async_tools.run_sync`.

Usage::

    from sbir_etl.enrichers.sync_wrappers import (
        SyncUSAspendingClient,
        SyncSAMGovClient,
        SyncSemanticScholarClient,
    )

    usa = SyncUSAspendingClient()
    recipient = usa.autocomplete_recipient("Acme Corp")
    usa.close()

    sam = SyncSAMGovClient()
    entity = sam.get_entity_by_uei("ABC123DEF456")
    sam.close()

    with SyncSemanticScholarClient() as s2:
        record = s2.lookup_author("Jane Smith")
"""

from __future__ import annotations

from typing import Any

from ..utils.async_tools import run_sync
from .rate_limiting import RateLimiter
from .sam_gov.client import SAMGovAPIClient
from .semantic_scholar import PublicationRecord, SemanticScholarClient
from .usaspending.client import USAspendingAPIClient


class SyncUSAspendingClient:
    """Synchronous facade for :class:`USAspendingAPIClient`."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._client = USAspendingAPIClient(config=config)

    def close(self) -> None:
        run_sync(self._client.aclose())

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


class SyncSAMGovClient:
    """Synchronous facade for :class:`SAMGovAPIClient`."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._client = SAMGovAPIClient(config=config)

    def close(self) -> None:
        run_sync(self._client.aclose())

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


class SyncSemanticScholarClient:
    """Synchronous facade for :class:`SemanticScholarClient`.

    Exposes a blocking ``with``-statement context manager plus sync
    versions of ``search_author``, ``get_author_details``, and
    ``lookup_author``. Supports the ``shared_limiter`` parameter for
    sharing a global rate budget across worker threads.
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

    def close(self) -> None:
        run_sync(self._client.aclose())

    def __enter__(self) -> SyncSemanticScholarClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def search_author(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        return run_sync(self._client.search_author(name, limit))

    def get_author_details(self, author_id: str) -> dict[str, Any] | None:
        return run_sync(self._client.get_author_details(author_id))

    def lookup_author(self, name: str) -> PublicationRecord | None:
        return run_sync(self._client.lookup_author(name))
