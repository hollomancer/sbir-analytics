from pathlib import Path

import pandas as pd

from scripts.data.build_local_dod_research_inputs import build_local_awards


def test_local_awards_drop_exact_duplicates_and_fingerprint_id_collisions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "award_data.csv"
    base = {
        "Company": "Acme Inc",
        "Award Title": "Radar sensor",
        "Agency": "Department of Defense",
        "Branch": "Air Force",
        "Phase": "Phase II",
        "Program": "SBIR",
        "Agency Tracking Number": "TRACK-1",
        "Contract": "CONTRACT-1",
        "Proposal Award Date": "2024-01-15",
        "Contract End Date": "2025-01-15",
        "Topic Code": "SENSORS",
        "Award Year": "2024",
        "Award Amount": "100000",
        "UEI": "ABCDEFGHIJKL",
        "Duns": "123456789",
        "City": "Dayton",
        "State": "OH",
        "Zip": "45402",
        "Abstract": "A radar sensor project.",
    }
    distinct_same_id = {**base, "Award Title": "Lidar sensor", "Award Amount": "200000"}
    pd.DataFrame([base, base, distinct_same_id]).to_csv(source, index=False)

    result = build_local_awards(source, min_fy=2012, max_fy=2025)

    assert len(result) == 2
    assert result["award_id"].nunique() == 2
    assert result["award_id"].str.startswith("TRACK-1_CONTRACT-1#").all()
    assert result["source_system"].eq("SBIR.gov bulk award_data.csv").all()
