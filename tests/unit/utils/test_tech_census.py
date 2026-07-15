"""Unit and curated golden-case tests for the tech-census engine."""

from pathlib import Path

import pytest
import yaml

from sbir_etl.utils.tech_census import (
    CompiledCensus,
    classify_subset,
    gate_evidence,
    load_award_data_csv,
    load_census_config,
    matched_adjacent,
    matched_exclusion,
    passes_gate,
    run_census,
)


def _award(
    title: str = "",
    abstract: str = "",
    *,
    company: str = "Acme",
    agency: str = "Department of Defense",
    program: str = "SBIR",
    phase: str = "Phase II",
    year: int = 2024,
    amount: float = 1_000_000.0,
    tracking: str = "T-1",
    contract: str = "C-1",
    source_row: int = 2,
) -> dict:
    return {
        "title": title,
        "abstract": abstract,
        "company": company,
        "agency": agency,
        "program": program,
        "phase": phase,
        "award_year": year,
        "award_amount": amount,
        "agency_tracking_number": tracking,
        "contract": contract,
        "source_row": source_row,
    }


TOY_CFG = {
    "area_id": "toy_drones",
    "display_name": "Toy Drones",
    "gate": {
        "min_abstract_only_occurrences": 3,
        "terms": [
            r"\bdrone[s]?\b",
            r"\bUAS\b",
            r"\bunmanned aerial system[s]?\b",
            r"\bunmanned aerial\b",
        ],
    },
    "exclusions": [
        {"name": "counter_uas", "terms": [r"\bcounter-?drone[s]?\b"]},
    ],
    "adjacent_nonaerial": [
        {"name": "ugv", "terms": [r"\bUGV[s]?\b"]},
    ],
    "subsets": [
        {"name": "Propulsion", "terms": [r"\bbattery\b", r"\bpropulsion\b"]},
        {"name": "Sensors", "terms": [r"\bgimbal[s]?\b"]},
    ],
    "fallback_subset": "General",
}


def _compiled() -> CompiledCensus:
    return CompiledCensus(dict(TOY_CFG))


def test_profiles_keep_broad_relevance_separate_from_strict_manufacturing() -> None:
    strict = load_census_config("drone_manufacturing")
    broad = load_census_config("uas_relevance")
    assert strict["programs"] == ["SBIR"]
    assert broad["programs"] == ["SBIR", "STTR"]
    assert strict["physical_gate"]["terms"]
    assert "physical_gate" not in broad
    assert strict["version"] == "2.0.0"


def test_load_missing_config_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_census_config("no_such_area")


@pytest.mark.parametrize("missing_key", ["display_name", "gate", "subsets", "fallback_subset"])
def test_config_missing_required_key_raises(tmp_path: Path, missing_key: str) -> None:
    cfg = dict(TOY_CFG)
    del cfg[missing_key]
    (tmp_path / "broken.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        load_census_config("broken", config_dir=tmp_path)


def test_gate_title_hit_always_admits() -> None:
    assert passes_gate(_award(title="A New Drone Platform"), _compiled())


def test_overlapping_aliases_do_not_inflate_one_mention() -> None:
    compiled = _compiled()
    award = _award(
        title="Advanced Battery Chemistry",
        abstract="A requirement used by an unmanned aerial system (UAS).",
    )
    raw_hits = sum(
        len(pattern.findall(f"{award['title']} {award['abstract']}"))
        for pattern in compiled.gate_terms
    )
    assert raw_hits == 3
    assert gate_evidence(award, compiled) == ["unmanned aerial system", "UAS"]
    assert not passes_gate(award, compiled)


def test_repeated_nonoverlapping_mentions_admit() -> None:
    award = _award(
        title="Generic Study",
        abstract="A drone is built. The drone is tested. A third drone is delivered.",
    )
    assert passes_gate(award, _compiled())


def test_exclusion_adjacent_and_subset_priority() -> None:
    compiled = _compiled()
    assert matched_exclusion(_award(title="Counter-drone radar"), compiled) == "counter_uas"
    assert matched_adjacent(_award(title="UGV chassis"), compiled) == "ugv"
    assert classify_subset(_award(title="Drone battery and gimbal"), compiled) == "Propulsion"
    assert classify_subset(_award(title="Generic drone"), compiled) == "General"


def test_run_census_aggregates_without_double_counting() -> None:
    result = run_census(
        [
            _award(title="Drone battery", year=2024, amount=100_000),
            _award(title="Drone battery", year=2024, amount=200_000, tracking="T-2"),
            _award(title="Drone gimbal", year=2025, amount=50_000, tracking="T-3"),
            _award(title="Counter-drone radar", amount=999_999),
            _award(title="UGV wheels", amount=999_999),
        ],
        _compiled(),
    )
    assert result["grand_total"] == {"n": 3, "usd": 350_000.0}
    assert result["subset_totals"]["Propulsion"] == {"n": 2, "usd": 300_000.0}
    assert result["fy_totals"][2025] == {"n": 1, "usd": 50_000.0}
    assert result["exclusion_counts"] == {"counter_uas": 1}
    assert result["adjacent_counts"] == {"ugv": 1}


def test_strict_program_filter_excludes_sttr_and_unknown() -> None:
    compiled = CompiledCensus.from_area("drone_manufacturing")
    awards = [
        _award(title="Drone airframe", program="SBIR"),
        _award(title="Drone airframe", program="STTR", tracking="T-2"),
        _award(title="Drone airframe", program="", tracking="T-3"),
    ]
    result = run_census(awards, compiled)
    assert result["grand_total"]["n"] == 1
    assert result["program_exclusion_counts"] == {"STTR": 1, "UNKNOWN": 1}


def test_explicit_empty_program_override_disables_filtering() -> None:
    compiled = CompiledCensus.from_area("drone_manufacturing")
    result = run_census([_award(title="Drone airframe", program="STTR")], compiled, programs=[])
    assert result["grand_total"]["n"] == 1
    assert result["programs"] == []


def test_broad_profile_includes_software_that_strict_profile_rejects() -> None:
    award = _award(title="Drone Mission Planning Software", abstract="Autonomy algorithms")
    broad = run_census([award], CompiledCensus.from_area("uas_relevance"))
    strict = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert broad["grand_total"]["n"] == 1
    assert broad["classified_awards"][0]["scope_class"] == "Software, Autonomy & Analytics"
    assert strict["grand_total"]["n"] == 0
    assert strict["exclusion_counts"] == {"nonphysical_primary": 1}


def test_nonphysical_title_is_excluded_even_with_incidental_hardware_evidence() -> None:
    award = _award(
        title="AI-Enabled UAS Airworthiness Certification Software",
        abstract="We develop an aircraft integration prototype for the UAS.",
    )
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 0
    assert result["exclusion_counts"] == {"nonphysical_primary": 1}


@pytest.mark.parametrize(
    "title",
    [
        "UAS Sensor Fusion Software",
        "Machine Learning for UAS Radar Classification",
        "Drone Wing Structural Analysis Software",
    ],
)
def test_generic_hardware_noun_does_not_rescue_nonphysical_title(title: str) -> None:
    result = run_census([_award(title=title)], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 0
    assert result["exclusion_counts"] == {"nonphysical_primary": 1}


def test_explicit_hardware_deliverable_can_rescue_mixed_title() -> None:
    result = run_census(
        [_award(title="Machine-Learning UAS Sensor Hardware")],
        CompiledCensus.from_area("drone_manufacturing"),
    )
    assert result["grand_total"]["n"] == 1


def test_strict_profile_includes_modern_physical_platform_alias() -> None:
    award = _award(title="Fabricated Composite Wing for Collaborative Combat Aircraft")
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 1
    assert result["classified_awards"][0]["subset"].startswith("Airframes")


@pytest.mark.parametrize(
    "title",
    [
        "CCA Airframe Manufacturing",
        "ACP Avionics Hardware",
        "HAPS Propulsion System",
    ],
)
def test_broad_relevance_profile_is_superset_for_modern_physical_aliases(title: str) -> None:
    award = _award(title=title)
    strict = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    broad = run_census([award], CompiledCensus.from_area("uas_relevance"))
    assert strict["grand_total"]["n"] == 1
    assert broad["grand_total"]["n"] == 1


@pytest.mark.parametrize(
    "title",
    [
        "Circuit Card Assembly (CCA) Manufacturing Process",
        "Advanced Care Planning (ACP) Platform Software",
        "Hamiltonian Analysis-Based Prediction Service (HAPS)",
    ],
)
def test_ambiguous_modern_acronyms_require_aerial_context(title: str) -> None:
    award = _award(title=title)
    strict = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    broad = run_census([award], CompiledCensus.from_area("uas_relevance"))
    assert strict["grand_total"]["n"] == 0
    assert broad["grand_total"]["n"] == 0


def test_one_uas_mention_with_nearby_physical_development_evidence_passes() -> None:
    award = _award(
        title="Advanced Ceramic Coating",
        abstract="We develop an engine coating for an unmanned aerial system.",
    )
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 1
    assert result["classified_awards"][0]["physical_evidence"] == [
        "physical: coating",
        "relationship: develop",
        "relevance: unmanned aerial system",
    ]


def test_same_span_cannot_supply_physical_and_relationship_evidence() -> None:
    award = _award(
        title="Advanced Ceramic Coating",
        abstract="A coating is used on an unmanned aerial system.",
    )
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 0
    assert result["rejection_counts"] == {"relevance_gate": 1}


def test_physical_noun_without_funded_relationship_is_rejected() -> None:
    award = _award(
        title="Mission Analysis",
        abstract="Drone missions use drones. Another drone may carry a battery in the future.",
    )
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["grand_total"]["n"] == 0
    assert result["exclusion_counts"] == {"nonphysical_primary": 1}


def test_failed_relevance_exclusion_is_preserved_in_audit_rows() -> None:
    award = _award(
        title="Generic Radar",
        abstract="This counter-UAS system tracks one UAS.",
    )
    result = run_census([award], CompiledCensus.from_area("drone_manufacturing"))
    assert result["exclusion_counts"] == {"counter_uas": 1}
    assert len(result["excluded_awards"]) == 1
    assert result["excluded_awards"][0]["classification_source"] == "rules"


def test_counter_uas_and_nonaerial_are_excluded_but_interceptor_hardware_is_not() -> None:
    compiled = CompiledCensus.from_area("drone_manufacturing")
    result = run_census(
        [
            _award(title="Counter-UAS Radar Battery System", tracking="T-1"),
            _award(title="UUV Airframe with UAV Interoperability", tracking="T-2"),
            _award(title="Counter-UAS Interceptor Drone Airframe", tracking="T-3"),
        ],
        compiled,
    )
    assert result["grand_total"]["n"] == 1
    assert result["classified_awards"][0]["agency_tracking_number"] == "T-3"
    assert result["exclusion_counts"] == {"counter_uas": 1, "non_aerial_title": 1}


def test_classified_rows_preserve_audit_evidence_and_source_ids() -> None:
    award = _award(title="Drone Avionics", tracking="TRACK", contract="CONTRACT", source_row=42)
    row = run_census([award], CompiledCensus.from_area("drone_manufacturing"))["classified_awards"][
        0
    ]
    assert row["program"] == "SBIR"
    assert row["agency_tracking_number"] == "TRACK"
    assert row["contract"] == "CONTRACT"
    assert row["source_row"] == 42
    assert row["gate_evidence"] and row["physical_evidence"]
    assert "subset_evidence" in row and "scope_evidence" in row
    assert row["classification_source"] == "rules"


def test_versioned_override_ledger_can_include_and_exclude(tmp_path: Path) -> None:
    cfg = dict(TOY_CFG)
    cfg["overrides_file"] = "overrides.yaml"
    (tmp_path / "overrides.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "review-1",
                "overrides": [
                    {
                        "identifiers": {"agency_tracking_number": "IN"},
                        "action": "include",
                        "subset": "Sensors",
                        "reason": "Reviewed physical deliverable",
                    },
                    {
                        "identifiers": {"agency_tracking_number": "OUT"},
                        "action": "exclude",
                        "reason": "Reviewed false positive",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "toy_drones.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    compiled = CompiledCensus.from_area("toy_drones", tmp_path)
    result = run_census(
        [
            _award(title="Unrelated", tracking="IN"),
            _award(title="Drone gimbal", tracking="OUT"),
        ],
        compiled,
    )
    assert result["override_version"] == "review-1"
    assert result["grand_total"]["n"] == 1
    assert result["classified_awards"][0]["classification_source"] == "override"
    assert result["classified_awards"][0]["subset"] == "Sensors"
    assert result["exclusion_counts"] == {"manual_override": 1}


def test_csv_loader_preserves_program_identifiers_and_source_row(tmp_path: Path) -> None:
    path = tmp_path / "awards.csv"
    path.write_text(
        "Award Title,Abstract,Company,Agency,Program,Phase,Award Year,Award Amount,"
        "Agency Tracking Number,Contract\n"
        'Drone Airframe,"Build it",Acme,DOD,SBIR,Phase II,2024,"$1,250",TRACK,CONTRACT\n',
        encoding="utf-8",
    )
    award = load_award_data_csv(path)[0]
    assert award["program"] == "SBIR"
    assert award["agency_tracking_number"] == "TRACK"
    assert award["contract"] == "CONTRACT"
    assert award["source_row"] == 2
    assert award["award_amount"] == 1_250.0
