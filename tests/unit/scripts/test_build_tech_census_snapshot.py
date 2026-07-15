"""Safety tests for the tech-census snapshot publishing CLI."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "build_tech_census_snapshot.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("build_tech_census_snapshot", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_warning_blocks_zero_snapshot_publish(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    awards = tmp_path / "awards.csv"
    awards.write_text(
        "Award Title,Abstract,Company,Agency,Program,Phase,Award Year,Award Amount\n"
        "Drone Airframe,Build it,Acme,DOD,,Phase II,2025,100000\n",
        encoding="utf-8",
    )
    snapshot_dir = tmp_path / "snapshots"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "--area",
            "drone_manufacturing",
            "--period",
            "2026",
            "--awards",
            str(awards),
            "--snapshot-dir",
            str(snapshot_dir),
        ],
    )

    assert _load_script().main() == 1
    assert not list(snapshot_dir.rglob("*.json"))
    assert "no usable program values" in capsys.readouterr().err
