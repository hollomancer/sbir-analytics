"""Tests for asset naming standards module."""

from src.assets.asset_naming_standards import (
    ASSET_RENAMING_MAP,
    GROUP_RENAMING_MAP,
    AssetNamingStandards,
    PipelineStage,
    get_group_name,
    get_standardized_asset_name,
)


class TestPipelineStage:
    """Tests for PipelineStage enum."""

    def test_extraction_stage(self):
        """Test EXTRACTION stage has correct prefix and group."""
        stage = PipelineStage.EXTRACTION
        assert stage.value == ("raw_", "extraction")

    def test_validation_stage(self):
        """Test VALIDATION stage has correct prefix and group."""
        stage = PipelineStage.VALIDATION
        assert stage.value == ("validated_", "validation")

    def test_enrichment_stage(self):
        """Test ENRICHMENT stage has correct prefix and group."""
        stage = PipelineStage.ENRICHMENT
        assert stage.value == ("enriched_", "enrichment")

    def test_transformation_stage(self):
        """Test TRANSFORMATION stage has correct prefix and group."""
        stage = PipelineStage.TRANSFORMATION
        assert stage.value == ("transformed_", "transformation")

    def test_loading_stage(self):
        """Test LOADING stage has correct prefix and group."""
        stage = PipelineStage.LOADING
        assert stage.value == ("loaded_", "loading")

    def test_all_stages_defined(self):
        """Test all expected pipeline stages are defined."""
        expected_stages = {"EXTRACTION", "VALIDATION", "ENRICHMENT", "TRANSFORMATION", "LOADING"}
        actual_stages = {stage.name for stage in PipelineStage}
        assert actual_stages == expected_stages

    def test_enum_access_by_name(self):
        """Test accessing PipelineStage by name."""
        stage = PipelineStage["ENRICHMENT"]
        assert stage == PipelineStage.ENRICHMENT

    def test_enum_iteration(self):
        """Test iterating over PipelineStage enum."""
        stages = list(PipelineStage)
        assert len(stages) == 5
        assert PipelineStage.EXTRACTION in stages


class TestAssetNamingStandards:
    """Tests for AssetNamingStandards class."""

    def test_stage_prefixes_extraction(self):
        """Test stage prefix for extraction."""
        assert AssetNamingStandards.STAGE_PREFIXES["extraction"] == "raw_"

    def test_stage_prefixes_validation(self):
        """Test stage prefix for validation."""
        assert AssetNamingStandards.STAGE_PREFIXES["validation"] == "validated_"

    def test_stage_prefixes_enrichment(self):
        """Test stage prefix for enrichment."""
        assert AssetNamingStandards.STAGE_PREFIXES["enrichment"] == "enriched_"

    def test_stage_prefixes_transformation(self):
        """Test stage prefix for transformation."""
        assert AssetNamingStandards.STAGE_PREFIXES["transformation"] == "transformed_"

    def test_stage_prefixes_loading(self):
        """Test stage prefix for loading."""
        assert AssetNamingStandards.STAGE_PREFIXES["loading"] == "loaded_"

    def test_all_stage_prefixes_defined(self):
        """Test all stage prefixes are defined."""
        expected_stages = {"extraction", "validation", "enrichment", "transformation", "loading"}
        assert set(AssetNamingStandards.STAGE_PREFIXES.keys()) == expected_stages

    def test_group_names_match_stages(self):
        """Test group names match stage keys."""
        assert AssetNamingStandards.GROUP_NAMES["extraction"] == "extraction"
        assert AssetNamingStandards.GROUP_NAMES["validation"] == "validation"
        assert AssetNamingStandards.GROUP_NAMES["enrichment"] == "enrichment"
        assert AssetNamingStandards.GROUP_NAMES["transformation"] == "transformation"
        assert AssetNamingStandards.GROUP_NAMES["loading"] == "loading"

    def test_entity_types_includes_sbir_awards(self):
        """Test entity types includes sbir_awards."""
        assert "sbir_awards" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_includes_usaspending_data(self):
        """Test entity types includes usaspending_data."""
        assert "usaspending_data" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_includes_uspto_patents(self):
        """Test entity types includes uspto_patents."""
        assert "uspto_patents" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_includes_companies(self):
        """Test entity types includes companies."""
        assert "companies" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_includes_contracts(self):
        """Test entity types includes contracts."""
        assert "contracts" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_includes_transitions(self):
        """Test entity types includes transitions."""
        assert "transitions" in AssetNamingStandards.ENTITY_TYPES

    def test_entity_types_is_list(self):
        """Test ENTITY_TYPES is a list."""
        assert isinstance(AssetNamingStandards.ENTITY_TYPES, list)


class TestGetStandardizedAssetName:
    """Tests for get_standardized_asset_name function."""

    def test_extraction_stage_sbir_awards(self):
        """Test standardized name for extraction stage SBIR awards."""
        name = get_standardized_asset_name("extraction", "sbir_awards")
        assert name == "raw_sbir_awards"

    def test_validation_stage_patents(self):
        """Test standardized name for validation stage patents."""
        name = get_standardized_asset_name("validation", "patents")
        assert name == "validated_patents"

    def test_enrichment_stage_companies(self):
        """Test standardized name for enrichment stage companies."""
        name = get_standardized_asset_name("enrichment", "companies")
        assert name == "enriched_companies"

    def test_transformation_stage_contracts(self):
        """Test standardized name for transformation stage contracts."""
        name = get_standardized_asset_name("transformation", "contracts")
        assert name == "transformed_contracts"

    def test_loading_stage_transitions(self):
        """Test standardized name for loading stage transitions."""
        name = get_standardized_asset_name("loading", "transitions")
        assert name == "loaded_transitions"

    def test_with_suffix(self):
        """Test standardized name with suffix."""
        name = get_standardized_asset_name("extraction", "sbir_awards", "filtered")
        assert name == "raw_sbir_awards_filtered"

    def test_with_multi_word_suffix(self):
        """Test standardized name with multi-word suffix."""
        name = get_standardized_asset_name("enrichment", "companies", "with_patents")
        assert name == "enriched_companies_with_patents"

    def test_unknown_stage_returns_no_prefix(self):
        """Test unknown stage returns entity name without prefix."""
        name = get_standardized_asset_name("unknown_stage", "entity")
        assert name == "entity"

    def test_unknown_stage_with_suffix(self):
        """Test unknown stage with suffix."""
        name = get_standardized_asset_name("unknown", "entity", "suffix")
        assert name == "entity_suffix"

    def test_empty_suffix_ignored(self):
        """Test empty suffix is ignored."""
        name = get_standardized_asset_name("extraction", "data", "")
        assert name == "raw_data"

    def test_case_sensitive_stage(self):
        """Test stage name is case sensitive."""
        name = get_standardized_asset_name("EXTRACTION", "data")
        # Should not match uppercase, no prefix
        assert name == "data"


class TestGetGroupName:
    """Tests for get_group_name function."""

    def test_extraction_group(self):
        """Test extraction group name."""
        group = get_group_name("extraction")
        assert group == "extraction"

    def test_validation_group(self):
        """Test validation group name."""
        group = get_group_name("validation")
        assert group == "validation"

    def test_enrichment_group(self):
        """Test enrichment group name."""
        group = get_group_name("enrichment")
        assert group == "enrichment"

    def test_transformation_group(self):
        """Test transformation group name."""
        group = get_group_name("transformation")
        assert group == "transformation"

    def test_loading_group(self):
        """Test loading group name."""
        group = get_group_name("loading")
        assert group == "loading"

    def test_unknown_group_returns_input(self):
        """Test unknown group name returns input unchanged."""
        group = get_group_name("custom_group")
        assert group == "custom_group"

    def test_empty_string_group(self):
        """Test empty string group name."""
        group = get_group_name("")
        assert group == ""


class TestAssetRenamingMap:
    """Tests for ASSET_RENAMING_MAP dictionary."""

    def test_sbir_assets_already_correct(self):
        """Test SBIR assets that are already correctly named."""
        assert ASSET_RENAMING_MAP["raw_sbir_awards"] == "raw_sbir_awards"
        assert ASSET_RENAMING_MAP["validated_sbir_awards"] == "validated_sbir_awards"
        assert ASSET_RENAMING_MAP["enriched_sbir_awards"] == "enriched_sbir_awards"

    def test_usaspending_assets_renamed(self):
        """Test USAspending assets are renamed correctly."""
        assert ASSET_RENAMING_MAP["usaspending_recipient_lookup"] == "raw_usaspending_recipients"
        assert (
            ASSET_RENAMING_MAP["usaspending_transaction_normalized"]
            == "raw_usaspending_transactions"
        )
        assert ASSET_RENAMING_MAP["usaspending_dump_profile"] == "raw_usaspending_profile"

    def test_uspto_raw_assets_already_correct(self):
        """Test USPTO raw assets are already correctly named."""
        assert ASSET_RENAMING_MAP["raw_uspto_assignments"] == "raw_uspto_assignments"
        assert ASSET_RENAMING_MAP["raw_uspto_assignees"] == "raw_uspto_assignees"

    def test_uspto_parsed_to_validated(self):
        """Test USPTO parsed assets renamed to validated."""
        assert ASSET_RENAMING_MAP["parsed_uspto_assignees"] == "validated_uspto_assignees"
        assert ASSET_RENAMING_MAP["parsed_uspto_assignors"] == "validated_uspto_assignors"

    def test_neo4j_to_loaded(self):
        """Test Neo4j assets renamed to loaded prefix."""
        assert ASSET_RENAMING_MAP["neo4j_patents"] == "loaded_patents"
        assert ASSET_RENAMING_MAP["neo4j_patent_assignments"] == "loaded_patent_assignments"
        assert ASSET_RENAMING_MAP["neo4j_patent_entities"] == "loaded_patent_entities"

    def test_cet_taxonomy_renamed(self):
        """Test CET taxonomy renamed correctly."""
        assert ASSET_RENAMING_MAP["cet_taxonomy"] == "raw_cet_taxonomy"

    def test_cet_classifications_enriched(self):
        """Test CET classifications use enriched prefix."""
        assert (
            ASSET_RENAMING_MAP["cet_award_classifications"] == "enriched_cet_award_classifications"
        )
        assert (
            ASSET_RENAMING_MAP["cet_patent_classifications"]
            == "enriched_cet_patent_classifications"
        )

    def test_cet_analytics_transformed(self):
        """Test CET analytics use transformed prefix."""
        assert ASSET_RENAMING_MAP["cet_analytics"] == "transformed_cet_analytics"
        assert (
            ASSET_RENAMING_MAP["cet_analytics_aggregates"] == "transformed_cet_analytics_aggregates"
        )

    def test_cet_neo4j_loaded(self):
        """Test CET Neo4j assets use loaded prefix."""
        assert ASSET_RENAMING_MAP["neo4j_cetarea_nodes"] == "loaded_cet_areas"
        assert ASSET_RENAMING_MAP["neo4j_award_cet_enrichment"] == "loaded_award_cet_enrichment"

    def test_transition_contracts_renamed(self):
        """Test transition contracts renamed correctly."""
        assert ASSET_RENAMING_MAP["contracts_ingestion"] == "raw_contracts"
        assert ASSET_RENAMING_MAP["contracts_sample"] == "validated_contracts_sample"

    def test_transition_processing_transformed(self):
        """Test transition processing assets use transformed prefix."""
        assert ASSET_RENAMING_MAP["transition_scores_v1"] == "transformed_transition_scores"
        assert ASSET_RENAMING_MAP["transition_evidence_v1"] == "transformed_transition_evidence"
        assert ASSET_RENAMING_MAP["transition_detections"] == "transformed_transition_detections"

    def test_transition_neo4j_loaded(self):
        """Test transition Neo4j assets use loaded prefix."""
        assert ASSET_RENAMING_MAP["neo4j_transitions"] == "loaded_transitions"
        assert (
            ASSET_RENAMING_MAP["neo4j_transition_relationships"]
            == "loaded_transition_relationships"
        )

    def test_uspto_ai_assets_renamed(self):
        """Test USPTO AI assets renamed correctly."""
        assert ASSET_RENAMING_MAP["uspto_ai_ingest"] == "raw_uspto_ai_predictions"
        assert ASSET_RENAMING_MAP["uspto_ai_cache_stats"] == "validated_uspto_ai_cache_stats"

    def test_renaming_map_is_dict(self):
        """Test ASSET_RENAMING_MAP is a dictionary."""
        assert isinstance(ASSET_RENAMING_MAP, dict)

    def test_renaming_map_has_many_entries(self):
        """Test ASSET_RENAMING_MAP has many entries."""
        assert len(ASSET_RENAMING_MAP) >= 40  # Should have at least 40 mappings

    def test_all_values_have_stage_prefix(self):
        """Test all renaming map values have valid stage prefix or are unchanged."""
        valid_prefixes = {"raw_", "validated_", "enriched_", "transformed_", "loaded_"}

        for old_name, new_name in ASSET_RENAMING_MAP.items():
            # Either has a valid prefix or is unchanged from original
            has_valid_prefix = any(new_name.startswith(prefix) for prefix in valid_prefixes)
            is_unchanged = old_name == new_name

            assert (
                has_valid_prefix or is_unchanged
            ), f"Asset {old_name} -> {new_name} missing valid prefix"


class TestGroupRenamingMap:
    """Tests for GROUP_RENAMING_MAP dictionary."""

    def test_sbir_ingestion_to_extraction(self):
        """Test sbir_ingestion mapped to extraction."""
        assert GROUP_RENAMING_MAP["sbir_ingestion"] == "extraction"

    def test_usaspending_ingestion_to_extraction(self):
        """Test usaspending_ingestion mapped to extraction."""
        assert GROUP_RENAMING_MAP["usaspending_ingestion"] == "extraction"

    def test_uspto_to_extraction(self):
        """Test uspto mapped to extraction."""
        assert GROUP_RENAMING_MAP["uspto"] == "extraction"

    def test_enrichment_unchanged(self):
        """Test enrichment group unchanged."""
        assert GROUP_RENAMING_MAP["enrichment"] == "enrichment"

    def test_transition_to_transformation(self):
        """Test transition mapped to transformation."""
        assert GROUP_RENAMING_MAP["transition"] == "transformation"

    def test_ml_to_enrichment(self):
        """Test ml (CET classification) mapped to enrichment."""
        assert GROUP_RENAMING_MAP["ml"] == "enrichment"

    def test_group_renaming_map_is_dict(self):
        """Test GROUP_RENAMING_MAP is a dictionary."""
        assert isinstance(GROUP_RENAMING_MAP, dict)

    def test_all_values_are_valid_groups(self):
        """Test all group renaming values are valid pipeline groups."""
        valid_groups = {"extraction", "validation", "enrichment", "transformation", "loading"}

        for old_group, new_group in GROUP_RENAMING_MAP.items():
            assert (
                new_group in valid_groups
            ), f"Group {old_group} -> {new_group} is not a valid pipeline group"


class TestNamingStandardsIntegration:
    """Integration tests for naming standards."""

    def test_standardized_name_matches_renaming_map(self):
        """Test standardized name generation matches renaming map for SBIR."""
        # Generate name using function
        generated = get_standardized_asset_name("extraction", "sbir_awards")

        # Check it matches the expected renamed value
        assert generated == ASSET_RENAMING_MAP["raw_sbir_awards"]

    def test_all_stages_have_consistent_prefixes(self):
        """Test all pipeline stages have consistent prefix mapping."""
        for stage_name, prefix in AssetNamingStandards.STAGE_PREFIXES.items():
            # Test that generated names use the correct prefix
            entity = "test_entity"
            name = get_standardized_asset_name(stage_name, entity)
            assert name.startswith(prefix), f"Stage {stage_name} should use prefix {prefix}"

    def test_group_name_function_matches_constant(self):
        """Test get_group_name matches AssetNamingStandards.GROUP_NAMES."""
        for stage, expected_group in AssetNamingStandards.GROUP_NAMES.items():
            actual_group = get_group_name(stage)
            assert actual_group == expected_group

    def test_pipeline_stage_enum_matches_constants(self):
        """Test PipelineStage enum values match AssetNamingStandards."""
        for stage in PipelineStage:
            prefix, group = stage.value
            stage_name_lower = stage.name.lower()

            # Check prefix matches
            assert AssetNamingStandards.STAGE_PREFIXES[stage_name_lower] == prefix

            # Check group matches
            assert AssetNamingStandards.GROUP_NAMES[stage_name_lower] == group
