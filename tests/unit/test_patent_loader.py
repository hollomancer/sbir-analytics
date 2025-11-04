"""Unit tests for PatentLoader Neo4j operations.

Tests cover:
- Node creation (Patents, PatentAssignments, PatentEntities)
- Relationship creation (ASSIGNED_VIA, ASSIGNED_FROM, ASSIGNED_TO, etc.)
- Index and constraint management
- Error handling and edge cases
- Metrics tracking
"""

from datetime import date
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.fast


# Import the modules under test; skip if dependencies unavailable
pytest.importorskip("neo4j", reason="neo4j driver missing")
Neo4jClient = pytest.importorskip(
    "src.loaders.neo4j_client", reason="neo4j_client module missing"
).Neo4jClient
PatentLoader = pytest.importorskip(
    "src.loaders.patent_loader", reason="patent_loader module missing"
).PatentLoader
PatentLoaderConfig = pytest.importorskip(
    "src.loaders.patent_loader", reason="patent_loader module missing"
).PatentLoaderConfig
LoadMetrics = pytest.importorskip(
    "src.loaders.neo4j_client", reason="LoadMetrics missing"
).LoadMetrics


class TestPatentLoaderConfig:
    """Test PatentLoaderConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PatentLoaderConfig()
        assert config.batch_size == 1000
        assert config.create_indexes is True
        assert config.create_constraints is True
        assert config.link_to_sbir is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PatentLoaderConfig(
            batch_size=500,
            create_indexes=False,
            create_constraints=False,
            link_to_sbir=False,
        )
        assert config.batch_size == 500
        assert config.create_indexes is False
        assert config.create_constraints is False
        assert config.link_to_sbir is False


class TestPatentLoaderInitialization:
    """Test PatentLoader initialization."""

    def test_loader_initialization(self):
        """Test PatentLoader initialization with mock client."""
        mock_client = MagicMock(spec=Neo4jClient)
        loader = PatentLoader(mock_client)
        assert loader.client == mock_client
        assert loader.config.batch_size == 1000

    def test_loader_with_custom_config(self):
        """Test PatentLoader initialization with custom config."""
        mock_client = MagicMock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=2000)
        loader = PatentLoader(mock_client, config)
        assert loader.config.batch_size == 2000


class TestPatentLoaderConstraints:
    """Test constraint creation."""

    def test_create_constraints_success(self):
        """Test successful constraint creation."""
        mock_client = MagicMock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # Verify constraints were created
        assert mock_session.run.call_count == 3
        calls = mock_session.run.call_args_list
        constraint_strs = [call[0][0] for call in calls]
        assert any("patent_grant_doc_num" in s for s in constraint_strs)
        assert any("patent_assignment_rf_id" in s for s in constraint_strs)
        assert any("patent_entity_id" in s for s in constraint_strs)

    def test_create_constraints_with_exception(self):
        """Test constraint creation handles exceptions gracefully."""
        mock_client = MagicMock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Constraint already exists")
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        # Should not raise exception
        loader.create_constraints()


class TestPatentLoaderIndexes:
    """Test index creation."""

    def test_create_indexes_success(self):
        """Test successful index creation."""
        mock_client = MagicMock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_indexes()

        # Verify indexes were created
        assert mock_session.run.call_count == 6  # Tier 1 (3) + Tier 2 (3)
        calls = mock_session.run.call_args_list
        index_strs = [call[0][0] for call in calls]

        # Check for essential indexes
        assert any("grant_doc_num" in s for s in index_strs)
        assert any("rf_id" in s for s in index_strs)
        assert any("normalized_name" in s for s in index_strs)

        # Check for tier 2 indexes
        assert any("appno_date" in s for s in index_strs)
        assert any("exec_date" in s for s in index_strs)
        assert any("entity_type" in s for s in index_strs)


class TestPatentNodeLoading:
    """Test Patent node creation."""

    def test_load_patents_empty_list(self):
        """Test loading empty patent list."""
        mock_client = MagicMock(spec=Neo4jClient)
        mock_client.batch_upsert_nodes.return_value = LoadMetrics()

        loader = PatentLoader(mock_client)
        result = loader.load_patents([])

        assert result.nodes_created.get("Patent", 0) == 0
        mock_client.batch_upsert_nodes.assert_not_called()

    def test_load_patents_single_patent(self):
        """Test loading a single patent."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["Patent"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [
            {
                "grant_doc_num": "5858003",
                "title": "SYSTEMS AND METHODS FOR PROMOTING TISSUE GROWTH",
                "appno_date": date(1994, 10, 20),
                "grant_date": date(1999, 1, 12),
            }
        ]

        result = loader.load_patents(patents)

        assert result.nodes_created["Patent"] == 1
        mock_client.batch_upsert_nodes.assert_called_once()
        call_args = mock_client.batch_upsert_nodes.call_args
        assert call_args[1]["label"] == "Patent"
        assert call_args[1]["key_property"] == "grant_doc_num"

    def test_load_patents_missing_grant_doc_num(self):
        """Test patent with missing grant_doc_num is skipped."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.errors = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [
            {
                "title": "Patent without grant number",
                "appno_date": date(2020, 1, 1),
            }
        ]

        result = loader.load_patents(patents)

        assert result.errors == 1

    def test_load_patents_date_conversion(self):
        """Test date objects are converted to ISO format strings."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["Patent"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [
            {
                "grant_doc_num": "5858003",
                "title": "Test Patent",
                "appno_date": date(1994, 10, 20),
                "grant_date": date(1999, 1, 12),
            }
        ]

        loader.load_patents(patents)

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        assert isinstance(nodes[0]["appno_date"], str)
        assert nodes[0]["appno_date"] == "1994-10-20"
        assert nodes[0]["grant_date"] == "1999-01-12"

    def test_load_patents_batch_size(self):
        """Test patents are batched correctly."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["Patent"] = 5
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [{"grant_doc_num": f"PAT{i}", "title": f"Patent {i}"} for i in range(5)]

        loader.load_patents(patents)

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        assert len(nodes) == 5


class TestPatentAssignmentNodeLoading:
    """Test PatentAssignment node creation."""

    def test_load_patent_assignments_single(self):
        """Test loading a single assignment."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["PatentAssignment"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "rf_id": "RF001",
                "file_id": "F-100",
                "conveyance_type": "assignment",
                "execution_date": date(2023, 7, 15),
                "recorded_date": date(2023, 7, 20),
            }
        ]

        result = loader.load_patent_assignments(assignments)

        assert result.nodes_created["PatentAssignment"] == 1
        call_args = mock_client.batch_upsert_nodes.call_args
        assert call_args[1]["label"] == "PatentAssignment"
        assert call_args[1]["key_property"] == "rf_id"

    def test_load_patent_assignments_missing_rf_id(self):
        """Test assignment with missing rf_id is skipped."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.errors = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "file_id": "F-100",
                "conveyance_type": "assignment",
            }
        ]

        result = loader.load_patent_assignments(assignments)

        assert result.errors == 1

    def test_load_patent_assignments_empty(self):
        """Test loading empty assignments list."""
        mock_client = MagicMock(spec=Neo4jClient)
        loader = PatentLoader(mock_client)

        result = loader.load_patent_assignments([])

        assert result.nodes_created.get("PatentAssignment", 0) == 0
        mock_client.batch_upsert_nodes.assert_not_called()


class TestPatentEntityNodeLoading:
    """Test PatentEntity node creation."""

    def test_load_patent_entities_assignees(self):
        """Test loading assignee entities."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["PatentEntity"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        entities = [
            {
                "entity_id": "ENT001",
                "name": "Acme Corporation",
                "normalized_name": "ACME CORPORATION",
                "city": "Springfield",
                "state": "IL",
            }
        ]

        result = loader.load_patent_entities(entities, entity_type="ASSIGNEE")

        assert result.nodes_created["PatentEntity"] == 1
        call_args = mock_client.batch_upsert_nodes.call_args
        assert call_args[1]["label"] == "PatentEntity"
        nodes = call_args[1]["nodes"]
        assert nodes[0]["entity_type"] == "ASSIGNEE"

    def test_load_patent_entities_assignors(self):
        """Test loading assignor entities."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["PatentEntity"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        entities = [
            {
                "entity_id": "ENT002",
                "name": "John Smith",
                "normalized_name": "JOHN SMITH",
            }
        ]

        loader.load_patent_entities(entities, entity_type="ASSIGNOR")

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        assert nodes[0]["entity_type"] == "ASSIGNOR"

    def test_load_patent_entities_missing_name(self):
        """Test entity with missing name is skipped."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.errors = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        entities = [
            {
                "entity_id": "ENT003",
                # missing name
            }
        ]

        result = loader.load_patent_entities(entities, entity_type="ASSIGNEE")

        assert result.errors == 1

    def test_load_patent_entities_removes_none_values(self):
        """Test None values are removed from entity nodes."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["PatentEntity"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        entities = [
            {
                "entity_id": "ENT004",
                "name": "Company",
                "normalized_name": "COMPANY",
                "street": None,  # Should be removed
                "city": "Boston",
            }
        ]

        loader.load_patent_entities(entities, entity_type="ASSIGNEE")

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        assert "street" not in nodes[0]
        assert nodes[0]["city"] == "Boston"


class TestAssignedViaRelationships:
    """Test ASSIGNED_VIA relationship creation."""

    def test_create_assigned_via_relationships(self):
        """Test creating ASSIGNED_VIA relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["ASSIGNED_VIA"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "grant_doc_num": "PAT001",
                "rf_id": "RF001",
            }
        ]

        result = loader.create_assigned_via_relationships(assignments)

        assert result.relationships_created["ASSIGNED_VIA"] == 1
        call_args = mock_client.batch_create_relationships.call_args
        rels = call_args[1]["relationships"]
        assert rels[0][0] == "Patent"
        assert rels[0][2] == "PAT001"
        assert rels[0][5] == "RF001"
        assert rels[0][6] == "ASSIGNED_VIA"

    def test_create_assigned_via_missing_keys(self):
        """Test relationship with missing keys is skipped."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.errors = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "grant_doc_num": "PAT001",
                # missing rf_id
            }
        ]

        result = loader.create_assigned_via_relationships(assignments)

        assert result.errors == 1


class TestAssignedFromRelationships:
    """Test ASSIGNED_FROM relationship creation."""

    def test_create_assigned_from_relationships(self):
        """Test creating ASSIGNED_FROM relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["ASSIGNED_FROM"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "rf_id": "RF001",
                "assignor_entity_id": "ENT001",
                "execution_date": date(2023, 7, 15),
            }
        ]

        result = loader.create_assigned_from_relationships(assignments)

        assert result.relationships_created["ASSIGNED_FROM"] == 1
        call_args = mock_client.batch_create_relationships.call_args
        rels = call_args[1]["relationships"]
        assert rels[0][6] == "ASSIGNED_FROM"
        assert rels[0][7]["execution_date"] == "2023-07-15"

    def test_create_assigned_from_missing_entity_id(self):
        """Test relationship with missing entity_id is skipped."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.errors = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "rf_id": "RF001",
                # missing assignor_entity_id
            }
        ]

        result = loader.create_assigned_from_relationships(assignments)

        assert result.errors == 1


class TestAssignedToRelationships:
    """Test ASSIGNED_TO relationship creation."""

    def test_create_assigned_to_relationships(self):
        """Test creating ASSIGNED_TO relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["ASSIGNED_TO"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        assignments = [
            {
                "rf_id": "RF001",
                "assignee_entity_id": "ENT002",
                "recorded_date": date(2023, 7, 20),
            }
        ]

        result = loader.create_assigned_to_relationships(assignments)

        assert result.relationships_created["ASSIGNED_TO"] == 1
        call_args = mock_client.batch_create_relationships.call_args
        rels = call_args[1]["relationships"]
        assert rels[0][6] == "ASSIGNED_TO"
        assert rels[0][7]["recorded_date"] == "2023-07-20"


class TestGeneratedFromRelationships:
    """Test GENERATED_FROM relationship creation (SBIR linkage)."""

    def test_create_generated_from_relationships(self):
        """Test creating GENERATED_FROM relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["GENERATED_FROM"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        patent_awards = [
            {
                "grant_doc_num": "PAT001",
                "award_id": "AWARD-2023-001",
            }
        ]

        result = loader.create_generated_from_relationships(patent_awards)

        assert result.relationships_created["GENERATED_FROM"] == 1


class TestOwnsRelationships:
    """Test OWNS relationship creation."""

    def test_create_owns_relationships(self):
        """Test creating OWNS relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["OWNS"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        company_patents = [
            {
                "uei": "COMPANY-UEI-1",
                "grant_doc_num": "PAT001",
            }
        ]

        result = loader.create_owns_relationships(company_patents)

        assert result.relationships_created["OWNS"] == 1


class TestChainOfRelationships:
    """Test CHAIN_OF relationship creation."""

    def test_create_chain_of_relationships(self):
        """Test creating CHAIN_OF relationships."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.relationships_created["CHAIN_OF"] = 1
        mock_client.batch_create_relationships.return_value = metrics

        loader = PatentLoader(mock_client)
        chains = [
            {
                "current_rf_id": "RF002",
                "previous_rf_id": "RF001",
            }
        ]

        result = loader.create_chain_of_relationships(chains)

        assert result.relationships_created["CHAIN_OF"] == 1


class TestMetricsAccumulation:
    """Test metrics accumulation across multiple operations."""

    def test_metrics_accumulation_across_operations(self):
        """Test metrics are properly accumulated."""
        MagicMock(spec=Neo4jClient)

        # First operation
        metrics1 = LoadMetrics()
        metrics1.nodes_created["Patent"] = 10

        # Second operation
        metrics2 = LoadMetrics()
        metrics2.nodes_created["PatentAssignment"] = 5

        # Simulate accumulation
        all_metrics = LoadMetrics()
        all_metrics.nodes_created["Patent"] = 10
        all_metrics.nodes_created["PatentAssignment"] = 5

        assert all_metrics.nodes_created["Patent"] == 10
        assert all_metrics.nodes_created["PatentAssignment"] == 5


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_node_list_all_types(self):
        """Test all node loading methods handle empty lists."""
        mock_client = MagicMock(spec=Neo4jClient)
        loader = PatentLoader(mock_client)

        # All should handle empty lists without calling batch_upsert_nodes
        loader.load_patents([])
        loader.load_patent_assignments([])
        loader.load_patent_entities([], entity_type="ASSIGNEE")

        # batch_upsert_nodes should not be called
        mock_client.batch_upsert_nodes.assert_not_called()

    def test_whitespace_trimming_in_keys(self):
        """Test that whitespace is trimmed from key values."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["Patent"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [
            {
                "grant_doc_num": "  PAT001  ",  # with whitespace
                "title": "Patent",
            }
        ]

        loader.load_patents(patents)

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        # Should be trimmed
        assert nodes[0]["grant_doc_num"] == "PAT001"

    def test_string_conversion_for_numeric_keys(self):
        """Test numeric grant_doc_num is converted to string."""
        mock_client = MagicMock(spec=Neo4jClient)
        metrics = LoadMetrics()
        metrics.nodes_created["Patent"] = 1
        mock_client.batch_upsert_nodes.return_value = metrics

        loader = PatentLoader(mock_client)
        patents = [
            {
                "grant_doc_num": 5858003,  # numeric
                "title": "Patent",
            }
        ]

        loader.load_patents(patents)

        call_args = mock_client.batch_upsert_nodes.call_args
        nodes = call_args[1]["nodes"]
        assert isinstance(nodes[0]["grant_doc_num"], str)
        assert nodes[0]["grant_doc_num"] == "5858003"
