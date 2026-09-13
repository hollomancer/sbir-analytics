"""Tests for shared FPDS source-system constraints."""

import pytest

from sbir_etl.utils.fpds_constraints import (
    FPDS_DESCRIPTION_DIAGNOSTIC_THRESHOLDS,
    FPDS_DESCRIPTION_MAX_CHARS,
    threshold_is_uniformly_observable,
)


def test_description_diagnostics_never_exceed_source_cap() -> None:
    assert max(FPDS_DESCRIPTION_DIAGNOSTIC_THRESHOLDS) == FPDS_DESCRIPTION_MAX_CHARS
    assert all(
        threshold_is_uniformly_observable(threshold)
        for threshold in FPDS_DESCRIPTION_DIAGNOSTIC_THRESHOLDS
    )


def test_description_threshold_above_source_cap_is_not_uniformly_observable() -> None:
    assert not threshold_is_uniformly_observable(900)
    with pytest.raises(ValueError, match="nonnegative"):
        threshold_is_uniformly_observable(-1)
