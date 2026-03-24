"""Tests for Phase 0 foundation tools."""

import pytest
import pandas as pd

from sbir_etl.tools.phase0.resolve_entities import ResolveEntitiesTool, _normalize_name, _generate_canonical_id


class TestNormalizeName:
    def test_removes_suffixes(self):
        assert _normalize_name("Acme Inc") == "ACME"
        assert _normalize_name("Tech Corp") == "TECH"
        assert _normalize_name("Widget LLC") == "WIDGET"

    def test_removes_punctuation(self):
        assert _normalize_name("O'Brien & Associates") == "OBRIEN ASSOCIATES"

    def test_handles_none(self):
        assert _normalize_name(None) == ""

    def test_handles_empty(self):
        assert _normalize_name("") == ""

    def test_collapses_whitespace(self):
        assert _normalize_name("Acme   Technologies   Inc") == "ACME TECHNOLOGIES"


class TestGenerateCanonicalId:
    def test_deterministic(self):
        id1 = _generate_canonical_id("Acme Corp", uei="ABC123")
        id2 = _generate_canonical_id("Acme Corp", uei="ABC123")
        assert id1 == id2

    def test_uei_takes_precedence(self):
        id_with_uei = _generate_canonical_id("Acme Corp", uei="ABC123")
        id_different_name = _generate_canonical_id("Different Name", uei="ABC123")
        assert id_with_uei == id_different_name

    def test_starts_with_co(self):
        id1 = _generate_canonical_id("Test")
        assert id1.startswith("co-")

    def test_different_names_different_ids(self):
        id1 = _generate_canonical_id("Acme Corp")
        id2 = _generate_canonical_id("Widget Inc")
        assert id1 != id2


class TestResolveEntitiesTool:
    def test_basic_resolution(self):
        tool = ResolveEntitiesTool()

        sam = pd.DataFrame({
            "unique_entity_id": ["UEI001", "UEI002"],
            "legal_business_name": ["Acme Corp", "Widget Inc"],
            "physical_address_state": ["CA", "MA"],
            "naics_code": ["541511", "541512"],
        })

        sbir = pd.DataFrame({
            "company": ["Acme Corporation", "Widget Inc", "Unknown Co"],
            "state": ["CA", "MA", "TX"],
            "uei": ["UEI001", "UEI002", ""],
        })

        result = tool.run(sam_entities=sam, sbir_companies=sbir)
        assert result.metadata.tool_name == "resolve_entities"
        assert isinstance(result.data, dict)
        assert "entities" in result.data
        assert "stats" in result.data

    def test_uei_exact_match(self):
        tool = ResolveEntitiesTool()

        sam = pd.DataFrame({
            "unique_entity_id": ["UEI001"],
            "legal_business_name": ["Acme Corp"],
            "physical_address_state": ["CA"],
        })

        sbir = pd.DataFrame({
            "company": ["ACME CORPORATION"],
            "state": ["CA"],
            "uei": ["UEI001"],
        })

        result = tool.run(sam_entities=sam, sbir_companies=sbir)
        stats = result.data["stats"]
        assert stats["deterministic_matches"] >= 1

    def test_empty_inputs(self):
        tool = ResolveEntitiesTool()
        result = tool.run()
        assert isinstance(result.data, dict)
        entities = result.data["entities"]
        assert len(entities) == 0

    def test_metadata_populated(self):
        tool = ResolveEntitiesTool()
        sam = pd.DataFrame({
            "unique_entity_id": ["UEI001"],
            "legal_business_name": ["Acme Corp"],
            "physical_address_state": ["CA"],
        })
        result = tool.run(sam_entities=sam)
        assert len(result.metadata.data_sources) >= 1
        assert result.metadata.data_sources[0].name == "SAM.gov Entity Data"

    def test_new_entity_creation(self):
        """Companies not found in SAM.gov should create new entities."""
        tool = ResolveEntitiesTool()

        # Provide SAM data so fuzzy matching path is exercised
        sam = pd.DataFrame({
            "unique_entity_id": ["UEI999"],
            "legal_business_name": ["Completely Different Corp"],
            "physical_address_state": ["NY"],
        })

        sbir = pd.DataFrame({
            "company": ["Totally New Company"],
            "state": ["TX"],
            "uei": [""],
            "duns": [""],
        })

        result = tool.run(sam_entities=sam, sbir_companies=sbir)
        stats = result.data["stats"]
        assert stats["new_entities_created"] >= 1


class TestExtractSAMEntitiesTool:
    """Test SAM entities extraction with mocked extractor."""

    def test_import(self):
        from sbir_etl.tools.phase0.extract_sam_entities import ExtractSAMEntitiesTool
        tool = ExtractSAMEntitiesTool()
        assert tool.name == "extract_sam_entities"
        assert tool.version == "1.0.0"


class TestExtractFPDSContractsTool:
    """Test FPDS contracts extraction."""

    def test_import(self):
        from sbir_etl.tools.phase0.extract_fpds_contracts import ExtractFPDSContractsTool
        tool = ExtractFPDSContractsTool()
        assert tool.name == "extract_fpds_contracts"

    def test_requires_input(self):
        from sbir_etl.tools.phase0.extract_fpds_contracts import ExtractFPDSContractsTool
        tool = ExtractFPDSContractsTool()
        with pytest.raises(ValueError, match="Must provide either"):
            tool.run()
