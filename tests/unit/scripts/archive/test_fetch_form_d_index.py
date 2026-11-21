"""Matcher tests for the archived Form D index fetcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "scripts" / "archive" / "data" / "fetch_form_d_index.py"
)
_spec = importlib.util.spec_from_file_location("fetch_form_d_index", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["fetch_form_d_index"] = _mod
_spec.loader.exec_module(_mod)


def _entry(name: str) -> dict:
    return {"company_name": name, "cik": "1", "date_filed": "2020-01-01"}


def _sbir(*names: str) -> dict[str, dict]:
    return {_mod.normalize_name(n): {} for n in names}


def test_subset_filer_name_is_not_matched() -> None:
    matches = _mod.match_form_d_to_sbir([_entry("Space LLC")], _sbir("Space Kinetic Corp."))
    assert matches == {}


def test_best_candidate_is_kept_and_type_and_score_are_recorded() -> None:
    entries = [_entry("Spectral Sciencs Inc"), _entry("Spectral Science")]
    matches = _mod.match_form_d_to_sbir(entries, _sbir("Spectral Sciences, Inc."))
    (match,) = matches.values()
    assert [e["company_name"] for e in match["entries"]] == ["Spectral Science"]
    assert match["name_match_type"] == "fuzzy"
    assert 0.85 <= match["name_score"] < 1.0


def test_exact_normalized_name_is_recorded_as_exact() -> None:
    matches = _mod.match_form_d_to_sbir([_entry("CREARE LLC")], _sbir("Creare, Inc."))
    (match,) = matches.values()
    assert match["name_match_type"] == "exact"
    assert match["name_score"] == 1.0
