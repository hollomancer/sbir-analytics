"""Empty-frame materializations must overwrite their parquet, not skip the write.

The assets previously wrote the parquet only when the frame was non-empty while
writing `checks.json` unconditionally. A run that legitimately produced no rows
therefore left the *previous* parquet on disk next to a fresh checks file
reporting `total_rows: 0` — a stale table that reads as a current zero-row
result, with nothing downstream able to tell the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from dagster import build_asset_context


pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _contracts(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


PHASE_III_ROW = {
    "contract_id": "C_III_1",
    "research": "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE III ACTION",
    "action_date": "2020-05-01",
    "vendor_uei": "UEI0000000001",
    "vendor_name": "Acme Corp",
    "awarding_agency_name": "DOD",
}

PHASE_II_ROW = {
    "contract_id": "C_II_1",
    "research": "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION",
    "action_date": "2020-05-01",
    "vendor_uei": "UEI0000000002",
    "vendor_name": "Beta Labs",
    "awarding_agency_name": "DOD",
}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    contracts_path = tmp_path / "contracts.parquet"
    output_path = tmp_path / "phase_iii.parquet"
    monkeypatch.setenv("SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH", str(contracts_path))
    monkeypatch.setenv("SBIR_ETL__PHASE_TRANSITION__PHASE_III_OUTPUT_PATH", str(output_path))
    return contracts_path, output_path


def test_empty_result_overwrites_previous_parquet(paths) -> None:
    from sbir_analytics.assets.phase_transition.phase_iii import validated_phase_iii_contracts

    contracts_path, output_path = paths

    # First run: real Phase III rows land on disk.
    _contracts([PHASE_III_ROW]).to_parquet(contracts_path, index=False)
    validated_phase_iii_contracts(build_asset_context())
    assert len(pd.read_parquet(output_path)) == 1

    # Second run: the source no longer contains any Phase III row.
    _contracts([PHASE_II_ROW]).to_parquet(contracts_path, index=False)
    validated_phase_iii_contracts(build_asset_context())

    checks = json.loads(Path(str(output_path.with_suffix(".checks.json"))).read_text())
    assert checks["total_rows"] == 0
    # The parquet must agree with checks.json rather than retaining the old row.
    assert len(pd.read_parquet(output_path)) == 0


def test_empty_result_writes_parquet_when_none_existed(paths) -> None:
    from sbir_analytics.assets.phase_transition.phase_iii import validated_phase_iii_contracts

    contracts_path, output_path = paths
    _contracts([PHASE_II_ROW]).to_parquet(contracts_path, index=False)

    validated_phase_iii_contracts(build_asset_context())

    assert output_path.exists()
    assert len(pd.read_parquet(output_path)) == 0
