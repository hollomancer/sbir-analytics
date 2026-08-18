from pathlib import Path

import pytest
import yaml

from sbir_etl.reporting.defense_taxonomy_crosswalk import (
    DEFAULT_CROSSWALK_PATH,
    DEFAULT_TAXONOMY_PATH,
    load_defense_crosswalk,
)


def test_crosswalk_covers_all_canonical_cet_ids() -> None:
    crosswalk = load_defense_crosswalk()
    taxonomy = yaml.safe_load(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))
    canonical_ids = {area["cet_id"] for area in taxonomy["cet_areas"]}

    assert crosswalk.source_taxonomy == "NSTC-2025Q1"
    assert crosswalk.target_versions == {
        "dod_cta14": "DOD-CTA-14-2022",
        "dod_sc8": "DOD-SC-8-2022",
        "nssts_cet14": "NSSTS-CET-14-2026",
    }
    assert set(crosswalk.mappings) == canonical_ids


def test_representative_direct_and_partial_mappings() -> None:
    crosswalk = load_defense_crosswalk()

    assert crosswalk.targets_for("hypersonics", "dod_cta14") == ["hypersonics"]
    assert crosswalk.targets_for("hypersonics", "dod_sc8") == ["kinetic_capabilities"]
    assert crosswalk.targets_for("advanced_nuclear_energy_systems", "dod_cta14") == []
    renewable = crosswalk.mapping_details("renewable_energy_generation_and_storage", "dod_sc8")
    assert renewable[0]["target"] == "energy_storage_and_batteries"
    assert renewable[0]["strength"] == "partial"


def test_unknown_target_fails_referential_integrity(tmp_path: Path) -> None:
    payload = yaml.safe_load(DEFAULT_CROSSWALK_PATH.read_text(encoding="utf-8"))
    payload["mappings"][0]["dod_cta14"][0]["target"] = "not_a_real_target"
    invalid_path = tmp_path / "invalid_crosswalk.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown dod_cta14 target"):
        load_defense_crosswalk(crosswalk_path=invalid_path)


def test_missing_canonical_cet_fails_coverage_check(tmp_path: Path) -> None:
    payload = yaml.safe_load(DEFAULT_CROSSWALK_PATH.read_text(encoding="utf-8"))
    payload["mappings"] = payload["mappings"][:-1]
    invalid_path = tmp_path / "incomplete_crosswalk.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="cover canonical CET IDs exactly"):
        load_defense_crosswalk(crosswalk_path=invalid_path)


def test_nssts_appendix_a_defines_fourteen_reachable_areas() -> None:
    crosswalk = load_defense_crosswalk()
    payload = yaml.safe_load(DEFAULT_CROSSWALK_PATH.read_text(encoding="utf-8"))
    areas = {area["id"] for area in payload["target_taxonomies"]["nssts_cet14"]}

    assert len(areas) == 14
    mapped = {
        row["target"]
        for cet_id in crosswalk.mappings
        for row in crosswalk.mapping_details(cet_id, "nssts_cet14")
    }
    assert mapped == areas, "every NSSTS area should be reachable from the canonical taxonomy"


def test_nssts_drops_renewable_energy_from_the_national_security_list() -> None:
    """The 2026 list has no renewable area, unlike DOD-CTA-14-2022."""

    crosswalk = load_defense_crosswalk()

    assert crosswalk.targets_for("renewable_energy_generation_and_storage", "nssts_cet14") == []
    assert crosswalk.targets_for("renewable_energy_generation_and_storage", "dod_cta14") == [
        "renewable_energy_generation_and_storage"
    ]
    assert crosswalk.mission_needs_for("renewable_energy_generation_and_storage") == {}


def test_appendix_b_alignment_matches_the_published_table() -> None:
    crosswalk = load_defense_crosswalk()

    # Biotechnology carries three marks in Appendix B and no battlefield marks.
    assert crosswalk.mission_needs_for("biotechnologies") == {
        "border_security": "current",
        "biological_weapons_defense": "current",
        "transformative_emerging_technology": "current",
    }
    # Quantum is the only row whose marks are parenthesised, except its solid
    # transformative-ET mark.
    assert crosswalk.mission_needs_for("quantum_information_science") == {
        "space_air_long_range_strike": "horizon",
        "undersea": "horizon",
        "nuclear_deterrence_and_missile_defense": "horizon",
        "cyber_defense": "horizon",
        "transformative_emerging_technology": "current",
    }


def test_mission_profile_requires_a_direct_mapping_by_default() -> None:
    crosswalk = load_defense_crosswalk()

    # Only a partial subset of financial technologies reaches NSSTS, so the area
    # inherits no mission profile unless partial mappings are opted in.
    assert crosswalk.targets_for("financial_technologies", "nssts_cet14") == [
        "information_management_and_cybersecurity"
    ]
    assert crosswalk.mission_needs_for("financial_technologies") == {}
    widened = crosswalk.mission_needs_for("financial_technologies", strengths=("direct", "partial"))
    assert widened["cyber_defense"] == "current"


def test_unknown_mission_need_fails_validation(tmp_path: Path) -> None:
    payload = yaml.safe_load(DEFAULT_CROSSWALK_PATH.read_text(encoding="utf-8"))
    payload["target_taxonomies"]["nssts_cet14"][0]["mission_alignment"] = {"not_a_need": "current"}
    invalid_path = tmp_path / "bad_need_crosswalk.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown mission need"):
        load_defense_crosswalk(crosswalk_path=invalid_path)


def test_invalid_alignment_level_fails_validation(tmp_path: Path) -> None:
    payload = yaml.safe_load(DEFAULT_CROSSWALK_PATH.read_text(encoding="utf-8"))
    payload["target_taxonomies"]["nssts_cet14"][0]["mission_alignment"] = {"undersea": "maybe"}
    invalid_path = tmp_path / "bad_level_crosswalk.yaml"
    invalid_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid alignment level"):
        load_defense_crosswalk(crosswalk_path=invalid_path)
