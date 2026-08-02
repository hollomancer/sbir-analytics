"""Tests for firm extraction from self-labeled notices."""

from scripts.phase3_benchmark.consolidate_selflabeled import firm_from_notice


def test_prefers_awardee_when_present():
    assert firm_from_notice({"Awardee": "PROGENY SYSTEMS CORP"}) == "PROGENY SYSTEMS CORP"


def test_parses_firm_from_description_before_address():
    # internal comma in the firm name must survive (stops at the comma before the street number)
    row = {
        "Awardee": "",
        "Description": (
            "The USDA intends to award a non-competitive sole source contract "
            "through the SBIR Program to Synoptos, Inc., 1900 Campus Commons Dr, Reston VA"
        ),
    }
    assert firm_from_notice(row) == "Synoptos, Inc."


def test_parses_firm_from_modification_clause():
    row = {
        "Awardee": "",
        "Description": (
            "NAVSEA intends to utilize other than full and open competition to award a "
            "contract modification under contract N00024-08-C-6272 to Progeny Systems "
            "Corporation, 9500 Innovation Drive, Manassas VA"
        ),
    }
    assert firm_from_notice(row) == "Progeny Systems Corporation"


def test_returns_blank_when_no_firm():
    assert (
        firm_from_notice({"Awardee": "", "Description": "Solar Powered Tent System", "Title": ""})
        == ""
    )
