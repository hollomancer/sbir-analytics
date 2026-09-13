"""Lifecycle tests for the archived Form D detail fetcher."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import FORM_D_TIER_RULE_VERSION

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

    with pytest.raises(ValueError, match="rescore_form_d_details.py"):
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
