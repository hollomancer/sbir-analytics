from pathlib import Path

import pytest


# Import the modules under test; if they are not available skip the tests gracefully.
pytest.importorskip("pandas")
PatentAssignmentTransformer = pytest.importorskip(
    "src.transformers.patent_transformer", reason="transformer module missing"
).PatentAssignmentTransformer
USPTOExtractor = pytest.importorskip(
    "src.extractors.uspto_extractor", reason="extractor module missing"
).USPTOExtractor
# Import Pydantic model for assertions
models_module = pytest.importorskip("src.models.uspto_models", reason="uspto models missing")
PatentAssignment = getattr(models_module, "PatentAssignment", None)
PatentDocument = getattr(models_module, "PatentDocument", None)
PatentAssignee = getattr(models_module, "PatentAssignee", None)


def write_csv(tmp_path: Path, filename: str, rows: dict):
    """
    Helper to write a small CSV to tmp_path with provided rows (list of dicts).
    Returns Path to file.
    """
    import csv

    out = tmp_path / filename
    if not rows:
        out.write_text("")  # create empty file
        return out
    # ensure deterministic header order
    headers = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return out


def sample_raw_row(grant_num="GRANT123", assignee_name="Acme Corporation"):
    """
    Build a representative raw row dict used by the transformer/extractor mapping.
    Keys chosen to match heuristics in the transformer/extractor.
    """
    return {
        "rf_id": "RF001",
        "file_id": "F-100",
        "grant_doc_num": grant_num,
        "application_number": "APP-2023-001",
        "publication_number": "PUB-2023-001",
        "grant_date": "2023-08-01",
        "filing_date": "2022-01-10",
        "title": "Novel widget technology",
        "abstract": "An invention about widgets.",
        "assignee_name": assignee_name,
        "assignee_street": "123 Main St",
        "assignee_city": "Springfield",
        "assignee_state": "IL",
        "assignee_postal": "62704",
        "assignee_country": "USA",
        "assignor_name": "John Smith",
        "execution_date": "2023-07-15",
        "conveyance_text": "Assignment of all rights, work-for-hire",
        "recorded_date": "2023-07-20",
    }


def test_transform_row_basic(tmp_path):
    """
    Verify transform_row produces a PatentAssignment model with normalized fields and parsed dates.
    """
    # Create a simple SBIR grant -> company link index for matching
    sbir_index = {"GRANT123": "company-uei-1"}
    transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

    raw = sample_raw_row()
    result = transformer.transform_row(raw)

    # If model is available, assert types and values; otherwise ensure dict result structure
    if PatentAssignment is None:
        assert isinstance(result, dict)
        assert result.get("rf_id") == "RF001"
        assert "_error" not in result
        return

    assert isinstance(result, PatentAssignment)
    # Check normalized identifier and linking metadata
    assert result.rf_id == "RF001"
    assert result.document is not None
    if isinstance(result.document, PatentDocument):
        assert result.document.grant_number == "GRANT123"
        # date fields parsed
        assert result.document.grant_date is not None
    # assignee normalized name and address fields
    if isinstance(result.assignee, PatentAssignee):
        assert result.assignee.name is not None
        assert result.assignee.city == "Springfield"
        assert result.assignee.postal_code == "62704"
    # conveyance type inference and employer flag
    if result.conveyance:
        # conveyance_type may be enum; check presence
        assert getattr(result.conveyance, "conveyance_type", None) is not None
        assert result.conveyance.employer_assign in (True, False, None)
    # SBIR link metadata
    assert "linked_sbir_company" in result.metadata
    linked = result.metadata["linked_sbir_company"]
    assert linked["company_id"] == "company-uei-1"
    assert linked["match_score"] >= 0.0


def test_transform_chunk_and_iterable():
    """
    Verify transform_chunk yields PatentAssignment objects for multiple rows.
    """
    rows = [sample_raw_row(grant_num=f"GRANT{i}", assignee_name=f"Acme {i}") for i in range(3)]
    # seed SBIR index such that only the second matches via exact grant
    sbir_map = {"GRANT1": "company-1"}
    transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_map)

    out = list(transformer.transform_chunk(rows))
    # Expect same number of outputs as inputs
    assert len(out) == len(rows)
    # At least one should have metadata linking to company-1
    linked = [
        o for o in out if isinstance(o, PatentAssignment) and "linked_sbir_company" in o.metadata
    ]
    assert len(linked) >= 1
    if linked:
        assert linked[0].metadata["linked_sbir_company"]["company_id"] == "company-1"


def test_extractor_csv_stream_and_assignments(tmp_path):
    """
    Create a small CSV file and ensure USPTOExtractor streams rows and transforms into PatentAssignment.
    """
    rows = [sample_raw_row(grant_num="GR-1"), sample_raw_row(grant_num="GR-2")]
    csv_path = write_csv(tmp_path, "assignment_test.csv", rows)
    # place file in a directory and construct extractor for that dir
    extract_dir = tmp_path
    ex = USPTOExtractor(extract_dir)
    # discover files
    found = ex.discover_files()
    assert any(p.name == "assignment_test.csv" for p in found)

    # stream rows
    streamed = list(ex.stream_rows(csv_path, chunk_size=1))
    assert len(streamed) == 2
    # stream assignments (should yield PatentAssignment instances or dicts)
    assigned = list(ex.stream_assignments(csv_path, chunk_size=1))
    assert len(assigned) == 2
    # If Pydantic model present, assert types
    if PatentAssignment is not None:
        assert all(isinstance(a, PatentAssignment) for a in assigned)


def test_address_parsing_variants():
    """
    Validate the address parsing heuristics cover common variants.
    """
    from src.transformers.patent_transformer import PatentAssignmentTransformer

    t = PatentAssignmentTransformer()
    # Common comma-separated
    addr = "123 Main St, Springfield, IL 62704, USA"
    street, city, state, postal, country = t._parse_address(addr)
    assert street and "Main" in street
    assert city == "Springfield"
    assert state == "IL"
    assert postal == "62704"
    assert country == "USA"

    # Single-line with state and zip
    addr2 = "456 Elm Road Suite 5 NY 10001"
    st2, c2, s2, p2, co2 = t._parse_address(addr2)
    # expect zipcode extracted
    assert p2 == "10001"
    # state detected as two-letter if present
    assert s2 in (None, "NY")

    # Missing parts
    minimal = "Global Widgets"
    st3, c3, s3, p3, co3 = t._parse_address(minimal)
    assert st3 is not None  # it will put the string into street
    assert c3 is None or isinstance(c3, str)


if __name__ == "__main__":
    pytest.main()
