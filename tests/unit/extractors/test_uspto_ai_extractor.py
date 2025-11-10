"""Tests for USPTO AI predictions extractor."""

import json
from pathlib import Path

import pytest

from src.extractors.uspto_ai_extractor import USPTOAIExtractor, _Checkpoint


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast



@pytest.fixture
def temp_input_dir(tmp_path):
    """Temporary input directory."""
    input_dir = tmp_path / "uspto_data"
    input_dir.mkdir()
    return input_dir


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


@pytest.fixture
def sample_ndjson_data():
    """Sample NDJSON data."""
    return [
        {"grant_doc_num": "US1234567B2", "score": "0.95", "category": "AI"},
        {"patent_number": "US7654321A1", "score": "0.88", "category": "ML"},
        {"grant_id": "US9876543C3", "confidence": "0.92", "category": "Quantum"},
    ]


@pytest.fixture
def sample_csv_data():
    """Sample CSV data."""
    return [
        {"grant_doc_num": "US1234567B2", "score": "0.95", "category": "AI"},
        {"grant_doc_num": "US7654321A1", "score": "0.88", "category": "ML"},
    ]


# ==================== Initialization Tests ====================


class TestUSPTOAIExtractorInitialization:
    """Tests for USPTOAIExtractor initialization."""

    def test_initialization_success(self, temp_input_dir, temp_checkpoint_dir):
        """Test successful initialization."""
        extractor = USPTOAIExtractor(
            temp_input_dir,
            checkpoint_dir=temp_checkpoint_dir,
        )

        assert extractor.input_dir == temp_input_dir
        assert extractor.checkpoint_dir == temp_checkpoint_dir
        assert extractor.continue_on_error is True
        assert extractor.log_every == 100_000
        assert extractor._seen_ids_mem == set()

    def test_initialization_custom_settings(self, temp_input_dir, temp_checkpoint_dir):
        """Test initialization with custom settings."""
        extractor = USPTOAIExtractor(
            temp_input_dir,
            checkpoint_dir=temp_checkpoint_dir,
            continue_on_error=False,
            log_every=50000,
        )

        assert extractor.continue_on_error is False
        assert extractor.log_every == 50000

    def test_initialization_creates_checkpoint_dir(self, temp_input_dir, tmp_path):
        """Test initialization creates checkpoint directory."""
        checkpoint_dir = tmp_path / "new_checkpoints"
        assert not checkpoint_dir.exists()

        USPTOAIExtractor(
            temp_input_dir,
            checkpoint_dir=checkpoint_dir,
        )

        assert checkpoint_dir.exists()

    def test_initialization_nonexistent_input_dir(self, tmp_path):
        """Test initialization fails with nonexistent input directory."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError, match="Input directory does not exist"):
            USPTOAIExtractor(nonexistent)

    def test_initialization_negative_log_every(self, temp_input_dir):
        """Test initialization handles negative log_every."""
        extractor = USPTOAIExtractor(
            temp_input_dir,
            log_every=-100,
        )

        assert extractor.log_every == 0  # max(0, -100)


# ==================== File Discovery Tests ====================


class TestFileDiscovery:
    """Tests for file discovery."""

    def test_discover_files_ndjson(self, temp_input_dir):
        """Test discovering NDJSON files."""
        (temp_input_dir / "data1.ndjson").touch()
        (temp_input_dir / "data2.jsonl").touch()
        (temp_input_dir / "other.txt").touch()

        extractor = USPTOAIExtractor(temp_input_dir)
        files = extractor.discover_files()

        assert len(files) == 2
        assert all(f.suffix in [".ndjson", ".jsonl"] for f in files)

    def test_discover_files_all_types(self, temp_input_dir):
        """Test discovering all supported file types."""
        (temp_input_dir / "data1.ndjson").touch()
        (temp_input_dir / "data2.csv").touch()
        (temp_input_dir / "data3.dta").touch()
        (temp_input_dir / "data4.parquet").touch()

        extractor = USPTOAIExtractor(temp_input_dir)
        files = extractor.discover_files()

        assert len(files) == 4

    def test_discover_files_with_globs(self, temp_input_dir):
        """Test discovering files with custom globs."""
        (temp_input_dir / "patents_2023.ndjson").touch()
        (temp_input_dir / "patents_2024.ndjson").touch()
        (temp_input_dir / "other.ndjson").touch()

        extractor = USPTOAIExtractor(temp_input_dir)
        files = extractor.discover_files(file_globs=["patents_*.ndjson"])

        assert len(files) == 2
        assert all("patents_" in f.name for f in files)

    def test_discover_files_empty_directory(self, temp_input_dir):
        """Test discovering files in empty directory."""
        extractor = USPTOAIExtractor(temp_input_dir)
        files = extractor.discover_files()

        assert len(files) == 0

    def test_discover_files_nested_directories(self, temp_input_dir):
        """Test discovering files in nested directories."""
        nested = temp_input_dir / "subdir" / "deep"
        nested.mkdir(parents=True)
        (nested / "data.ndjson").touch()

        extractor = USPTOAIExtractor(temp_input_dir)
        files = extractor.discover_files()

        assert len(files) == 1
        assert files[0].name == "data.ndjson"


# ==================== NDJSON Streaming Tests ====================


class TestNDJSONStreaming:
    """Tests for NDJSON streaming."""

    def test_stream_raw_ndjson(self, temp_input_dir, sample_ndjson_data):
        """Test streaming raw NDJSON records."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_raw(ndjson_file))

        assert len(records) == 3
        assert records[0]["grant_doc_num"] == "US1234567B2"

    def test_stream_raw_jsonl(self, temp_input_dir, sample_ndjson_data):
        """Test streaming .jsonl files."""
        jsonl_file = temp_input_dir / "data.jsonl"
        with open(jsonl_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_raw(jsonl_file))

        assert len(records) == 3

    def test_stream_raw_ndjson_malformed_line(self, temp_input_dir):
        """Test streaming handles malformed JSON lines."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            f.write('{"valid": "record"}\n')
            f.write("{invalid json}\n")
            f.write('{"another": "record"}\n')

        extractor = USPTOAIExtractor(temp_input_dir, continue_on_error=True)
        records = list(extractor.stream_raw(ndjson_file))

        # Should skip malformed line and continue
        assert len(records) == 2


# ==================== CSV Streaming Tests ====================


class TestCSVStreaming:
    """Tests for CSV streaming."""

    def test_stream_raw_csv(self, temp_input_dir, sample_csv_data):
        """Test streaming raw CSV records."""
        csv_file = temp_input_dir / "data.csv"
        with open(csv_file, "w", newline="") as f:
            import csv

            writer = csv.DictWriter(f, fieldnames=["grant_doc_num", "score", "category"])
            writer.writeheader()
            writer.writerows(sample_csv_data)

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_raw(csv_file))

        assert len(records) == 2
        assert records[0]["grant_doc_num"] == "US1234567B2"


# ==================== Normalized Streaming Tests ====================


class TestNormalizedStreaming:
    """Tests for normalized streaming."""

    def test_stream_normalized_basic(self, temp_input_dir, sample_ndjson_data):
        """Test streaming normalized records."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_normalized(ndjson_file))

        assert len(records) == 3
        assert "grant_doc_num" in records[0]
        assert "prediction" in records[0]
        assert "_meta" in records[0]
        assert records[0]["_meta"]["row_index"] == 1

    def test_stream_normalized_with_dedupe(self, temp_input_dir):
        """Test streaming with deduplication."""
        ndjson_file = temp_input_dir / "data.ndjson"
        data = [
            {"grant_doc_num": "US1234567B2", "score": "0.95"},
            {"grant_doc_num": "US1234567B2", "score": "0.88"},  # Duplicate
            {"grant_doc_num": "US7654321A1", "score": "0.92"},
        ]
        with open(ndjson_file, "w") as f:
            for record in data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_normalized(ndjson_file, dedupe=True))

        # Should only have 2 records (duplicate removed)
        assert len(records) == 2
        assert records[0]["grant_doc_num"] == "US1234567B2"
        assert records[1]["grant_doc_num"] == "US7654321A1"

    def test_stream_normalized_skip_missing_id(self, temp_input_dir):
        """Test streaming skips records with missing IDs."""
        ndjson_file = temp_input_dir / "data.ndjson"
        data = [
            {"grant_doc_num": "US1234567B2", "score": "0.95"},
            {"score": "0.88", "category": "ML"},  # No ID
            {"grant_doc_num": "US7654321A1", "score": "0.92"},
        ]
        with open(ndjson_file, "w") as f:
            for record in data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_normalized(ndjson_file, skip_missing_id=True))

        # Should skip record without ID
        assert len(records) == 2

    def test_stream_normalized_keep_missing_id(self, temp_input_dir):
        """Test streaming keeps records with missing IDs when configured."""
        ndjson_file = temp_input_dir / "data.ndjson"
        data = [
            {"grant_doc_num": "US1234567B2", "score": "0.95"},
            {"score": "0.88", "category": "ML"},  # No ID
        ]
        with open(ndjson_file, "w") as f:
            for record in data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_normalized(ndjson_file, skip_missing_id=False))

        # Should keep all records
        assert len(records) == 2
        assert records[1]["grant_doc_num"] is None


# ==================== Batch Streaming Tests ====================


class TestBatchStreaming:
    """Tests for batch streaming."""

    def test_stream_batches(self, temp_input_dir, sample_ndjson_data):
        """Test streaming records in batches."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        batches = list(extractor.stream_batches(ndjson_file, batch_size=2))

        # 3 records with batch_size=2 should give 2 batches
        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 1


# ==================== Checkpoint Tests ====================


class TestCheckpointing:
    """Tests for checkpoint functionality."""

    def test_checkpoint_dataclass(self):
        """Test _Checkpoint dataclass."""
        checkpoint = _Checkpoint(path=Path("/test/file.ndjson"), last_offset=1000)

        assert checkpoint.path == Path("/test/file.ndjson")
        assert checkpoint.last_offset == 1000

    def test_checkpoint_default_offset(self):
        """Test _Checkpoint with default offset."""
        checkpoint = _Checkpoint(path=Path("/test/file.ndjson"))

        assert checkpoint.last_offset == 0

    def test_save_and_load_checkpoint(self, temp_input_dir, temp_checkpoint_dir):
        """Test saving and loading checkpoints."""
        ndjson_file = temp_input_dir / "data.ndjson"
        ndjson_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir, checkpoint_dir=temp_checkpoint_dir)

        # Save checkpoint
        extractor._save_checkpoint(ndjson_file, last_offset=500)

        # Load checkpoint
        checkpoint = extractor._load_checkpoint(ndjson_file)

        assert checkpoint.last_offset == 500

    def test_load_checkpoint_not_exists(self, temp_input_dir, temp_checkpoint_dir):
        """Test loading nonexistent checkpoint."""
        ndjson_file = temp_input_dir / "data.ndjson"
        ndjson_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir, checkpoint_dir=temp_checkpoint_dir)
        checkpoint = extractor._load_checkpoint(ndjson_file)

        # Should return default checkpoint
        assert checkpoint.last_offset == 0


# ==================== ID Extraction Tests ====================


class TestIDExtraction:
    """Tests for grant ID extraction."""

    def test_extract_grant_id_grant_doc_num(self):
        """Test extracting ID from grant_doc_num field."""
        record = {"grant_doc_num": "US1234567B2", "score": 0.95}

        grant_id = USPTOAIExtractor._extract_grant_id(record)

        assert grant_id == "US1234567B2"

    def test_extract_grant_id_patent_number(self):
        """Test extracting ID from patent_number field."""
        record = {"patent_number": "US7654321A1", "score": 0.88}

        grant_id = USPTOAIExtractor._extract_grant_id(record)

        assert grant_id == "US7654321A1"

    def test_extract_grant_id_grant_id(self):
        """Test extracting ID from grant_id field."""
        record = {"grant_id": "US9876543C3", "score": 0.92}

        grant_id = USPTOAIExtractor._extract_grant_id(record)

        assert grant_id == "US9876543C3"

    def test_extract_grant_id_custom_candidates(self):
        """Test extracting ID with custom candidate fields."""
        record = {"custom_patent_id": "US1111111D1", "score": 0.85}

        grant_id = USPTOAIExtractor._extract_grant_id(record, id_candidates=["custom_patent_id"])

        assert grant_id == "US1111111D1"

    def test_extract_grant_id_missing(self):
        """Test extracting ID when no field matches."""
        record = {"score": 0.95, "category": "AI"}

        grant_id = USPTOAIExtractor._extract_grant_id(record)

        assert grant_id is None


# ==================== Score Field Coercion Tests ====================


class TestScoreFieldCoercion:
    """Tests for score field type coercion."""

    def test_coerce_score_fields_string_to_float(self):
        """Test coercing string score fields to float."""
        record = {"score": "0.95", "confidence": "0.88", "probability": "0.92"}

        coerced = USPTOAIExtractor._coerce_score_fields(record)

        assert coerced["score"] == 0.95
        assert coerced["confidence"] == 0.88
        assert coerced["probability"] == 0.92

    def test_coerce_score_fields_already_float(self):
        """Test coercing already-float fields."""
        record = {"score": 0.95, "confidence": 0.88}

        coerced = USPTOAIExtractor._coerce_score_fields(record)

        assert coerced["score"] == 0.95
        assert coerced["confidence"] == 0.88

    def test_coerce_score_fields_invalid_values(self):
        """Test coercing handles invalid values."""
        record = {"score": "invalid", "confidence": "N/A"}

        coerced = USPTOAIExtractor._coerce_score_fields(record)

        # Should keep original values if coercion fails
        assert coerced["score"] == "invalid"
        assert coerced["confidence"] == "N/A"

    def test_coerce_score_fields_nested_dict(self):
        """Test coercing nested score fields."""
        record = {
            "nested": {"score": "0.95"},
            "other_field": "value",
        }

        coerced = USPTOAIExtractor._coerce_score_fields(record)

        # Should handle nested structures
        assert "nested" in coerced


# ==================== Utility Methods Tests ====================


class TestUtilityMethods:
    """Tests for utility methods."""

    def test_read_first_n(self, temp_input_dir, sample_ndjson_data):
        """Test reading first N records."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = extractor.read_first_n(ndjson_file, n=2)

        assert len(records) == 2

    def test_read_first_n_more_than_available(self, temp_input_dir, sample_ndjson_data):
        """Test reading more records than available."""
        ndjson_file = temp_input_dir / "data.ndjson"
        with open(ndjson_file, "w") as f:
            for record in sample_ndjson_data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = extractor.read_first_n(ndjson_file, n=10)

        # Should return all 3 available records
        assert len(records) == 3


# ==================== Error Handling Tests ====================


class TestErrorHandling:
    """Tests for error handling."""

    def test_stream_raw_nonexistent_file(self, temp_input_dir):
        """Test streaming nonexistent file raises error."""
        nonexistent = temp_input_dir / "nonexistent.ndjson"

        extractor = USPTOAIExtractor(temp_input_dir)

        with pytest.raises(FileNotFoundError, match="File not found"):
            list(extractor.stream_raw(nonexistent))

    def test_stream_raw_unsupported_extension(self, temp_input_dir):
        """Test streaming unsupported file type raises error."""
        txt_file = temp_input_dir / "data.txt"
        txt_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir)

        with pytest.raises(ValueError, match="Unsupported file extension"):
            list(extractor.stream_raw(txt_file))

    def test_handle_error_continue_on_error_true(self, temp_input_dir, caplog):
        """Test error handling with continue_on_error=True."""
        ndjson_file = temp_input_dir / "data.ndjson"
        ndjson_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir, continue_on_error=True)

        # Should log warning but not raise
        extractor._handle_error(ndjson_file, "Test error")

        # Should have logged the error
        assert len(caplog.records) > 0

    def test_handle_error_continue_on_error_false(self, temp_input_dir):
        """Test error handling with continue_on_error=False."""
        ndjson_file = temp_input_dir / "data.ndjson"
        ndjson_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir, continue_on_error=False)

        with pytest.raises(RuntimeError, match="Test error"):
            extractor._handle_error(ndjson_file, "Test error")


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_stream_raw_empty_file(self, temp_input_dir):
        """Test streaming empty file."""
        empty_file = temp_input_dir / "empty.ndjson"
        empty_file.touch()

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_raw(empty_file))

        assert len(records) == 0

    def test_stream_normalized_all_missing_ids(self, temp_input_dir):
        """Test streaming when all records have missing IDs."""
        ndjson_file = temp_input_dir / "data.ndjson"
        data = [
            {"score": "0.95", "category": "AI"},
            {"score": "0.88", "category": "ML"},
        ]
        with open(ndjson_file, "w") as f:
            for record in data:
                f.write(json.dumps(record) + "\n")

        extractor = USPTOAIExtractor(temp_input_dir)
        records = list(extractor.stream_normalized(ndjson_file, skip_missing_id=True))

        assert len(records) == 0

    def test_checkpoint_key_generates_consistent_hash(self, temp_input_dir):
        """Test checkpoint key generation is consistent."""
        file_path = temp_input_dir / "data.ndjson"
        file_path.touch()

        extractor = USPTOAIExtractor(temp_input_dir)

        key1 = extractor._checkpoint_key(file_path)
        key2 = extractor._checkpoint_key(file_path)

        assert key1 == key2

    def test_need_progress_log(self):
        """Test progress log frequency check."""
        assert USPTOAIExtractor._need_progress_log(100000) is True
        assert USPTOAIExtractor._need_progress_log(100001) is False
        assert USPTOAIExtractor._need_progress_log(200000) is True
