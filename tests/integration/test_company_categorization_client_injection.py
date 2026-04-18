"""Integration tests for USAspending client injection in company_categorization.

Verifies the enricher chain entry points accept an injected
``USAspendingAPIClient`` (no module-level global) and that the injected
client is the one that receives API calls.

These tests use a ``MagicMock`` client so no real HTTP traffic is made; the
integration they cover is the wiring between public retrieval functions and
their internal helpers (``_fuzzy_match_recipient``, ``_fetch_award_details``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from sbir_etl.enrichers.company_categorization import (
    retrieve_company_contracts_api,
    retrieve_sbir_awards_api,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _disable_api_cache(monkeypatch):
    """Ensure cache never returns hits so tests are deterministic regardless of local cache state."""
    from sbir_etl.utils.cache.api_cache import APICache

    monkeypatch.setattr(APICache, "get", lambda *_a, **_k: None)


def _coro(value):
    async def _inner():
        return value

    return _inner()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.search_transactions = MagicMock(
        side_effect=lambda **_: _coro(
            {"results": [], "page_metadata": {"hasNext": False, "total": 0}}
        )
    )
    client.autocomplete_recipient = MagicMock(
        side_effect=lambda *_a, **_k: _coro({"results": []})
    )
    client.fetch_award_details = MagicMock(
        side_effect=lambda *_a, **_k: _coro({})
    )
    return client


def test_retrieve_company_contracts_api_uses_injected_client(mock_client):
    """Caller-provided client must receive the API call (no global singleton)."""
    df = retrieve_company_contracts_api(uei="ABC123DEF456", client=mock_client)

    assert isinstance(df, pd.DataFrame)
    assert mock_client.search_transactions.called, (
        "Injected client.search_transactions was not invoked"
    )
    # No autocomplete path when UEI is valid
    assert not mock_client.autocomplete_recipient.called


def test_retrieve_sbir_awards_api_uses_injected_client(mock_client):
    df = retrieve_sbir_awards_api(uei="ABC123DEF456", client=mock_client)

    assert isinstance(df, pd.DataFrame)
    assert mock_client.search_transactions.called


def test_fuzzy_match_branch_uses_injected_client(mock_client):
    """When UEI/DUNS are missing, fuzzy-match autocomplete also uses injected client."""
    df = retrieve_company_contracts_api(
        company_name="Advanced Technologies", client=mock_client
    )

    assert isinstance(df, pd.DataFrame)
    assert mock_client.autocomplete_recipient.called
    assert mock_client.search_transactions.called


def test_no_client_instantiates_local_one(monkeypatch):
    """When no client is passed the function creates one locally (no global cache)."""
    created = []

    class _StubClient:
        def __init__(self, *_a, **_k):
            created.append(self)

        def search_transactions(self, **_k):
            return _coro({"results": [], "page_metadata": {"hasNext": False, "total": 0}})

    monkeypatch.setattr(
        "sbir_etl.enrichers.company_categorization.USAspendingAPIClient", _StubClient
    )

    df1 = retrieve_company_contracts_api(uei="ABC123DEF456")
    df2 = retrieve_company_contracts_api(uei="ABC123DEF456")

    assert isinstance(df1, pd.DataFrame) and isinstance(df2, pd.DataFrame)
    # Each call gets its own client (no shared global).
    assert len(created) == 2


def test_no_valid_identifier_short_circuits_without_client(mock_client):
    """Early validation returns empty DataFrame without touching the client."""
    df = retrieve_company_contracts_api(client=mock_client)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert not mock_client.search_transactions.called
