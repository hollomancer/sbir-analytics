import json
import sys
from pathlib import Path

from scripts.data import build_tech_census as census_cli


def test_cli_labels_console_and_summary_non_citable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    awards_csv = tmp_path / "award_data.csv"
    awards_csv.write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(census_cli, "DATA", tmp_path)
    monkeypatch.setattr(
        census_cli,
        "load_award_data_csv",
        lambda _path: [
            {
                "title": "Drone airframe prototype",
                "abstract": "We will design and fabricate the airframe.",
                "company": "Example Robotics",
                "state": "MA",
                "program": "SBIR",
                "phase": "Phase II",
                "award_year": 2025,
                "award_amount": 500_000.0,
                "agency_tracking_number": "TRACK-1",
                "contract": "CONTRACT-1",
                "source_row": 2,
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_tech_census.py",
            "--area",
            "drone_manufacturing",
            "--awards",
            str(awards_csv),
        ],
    )

    assert census_cli.main() == 0

    output = capsys.readouterr().out
    assert "Status: EXPLORATORY / NON-CITABLE" in output
    summary = json.loads(
        (tmp_path / "tech_census" / "drone_manufacturing" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["_epistemic"]["tier"] == "exploratory"
    assert summary["_epistemic"]["citable"] is False
