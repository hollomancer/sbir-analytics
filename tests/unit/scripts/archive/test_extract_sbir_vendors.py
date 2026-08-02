"""Tests for the bounded SBIR vendor-frame builder."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


SCRIPT_PATH = Path(__file__).parents[4] / "scripts" / "archive" / "extract_sbir_vendors.py"
_SPEC = importlib.util.spec_from_file_location("extract_sbir_vendors", SCRIPT_PATH)
assert _SPEC and _SPEC.loader
extract_sbir_vendors = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(extract_sbir_vendors)

pytestmark = pytest.mark.fast


def test_extract_vendors_keeps_complete_name_frame(tmp_path) -> None:
    awards = tmp_path / "awards.csv"
    frame = pd.DataFrame(
        {
            "UEI": [" UEI000000001 ", None, "UEI000000001"],
            "Duns": ["123456789", "987654321", None],
            "Company": ["Acme, Inc.", "Beta Labs", "Acme, Inc."],
            "Abstract": ["unused"] * 3,
        }
    )
    frame.to_csv(awards, index=False)
    output = tmp_path / "vendor_filters.json"

    stats = extract_sbir_vendors.extract_vendors(awards, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert stats == {
        "total_awards": 3,
        "unique_uei": 1,
        "unique_duns": 2,
        "unique_companies": 2,
    }
    assert payload["uei"] == ["UEI000000001"]
    assert payload["duns"] == ["123456789", "987654321"]
    assert payload["company_names"] == ["ACME, INC.", "BETA LABS"]


def test_extract_vendors_requires_identifier_or_name_column(tmp_path) -> None:
    awards = tmp_path / "awards.csv"
    pd.DataFrame({"Award Title": ["Example"]}).to_csv(awards, index=False)

    with pytest.raises(ValueError, match="none of the vendor columns"):
        extract_sbir_vendors.extract_vendors(awards, tmp_path / "filters.json")
