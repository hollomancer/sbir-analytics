import csv
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# Integration test requires pandas for CSV reading in the extractor; skip if not present.
pytest.importorskip("pandas")


def _write_sample_csv(path: Path):
    """
    Write a minimal, representative USPTO-style CSV that the extractor's
    `stream_assignments` mapping will consume and convert into a PatentAssignment.
    """
    headers = [
        "rf_id",
        "file_id",
        "grant_doc_num",
        "application_number",
        "publication_number",
        "filing_date",
        "publication_date",
        "grant_date",
        "title",
        "abstract",
        "conveyance_rf_id",
        "conveyance_type",
        "conveyance_text",
        "recorded_date",
        "assignee_rf_id",
        "assignee_name",
        "assignee_street",
        "assignee_city",
        "assignee_state",
        "assignee_postal",
        "assignee_country",
        "assignee_uei",
        "assignee_cage",
        "assignee_duns",
        "assignor_rf_id",
        "assignor_name",
        "execution_date",
        "acknowledgment_date",
    ]

    row = {
        "rf_id": "r1",
        "file_id": "f1",
        "grant_doc_num": "US-123456",
        "application_number": "APP-0001",
        "publication_number": "PUB-0001",
        "filing_date": "2020-01-15",
        "publication_date": "2021-02-20",
        "grant_date": "2021-03-10",
        "title": "Test Patent Title",
        "abstract": "This is a test abstract.",
        "conveyance_rf_id": "c1",
        "conveyance_type": "assignment",
        "conveyance_text": "Assignment of rights",
        "recorded_date": "2021-04-01",
        "assignee_rf_id": "a1",
        "assignee_name": "Acme Corp.",
        "assignee_street": "1 Test Way",
        "assignee_city": "Testville",
        "assignee_state": "CA",
        "assignee_postal": "90210",
        "assignee_country": "US",
        "assignee_uei": "UEI123",
        "assignee_cage": "CAGE1",
        "assignee_duns": "DUNS1",
        "assignor_rf_id": "as1",
        "assignor_name": "Jane Assignor",
        "execution_date": "2021-02-01",
        "acknowledgment_date": "2021-02-05",
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)


def test_stream_assignments_from_csv(tmp_path):
    """
    Integration test: write a sample CSV and run USPTOExtractor.stream_assignments
    to ensure the extractor constructs a PatentAssignment instance (not an error dict).
    """
    # Import under test
    from src.extractors.uspto_extractor import USPTOExtractor
    from src.models.uspto_models import PatentAssignment

    # Prepare sample CSV
    csv_file = tmp_path / "sample_assignment.csv"
    _write_sample_csv(csv_file)

    # Instantiate extractor pointed at the tmp directory (input_dir)
    extractor = USPTOExtractor(tmp_path, continue_on_error=False, log_every=1000)

    # Run stream_assignments against the specific file
    results = list(extractor.stream_assignments(csv_file, chunk_size=1))

    # We expect exactly one result and it should be a PatentAssignment instance
    assert len(results) == 1, "Expected a single assignment record from sample CSV"
    assignment = results[0]

    # If construction failed the extractor yields a dict with '_error'
    assert not (isinstance(assignment, dict) and "_error" in assignment), (
        "Extractor produced an error record instead of a PatentAssignment: " f"{assignment}"
    )

    assert isinstance(assignment, PatentAssignment), "Result must be a PatentAssignment instance"

    # Basic content checks
    # Assignee name should be preserved
    assert assignment.assignee is not None
    assert assignment.assignee.name == "Acme Corp."

    # Document grant number should be normalized (non-empty)
    assert assignment.document is not None
    assert assignment.document.grant_number is not None
    assert assignment.document.grant_number.replace("-", "") != ""

    # Dates should be parsed into date objects
    assert assignment.execution_date == date(2021, 2, 1)
    assert assignment.recorded_date == date(2021, 4, 1) or assignment.recorded_date is None
