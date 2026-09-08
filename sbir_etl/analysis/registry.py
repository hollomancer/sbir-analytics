"""Load the analysis profile registry.

Epistemic tier: pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sbir_etl.analysis.contracts import AnalysisKind, ProfileEntry
from sbir_etl.config.yaml_io import read_yaml_mapping


EPISTEMIC_TIER = "pipelines"


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "analysis_profiles" / "registry.yaml"


@dataclass(frozen=True)
class AnalysisRegistry:
    profiles: tuple[ProfileEntry, ...]

    def get(self, profile_id: str) -> ProfileEntry:
        for entry in self.profiles:
            if entry.profile_id == profile_id:
                return entry
        known = ", ".join(entry.profile_id for entry in self.profiles) or "(none)"
        raise KeyError(f"unknown analysis profile {profile_id!r}; known: {known}")

    def ids_for(
        self,
        kind: AnalysisKind,
        *,
        dagster_asset: bool | None = None,
    ) -> tuple[str, ...]:
        out: list[str] = []
        for entry in self.profiles:
            if entry.analysis_kind is not kind:
                continue
            if dagster_asset is not None and entry.dagster_asset is not dagster_asset:
                continue
            out.append(entry.profile_id)
        return tuple(out)


def load_registry(path: Path | None = None) -> AnalysisRegistry:
    registry_path = path or default_registry_path()
    raw = read_yaml_mapping(registry_path)
    rows = raw.get("profiles") or []
    if not isinstance(rows, list):
        raise ValueError(f"{registry_path} profiles must be a list")
    root = registry_path.resolve().parents[2]
    profiles: list[ProfileEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each profile row must be a mapping")
        config_path = Path(str(row["config_path"]))
        if not config_path.is_absolute():
            config_path = root / config_path
        profiles.append(
            ProfileEntry(
                profile_id=str(row["profile_id"]),
                analysis_kind=AnalysisKind(str(row["analysis_kind"])),
                config_path=config_path,
                taxonomy_version=str(row["taxonomy_version"]),
                methodology_version=str(row["methodology_version"]),
                dagster_asset=bool(row.get("dagster_asset", False)),
            )
        )
    return AnalysisRegistry(profiles=tuple(profiles))
