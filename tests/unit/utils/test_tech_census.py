"""Unit tests for the generalized tech-census engine (sbir_etl.utils.tech_census).

Synthetic fixtures only -- the real drone_manufacturing.yaml config is
verified against real award_data.csv separately (data-bearing, not run in
CI), following the same split used for nano_verify_report_figures.py /
verify_tech_area_figures.py elsewhere in this repo.
"""

import pytest

from sbir_etl.utils.tech_census import (
    CompiledCensus,
    classify_subset,
    load_census_config,
    matched_adjacent,
    matched_exclusion,
    passes_gate,
    run_census,
)


def _award(
    title="",
    abstract="",
    company="Acme",
    agency="Department of Defense",
    phase="Phase II",
    year=2024,
    amount=1_000_000.0,
):
    return {
        "title": title,
        "abstract": abstract,
        "company": company,
        "agency": agency,
        "phase": phase,
        "award_year": year,
        "award_amount": amount,
    }


# A minimal, deliberately synthetic config exercising the same shape as
# drone_manufacturing.yaml, including two overlapping gate patterns (to
# reproduce the exact false-positive mechanism found and fixed while
# building the real config).
TOY_CFG = {
    "area_id": "toy_drones",
    "display_name": "Toy Drones",
    "gate": {
        "min_abstract_only_occurrences": 3,
        "terms": [
            r"\bdrone[s]?\b",
            r"\bunmanned aerial system[s]?\b",
            r"\bunmanned aerial\b",  # overlaps with the pattern above
        ],
    },
    "exclusions": [
        {
            "name": "counter_uas",
            "display_name": "Counter-UAS",
            "terms": [r"\bcounter-?drone[s]?\b"],
        }
    ],
    "adjacent_nonaerial": [
        {"name": "ugv", "display_name": "UGV", "terms": [r"\bUGV[s]?\b"]},
    ],
    "subsets": [
        {"name": "Propulsion", "terms": [r"\bbattery\b", r"\bpropulsion\b"]},
        {"name": "Sensors", "terms": [r"\bgimbal[s]?\b"]},
    ],
    "fallback_subset": "General",
}


def _compiled():
    return CompiledCensus(dict(TOY_CFG))


# --------------------------------------------------------------------------- #
# config loading
# --------------------------------------------------------------------------- #


def test_load_real_drone_config():
    cfg = load_census_config("drone_manufacturing")
    assert cfg["area_id"] == "drone_manufacturing"
    assert len(cfg["gate"]["terms"]) > 0
    assert cfg["fallback_subset"]


def test_load_missing_config_raises():
    with pytest.raises(FileNotFoundError):
        load_census_config("no_such_area")


@pytest.mark.parametrize("missing_key", ["display_name", "gate", "subsets", "fallback_subset"])
def test_config_missing_required_key_raises(tmp_path, missing_key):
    import yaml

    cfg = dict(TOY_CFG)
    del cfg[missing_key]
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        load_census_config("broken", config_dir=tmp_path)


# --------------------------------------------------------------------------- #
# gate: title hit vs occurrence threshold
# --------------------------------------------------------------------------- #


def test_gate_title_hit_always_admits():
    c = _compiled()
    award = _award(title="A New Drone Platform", abstract="Nothing else relevant here.")
    assert passes_gate(award, c) is True


def test_gate_single_incidental_mention_rejected():
    c = _compiled()
    # One mention, "unmanned aerial system" also matches the overlapping
    # "unmanned aerial" pattern -- 2 total occurrences, below the threshold.
    award = _award(
        title="Advanced Battery Chemistry Benchmark",
        abstract="This exceeds the requirement seen in unmanned aerial systems today.",
    )
    assert passes_gate(award, c) is False


def test_gate_overlapping_patterns_do_not_inflate_a_single_mention():
    """The exact false-positive mechanism found in the real data: two gate
    patterns matching the SAME phrase must not count as independent evidence."""
    c = _compiled()
    award = _award(
        title="Directed Energy Weapon Power System",
        abstract="Adversary use of unmanned aerial systems is growing rapidly.",
    )
    text_occurrences = sum(
        len(rx.findall(f"{award['title']} {award['abstract']}")) for rx in c.gate_terms
    )
    assert text_occurrences == 2  # "unmanned aerial system" + "unmanned aerial" overlap
    assert passes_gate(award, c) is False


def test_gate_repeated_mentions_admit():
    c = _compiled()
    award = _award(
        title="Generic Platform Study",
        abstract=(
            "We develop a drone for logistics. The drone flies autonomously. "
            "Field tests of the drone were completed in 2023."
        ),
    )
    assert passes_gate(award, c) is True


def test_gate_no_terms_rejected():
    c = _compiled()
    award = _award(title="Unrelated Widget", abstract="Nothing to see here.")
    assert passes_gate(award, c) is False


# --------------------------------------------------------------------------- #
# exclusions / adjacent categories
# --------------------------------------------------------------------------- #


def test_exclusion_detected_on_gate_passing_award():
    c = _compiled()
    award = _award(title="Counter-drone Radar System", abstract="Detects and defeats hostile UAVs.")
    assert passes_gate(award, c) is True
    assert matched_exclusion(award, c) == "counter_uas"


def test_adjacent_nonaerial_detected():
    c = _compiled()
    award = _award(title="UGV Chassis Design", abstract="A ground robot chassis.")
    assert passes_gate(award, c) is False
    assert matched_adjacent(award, c) == "ugv"


# --------------------------------------------------------------------------- #
# subset classification
# --------------------------------------------------------------------------- #


def test_subset_priority_first_match_wins():
    c = _compiled()
    # Mentions both a Propulsion term and a Sensors term -- Propulsion is
    # listed first in TOY_CFG, so it should win.
    award = _award(title="Drone battery and gimbal integration")
    assert classify_subset(award, c) == "Propulsion"


def test_subset_fallback_when_no_specific_match():
    c = _compiled()
    award = _award(title="Generic drone airframe")
    assert classify_subset(award, c) == "General"


# --------------------------------------------------------------------------- #
# run_census: end-to-end aggregation
# --------------------------------------------------------------------------- #


def test_run_census_aggregates_correctly():
    c = _compiled()
    awards = [
        _award(title="Drone battery system", year=2024, amount=100_000.0),
        _award(title="Drone battery system", year=2024, amount=200_000.0),
        _award(title="Drone gimbal payload", year=2025, amount=50_000.0),
        _award(title="Counter-drone radar", year=2025, amount=999_999.0),  # excluded
        _award(title="UGV wheels", year=2025, amount=999_999.0),  # adjacent, not gate-passing
        _award(title="Unrelated widget", year=2025, amount=999_999.0),  # not relevant at all
    ]
    result = run_census(awards, c)

    assert result["grand_total"] == {"n": 3, "usd": 350_000.0}
    assert result["subset_totals"]["Propulsion"] == {"n": 2, "usd": 300_000.0}
    assert result["subset_totals"]["Sensors"] == {"n": 1, "usd": 50_000.0}
    assert result["fy_totals"][2024] == {"n": 2, "usd": 300_000.0}
    assert result["fy_totals"][2025] == {"n": 1, "usd": 50_000.0}
    assert result["by_fy_subset"][(2024, "Propulsion")] == {"n": 2, "usd": 300_000.0}
    assert result["exclusion_counts"] == {"counter_uas": 1}
    assert result["adjacent_counts"] == {"ugv": 1}
    # subset totals sum to grand total -- no double-counting, nothing dropped
    assert sum(v["n"] for v in result["subset_totals"].values()) == result["grand_total"]["n"]


def test_run_census_empty_input():
    c = _compiled()
    result = run_census([], c)
    assert result["grand_total"] == {"n": 0, "usd": 0.0}
    assert result["classified_awards"] == []
