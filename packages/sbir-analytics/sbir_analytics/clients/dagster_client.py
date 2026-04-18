"""Dagster client for asset operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dagster import AssetKey, DagsterEventType, DagsterInstance, Definitions, materialize
from dagster._core.definitions.asset_selection import AssetSelection
from dagster._core.event_api import EventRecordsFilter
from loguru import logger

from sbir_etl.config.schemas import PipelineConfig


@dataclass
class AssetStatus:
    """Asset materialization status."""

    asset_key: str
    status: str  # "success", "failed", "running", "not_started"
    last_run: datetime | None = None
    duration: float | None = None  # seconds
    records_processed: int | None = None


@dataclass
class RunResult:
    """Result of a Dagster run."""

    run_id: str
    status: str
    started_at: datetime
    asset_key: str | None = None


class DagsterClient:
    """Dagster client for asset status queries and materialization triggering."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._defs: Definitions | None = None
        self._instance: DagsterInstance | None = None

    @property
    def defs(self) -> Definitions:
        """Get or load Dagster definitions."""
        if self._defs is None:
            try:
                from sbir_analytics.definitions import defs

                self._defs = defs
            except Exception as e:
                logger.warning(f"Failed to load Dagster definitions: {e}")
                from dagster import Definitions

                self._defs = Definitions()
        return self._defs

    @property
    def instance(self) -> DagsterInstance:
        """Get or create Dagster instance."""
        if self._instance is None:
            try:
                self._instance = DagsterInstance.get()
            except Exception:
                logger.warning("Using ephemeral Dagster instance (no persistent storage)")
                self._instance = DagsterInstance.ephemeral()
        return self._instance

    def list_assets(self) -> list[dict[str, Any]]:
        """List all assets with metadata."""
        assets_info: list[Any] = []
        if self.defs.assets is None:
            return assets_info
        for asset in self.defs.assets:
            if hasattr(asset, "key"):
                asset_key = str(asset.key)
            else:
                continue
            group_name = getattr(asset, "group_name", None) or ""
            description = getattr(asset, "description", None) or ""
            is_source = getattr(asset, "is_source", False)
            assets_info.append(
                {
                    "key": asset_key,
                    "group": group_name,
                    "description": description,
                    "is_source": is_source,
                }
            )
        return assets_info

    def get_asset_status(self, asset_key: str) -> AssetStatus:
        """Get status of a specific asset."""
        try:
            key = AssetKey.from_user_string(asset_key) if isinstance(asset_key, str) else asset_key
            materializations = self.instance.get_event_records(
                EventRecordsFilter(
                    event_type=DagsterEventType.ASSET_MATERIALIZATION,
                    asset_key=key,
                ),
                limit=1,
            )

            if materializations:
                latest = materializations[0]
                event = latest.dagster_event if hasattr(latest, "dagster_event") else None  # type: ignore[attr-defined]
                metadata = (
                    event.dagster_event.metadata
                    if event and hasattr(event, "dagster_event") and event.dagster_event
                    else {}
                )

                return AssetStatus(
                    asset_key=asset_key,
                    status="success",
                    last_run=datetime.fromtimestamp(latest.timestamp),
                    duration=metadata.get("duration") if "duration" in metadata else None,
                    records_processed=(
                        int(metadata["records_processed"].value)
                        if "records_processed" in metadata
                        else None
                    ),
                )
            else:
                return AssetStatus(
                    asset_key=asset_key,
                    status="not_started",
                )

        except Exception as e:
            logger.error(f"Failed to get asset status for {asset_key}: {e}")
            return AssetStatus(
                asset_key=asset_key,
                status="unknown",
            )

    def trigger_materialization(
        self,
        asset_keys: list[str] | None = None,
        asset_groups: list[str] | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Trigger materialization of assets.

        Raises:
            ValueError: If both asset_keys and asset_groups are None
        """
        if asset_keys is None and asset_groups is None:
            raise ValueError("Must specify either asset_keys or asset_groups")

        try:
            if asset_keys:
                selection: Any = AssetSelection.keys(
                    *[AssetKey.from_user_string(k) for k in asset_keys]
                )
            elif asset_groups:
                selection = AssetSelection.groups(*asset_groups)
            else:
                selection = AssetSelection.all()

            if self.defs.assets:
                result = materialize(
                    assets=list(self.defs.assets),  # type: ignore[arg-type]
                    selection=selection,
                    instance=self.instance,
                    **kwargs,
                )
            else:
                result = materialize(
                    [],
                    instance=self.instance,
                    **kwargs,
                )

            return RunResult(
                run_id=str(result.run_id) if hasattr(result, "run_id") else "unknown",
                status="success" if result.success else "failed",
                started_at=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Failed to trigger materialization: {e}")
            raise

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        """Get status of a specific run."""
        try:
            run = self.instance.get_run_by_id(run_id)
            if run is None:
                return {"status": "not_found", "run_id": run_id}

            status_value = (
                run.status.value
                if hasattr(run, "status") and hasattr(run.status, "value")
                else "unknown"
            )
            start_time = (
                run.run_start_time.isoformat()
                if hasattr(run, "run_start_time") and run.run_start_time
                else None
            )
            end_time = (
                run.run_end_time.isoformat()
                if hasattr(run, "run_end_time") and run.run_end_time
                else None
            )
            return {
                "run_id": run_id,
                "status": status_value,
                "start_time": start_time,
                "end_time": end_time,
            }

        except Exception as e:
            logger.error(f"Failed to get run status for {run_id}: {e}")
            return {"status": "error", "run_id": run_id, "error": str(e)}

    def list_recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return metadata for recent Dagster runs."""
        try:
            runs = self.instance.get_runs(limit=limit)
        except Exception as exc:
            logger.error(f"Failed to list Dagster runs: {exc}")
            return []

        results: list[dict[str, Any]] = []
        for run in runs:
            start_time = (
                run.run_start_time.isoformat()
                if hasattr(run, "run_start_time") and run.run_start_time
                else None
            )
            end_time = (
                run.run_end_time.isoformat()
                if hasattr(run, "run_end_time") and run.run_end_time
                else None
            )
            results.append(
                {
                    "run_id": run.run_id,
                    "status": run.status.value if hasattr(run, "status") else "unknown",
                    "job_name": getattr(run, "pipeline_name", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )
        return results
