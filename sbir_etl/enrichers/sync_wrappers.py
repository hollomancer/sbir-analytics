"""Synchronous wrappers for async enricher API clients.

Provides thin sync facades around :class:`USAspendingAPIClient` and
:class:`SAMGovAPIClient` so that scripts and notebooks that don't run
inside an async event loop can still leverage the shared rate-limiting,
retry, and error-handling infrastructure.

Each method delegates to the async original via
:func:`sbir_etl.utils.async_tools.run_sync`.

Usage::

    from sbir_etl.enrichers.sync_wrappers import (
        SyncUSAspendingClient,
        SyncSAMGovClient,
    )

    usa = SyncUSAspendingClient()
    recipient = usa.autocomplete_recipient("Acme Corp")
    usa.close()

    sam = SyncSAMGovClient()
    entity = sam.get_entity_by_uei("ABC123DEF456")
    sam.close()
"""

from __future__ import annotations

from typing import Any

from ..utils.async_tools import run_sync
from .sam_gov.client import SAMGovAPIClient
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
