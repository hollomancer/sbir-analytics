"""Shared fixtures for enricher tests."""

import pandas as pd
import pytest


@pytest.fixture
def sample_sbir_df():
    """Sample SBIR DataFrame for enricher tests."""
    return pd.DataFrame(
        {
            "award_id": [f"AWD-{i}" for i in range(5)],
            "company_name": [f"Company {i}" for i in range(5)],
            "company_uei": [f"UEI{i:09d}" for i in range(5)],
        }
    )


@pytest.fixture
def sample_recipient_df():
    """Sample recipient DataFrame for enricher tests."""
    return pd.DataFrame(
        {
            "recipient_name": ["Acme Corp", "TechStart Inc"],
            "recipient_uei": ["UEI000000001", "UEI000000002"],
        }
    )
