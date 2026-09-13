"""Tests for the offline Form D confidence-tier migration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_CORROBORATED_PERSON_V2,
    FORM_D_TIER_RULE_PERSON_OR_ZIP_V1,
)

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "data" / "rescore_form_d_details.py"
_spec = importlib.util.spec_from_file_location("rescore_form_d_details", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["rescore_form_d_details"] = _mod
_spec.loader.exec_module(_mod)


def _record(
    *,
    tier: str = "high",
    person: float | None = 0.9,
    address: float | None = 0.0,
    state: float | None = 0.0,
    ciks: tuple[str, ...] = ("000123",),
) -> dict:
    return {
        "company_name": "Acme Labs",
        "match_confidence": {
            "tier": tier,
            "score": 0.7,
            "name_score": 0.9,
            "person_score": person,
            "person_match_detail": "PI 'Robert Chen' <> Officer 'Roberta Chen' (96%)",
            "state_score": state,
            "address_score": address,
            "temporal_score": 1.0,
            "year_of_inc_score": 1.0,
        },
        "offerings": [
            {
                "accession_number": f"ACCESSION-{index}",
                "cik": cik,
                "filing_date": f"202{index}-01-01",
            }
            for index, cik in enumerate(ciks)
        ],
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_rescore_record_demotes_person_only_and_stamps_rule_and_scope() -> None:
    migrated = _mod.rescore_record(_record())

    assert migrated["match_confidence"]["tier"] == "medium"
    assert migrated["match_confidence"]["rule_version"] == FORM_D_TIER_RULE_CORROBORATED_PERSON_V2
    assert migrated["match_confidence_scope"]["unit"] == "company-record"
    assert migrated["match_confidence_scope"]["distinct_ciks"] == ["123"]


def test_rescore_record_keeps_person_plus_state_high_without_zip() -> None:
    migrated = _mod.rescore_record(_record(person=0.9, address=0.0, state=1.0))

    assert migrated["match_confidence"]["tier"] == "high"


def test_historical_rule_can_be_reproduced_explicitly() -> None:
    migrated = _mod.rescore_record(
        _record(),
        rule_version=FORM_D_TIER_RULE_PERSON_OR_ZIP_V1,
    )

    assert migrated["match_confidence"]["tier"] == "high"
    assert migrated["match_confidence"]["rule_version"] == FORM_D_TIER_RULE_PERSON_OR_ZIP_V1


def test_rescore_jsonl_is_deterministic_idempotent_and_reports_aggregation(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write_jsonl(
        source,
        [
            _record(),
            _record(person=0.9, state=1.0, ciks=("000123", "000456")),
            _record(person=0.2, address=1.0, state=0.0),
        ],
    )

    summary = _mod.rescore_jsonl(source, first)
    second_summary = _mod.rescore_jsonl(first, second)

    assert first.read_bytes() == second.read_bytes()
    assert summary["record_count"] == 3
    assert summary["tiers_before"] == {"high": 3}
    assert summary["tiers_after"] == {"high": 2, "medium": 1}
    assert summary["rule_versions_before"] == {"unversioned": 3}
    assert summary["multi_filing_records"] == 1
    assert summary["multi_cik_records"] == 1
    assert second_summary["rule_versions_before"] == {FORM_D_TIER_RULE_CORROBORATED_PERSON_V2: 3}


def test_in_place_parse_failure_preserves_original_bytes(tmp_path: Path) -> None:
    path = tmp_path / "details.jsonl"
    original = json.dumps(_record()) + "\n{not-json}\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(_mod.FormDRescoreError, match="line 2: invalid JSON"):
        _mod.rescore_jsonl(path, path)

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".details.jsonl.*.tmp")) == []


def test_invalid_stored_score_fails_instead_of_guessing() -> None:
    record = _record()
    record["match_confidence"]["person_score"] = "0.9"

    with pytest.raises(_mod.FormDRescoreError, match="person_score must be a number or null"):
        _mod.rescore_record(record)
