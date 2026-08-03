import json
from datetime import date

import pandas as pd

from scripts.data.build_nsf_sbir_direct_awards import build_release


def test_build_release_writes_phase_one_products(tmp_path) -> None:
    awards = tmp_path / "award_data.csv"
    pd.DataFrame(
        [
            {
                "Company": "Example Materials Inc",
                "Award Title": "SBIR Phase II: Materials",
                "Agency": "NSF",
                "Phase": "Phase II",
                "Program": "SBIR",
                "Agency Tracking Number": "0512345",
                "Contract": "620588",
                "Proposal Award Date": "2024-06-01",
                "Contract End Date": "2027-05-31",
                "Award Year": "2024",
                "Award Amount": "900000",
                "UEI": "ABCDEFGHIJKL",
                "Abstract": "Resilient material production",
            }
        ]
    ).to_csv(awards, index=False)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "0620588.json").write_text(
        json.dumps(
            {
                "response": {
                    "award": [
                        {
                            "id": "0620588",
                            "title": "SBIR Phase II: Materials",
                            "abstractText": "Resilient material production",
                            "fundProgramName": "Small Business Innovation Research",
                            "startDate": "06/01/2024",
                            "expDate": "05/31/2027",
                            "estimatedTotalAmt": "900000",
                            "fundsObligatedAmt": "900000",
                            "awardeeName": "Example Materials Inc",
                            "ueiNumber": "ABCDEFGHIJKL",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    manifest = build_release(
        awards_path=awards,
        output_dir=output,
        analysis_date=date(2026, 8, 3),
        direct_sources=[snapshot],
    )
    assert manifest["analysis_date"] == "2026-08-03"
    assert manifest["products"]["direct_awards"]["row_count"] == 1
    assert (output / "nsf_sbir_awards_direct.parquet").is_file()
    assert (output / "nsf_sbir_award_reconciliation.parquet").is_file()
    quality = json.loads((output / "nsf_defense_lineage_quality.json").read_text())
    assert quality["quality_gates_passed"] is True
    assert quality["awardee_status_counts"] == {"current": 1}
