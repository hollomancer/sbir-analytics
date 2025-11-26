import json
from datetime import date

import pandas as pd
from dagster import asset

from src.models.ma_models import MAEvent


@asset(deps=["raw_sbir_awards", "loaded_patent_assignments"])
def company_mergers_and_acquisitions(
    raw_sbir_awards: pd.DataFrame, loaded_patent_assignments: pd.DataFrame
):
    """Detects potential mergers and acquisitions based on patent assignment data and stores them."""

    # 1.3: Join SBIR companies with patent assignor data
    merged_data = pd.merge(
        raw_sbir_awards,
        loaded_patent_assignments,
        left_on="company_name",
        right_on="assignor_name",
        how="inner",
    )

    # 1.4: Detect changes in patent assignees over time
    potential_ma_events = []
    for company_name, group in merged_data.groupby("company_name"):
        unique_assignees = group["assignee_name"].unique()
        if len(unique_assignees) > 1:
            for assignee in unique_assignees:
                if assignee != company_name:
                    # 1.5: Create M&A candidate events
                    potential_ma_events.append(
                        MAEvent(
                            acquiring_company_name=assignee,
                            acquired_company_name=company_name,
                            acquisition_date=date.today(),  # Placeholder date
                            source="uspto_patent_assignments",
                            confidence_score=0.7,  # Placeholder score
                        )
                    )

    # 1.10.1: Store the unenriched M&A candidate events
    output_path = "reports/ma_events.json"
    with open(output_path, "w") as f:
        f.write(
            json.dumps([event.model_dump() for event in potential_ma_events], indent=4, default=str)
        )

    return potential_ma_events
