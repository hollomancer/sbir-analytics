"""DUNS keys used by the NSF defense-funding joins."""

from __future__ import annotations

import pytest

from sbir_etl.supply_chain import defense_funding


pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    "value",
    ["123456789A", "1A2B3C4D5E6F7G8H9", "12345678.9", 12345678.9, "000000000", "N/A"],
)
def test_defense_funding_duns_rejects_malformed_and_placeholder_values(value: object) -> None:
    assert defense_funding._duns(value) is None


def test_defense_funding_duns_repairs_float_artifact() -> None:
    assert defense_funding._duns("12345678.0") == "012345678"
    assert defense_funding._duns(" 123-456-789 ") == "123456789"
