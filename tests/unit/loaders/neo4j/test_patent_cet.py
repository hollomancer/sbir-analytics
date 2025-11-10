"""Tests for Neo4j Patent-CET loader."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.exceptions import ConfigurationError
from src.loaders.neo4j.patent_cet import Neo4jConfig, Neo4jPatentCETLoader


class TestNeo4jConfig:
    """Tests for Neo4jConfig dataclass."""

    def test_config_default_values(self):
        """Test Neo4jConfig with default values."""
        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password"
        )

        assert config.uri == "bolt://localhost:7687"
        assert config.user == "neo4j"
        assert config.password == "password"
        assert config.database == "neo4j"
        assert config.max_connection_lifetime == 3600

    def test_config_custom_values(self):
        """Test Neo4jConfig with custom values."""
        config = Neo4jConfig(
            uri="bolt://custom:7687",
            user="admin",
            password="secret",
            database="custom_db",
            max_connection_lifetime=7200
        )

        assert config.uri == "bolt://custom:7687"
        assert config.user == "admin"
        assert config.password == "secret"
        assert config.database == "custom_db"
        assert config.max_connection_lifetime == 7200


class TestNeo4jPatentCETLoaderInitialization:
    """Tests for Neo4jPatentCETLoader initialization."""

    def test_initialization_with_driver(self):
        """Test initialization with pre-existing driver."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        assert loader._driver == mock_driver
        assert loader._db == "neo4j"
        assert loader._batch_size == 1000
        assert loader._auto_create_constraints is False

    def test_initialization_with_custom_database(self):
        """Test initialization with custom database."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, database="custom")

        assert loader._db == "custom"

    def test_initialization_with_custom_batch_size(self):
        """Test initialization with custom batch size."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=500)

        assert loader._batch_size == 500

    def test_initialization_without_driver_or_credentials(self):
        """Test initialization fails without driver or credentials."""
        with pytest.raises(ConfigurationError, match="Provide either a driver or uri/user/password"):
            Neo4jPatentCETLoader()

    def test_initialization_with_partial_credentials(self):
        """Test initialization fails with partial credentials."""
        with pytest.raises(ConfigurationError):
            Neo4jPatentCETLoader(uri="bolt://localhost:7687", user="neo4j")

    @patch('src.loaders.neo4j.patent_cet.GraphDatabase')
    def test_initialization_creates_driver_from_credentials(self, mock_graphdb):
        """Test initialization creates driver from uri/user/password."""
        mock_driver = Mock()
        mock_graphdb.driver.return_value = mock_driver

        loader = Neo4jPatentCETLoader(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password"
        )

        mock_graphdb.driver.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
            max_connection_lifetime=3600
        )
        assert loader._driver == mock_driver

    @patch('src.loaders.neo4j.patent_cet.GraphDatabase')
    def test_initialization_with_custom_max_connection_lifetime(self, mock_graphdb):
        """Test initialization with custom max_connection_lifetime."""
        mock_driver = Mock()
        mock_graphdb.driver.return_value = mock_driver

        loader = Neo4jPatentCETLoader(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="password",
            max_connection_lifetime=7200
        )

        mock_graphdb.driver.assert_called_once_with(
            "bolt://localhost:7687",
            auth=("neo4j", "password"),
            max_connection_lifetime=7200
        )

    def test_initialization_with_zero_batch_size(self):
        """Test initialization with zero batch size defaults to 1000."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=0)

        assert loader._batch_size == 1000

    def test_initialization_with_negative_batch_size(self):
        """Test initialization with negative batch size defaults to 1000."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=-100)

        assert loader._batch_size == 1000

    def test_initialization_with_auto_create_constraints(self):
        """Test initialization with auto_create_constraints."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver, auto_create_constraints=True)

        assert loader._auto_create_constraints is True
        # Should have called ensure_constraints
        assert mock_driver.session.called


class TestNeo4jPatentCETLoaderLifecycle:
    """Tests for loader lifecycle methods."""

    def test_close_closes_driver(self):
        """Test close method closes driver."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        loader.close()

        mock_driver.close.assert_called_once()

    def test_close_with_none_driver(self):
        """Test close handles None driver gracefully."""
        loader = Neo4jPatentCETLoader(driver=Mock())
        loader._driver = None

        # Should not raise
        loader.close()


class TestNeo4jPatentCETLoaderConstraints:
    """Tests for constraint creation methods."""

    def test_ensure_constraints_creates_both(self):
        """Test ensure_constraints creates both constraints."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)
        loader.ensure_constraints()

        # Should call execute_write twice (CETArea, Patent)
        assert mock_session.execute_write.call_count == 2

    def test_ensure_constraints_uses_if_not_exists(self):
        """Test constraints use IF NOT EXISTS."""
        mock_driver = Mock()
        mock_session = MagicMock()

        executed_queries = []
        def capture_query(fn):
            mock_tx = Mock()
            def run_side_effect(query):
                executed_queries.append(query)
                result = Mock()
                result.consume.return_value = None
                return result
            mock_tx.run.side_effect = run_side_effect
            return fn(mock_tx)

        mock_session.execute_write.side_effect = capture_query
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)
        loader.ensure_constraints()

        # Both queries should have IF NOT EXISTS
        for query in executed_queries:
            assert "IF NOT EXISTS" in query

    def test_ensure_constraints_creates_cetarea_constraint(self):
        """Test CETArea constraint is created."""
        mock_driver = Mock()
        mock_session = MagicMock()

        executed_queries = []
        def capture_query(fn):
            mock_tx = Mock()
            def run_side_effect(query):
                executed_queries.append(query)
                result = Mock()
                result.consume.return_value = None
                return result
            mock_tx.run.side_effect = run_side_effect
            return fn(mock_tx)

        mock_session.execute_write.side_effect = capture_query
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)
        loader.ensure_constraints()

        all_queries = ' '.join(executed_queries)
        assert "CETArea" in all_queries
        assert "UNIQUE" in all_queries

    def test_ensure_constraints_creates_patent_constraint(self):
        """Test Patent constraint is created."""
        mock_driver = Mock()
        mock_session = MagicMock()

        executed_queries = []
        def capture_query(fn):
            mock_tx = Mock()
            def run_side_effect(query):
                executed_queries.append(query)
                result = Mock()
                result.consume.return_value = None
                return result
            mock_tx.run.side_effect = run_side_effect
            return fn(mock_tx)

        mock_session.execute_write.side_effect = capture_query
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)
        loader.ensure_constraints()

        all_queries = ' '.join(executed_queries)
        assert "Patent" in all_queries


class TestNeo4jPatentCETLoaderUpsertCETAreas:
    """Tests for upsert_cet_areas method."""

    def test_upsert_cet_areas_empty_list(self):
        """Test upserting empty list returns 0."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        result = loader.upsert_cet_areas([])

        assert result == 0

    def test_upsert_cet_areas_filters_invalid(self):
        """Test upsert filters out invalid areas."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        areas = [
            None,
            {},
            {"name": "Missing ID"},
            {"id": ""},
        ]

        result = loader.upsert_cet_areas(areas)

        assert result == 0

    def test_upsert_cet_areas_single(self):
        """Test upserting single CET area."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        areas = [{"id": "cet1", "name": "AI", "taxonomy_version": "2025.1"}]
        result = loader.upsert_cet_areas(areas)

        assert result == 1

    def test_upsert_cet_areas_multiple(self):
        """Test upserting multiple CET areas."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        areas = [
            {"id": "cet1", "name": "AI"},
            {"id": "cet2", "name": "Biotech"},
            {"id": "cet3", "name": "Energy"},
        ]
        result = loader.upsert_cet_areas(areas)

        assert result == 3

    def test_upsert_cet_areas_with_keywords(self):
        """Test upserting CET areas with keywords."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        areas = [{"id": "cet1", "keywords": ["machine learning", "AI", "neural"]}]
        result = loader.upsert_cet_areas(areas)

        assert result == 1


class TestNeo4jPatentCETLoaderUpsertPatents:
    """Tests for upsert_patents method."""

    def test_upsert_patents_empty_list(self):
        """Test upserting empty list returns 0."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        result = loader.upsert_patents([])

        assert result == 0

    def test_upsert_patents_filters_invalid(self):
        """Test upsert filters out invalid patents."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [
            None,
            {},
            {"title": "Missing ID"},
        ]

        result = loader.upsert_patents(patents)

        assert result == 0

    def test_upsert_patents_single(self):
        """Test upserting single patent."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [{"patent_id": "US123", "title": "ML System", "assignee": "Acme"}]
        result = loader.upsert_patents(patents)

        assert result == 1

    def test_upsert_patents_accepts_id_key(self):
        """Test upsert accepts 'id' key instead of 'patent_id'."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [{"id": "US123", "title": "ML System"}]
        result = loader.upsert_patents(patents)

        assert result == 1

    def test_upsert_patents_multiple(self):
        """Test upserting multiple patents."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [
            {"patent_id": "US123", "title": "ML System"},
            {"patent_id": "US456", "title": "Sensor Tech"},
            {"patent_id": "US789", "title": "Battery Tech"},
        ]
        result = loader.upsert_patents(patents)

        assert result == 3

    def test_upsert_patents_with_application_year(self):
        """Test upserting patents with application_year."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [{"patent_id": "US123", "application_year": 2022}]
        result = loader.upsert_patents(patents)

        assert result == 1


class TestNeo4jPatentCETLoaderLinkPatentCET:
    """Tests for link_patent_cet method."""

    def test_link_patent_cet_empty_list(self):
        """Test linking empty list returns 0."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        result = loader.link_patent_cet([])

        assert result == 0

    def test_link_patent_cet_filters_invalid(self):
        """Test link filters out invalid relationships."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [
            None,
            {},
            {"patent_id": "US123"},  # Missing cet_id
            {"cet_id": "cet1"},  # Missing patent_id
        ]

        result = loader.link_patent_cet(rels)

        assert result == 0

    def test_link_patent_cet_single(self):
        """Test linking single patent to CET."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [{
            "patent_id": "US123",
            "cet_id": "cet1",
            "score": 0.92,
            "primary": True,
            "classified_at": "2025-10-27T12:00:00Z",
        }]
        result = loader.link_patent_cet(rels)

        assert result == 1

    def test_link_patent_cet_multiple(self):
        """Test linking multiple patents to CETs."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [
            {"patent_id": "US123", "cet_id": "cet1", "score": 0.92, "primary": True},
            {"patent_id": "US456", "cet_id": "cet2", "score": 0.85, "primary": True},
            {"patent_id": "US123", "cet_id": "cet3", "score": 0.70, "primary": False},
        ]
        result = loader.link_patent_cet(rels)

        assert result == 3

    def test_link_patent_cet_handles_missing_score(self):
        """Test link handles missing score."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [{"patent_id": "US123", "cet_id": "cet1"}]
        result = loader.link_patent_cet(rels)

        assert result == 1

    def test_link_patent_cet_handles_missing_primary(self):
        """Test link handles missing primary flag."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [{"patent_id": "US123", "cet_id": "cet1", "score": 0.8}]
        result = loader.link_patent_cet(rels)

        assert result == 1

    def test_link_patent_cet_with_model_version(self):
        """Test link with model_version and taxonomy_version."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        rels = [{
            "patent_id": "US123",
            "cet_id": "cet1",
            "score": 0.92,
            "model_version": "v2.0",
            "taxonomy_version": "2025.1",
        }]
        result = loader.link_patent_cet(rels)

        assert result == 1


class TestNeo4jPatentCETLoaderBatching:
    """Tests for batching behavior."""

    def test_batching_single_batch(self):
        """Test batching with data fitting in one batch."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=10)

        areas = [{"id": f"cet{i}"} for i in range(5)]
        result = loader.upsert_cet_areas(areas)

        assert result == 5
        # Should call execute_write once (5 items < 10 batch size)
        assert mock_session.execute_write.call_count == 1

    def test_batching_multiple_batches(self):
        """Test batching with data requiring multiple batches."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=5)

        areas = [{"id": f"cet{i}"} for i in range(12)]
        result = loader.upsert_cet_areas(areas)

        assert result == 12
        # Should call execute_write 3 times (12 / 5 = 2.4 → 3 batches)
        assert mock_session.execute_write.call_count == 3

    def test_batching_exact_multiple(self):
        """Test batching with exact multiple of batch size."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=5)

        areas = [{"id": f"cet{i}"} for i in range(10)]
        result = loader.upsert_cet_areas(areas)

        assert result == 10
        # Should call execute_write exactly 2 times
        assert mock_session.execute_write.call_count == 2


class TestNeo4jPatentCETLoaderLoadClassifications:
    """Tests for load_classifications composite method."""

    def test_load_classifications_empty(self):
        """Test load_classifications with empty data."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        result = loader.load_classifications([])

        assert result == {"cet_areas": 0, "patents": 0, "relationships": 0}

    def test_load_classifications_with_cet_areas(self):
        """Test load_classifications with provided CET areas."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        cet_areas = [{"id": "cet1", "name": "AI"}]
        classifications = [{
            "patent_id": "US123",
            "cet_id": "cet1",
            "score": 0.92,
        }]

        result = loader.load_classifications(classifications, cet_areas=cet_areas)

        assert result["cet_areas"] == 1
        assert result["patents"] == 1
        assert result["relationships"] == 1

    def test_load_classifications_with_provided_patents(self):
        """Test load_classifications with provided patents."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        patents = [{"patent_id": "US123", "title": "ML System"}]
        classifications = [{
            "patent_id": "US123",
            "cet_id": "cet1",
            "score": 0.92,
        }]

        result = loader.load_classifications(classifications, patents=patents)

        assert result["patents"] == 1
        assert result["relationships"] == 1

    def test_load_classifications_derives_patents(self):
        """Test load_classifications derives patents from classifications."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        classifications = [
            {"patent_id": "US123", "cet_id": "cet1", "title": "ML System", "assignee": "Acme"},
            {"patent_id": "US456", "cet_id": "cet2", "title": "Sensor"},
        ]

        result = loader.load_classifications(classifications, derive_patents_from_rows=True)

        assert result["patents"] == 2
        assert result["relationships"] == 2

    def test_load_classifications_deduplicates_derived_patents(self):
        """Test load_classifications deduplicates derived patents."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        classifications = [
            {"patent_id": "US123", "cet_id": "cet1"},
            {"patent_id": "US123", "cet_id": "cet2"},  # Same patent
        ]

        result = loader.load_classifications(classifications, derive_patents_from_rows=True)

        # Should only create 1 patent node
        assert result["patents"] == 1
        assert result["relationships"] == 2

    def test_load_classifications_calls_ensure_constraints(self):
        """Test load_classifications calls ensure_constraints."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        with patch.object(loader, 'ensure_constraints') as mock_ensure:
            loader.load_classifications([])
            mock_ensure.assert_called_once()


class TestNeo4jPatentCETLoaderEdgeCases:
    """Tests for edge cases in Neo4jPatentCETLoader."""

    def test_session_uses_correct_database(self):
        """Test sessions use correct database."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, database="custom_db")

        loader.upsert_cet_areas([{"id": "cet1"}])

        # Verify session was called with correct database
        mock_driver.session.assert_called_with(database="custom_db")

    def test_multiple_upserts_accumulate(self):
        """Test multiple upsert calls work correctly."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        result1 = loader.upsert_cet_areas([{"id": "cet1"}])
        result2 = loader.upsert_cet_areas([{"id": "cet2"}])

        assert result1 == 1
        assert result2 == 1

    def test_very_large_batch_size(self):
        """Test loader with very large batch size."""
        mock_driver = Mock()
        loader = Neo4jPatentCETLoader(driver=mock_driver, batch_size=1000000)

        assert loader._batch_size == 1000000

    def test_string_conversion_in_upsert(self):
        """Test patent_id is converted to string."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_tx = Mock()
        mock_tx.run.return_value.consume.return_value = None
        mock_session.execute_write.side_effect = lambda fn: fn(mock_tx)
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = Neo4jPatentCETLoader(driver=mock_driver)

        # Integer patent_id
        patents = [{"patent_id": 123, "title": "Test"}]
        result = loader.upsert_patents(patents)

        assert result == 1
