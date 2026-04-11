"""Shared fixtures for enricher tests."""

import pandas as pd
import pytest


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
