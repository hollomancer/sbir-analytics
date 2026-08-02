"""Tests for the forward-measurement helpers."""


from scripts.phase3_benchmark.measure_forward import (
    firm_from_row,
    fusion_order,
    normalize_name,
)

_COEF = {"cw": 2.21, "cc": -0.71, "mw": 0.028, "mc": 0.204, "sw": 0.039, "sc": 0.131}


def test_normalize_strips_suffix():
    assert normalize_name("Acme Photonics, Inc.") == "ACME PHOTONICS"


def test_firm_from_row_prefers_awardee_then_parses():
    assert firm_from_row({"Awardee": "PROGENY SYSTEMS CORP"}) == "PROGENY SYSTEMS CORP"
    parsed = firm_from_row(
        {
            "Awardee": "",
            "Description": (
                "The USDA intends to award a non-competitive sole source contract through "
                "the SBIR Program to Synoptos, Inc., 1900 Campus Commons Dr, Reston VA"
            ),
        }
    )
    assert parsed == "Synoptos, Inc."


def test_fusion_order_ranks_topical_match_first():
    query = "a quantum radar system for electromagnetic sensing of aircraft"
    cands = [
        "quantum radar electromagnetic sensing platform for aircraft detection",  # true
        "a bioresorbable bone adhesive for cranial flap fixation",
        "supply chain logistics optimization software",
    ]
    order = fusion_order(query, cands, _COEF)
    assert int(order[0]) == 0
