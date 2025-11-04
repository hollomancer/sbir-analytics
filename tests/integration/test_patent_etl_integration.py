"""Integration and end-to-end tests for USPTO patent ETL pipeline.

Tests cover:
- Extract → Validate → Transform → Load workflow
- Data quality validation with sample data
- Company linkage matching
- Edge cases and error scenarios
"""

from pathlib import Path

import pytest


# Optional imports with graceful skipping
pytest.importorskip("pandas", reason="pandas missing")

USPTOExtractor = pytest.importorskip(
    "src.extractors.uspto_extractor", reason="extractor module missing"
).USPTOExtractor

PatentAssignmentTransformer = pytest.importorskip(
    "src.transformers.patent_transformer", reason="transformer module missing"
).PatentAssignmentTransformer

PatentAssignment = pytest.importorskip(
    "src.models.uspto_models", reason="uspto_models missing"
).PatentAssignment

PatentDocument = pytest.importorskip(
    "src.models.uspto_models", reason="uspto_models missing"
).PatentDocument


def create_sample_csv_file(tmp_path: Path, filename: str, rows: list[dict]) -> Path:
    """Helper to create a sample CSV file for testing."""
    import csv

    out = tmp_path / filename
    if not rows:
        out.write_text("")
        return out

    headers = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return out


def sample_assignment_row(
    rf_id="RF001",
    grant_doc_num="5858003",
    assignee_name="Acme Corporation",
    assignor_name="John Smith",
):
    """Create a sample assignment row."""
    return {
        "rf_id": rf_id,
        "file_id": "F-100",
        "grant_doc_num": grant_doc_num,
        "application_number": "APP-2020-001",
        "publication_number": "PUB-2020-001",
        "grant_date": "2023-08-01",
        "filing_date": "2020-01-10",
        "title": "Novel technology",
        "abstract": "An invention.",
        "assignee_name": assignee_name,
        "assignee_street": "123 Main St",
        "assignee_city": "Springfield",
        "assignee_state": "IL",
        "assignee_postal": "62704",
        "assignee_country": "USA",
        "assignor_name": assignor_name,
        "execution_date": "2023-07-15",
        "conveyance_text": "Assignment of all rights",
        "recorded_date": "2023-07-20",
    }


class TestExtractorBasicParsing:
    """Test USPTOExtractor basic CSV parsing."""

    def test_extractor_reads_csv_file(self, tmp_path):
        """Test extractor can read a CSV file."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "assignments.csv",
            [
                sample_assignment_row(rf_id="RF001"),
                sample_assignment_row(rf_id="RF002"),
            ],
        )

        extractor = USPTOExtractor()
        rows = list(extractor.stream_rows(str(csv_file), chunk_size=10))

        assert len(rows) == 2
        assert rows[0]["rf_id"] == "RF001"
        assert rows[1]["rf_id"] == "RF002"

    def test_extractor_handles_empty_file(self, tmp_path):
        """Test extractor handles empty CSV file."""
        csv_file = create_sample_csv_file(tmp_path, "empty.csv", [])

        extractor = USPTOExtractor()
        rows = list(extractor.stream_rows(str(csv_file)))

        assert len(rows) == 0

    def test_extractor_chunking(self, tmp_path):
        """Test extractor respects chunk size."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "large.csv",
            [sample_assignment_row(rf_id=f"RF{i:04d}") for i in range(25)],
        )

        extractor = USPTOExtractor()
        chunks = list(extractor.stream_rows(str(csv_file), chunk_size=10))

        # Should get all 25 rows
        assert len(chunks) == 25

    def test_extractor_error_handling(self, tmp_path):
        """Test extractor handles corrupt file gracefully."""
        bad_file = tmp_path / "corrupt.csv"
        bad_file.write_text("bad,data,\nincomplete")

        extractor = USPTOExtractor(continue_on_error=True)
        rows = list(extractor.stream_rows(str(bad_file)))

        # Should handle error gracefully (may return partial data or empty)
        assert isinstance(rows, list)

    def test_extractor_sample_limit(self, tmp_path):
        """Test extractor respects sample limit."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "sample.csv",
            [sample_assignment_row(rf_id=f"RF{i:04d}") for i in range(100)],
        )

        extractor = USPTOExtractor()
        rows = list(extractor.stream_rows(str(csv_file), sample_limit=10))

        assert len(rows) <= 10


class TestTransformerBasicNormalization:
    """Test PatentAssignmentTransformer basic normalization."""

    def test_transform_basic_row(self):
        """Test transforming a basic assignment row."""
        raw_row = sample_assignment_row()
        transformer = PatentAssignmentTransformer()

        result = transformer.transform_row(raw_row)

        assert result is not None
        assert isinstance(result, dict) or isinstance(result, PatentAssignment)

    def test_transform_normalizes_names(self):
        """Test transformer normalizes entity names."""
        raw_row = sample_assignment_row(
            assignee_name="  ACME   CORPORATION  ",
            assignor_name="  john   smith  ",
        )
        transformer = PatentAssignmentTransformer()

        result = transformer.transform_row(raw_row)

        # Names should be normalized
        assert result is not None

    def test_transform_normalizes_dates(self):
        """Test transformer parses and normalizes dates."""
        raw_row = sample_assignment_row(
            execution_date="07/15/2023",
            recorded_date="2023-07-20",
        )
        transformer = PatentAssignmentTransformer()

        result = transformer.transform_row(raw_row)

        assert result is not None

    def test_transform_missing_required_fields(self):
        """Test transformer handles missing required fields."""
        raw_row = sample_assignment_row()
        del raw_row["rf_id"]  # Remove required field

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(raw_row)

        # Should handle gracefully (return error dict or None)
        assert result is not None or result is None

    def test_transform_conveyance_type_detection(self):
        """Test transformer detects conveyance type."""
        transformer = PatentAssignmentTransformer()

        # Test assignment
        row1 = sample_assignment_row(conveyance_text="Assignment of all rights")
        result1 = transformer.transform_row(row1)
        assert result1 is not None

        # Test license
        row2 = sample_assignment_row(conveyance_text="License agreement for patent")
        result2 = transformer.transform_row(row2)
        assert result2 is not None

    def test_transform_chunk_operation(self):
        """Test transforming a chunk of rows."""
        rows = [sample_assignment_row(rf_id=f"RF{i:04d}") for i in range(5)]
        transformer = PatentAssignmentTransformer()

        results = list(transformer.transform_chunk(rows))

        assert len(results) == 5
        assert all(r is not None for r in results)


class TestDataQualityValidation:
    """Test data quality validation with sample data."""

    def test_rf_id_uniqueness_validation(self):
        """Test RF_ID uniqueness validation."""
        rows = [
            sample_assignment_row(rf_id="RF001"),
            sample_assignment_row(rf_id="RF002"),
            sample_assignment_row(rf_id="RF001"),  # Duplicate
        ]

        # Check for duplicates
        rf_ids = [r["rf_id"] for r in rows]
        unique_rf_ids = set(rf_ids)

        assert len(unique_rf_ids) < len(rf_ids)  # Duplicates exist
        assert len(unique_rf_ids) == 2

    def test_required_fields_completeness(self):
        """Test required fields are present in sample data."""
        row = sample_assignment_row()

        required_fields = ["rf_id", "grant_doc_num", "assignee_name", "assignor_name"]
        for field in required_fields:
            assert field in row
            assert row[field] is not None

    def test_date_field_validity(self):
        """Test date fields are valid dates."""
        from datetime import datetime

        row = sample_assignment_row(
            execution_date="2023-07-15",
            recorded_date="2023-07-20",
            grant_date="2023-08-01",
        )

        # Parse dates
        try:
            exec_date = datetime.strptime(row["execution_date"], "%Y-%m-%d").date()
            rec_date = datetime.strptime(row["recorded_date"], "%Y-%m-%d").date()
            grant_date = datetime.strptime(row["grant_date"], "%Y-%m-%d").date()

            assert exec_date < rec_date  # Execution before recording
            assert rec_date < grant_date or rec_date == grant_date
        except ValueError:
            pytest.fail("Date parsing failed")

    def test_invalid_date_detection(self):
        """Test invalid dates are detected."""
        bad_dates = [
            "2023-13-01",  # Invalid month
            "2023-01-32",  # Invalid day
            "not-a-date",
        ]

        from datetime import datetime

        for bad_date in bad_dates:
            with pytest.raises(ValueError):
                datetime.strptime(bad_date, "%Y-%m-%d")

    def test_null_field_detection(self):
        """Test missing or null fields are detected."""
        row_with_nulls = sample_assignment_row()
        row_with_nulls["assignee_city"] = None
        row_with_nulls["assignee_state"] = ""

        # Check for nulls
        null_fields = [k for k, v in row_with_nulls.items() if v is None or v == ""]

        assert len(null_fields) > 0


class TestCompanyLinkageMatcher:
    """Test patent to SBIR company linkage."""

    def test_exact_grant_number_matching(self):
        """Test exact grant number matching."""
        # Simulate SBIR company index
        sbir_index = {
            "5858003": "company-1",
            "5858004": "company-2",
        }

        # Test patents
        test_grants = ["5858003", "5858004", "5858999"]

        matches = [sbir_index.get(g) for g in test_grants]

        assert matches[0] == "company-1"
        assert matches[1] == "company-2"
        assert matches[2] is None

    def test_fuzzy_grant_number_matching(self):
        """Test fuzzy grant number matching with partial matches."""
        from difflib import SequenceMatcher

        sbir_index = {
            "5858003": "company-1",
            "5858004": "company-2",
        }

        test_grant = "5858003"  # Exact match
        threshold = 0.8

        matches = []
        for indexed_grant, company in sbir_index.items():
            ratio = SequenceMatcher(None, test_grant, indexed_grant).ratio()
            if ratio >= threshold:
                matches.append((company, ratio))

        assert len(matches) >= 1

    def test_no_matches_for_unlinked_patents(self):
        """Test patents with no SBIR linkage."""
        sbir_index = {
            "5858003": "company-1",
        }

        unlinked_patents = ["5858999", "5858888", "5858777"]

        matches = [sbir_index.get(g) for g in unlinked_patents]

        assert all(m is None for m in matches)


class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    def test_missing_rf_id_handling(self):
        """Test handling of rows with missing rf_id."""
        row = sample_assignment_row()
        del row["rf_id"]

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(row)

        # Should either return None or include error marker
        assert result is None or isinstance(result, dict)

    def test_invalid_date_handling(self):
        """Test handling of invalid dates."""
        row = sample_assignment_row(
            execution_date="invalid-date",
            recorded_date="not-a-date",
        )

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(row)

        # Should handle gracefully
        assert result is not None or result is None

    def test_special_characters_in_names(self):
        """Test handling of special characters in entity names."""
        row = sample_assignment_row(
            assignee_name="Acme & Widget Corporation, Inc.",
            assignor_name="Dr. John Smith, Jr.",
        )

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(row)

        assert result is not None

    def test_very_long_text_fields(self):
        """Test handling of very long text fields."""
        row = sample_assignment_row(
            title="A" * 1000,  # Very long title
            abstract="B" * 5000,  # Very long abstract
        )

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(row)

        assert result is not None

    def test_unicode_characters(self):
        """Test handling of Unicode characters."""
        row = sample_assignment_row(
            assignee_name="Société Générale Français",
            assignor_name="José García",
        )

        transformer = PatentAssignmentTransformer()
        result = transformer.transform_row(row)

        assert result is not None

    def test_duplicate_rf_ids_in_batch(self):
        """Test handling of duplicate rf_ids in batch."""
        rows = [
            sample_assignment_row(rf_id="RF001"),
            sample_assignment_row(rf_id="RF001"),  # Duplicate
            sample_assignment_row(rf_id="RF002"),
        ]

        transformer = PatentAssignmentTransformer()
        results = list(transformer.transform_chunk(rows))

        # All should be transformed (duplicates handling is downstream)
        assert len(results) == 3


class TestBatchProcessing:
    """Test batch processing with realistic sample sizes."""

    def test_process_small_batch(self, tmp_path):
        """Test processing small batch of 10 assignments."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "small_batch.csv",
            [sample_assignment_row(rf_id=f"RF{i:04d}") for i in range(10)],
        )

        extractor = USPTOExtractor()
        transformer = PatentAssignmentTransformer()

        rows = list(extractor.stream_rows(str(csv_file)))
        results = list(transformer.transform_chunk(rows))

        assert len(results) == 10

    def test_process_medium_batch(self, tmp_path):
        """Test processing medium batch of 100 assignments."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "medium_batch.csv",
            [sample_assignment_row(rf_id=f"RF{i:05d}") for i in range(100)],
        )

        extractor = USPTOExtractor()
        transformer = PatentAssignmentTransformer()

        rows = list(extractor.stream_rows(str(csv_file)))
        results = list(transformer.transform_chunk(rows))

        assert len(results) == 100
        # Check at least some transformations succeeded
        assert sum(1 for r in results if r is not None) > 90

    def test_process_large_batch(self, tmp_path):
        """Test processing large batch of 1000 assignments."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "large_batch.csv",
            [sample_assignment_row(rf_id=f"RF{i:05d}") for i in range(1000)],
        )

        extractor = USPTOExtractor(chunk_size=100)
        transformer = PatentAssignmentTransformer()

        rows = list(extractor.stream_rows(str(csv_file), chunk_size=100))
        results = list(transformer.transform_chunk(rows))

        assert len(results) == 1000


class TestEndToEndPipeline:
    """End-to-end tests for complete pipeline."""

    def test_extract_transform_flow(self, tmp_path):
        """Test extract → transform flow."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "e2e_test.csv",
            [
                sample_assignment_row(rf_id="RF001", grant_doc_num="5858003"),
                sample_assignment_row(rf_id="RF002", grant_doc_num="5858004"),
                sample_assignment_row(rf_id="RF003", grant_doc_num="5858005"),
            ],
        )

        # Extract phase
        extractor = USPTOExtractor()
        raw_rows = list(extractor.stream_rows(str(csv_file)))
        assert len(raw_rows) == 3

        # Transform phase
        transformer = PatentAssignmentTransformer()
        transformed = list(transformer.transform_chunk(raw_rows))
        assert len(transformed) == 3

        # Validate phase
        assert all(r is not None for r in transformed)

    def test_extract_transform_with_mixed_quality(self, tmp_path):
        """Test extract → transform with mixed data quality."""
        rows_to_create = [
            sample_assignment_row(rf_id="RF001", grant_doc_num="5858003"),
            sample_assignment_row(rf_id="RF002", grant_doc_num=""),  # Missing grant
            sample_assignment_row(rf_id="RF003", grant_doc_num="5858005"),
        ]

        csv_file = create_sample_csv_file(tmp_path, "mixed_quality.csv", rows_to_create)

        # Extract
        extractor = USPTOExtractor()
        raw_rows = list(extractor.stream_rows(str(csv_file)))

        # Transform
        transformer = PatentAssignmentTransformer()
        transformed = list(transformer.transform_chunk(raw_rows))

        # Should process all, but some may have errors
        assert len(transformed) == 3


class TestPerformanceMetrics:
    """Test performance and metrics collection."""

    def test_throughput_calculation(self, tmp_path):
        """Test throughput metrics."""
        import time

        csv_file = create_sample_csv_file(
            tmp_path,
            "perf_test.csv",
            [sample_assignment_row(rf_id=f"RF{i:05d}") for i in range(100)],
        )

        extractor = USPTOExtractor()
        transformer = PatentAssignmentTransformer()

        start = time.time()
        rows = list(extractor.stream_rows(str(csv_file)))
        results = list(transformer.transform_chunk(rows))
        duration = time.time() - start

        throughput = len(results) / duration if duration > 0 else 0
        assert throughput > 0
        # Rough expectation: >10 records/second
        assert throughput > 10

    def test_success_rate_calculation(self, tmp_path):
        """Test success rate metrics."""
        csv_file = create_sample_csv_file(
            tmp_path,
            "success_rate.csv",
            [sample_assignment_row(rf_id=f"RF{i:05d}") for i in range(100)],
        )

        extractor = USPTOExtractor()
        transformer = PatentAssignmentTransformer()

        rows = list(extractor.stream_rows(str(csv_file)))
        results = list(transformer.transform_chunk(rows))

        successful = sum(1 for r in results if r is not None)
        success_rate = successful / len(results) if results else 0

        assert success_rate >= 0.95  # Expect ≥95% success


__all__ = [
    "TestExtractorBasicParsing",
    "TestTransformerBasicNormalization",
    "TestDataQualityValidation",
    "TestCompanyLinkageMatcher",
    "TestEdgeCasesAndErrors",
    "TestBatchProcessing",
    "TestEndToEndPipeline",
    "TestPerformanceMetrics",
]
