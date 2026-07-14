"""Snapshot safety, normalization, and persistence tests."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sbir_analytics.api.snapshots import (
    AnalysisKind,
    FileSnapshotRepository,
    SnapshotMetadata,
    SnapshotStoreError,
    snapshot_from_result,
    snapshot_from_tool_result,
    write_snapshot,
)
from sbir_analytics.assets.follow_on_multiplier import FollowOnMultiplierResult
from sbir_analytics.tools.base import DataSourceRef, ToolMetadata, ToolResult


def _tool_result() -> ToolResult:
    metadata = ToolMetadata(
        tool_name="compute_transition_rate",
        tool_version="1.0.0",
        execution_start=datetime(2026, 1, 1, tzinfo=UTC),
        execution_end=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        data_sources=[
            DataSourceRef(
                name="SBIR.gov Awards",
                url="https://sbir.gov/api",
                version="2026-Q1",
                record_count=2,
                access_method="bulk_download",
            )
        ],
        warnings=["conservative benchmark"],
        record_count=2,
    )
    return ToolResult(
        data={
            "results": pd.DataFrame(
                {
                    "company": ["A", "B"],
                    "rate": [0.5, np.nan],
                    "updated_at": [pd.Timestamp("2026-01-01", tz="UTC"), pd.NaT],
                    "note": ["ok", pd.NA],
                }
            ),
            "summary": {"companies": np.int64(2)},
        },
        metadata=metadata,
    )


def test_tool_result_snapshot_round_trip(tmp_path: Path) -> None:
    snapshot = snapshot_from_tool_result(
        AnalysisKind.TRANSITION_RATE,
        "2026-Q1",
        _tool_result(),
        pipeline_run_id="run-123",
        as_of=datetime(2026, 4, 1, tzinfo=UTC),
    )
    path = write_snapshot(tmp_path, snapshot)
    loaded = FileSnapshotRepository(tmp_path).get(AnalysisKind.TRANSITION_RATE, "2026-Q1")

    assert path.name == "2026-Q1.json"
    assert loaded.metadata.pipeline_run_id == "run-123"
    assert loaded.metadata.data_sources[0].record_count == 2
    assert loaded.result["results"][1]["rate"] is None
    assert loaded.result["results"][1]["updated_at"] is None
    assert loaded.result["results"][1]["note"] is None
    assert loaded.result["summary"]["companies"] == 2

    with pytest.raises(SnapshotStoreError, match="already exists"):
        write_snapshot(tmp_path, snapshot)


def test_repository_rejects_invalid_period_and_symlink_escape(tmp_path: Path) -> None:
    repository = FileSnapshotRepository(tmp_path)
    with pytest.raises(SnapshotStoreError, match="Invalid snapshot period"):
        repository.get(AnalysisKind.TRANSITION_RATE, "../../outside")

    outside = tmp_path.parent / "outside-snapshot.json"
    outside.write_text("{}", encoding="utf-8")
    directory = tmp_path / AnalysisKind.TRANSITION_RATE.value
    directory.mkdir(parents=True)
    (directory / "2026-Q1.json").symlink_to(outside)
    try:
        with pytest.raises(SnapshotStoreError, match="not safe"):
            repository.get(AnalysisKind.TRANSITION_RATE, "2026-Q1")
    finally:
        outside.unlink(missing_ok=True)


def test_follow_on_multiplier_result_can_be_exported(tmp_path: Path) -> None:
    result = FollowOnMultiplierResult(
        company=pd.DataFrame({"company_id": ["A"], "follow_on_multiplier": [4.0]}),
        agency=pd.DataFrame(),
        cohort=pd.DataFrame(),
        fiscal_year=pd.DataFrame(),
        quality=pd.DataFrame({"matched_record_count": [1]}),
    )
    snapshot = snapshot_from_result(
        AnalysisKind.FOLLOW_ON_MULTIPLIER,
        "2026-Q1",
        result,
        metadata=SnapshotMetadata(
            tool_name="calculate_follow_on_multipliers",
            tool_version="1.0.0",
            pipeline_run_id="run-456",
        ),
    )
    write_snapshot(tmp_path, snapshot)
    loaded = FileSnapshotRepository(tmp_path).get(AnalysisKind.FOLLOW_ON_MULTIPLIER, "2026-Q1")
    assert loaded.result["company"][0]["follow_on_multiplier"] == 4.0
    assert loaded.result["quality"][0]["matched_record_count"] == 1


def test_openapi_remains_read_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from sbir_analytics.api.app import create_app

    app = create_app(api_token="secret", snapshot_repository=FileSnapshotRepository(tmp_path))
    with TestClient(app) as client:
        operations = client.get("/openapi.json").json()["paths"].values()
    assert all(
        not ({"post", "put", "patch", "delete"} & endpoints.keys()) for endpoints in operations
    )


def test_tech_census_snapshot_is_servable_end_to_end(tmp_path: Path) -> None:
    """A real ComputeTechCensusTool run, written as a snapshot, is servable, listable, and comparable."""

    from fastapi.testclient import TestClient

    from sbir_analytics.api.app import create_app
    from sbir_analytics.tools.tech_census import ComputeTechCensusTool

    def _award(title: str, year: int, amount: float) -> dict:
        return {
            "title": title,
            "abstract": "",
            "company": "Acme",
            "agency": "Department of Defense",
            "phase": "Phase II",
            "award_year": year,
            "award_amount": amount,
        }

    tool = ComputeTechCensusTool()
    result_2025 = tool.run(
        awards_df=pd.DataFrame(
            [
                _award("Drone battery hybridizer", 2025, 1_000_000.0),
                _award("Drone gimbal payload system", 2025, 500_000.0),
            ]
        ),
        area_id="drone_manufacturing",
    )
    result_2026 = tool.run(
        awards_df=pd.DataFrame([_award("Drone propulsion system", 2026, 750_000.0)]),
        area_id="drone_manufacturing",
    )

    write_snapshot(
        tmp_path,
        snapshot_from_tool_result(
            AnalysisKind.TECH_CENSUS_DRONE_MANUFACTURING, "2025", result_2025
        ),
    )
    write_snapshot(
        tmp_path,
        snapshot_from_tool_result(
            AnalysisKind.TECH_CENSUS_DRONE_MANUFACTURING, "2026", result_2026
        ),
    )

    app = create_app(api_token="secret", snapshot_repository=FileSnapshotRepository(tmp_path))
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret"}

        get_response = client.get(
            "/v1/snapshots/tech_census_drone_manufacturing/2025", headers=headers
        )
        assert get_response.status_code == 200
        assert get_response.json()["result"]["summary"]["grand_total"] == {
            "n": 2,
            "usd": 1_500_000.0,
        }

        list_response = client.get(
            "/v1/snapshots",
            params={"analysis_kind": "tech_census_drone_manufacturing"},
            headers=headers,
        )
        assert list_response.status_code == 200
        periods = {entry["period"] for entry in list_response.json()["data"]}
        assert periods == {"2025", "2026"}

        compare_response = client.get(
            "/v1/snapshots/tech_census_drone_manufacturing/2025/compare/2026", headers=headers
        )
        assert compare_response.status_code == 200
        # compare_snapshots only diffs top-level int/float result keys; "results"
        # (list) and "summary" (dict) are both structured, so nothing qualifies.
        assert compare_response.json()["numeric_deltas"] == {}
