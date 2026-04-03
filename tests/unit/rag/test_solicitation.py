"""Tests for Solicitation model and SolicitationExtractor."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from sbir_etl.models.solicitation import Solicitation
from sbir_etl.extractors.solicitation import SolicitationExtractor


class TestSolicitationModel:
    """Tests for the Solicitation Pydantic model."""

    def test_required_fields(self):
        s = Solicitation(
            topic_code="AF231-001",
            solicitation_number="SBIR-2023.1",
            title="Counter-UAS Detection",
        )
        assert s.topic_code == "AF231-001"
        assert s.solicitation_number == "SBIR-2023.1"
        assert s.title == "Counter-UAS Detection"

    def test_optional_fields_default_none(self):
        s = Solicitation(
            topic_code="T1",
            solicitation_number="S1",
            title="Test",
        )
        assert s.description is None
        assert s.agency is None
        assert s.branch is None
        assert s.program is None
        assert s.open_date is None
        assert s.close_date is None
        assert s.year is None

    def test_full_model(self):
        s = Solicitation(
            topic_code="AF231-001",
            solicitation_number="SBIR-2023.1",
            title="Counter-UAS Detection",
            description="Develop passive RF sensing for low-observable UAS.",
            agency="DOD",
            branch="Air Force",
            program="SBIR",
            open_date=date(2023, 1, 15),
            close_date=date(2023, 2, 22),
            year=2023,
        )
        assert s.description is not None
        assert s.agency == "DOD"
        assert s.year == 2023

    def test_program_normalization(self):
        s = Solicitation(
            topic_code="T1",
            solicitation_number="S1",
            title="Test",
            program="sbir",
        )
        assert s.program == "SBIR"

    def test_whitespace_stripping(self):
        s = Solicitation(
            topic_code="  AF231-001  ",
            solicitation_number="  SBIR-2023.1  ",
            title="  Test Title  ",
        )
        assert s.topic_code == "AF231-001"
        assert s.title == "Test Title"

    def test_date_serialization(self):
        s = Solicitation(
            topic_code="T1",
            solicitation_number="S1",
            title="Test",
            open_date=date(2023, 1, 15),
        )
        data = s.model_dump()
        assert data["open_date"] == "2023-01-15"

    def test_missing_required_raises(self):
        with pytest.raises(Exception):
            Solicitation(topic_code="T1")  # Missing solicitation_number and title


class TestSolicitationExtractor:
    """Tests for the SolicitationExtractor."""

    def test_extract_empty_response(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        extractor = SolicitationExtractor(http_client=mock_client)
        result = extractor.extract_topics()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0
        assert "topic_code" in result.columns

    def test_extract_normalizes_fields(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "topicCode": "AF231-001",
                "solicitationNumber": "SBIR-2023.1",
                "topicTitle": "Counter-UAS Detection",
                "topicDescription": "Develop passive RF sensing...",
                "agency": "DOD",
                "branch": "Air Force",
                "program": "SBIR",
                "openDate": "2023-01-15",
                "closeDate": "2023-02-22",
                "solicitationYear": 2023,
            }
        ]
        mock_client.get.return_value = mock_response

        extractor = SolicitationExtractor(http_client=mock_client)
        result = extractor.extract_topics()

        assert len(result) == 1
        assert result.iloc[0]["topic_code"] == "AF231-001"
        assert result.iloc[0]["solicitation_number"] == "SBIR-2023.1"
        assert result.iloc[0]["title"] == "Counter-UAS Detection"
        assert result.iloc[0]["description"] == "Develop passive RF sensing..."
        assert result.iloc[0]["agency"] == "DOD"

    def test_extract_snake_case_fields(self):
        """Handles snake_case API response keys."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "topic_code": "N231-001",
                "solicitation_number": "SBIR-2023.2",
                "title": "Submarine Comms",
                "description": "Improve submarine communications.",
                "agency": "DOD",
                "program": "SBIR",
                "year": 2023,
            }
        ]
        mock_client.get.return_value = mock_response

        extractor = SolicitationExtractor(http_client=mock_client)
        result = extractor.extract_topics()

        assert result.iloc[0]["topic_code"] == "N231-001"
        assert result.iloc[0]["year"] == 2023

    def test_deduplicate_topics(self):
        extractor = SolicitationExtractor()
        df = pd.DataFrame(
            [
                {"topic_code": "T1", "solicitation_number": "S1", "title": "First"},
                {"topic_code": "T1", "solicitation_number": "S1", "title": "Duplicate"},
                {"topic_code": "T2", "solicitation_number": "S1", "title": "Different"},
            ]
        )

        result = extractor.deduplicate_topics(df)
        assert len(result) == 2
        assert result.iloc[0]["title"] == "First"  # Keeps first

    def test_deduplicate_empty(self):
        extractor = SolicitationExtractor()
        result = extractor.deduplicate_topics(pd.DataFrame())
        assert result.empty

    def test_pagination(self):
        """Extractor paginates until empty batch."""
        mock_client = MagicMock()

        responses = [
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value=[
                        {"topicCode": f"T{i}", "topicTitle": f"Topic {i}"} for i in range(100)
                    ]
                ),
            ),
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value=[
                        {"topicCode": f"T{i}", "topicTitle": f"Topic {i}"} for i in range(100, 150)
                    ]
                ),
            ),
            MagicMock(status_code=200, json=MagicMock(return_value=[])),
        ]
        mock_client.get.side_effect = responses

        extractor = SolicitationExtractor(http_client=mock_client)
        result = extractor.extract_topics(page_size=100)

        assert len(result) == 150
