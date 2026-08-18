"""Validated, versioned defense taxonomy crosswalks for CET reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config.yaml_io import read_yaml_mapping


DEFAULT_CROSSWALK_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "cet" / "defense_crosswalk.yaml"
)
DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "config" / "cet" / "taxonomy.yaml"
TARGET_KEYS = ("dod_cta14", "dod_sc8", "nssts_cet14")
MISSION_ALIGNMENT_TARGET = "nssts_cet14"
MISSION_ALIGNMENT_LEVELS = ("current", "horizon")


@dataclass(frozen=True)
class DefenseTaxonomyCrosswalk:
    """Validated mapping from canonical CET IDs to versioned defense tags."""

    version: str
    source_taxonomy: str
    target_versions: dict[str, str]
    mappings: dict[str, dict[str, tuple[dict[str, str], ...]]]
    source_path: Path
    mission_needs: tuple[dict[str, str], ...] = ()
    mission_alignment: dict[str, dict[str, str]] = field(default_factory=dict)

    def targets_for(self, cet_id: str, target_taxonomy: str) -> list[str]:
        """Return ordered target IDs for a CET and target taxonomy."""

        if target_taxonomy not in TARGET_KEYS:
            raise ValueError(f"unsupported target taxonomy: {target_taxonomy}")
        entry = self.mappings.get(cet_id)
        if entry is None:
            raise KeyError(f"CET ID is absent from defense crosswalk: {cet_id}")
        return [mapping["target"] for mapping in entry[target_taxonomy]]

    def mapping_details(self, cet_id: str, target_taxonomy: str) -> list[dict[str, str]]:
        """Return target, strength, and rationale records for audit output."""

        if target_taxonomy not in TARGET_KEYS:
            raise ValueError(f"unsupported target taxonomy: {target_taxonomy}")
        entry = self.mappings.get(cet_id)
        if entry is None:
            raise KeyError(f"CET ID is absent from defense crosswalk: {cet_id}")
        return [dict(mapping) for mapping in entry[target_taxonomy]]

    def mission_needs_for(
        self, cet_id: str, strengths: tuple[str, ...] = ("direct",)
    ) -> dict[str, str]:
        """Return NSSTS priority national security needs a CET aligns with.

        Alignment is published by NSSTS Appendix B against its own 14 CET areas,
        not against this repository's canonical 21-area taxonomy. A canonical CET
        therefore inherits an NSSTS area's mission profile only through a mapping
        whose strength is listed in ``strengths``. The default is ``direct`` only:
        a ``partial`` or ``enabling`` mapping means the two areas are not
        equivalent, so carrying the full mission profile across would overstate
        what the source table supports.

        Where two inherited areas disagree, ``current`` wins over ``horizon``.
        """

        entry = self.mappings.get(cet_id)
        if entry is None:
            raise KeyError(f"CET ID is absent from defense crosswalk: {cet_id}")
        needs: dict[str, str] = {}
        for mapping in entry[MISSION_ALIGNMENT_TARGET]:
            if mapping["strength"] not in strengths:
                continue
            for need_id, level in self.mission_alignment.get(mapping["target"], {}).items():
                if needs.get(need_id) != "current":
                    needs[need_id] = level
        return needs


def _canonical_ids(taxonomy_path: Path) -> tuple[str, set[str]]:
    payload = read_yaml_mapping(taxonomy_path, description="CET taxonomy")
    version = str(payload.get("version") or "")
    areas = payload.get("cet_areas")
    if not version or not isinstance(areas, list):
        raise ValueError("canonical taxonomy must define version and cet_areas")
    ids = {str(area.get("cet_id")) for area in areas if isinstance(area, dict)}
    if len(ids) != len(areas) or "None" in ids:
        raise ValueError("canonical taxonomy CET IDs must be present and unique")
    return version, ids


def load_defense_crosswalk(
    crosswalk_path: Path | None = None,
    taxonomy_path: Path | None = None,
) -> DefenseTaxonomyCrosswalk:
    """Load and validate complete coverage and target referential integrity."""

    source_path = crosswalk_path or DEFAULT_CROSSWALK_PATH
    canonical_path = taxonomy_path or DEFAULT_TAXONOMY_PATH
    payload = read_yaml_mapping(source_path, description="defense crosswalk")
    canonical_version, canonical_ids = _canonical_ids(canonical_path)

    version = str(payload.get("version") or "")
    source_taxonomy = str(payload.get("source_taxonomy") or "")
    if not version:
        raise ValueError("defense crosswalk must define a version")
    if source_taxonomy != canonical_version:
        raise ValueError(
            f"crosswalk source taxonomy {source_taxonomy!r} does not match "
            f"canonical version {canonical_version!r}"
        )

    strengths = set((payload.get("mapping_strengths") or {}).keys())
    if not strengths:
        raise ValueError("defense crosswalk must define mapping strengths")

    target_taxonomies = payload.get("target_taxonomies")
    sources = payload.get("authoritative_sources")
    if not isinstance(target_taxonomies, dict) or not isinstance(sources, dict):
        raise ValueError("defense crosswalk must define targets and authoritative sources")

    target_ids: dict[str, set[str]] = {}
    target_versions: dict[str, str] = {}
    for key in TARGET_KEYS:
        definitions = target_taxonomies.get(key)
        source = sources.get(key)
        if not isinstance(definitions, list) or not isinstance(source, dict):
            raise ValueError(f"missing target definitions or source for {key}")
        ids = [str(item.get("id")) for item in definitions if isinstance(item, dict)]
        if len(ids) != len(definitions) or len(ids) != len(set(ids)) or "None" in ids:
            raise ValueError(f"target IDs for {key} must be present and unique")
        target_ids[key] = set(ids)
        target_versions[key] = str(source.get("version") or "")
        if not target_versions[key]:
            raise ValueError(f"authoritative source for {key} must define version")

    raw_needs = payload.get("nssts_mission_needs")
    if not isinstance(raw_needs, list) or not raw_needs:
        raise ValueError("defense crosswalk must define nssts_mission_needs")
    mission_needs: list[dict[str, str]] = []
    need_ids: set[str] = set()
    for need in raw_needs:
        if not isinstance(need, dict):
            raise ValueError("each nssts_mission_needs entry must be a mapping")
        need_id = str(need.get("id") or "")
        name = str(need.get("name") or "")
        element = str(need.get("strategy_element") or "")
        if not need_id or not name or not element:
            raise ValueError("mission need requires id, name, and strategy_element")
        if need_id in need_ids:
            raise ValueError(f"duplicate mission need ID: {need_id}")
        need_ids.add(need_id)
        mission_needs.append({"id": need_id, "name": name, "strategy_element": element})

    mission_alignment: dict[str, dict[str, str]] = {}
    for item in target_taxonomies[MISSION_ALIGNMENT_TARGET]:
        area_id = str(item.get("id"))
        alignment = item.get("mission_alignment") or {}
        if not isinstance(alignment, dict):
            raise ValueError(f"mission_alignment for {area_id} must be a mapping")
        for need_id, level in alignment.items():
            if need_id not in need_ids:
                raise ValueError(f"unknown mission need {need_id!r} for {area_id}")
            if level not in MISSION_ALIGNMENT_LEVELS:
                raise ValueError(f"invalid alignment level {level!r} for {area_id}.{need_id}")
        mission_alignment[area_id] = {str(k): str(v) for k, v in alignment.items()}

    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list):
        raise ValueError("defense crosswalk mappings must be a list")
    normalized: dict[str, dict[str, tuple[dict[str, str], ...]]] = {}
    for entry in raw_mappings:
        if not isinstance(entry, dict) or not entry.get("cet_id"):
            raise ValueError("each defense crosswalk entry must define cet_id")
        cet_id = str(entry["cet_id"])
        if cet_id in normalized:
            raise ValueError(f"duplicate defense crosswalk CET ID: {cet_id}")
        target_mappings: dict[str, tuple[dict[str, str], ...]] = {}
        for key in TARGET_KEYS:
            rows = entry.get(key)
            if not isinstance(rows, list):
                raise ValueError(f"{cet_id}.{key} must be a list")
            seen: set[str] = set()
            clean_rows: list[dict[str, str]] = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"{cet_id}.{key} mapping must be a mapping")
                target = str(row.get("target") or "")
                strength = str(row.get("strength") or "")
                rationale = str(row.get("rationale") or "").strip()
                if target not in target_ids[key]:
                    raise ValueError(f"unknown {key} target {target!r} for {cet_id}")
                if target in seen:
                    raise ValueError(f"duplicate {key} target {target!r} for {cet_id}")
                if strength not in strengths or not rationale:
                    raise ValueError(f"{cet_id}.{key}.{target} needs valid strength and rationale")
                seen.add(target)
                clean_rows.append({"target": target, "strength": strength, "rationale": rationale})
            target_mappings[key] = tuple(clean_rows)
        normalized[cet_id] = target_mappings

    mapped_ids = set(normalized)
    if mapped_ids != canonical_ids:
        raise ValueError(
            "defense crosswalk must cover canonical CET IDs exactly; "
            f"missing={sorted(canonical_ids - mapped_ids)}, extra={sorted(mapped_ids - canonical_ids)}"
        )

    return DefenseTaxonomyCrosswalk(
        version=version,
        source_taxonomy=source_taxonomy,
        target_versions=target_versions,
        mappings=normalized,
        source_path=source_path,
        mission_needs=tuple(mission_needs),
        mission_alignment=mission_alignment,
    )


__all__ = [
    "DEFAULT_CROSSWALK_PATH",
    "DEFAULT_TAXONOMY_PATH",
    "MISSION_ALIGNMENT_LEVELS",
    "MISSION_ALIGNMENT_TARGET",
    "TARGET_KEYS",
    "DefenseTaxonomyCrosswalk",
    "load_defense_crosswalk",
]
