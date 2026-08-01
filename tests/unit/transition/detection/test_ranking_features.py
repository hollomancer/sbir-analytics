"""Tests for the ported structural ranking features."""

from __future__ import annotations

import pytest

from sbir_ml.transition.detection.ranking_features import id_xref, normalize_identifier


pytestmark = pytest.mark.fast


def test_id_xref_matches_firm_identifier_despite_formatting():
    identifiers = {"N00014-20-C-0055", "AF151-020"}
    assert id_xref("...work under contract N00014 20 C 0055 for...", identifiers) == 1.0
    assert id_xref("award n00014-20-c-0055 continuation", identifiers) == 1.0
    assert id_xref("unrelated sources sought notice", identifiers) == 0.0


def test_id_xref_ignores_short_identifiers_and_null_inputs():
    assert id_xref("mentions AF15 in passing", {"AF15"}) == 0.0  # <6 chars ignored
    assert id_xref(None, {"N0001420C0055"}) == 0.0
    assert id_xref("some text", {None}) == 0.0
    assert id_xref("some text", set()) == 0.0


def test_normalize_identifier_strips_to_alphanumerics():
    assert normalize_identifier("N00014-20-C-0055") == "N0001420C0055"
    assert normalize_identifier("army example 001") == "ARMYEXAMPLE001"
