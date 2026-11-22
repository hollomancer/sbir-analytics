"""Lifecycle tests for the archived Form D detail fetcher."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import (
    FORM_D_TIER_RULE_CORROBORATED_PERSON_V2,
    FORM_D_TIER_RULE_NAME_GATED_V3,
    FORM_D_TIER_RULE_VERSION,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "archive" / "data" / "fetch_form_d_details.py"
)
_spec = importlib.util.spec_from_file_location("fetch_form_d_details", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["fetch_form_d_details"] = _mod
_spec.loader.exec_module(_mod)


def test_resume_refuses_unversioned_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "details.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "company_name": "Legacy Co",
                "match_confidence": {"tier": "high"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Rebuild form_d_details.jsonl"):
        _mod.load_checkpoint(checkpoint)


def test_resume_accepts_current_rule_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "details.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "company_name": "Current Co",
                "match_confidence": {
                    "tier": "high",
                    "rule_version": FORM_D_TIER_RULE_VERSION,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert _mod.load_checkpoint(checkpoint) == {"Current Co"}


def test_index_without_name_score_is_refused_not_defaulted() -> None:
    legacy = [{"company_name": "Acme Labs", "form_d_filings": []}]
    problem = _mod.index_score_problem(legacy, FORM_D_TIER_RULE_VERSION)
    assert problem is not None and "lack name_score" in problem


def test_v3_needs_match_type_but_v2_does_not() -> None:
    scored = [{"company_name": "Acme Labs", "name_score": 1.0}]
    assert _mod.index_score_problem(scored, FORM_D_TIER_RULE_CORROBORATED_PERSON_V2) is None
    # The default rule is v3, so an untyped index fails without an explicit --rule-version.
    assert FORM_D_TIER_RULE_VERSION == FORM_D_TIER_RULE_NAME_GATED_V3
    problem = _mod.index_score_problem(scored, FORM_D_TIER_RULE_VERSION)
    assert problem is not None and "name_match_type" in problem
    typed = [{"company_name": "Acme Labs", "name_score": 1.0, "name_match_type": "exact"}]
    assert _mod.index_score_problem(typed, FORM_D_TIER_RULE_NAME_GATED_V3) is None
