"""Shared fixtures for OT consortium tiering tests."""

import pytest

from sbir_etl.ot_consortium.registry import CMFRecord, CMFRegistry


@pytest.fixture
def registry() -> CMFRegistry:
    """A small registry: one CMF with a verified UEI, one name-only."""
    return CMFRegistry(
        [
            CMFRecord(
                cmf_id="ATI",
                canonical_name="Advanced Technology International",
                aliases=["ATI"],
                uei="CMFATI000001",
                consortia_managed=["National Armaments Consortium (NAC)"],
                agencies=["DoD"],
            ),
            CMFRecord(
                cmf_id="NSTXL",
                canonical_name="National Security Technology Accelerator",
                aliases=["NSTXL"],
                uei=None,
                consortia_managed=["S2MARTS"],
                agencies=["DoD"],
            ),
        ]
    )


# UEI of the firm whose covered-sales claim we are testing.
FIRM_UEI = "FIRMUEI000001"
# A different firm whose *name* collides with the claimant but whose UEI differs.
OTHER_FIRM_UEI = "OTHERUEI00002"
