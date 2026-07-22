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
    }
    assert set(crosswalk.mappings) == canonical_ids


def test_representative_direct_and_partial_mappings() -> None:
    crosswalk = load_defense_crosswalk()

    assert crosswalk.targets_for("hypersonics", "dod_cta14") == ["hypersonics"]
    assert crosswalk.targets_for("hypersonics", "dod_sc8") == ["kinetic_capabilities"]
    assert crosswalk.targets_for("advanced_nuclear_energy_systems", "dod_cta14") == []
    renewable = crosswalk.mapping_details(
        "renewable_energy_generation_and_storage", "dod_sc8"
    )
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
