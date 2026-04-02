"""Tests for document preparation functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sbir_rag.document_prep import prepare_award_document, prepare_solicitation_document


class TestPrepareAwardDocument:
    """Test Award → LightRAG document conversion."""

    def _make_row(self, **overrides) -> pd.Series:
        defaults = {
            "award_id": "AWD-001",
            "award_title": "Quantum Sensing for Navigation",
            "abstract": "This project develops quantum sensors for GPS-denied environments.",
            "agency": "DOD",
            "phase": "Phase I",
            "keywords": "quantum, navigation, sensing",
            "award_year": 2024,
            "company_name": "QuantumTech Inc",
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_full_document(self):
        """All fields present produces header + body."""
        row = self._make_row()
        doc = prepare_award_document(row)

        assert "Agency: DOD" in doc["content"]
        assert "Phase: Phase I" in doc["content"]
        assert "Keywords: quantum, navigation, sensing" in doc["content"]
        assert "Quantum Sensing for Navigation" in doc["content"]
        assert "quantum sensors for GPS-denied" in doc["content"]

    def test_metadata_fields(self):
        """Metadata dict contains expected keys."""
        row = self._make_row()
        doc = prepare_award_document(row)

        assert doc["metadata"]["award_id"] == "AWD-001"
        assert doc["metadata"]["agency"] == "DOD"
        assert doc["metadata"]["phase"] == "Phase I"
        assert doc["metadata"]["award_year"] == 2024
        assert doc["metadata"]["company_name"] == "QuantumTech Inc"
        assert doc["metadata"]["document_type"] == "award"

    def test_missing_optional_fields(self):
        """Missing keywords/phase still produces valid document."""
        row = self._make_row(keywords=np.nan, phase=np.nan)
        doc = prepare_award_document(row)

        assert "Keywords" not in doc["content"]
        assert "Phase" not in doc["content"]
        assert "Agency: DOD" in doc["content"]
        assert "Quantum Sensing" in doc["content"]

    def test_missing_abstract(self):
        """Document with only title and no abstract."""
        row = self._make_row(abstract=np.nan)
        doc = prepare_award_document(row)

        assert "Quantum Sensing for Navigation" in doc["content"]
        assert doc["content"].strip()  # Not empty

    def test_empty_body_fields(self):
        """Both title and abstract missing produces header-only content."""
        row = self._make_row(award_title=np.nan, abstract=np.nan)
        doc = prepare_award_document(row)

        # Should still have header
        assert "Agency: DOD" in doc["content"]

    def test_nan_metadata_becomes_none(self):
        """NaN values in metadata fields become None."""
        row = self._make_row(agency=np.nan, phase=np.nan, award_year=np.nan)
        doc = prepare_award_document(row)

        assert doc["metadata"]["agency"] is None
        assert doc["metadata"]["phase"] is None
        assert doc["metadata"]["award_year"] is None

    def test_whitespace_only_fields_ignored(self):
        """Fields with only whitespace are treated as missing."""
        row = self._make_row(keywords="   ", award_title="  ")
        doc = prepare_award_document(row)

        assert "Keywords" not in doc["content"]


class TestPrepareSolicitationDocument:
    """Test solicitation → LightRAG document conversion."""

    def _make_row(self, **overrides) -> pd.Series:
        defaults = {
            "topic_code": "AF231-001",
            "solicitation_number": "SBIR-2023.1",
            "title": "Counter-UAS Detection in Urban Environments",
            "description": "Develop passive RF sensing for low-observable UAS in cluttered urban RF environments.",
            "agency": "DOD",
            "program": "SBIR",
            "year": 2023,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_full_document(self):
        """All fields present produces header + body."""
        row = self._make_row()
        doc = prepare_solicitation_document(row)

        assert "Solicitation Topic: AF231-001" in doc["content"]
        assert "Agency: DOD" in doc["content"]
        assert "Program: SBIR" in doc["content"]
        assert "Counter-UAS Detection" in doc["content"]
        assert "passive RF sensing" in doc["content"]

    def test_metadata_fields(self):
        """Metadata dict contains expected keys."""
        row = self._make_row()
        doc = prepare_solicitation_document(row)

        assert doc["metadata"]["topic_code"] == "AF231-001"
        assert doc["metadata"]["solicitation_number"] == "SBIR-2023.1"
        assert doc["metadata"]["agency"] == "DOD"
        assert doc["metadata"]["year"] == 2023
        assert doc["metadata"]["document_type"] == "solicitation"

    def test_missing_description(self):
        """Document with only title, no description."""
        row = self._make_row(description=np.nan)
        doc = prepare_solicitation_document(row)

        assert "Counter-UAS Detection" in doc["content"]
        assert doc["content"].strip()

    def test_nan_metadata_becomes_none(self):
        """NaN solicitation_number becomes None in metadata."""
        row = self._make_row(solicitation_number=np.nan, agency=np.nan)
        doc = prepare_solicitation_document(row)

        assert doc["metadata"]["solicitation_number"] is None
        assert doc["metadata"]["agency"] is None
