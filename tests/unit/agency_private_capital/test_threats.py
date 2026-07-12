"""Tests for the Phase 2 threats-to-validity gate."""

from __future__ import annotations

import json

import pytest

from sbir_analytics.assets.agency_private_capital.threats import (
    REQUIRED_THREATS,
    ThreatEntry,
    ThreatsToValidity,
)


pytestmark = pytest.mark.fast


def test_default_threats_cover_required_entries() -> None:
    payload = ThreatsToValidity().validate()
    assert payload["passed"] is True
    assert payload["missing"] == []
    assert {entry["id"] for entry in payload["entries"]} >= set(REQUIRED_THREATS)


def test_missing_required_threat_fails_gate() -> None:
    payload = ThreatsToValidity(
        entries=[
            ThreatEntry(
                id="safe_convertible_undercount",
                label="SAFE",
                description="desc",
                mitigation="mitigate",
                as_of="2026-07-08",
            )
        ]
    ).validate()

    assert payload["passed"] is False
    assert "late_stage_form_d_inclusion" in payload["missing"]


def test_write_outputs_json(tmp_path) -> None:
    path = tmp_path / "threats.json"
    payload = ThreatsToValidity().write(path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == payload
