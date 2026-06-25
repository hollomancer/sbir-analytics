"""CMF registry tests: matching, UEI enrichment, and the unknown-vendor diagnostic."""

import pandas as pd
import pytest

from sbir_etl.ot_consortium.registry import CMFRegistry, normalize_cmf_name

pytestmark = pytest.mark.fast


def test_seed_registry_loads():
    reg = CMFRegistry.from_csv("data/reference/cmf_registry.csv")
    assert len(reg.records) >= 6
    assert reg.match(name="Advanced Technology International") is not None


def test_missing_file_degrades_gracefully(tmp_path):
    reg = CMFRegistry.from_csv(tmp_path / "nope.csv")
    assert reg.records == []
    assert reg.match(name="anything") is None


def test_normalize_drops_suffixes():
    assert normalize_cmf_name("SOSSEC, Inc.") == normalize_cmf_name("SOSSEC Inc")
    assert normalize_cmf_name("  Foo   Bar  ") == "foo bar"


def test_match_by_name_and_alias(registry):
    by_canonical = registry.match(name="National Security Technology Accelerator")
    by_alias = registry.match(name="NSTXL")
    assert by_canonical is not None and by_alias is not None
    assert by_canonical.record.cmf_id == by_alias.record.cmf_id == "NSTXL"
    assert by_alias.method == "name"


def test_match_prefers_uei(registry):
    match = registry.match(name="totally different name", uei="CMFATI000001")
    assert match is not None
    assert match.method == "uei"
    assert match.record.cmf_id == "ATI"


def test_enrich_ueis_from_recipient_lookup(registry):
    lookup = pd.DataFrame(
        {
            "legal_business_name": ["National Security Technology Accelerator", "Acme Corp"],
            "uei": ["NSTXLUEI00001", "ACME000000001"],
        }
    )
    filled = registry.enrich_ueis_from_recipient_lookup(lookup)
    assert filled == 1
    match = registry.match(uei="NSTXLUEI00001")
    assert match is not None and match.record.cmf_id == "NSTXL"


def test_enrich_skips_ambiguous(registry):
    lookup = pd.DataFrame(
        {
            "legal_business_name": ["NSTXL", "NSTXL"],
            "uei": ["UEI_A00000001", "UEI_B00000002"],
        }
    )
    filled = registry.enrich_ueis_from_recipient_lookup(lookup)
    assert filled == 0  # ambiguous → left blank for review


def test_unknown_rollup_vendor_diagnostic(registry):
    obligations = pd.DataFrame(
        {
            "recipient_name": [
                "Mystery Technology Consortium",  # consortium-like, not registered
                "Mystery Technology Consortium",
                "NSTXL",  # already registered → excluded
                "Tiny Vendor LLC",  # not consortium-like → excluded
            ],
            "obligation_amount": [3_000_000, 2_000_000, 5_000_000, 100],
        }
    )
    flagged = registry.unknown_rollup_vendor_diagnostic(obligations)
    names = list(flagged["recipient_name"])
    assert "Mystery Technology Consortium" in names
    assert "NSTXL" not in names
    assert "Tiny Vendor LLC" not in names
    # Obligations summed across rows.
    row = flagged[flagged["recipient_name"] == "Mystery Technology Consortium"].iloc[0]
    assert row["total_obligation"] == 5_000_000
