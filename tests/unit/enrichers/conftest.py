"""Shared fixtures for enricher tests."""

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def disable_production_retry_waits(monkeypatch):
    """Keep unit tests from paying real API retry backoff delays.

    Tests that assert a sleep call replace these stubs with their own mocks.
    Integration tests retain the production waits because this fixture is
    scoped to ``tests/unit/enrichers``.
    """

    async def no_async_sleep(_seconds):
        return None

    monkeypatch.setattr("sbir_etl.enrichers.base_client.asyncio.sleep", no_async_sleep)
    monkeypatch.setattr("sbir_etl.enrichers.openai_client.time.sleep", lambda _seconds: None)


@pytest.fixture
def enricher_sbir_df():
    """Sample SBIR DataFrame for enricher tests.

    Note: This has a different schema (award_id, company_name, company_uei)
    than the shared sample_sbir_df fixture in conftest_shared.py.
    """
    return pd.DataFrame(
        {
            "award_id": [f"AWD-{i}" for i in range(5)],
            "company_name": [f"Company {i}" for i in range(5)],
            "company_uei": [f"UEI{i:09d}" for i in range(5)],
        }
    )


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


@pytest.fixture
def enricher_recipient_df():
    """Sample recipient DataFrame for enricher tests.

    Note: This has a different schema (recipient_name, recipient_uei)
    than the shared sample_recipient_df fixture in conftest_shared.py.
    """
    return pd.DataFrame(
        {
            "recipient_name": ["Acme Corp", "TechStart Inc"],
            "recipient_uei": ["UEI000000001", "UEI000000002"],
        }
    )
