"""Utilities for defining Dagster asset jobs consistently."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from dagster import AssetSelection, AssetsDefinition, JobDefinition, build_assets_job, define_asset_job


@dataclass(frozen=True)
class JobSpec:
    """Declarative description of an asset job."""

    name: str
    description: str
    asset_keys: Sequence[str] | None = None
    asset_groups: Sequence[str] | None = None
    assets: Sequence[AssetsDefinition] | None = None


def build_job_from_spec(spec: JobSpec) -> JobDefinition:
    """Create a Dagster job from a JobSpec."""

    if spec.assets:
        selection = AssetSelection.keys(*(asset.key for asset in spec.assets))
        return build_assets_job(
            name=spec.name,
            assets=list(spec.assets),
            selection=selection,
            description=spec.description,
        )

    selection = None
    if spec.asset_keys:
        selection = AssetSelection.keys(*spec.asset_keys)
    elif spec.asset_groups:
        selection = AssetSelection.groups(*spec.asset_groups)

    if selection is None:
        raise ValueError(
            f"Job '{spec.name}' must define asset_keys, asset_groups, or assets for selection"
        )

    return define_asset_job(name=spec.name, selection=selection, description=spec.description)


def build_placeholder_job(name: str, description: str) -> JobDefinition:
    """Create a placeholder job when assets cannot be imported."""

    return build_assets_job(
        name=f"{name}_placeholder",
        assets=[],
        description=description,
    )
