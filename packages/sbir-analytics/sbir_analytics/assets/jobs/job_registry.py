"""Utilities for defining Dagster asset jobs consistently."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dagster import (
    AssetsDefinition,
    AssetSelection,
    ExecutorDefinition,
    JobDefinition,
    define_asset_job,
)
from dagster._core.definitions.unresolved_asset_job_definition import (
    UnresolvedAssetJobDefinition,
)


@dataclass(frozen=True)
class JobSpec:
    """Declarative description of an asset job."""

    name: str
    description: str
    asset_keys: Sequence[str] | None = None
    asset_groups: Sequence[str] | None = None
    assets: Sequence[AssetsDefinition] | None = None


def build_job_from_spec(
    spec: JobSpec, executor: ExecutorDefinition | None = None
) -> JobDefinition | UnresolvedAssetJobDefinition:
    """Create a Dagster job from a JobSpec, optionally with a custom executor."""

    selection: Any | None = None
    if spec.assets:
        selection = AssetSelection.keys(*(asset.key for asset in spec.assets))
    elif spec.asset_keys:
        selection = AssetSelection.keys(*spec.asset_keys)
    elif spec.asset_groups:
        selection = AssetSelection.groups(*spec.asset_groups)

    if selection is None:
        raise ValueError(
            f"Job '{spec.name}' must define asset_keys, asset_groups, or assets for selection"
        )

    return define_asset_job(
        name=spec.name,
        selection=selection,
        description=spec.description,
        executor_def=executor,
    )
