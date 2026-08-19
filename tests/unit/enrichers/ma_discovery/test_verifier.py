"""Tests for the keyword M&A verifier."""

from __future__ import annotations

import pytest

from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition


pytestmark = pytest.mark.fast


def test_verify_acquisition_confirms_when_names_and_verb_present() -> None:
    result = verify_acquisition(
        "Physical Optics",
        "Mercury Systems",
        "Mercury Systems announced the acquisition of Physical Optics Corporation.",
    )
    assert result["confirmed"] is True
    assert result["date"] == "Unknown"
    assert result["value"] is None


def test_verify_acquisition_rejects_when_verb_missing() -> None:
    result = verify_acquisition(
        "Physical Optics",
        "Mercury Systems",
        "Mercury Systems and Physical Optics announced a joint research contract.",
    )
    assert result["confirmed"] is False
    assert result["date"] is None


def test_verify_acquisition_rejects_when_a_name_is_missing() -> None:
    result = verify_acquisition(
        "Physical Optics",
        "Mercury Systems",
        "Mercury Systems announced the acquisition of an unnamed optics firm.",
    )
    assert result["confirmed"] is False
    assert result["date"] is None
