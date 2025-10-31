from datetime import date

import pandas as pd

from src.assets.ma_detection import company_mergers_and_acquisitions


def test_company_mergers_and_acquisitions():
    # Mock sbir_awards dataframe
    sbir_awards_data = {
        "company_name": ["Company A", "Company B", "Company C"],
        "award_amount": [100000, 200000, 300000],
    }
    sbir_awards = pd.DataFrame(sbir_awards_data)

    # Mock uspto_patent_assignments dataframe for M&A event
    uspto_patent_assignments_data_ma = {
        "assignor_name": ["Company A", "Company A", "Company B"],
        "assignee_name": ["Company A", "Company D", "Company B"],
        "assignment_date": [date(2020, 1, 1), date(2021, 1, 1), date(2020, 1, 1)],
    }
    uspto_patent_assignments_ma = pd.DataFrame(uspto_patent_assignments_data_ma)

    # Test case with M&A event
    ma_events = company_mergers_and_acquisitions(sbir_awards, uspto_patent_assignments_ma)
    assert len(ma_events) > 0
    assert any(
        event.acquiring_company_name == "Company D" and event.acquired_company_name == "Company A"
        for event in ma_events
    )

    # Mock uspto_patent_assignments dataframe for no M&A event
    uspto_patent_assignments_data_no_ma = {
        "assignor_name": ["Company A", "Company B", "Company C"],
        "assignee_name": ["Company A", "Company B", "Company C"],
        "assignment_date": [date(2020, 1, 1), date(2021, 1, 1), date(2020, 1, 1)],
    }
    uspto_patent_assignments_no_ma = pd.DataFrame(uspto_patent_assignments_data_no_ma)

    # Test case with no M&A event
    no_ma_events = company_mergers_and_acquisitions(sbir_awards, uspto_patent_assignments_no_ma)
    assert len(no_ma_events) == 0
