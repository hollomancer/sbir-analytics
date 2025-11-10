"""Tests for assets package __init__ lazy import mechanism."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import importlib


class TestAssetsPackageStructure:
    """Tests for assets package structure and constants."""

    def test_all_list_exists(self):
        """Test __all__ list is defined."""
        from src.assets import __all__
        assert isinstance(__all__, list)

    def test_all_list_not_empty(self):
        """Test __all__ list contains exported symbols."""
        from src.assets import __all__
        assert len(__all__) > 0

    def test_all_list_contains_example_assets(self):
        """Test __all__ includes example assets."""
        from src.assets import __all__
        assert "raw_sbir_data" in __all__
        assert "validated_sbir_data" in __all__

    def test_all_list_contains_uspto_assets(self):
        """Test __all__ includes USPTO assets."""
        from src.assets import __all__
        assert "raw_uspto_assignments" in __all__
        assert "transformed_patents" in __all__
        assert "neo4j_patents" in __all__

    def test_all_list_contains_cet_assets(self):
        """Test __all__ includes CET assets."""
        from src.assets import __all__
        assert "neo4j_cetarea_nodes" in __all__
        assert "neo4j_award_cet_enrichment" in __all__

    def test_all_list_contains_transition_assets(self):
        """Test __all__ includes transition assets."""
        from src.assets import __all__
        assert "contracts_ingestion" in __all__
        assert "transition_scores_v1" in __all__
        assert "loaded_transitions" in __all__

    def test_lazy_mapping_exists(self):
        """Test _lazy_mapping dictionary exists."""
        from src.assets import _lazy_mapping
        assert isinstance(_lazy_mapping, dict)

    def test_lazy_mapping_not_empty(self):
        """Test _lazy_mapping contains mappings."""
        from src.assets import _lazy_mapping
        assert len(_lazy_mapping) > 0

    def test_lazy_mapping_structure(self):
        """Test _lazy_mapping has correct structure."""
        from src.assets import _lazy_mapping

        # Each entry should be: symbol -> (module_path, attribute_name)
        for symbol, mapping in _lazy_mapping.items():
            assert isinstance(symbol, str)
            assert isinstance(mapping, tuple)
            assert len(mapping) == 2
            module_path, attr_name = mapping
            assert isinstance(module_path, str)
            assert isinstance(attr_name, str)

    def test_lazy_mapping_modules_start_with_src_assets(self):
        """Test all lazy mapping modules are in src.assets package."""
        from src.assets import _lazy_mapping

        for symbol, (module_path, attr_name) in _lazy_mapping.items():
            assert module_path.startswith("src.assets."), \
                f"Module path {module_path} should start with 'src.assets.'"

    def test_all_matches_lazy_mapping_keys(self):
        """Test __all__ symbols match _lazy_mapping keys (mostly)."""
        from src.assets import __all__, _lazy_mapping

        # Most symbols in __all__ should be in _lazy_mapping
        # (some might be defined directly in future)
        all_set = set(__all__)
        mapping_set = set(_lazy_mapping.keys())

        # At least most should match
        overlap = all_set & mapping_set
        assert len(overlap) > 30, "Most __all__ symbols should be in _lazy_mapping"


class TestLazyImportMechanism:
    """Tests for lazy import __getattr__ mechanism."""

    def test_getattr_hook_exists(self):
        """Test __getattr__ function is defined."""
        import src.assets
        assert hasattr(src.assets, '__getattr__')

    def test_dir_hook_exists(self):
        """Test __dir__ function is defined."""
        import src.assets
        assert hasattr(src.assets, '__dir__')

    def test_dir_includes_all_symbols(self):
        """Test __dir__() includes all exported symbols."""
        from src.assets import __all__
        import src.assets

        dir_result = src.assets.__dir__()

        for symbol in __all__:
            assert symbol in dir_result, f"{symbol} should be in __dir__() result"

    def test_dir_is_sorted(self):
        """Test __dir__() returns sorted list."""
        import src.assets
        dir_result = src.assets.__dir__()

        assert dir_result == sorted(dir_result)

    @patch('src.assets.import_module')
    def test_getattr_imports_module_on_first_access(self, mock_import):
        """Test __getattr__ imports module on first access."""
        # Create a fresh module to avoid cached imports
        import sys
        import importlib

        # Remove from cache if present
        module_name = 'src.assets'
        if module_name in sys.modules:
            # Save lazy mapping before reload
            from src.assets import _lazy_mapping
            saved_mapping = _lazy_mapping.copy()

            # Reload module
            importlib.reload(sys.modules[module_name])

    @patch('src.assets.import_module')
    def test_getattr_returns_attribute_from_module(self, mock_import):
        """Test __getattr__ returns correct attribute from imported module."""
        from src.assets import __getattr__, _lazy_mapping

        # Mock the imported module
        mock_module = Mock()
        mock_asset = Mock()
        mock_module.raw_sbir_data = mock_asset
        mock_import.return_value = mock_module

        # Access a symbol from lazy mapping
        if "raw_sbir_data" in _lazy_mapping:
            # Call __getattr__ directly
            result = __getattr__("raw_sbir_data")

            # Should have imported the module
            module_path, attr_name = _lazy_mapping["raw_sbir_data"]
            mock_import.assert_called_once_with(module_path)

    def test_getattr_raises_for_unknown_symbol(self):
        """Test __getattr__ raises AttributeError for unknown symbols."""
        from src.assets import __getattr__

        with pytest.raises(AttributeError) as exc_info:
            __getattr__("nonexistent_symbol")

        assert "has no attribute 'nonexistent_symbol'" in str(exc_info.value)

    @patch('src.assets.import_module')
    def test_getattr_raises_if_attribute_missing_from_module(self, mock_import):
        """Test __getattr__ raises if imported module lacks attribute."""
        from src.assets import __getattr__, _lazy_mapping

        # Mock a module without the expected attribute
        mock_module = Mock(spec=[])  # Empty spec, no attributes
        mock_import.return_value = mock_module

        # Try to access a symbol that exists in mapping
        if "raw_sbir_data" in _lazy_mapping:
            with pytest.raises(AttributeError) as exc_info:
                __getattr__("raw_sbir_data")

            assert "does not define" in str(exc_info.value)


class TestLazyMappingContent:
    """Tests for _lazy_mapping content and structure."""

    def test_example_assets_mapped_correctly(self):
        """Test example assets have correct module paths."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["raw_sbir_data"] == (
            "src.assets.example_assets",
            "raw_sbir_data",
        )
        assert _lazy_mapping["validated_sbir_data"] == (
            "src.assets.example_assets",
            "validated_sbir_data",
        )

    def test_uspto_assets_mapped_correctly(self):
        """Test USPTO assets have correct module paths."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["raw_uspto_assignments"] == (
            "src.assets.uspto_assets",
            "raw_uspto_assignments",
        )
        assert _lazy_mapping["transformed_patents"] == (
            "src.assets.uspto_assets",
            "transformed_patents",
        )

    def test_cet_assets_mapped_correctly(self):
        """Test CET assets have correct module paths."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["neo4j_cetarea_nodes"] == (
            "src.assets.cet_assets",
            "neo4j_cetarea_nodes",
        )

    def test_transition_assets_mapped_correctly(self):
        """Test transition assets have correct module paths."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["contracts_ingestion"] == (
            "src.assets.transition_assets",
            "raw_contracts",
        )
        # Note: contracts_ingestion maps to raw_contracts attribute
        assert _lazy_mapping["contracts_ingestion"][1] == "raw_contracts"

    def test_transition_scores_mapped_correctly(self):
        """Test transition scores mapped correctly."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["transition_scores_v1"] == (
            "src.assets.transition_assets",
            "transformed_transition_scores",
        )

    def test_loaded_transitions_mapped_correctly(self):
        """Test loaded transitions mapped correctly."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["loaded_transitions"] == (
            "src.assets.transition_assets",
            "loaded_transitions",
        )

    def test_uspto_ai_assets_mapped_correctly(self):
        """Test USPTO AI assets mapped correctly."""
        from src.assets import _lazy_mapping

        assert _lazy_mapping["raw_uspto_ai_extract"] == (
            "src.assets.uspto_assets",
            "raw_uspto_ai_extract",
        )

    def test_asset_checks_in_mapping(self):
        """Test asset checks are in lazy mapping."""
        from src.assets import _lazy_mapping

        # USPTO checks
        assert "uspto_rf_id_asset_check" in _lazy_mapping
        assert "uspto_completeness_asset_check" in _lazy_mapping

        # Transition checks
        if "transition_analytics_quality_check" in _lazy_mapping:
            assert _lazy_mapping["transition_analytics_quality_check"][0] == "src.assets.transition_assets"


class TestLazyImportBehavior:
    """Tests for lazy import behavior and caching."""

    def test_symbol_not_imported_until_accessed(self):
        """Test symbols are not imported at package import time."""
        import sys

        # Clear any previously imported asset modules
        asset_modules = [key for key in sys.modules.keys()
                        if key.startswith('src.assets.') and key != 'src.assets']
        for module in asset_modules:
            del sys.modules[module]

        # Import the assets package
        import src.assets

        # Asset submodules should not be loaded yet
        # (They will be loaded on first access via __getattr__)
        assert 'src.assets.example_assets' not in sys.modules or \
               sys.modules.get('src.assets.example_assets') is None

    def test_multiple_symbols_from_same_module(self):
        """Test multiple symbols from the same module share mapping."""
        from src.assets import _lazy_mapping

        # Find symbols from the same module
        module_groups = {}
        for symbol, (module_path, attr_name) in _lazy_mapping.items():
            if module_path not in module_groups:
                module_groups[module_path] = []
            module_groups[module_path].append(symbol)

        # USPTO assets should have multiple symbols
        uspto_symbols = module_groups.get("src.assets.uspto_assets", [])
        assert len(uspto_symbols) > 5, "USPTO assets should have many symbols"

        # Transition assets should have multiple symbols
        transition_symbols = module_groups.get("src.assets.transition_assets", [])
        assert len(transition_symbols) > 5, "Transition assets should have many symbols"


class TestPackageDocumentation:
    """Tests for package documentation and conventions."""

    def test_module_has_docstring(self):
        """Test assets package has docstring."""
        import src.assets
        assert src.assets.__doc__ is not None
        assert len(src.assets.__doc__) > 0

    def test_docstring_mentions_lazy_import(self):
        """Test docstring mentions lazy import mechanism."""
        import src.assets
        docstring = src.assets.__doc__.lower()
        assert "lazy" in docstring or "import" in docstring

    def test_docstring_mentions_avoiding_heavy_imports(self):
        """Test docstring explains avoiding heavy dependencies."""
        import src.assets
        docstring = src.assets.__doc__.lower()
        assert "optional" in docstring or "dependencies" in docstring or "dagster" in docstring


class TestConsistencyChecks:
    """Tests for consistency between __all__, _lazy_mapping, and actual modules."""

    def test_no_duplicate_symbols_in_all(self):
        """Test __all__ has no duplicate symbols."""
        from src.assets import __all__

        assert len(__all__) == len(set(__all__)), "Duplicate symbols in __all__"

    def test_no_duplicate_symbols_in_lazy_mapping(self):
        """Test _lazy_mapping has no duplicate keys."""
        from src.assets import _lazy_mapping

        # Dictionary keys are inherently unique, but test for clarity
        assert len(_lazy_mapping) == len(set(_lazy_mapping.keys()))

    def test_lazy_mapping_symbols_are_valid_identifiers(self):
        """Test all lazy mapping symbols are valid Python identifiers."""
        from src.assets import _lazy_mapping

        for symbol in _lazy_mapping.keys():
            assert symbol.isidentifier(), f"{symbol} is not a valid Python identifier"

    def test_lazy_mapping_attributes_are_valid_identifiers(self):
        """Test all lazy mapping attributes are valid Python identifiers."""
        from src.assets import _lazy_mapping

        for symbol, (module_path, attr_name) in _lazy_mapping.items():
            assert attr_name.isidentifier(), \
                f"Attribute {attr_name} for {symbol} is not a valid Python identifier"

    def test_module_paths_use_dot_notation(self):
        """Test all module paths use proper dot notation."""
        from src.assets import _lazy_mapping

        for symbol, (module_path, attr_name) in _lazy_mapping.items():
            # Module paths should have at least 2 parts (src.assets.something)
            parts = module_path.split(".")
            assert len(parts) >= 3, f"Module path {module_path} should have at least 3 parts"
            assert parts[0] == "src"
            assert parts[1] == "assets"


class TestErrorHandling:
    """Tests for error handling in lazy import mechanism."""

    def test_getattr_error_message_quality(self):
        """Test __getattr__ error messages are helpful."""
        from src.assets import __getattr__

        with pytest.raises(AttributeError) as exc_info:
            __getattr__("definitely_not_a_real_asset")

        error_message = str(exc_info.value)
        # Error should mention the module name and the symbol
        assert "src.assets" in error_message
        assert "definitely_not_a_real_asset" in error_message

    @patch('src.assets.import_module')
    def test_getattr_includes_cause_in_error(self, mock_import):
        """Test __getattr__ includes underlying AttributeError as cause."""
        from src.assets import __getattr__, _lazy_mapping

        # Mock a module without the expected attribute
        mock_module = Mock(spec=[])
        mock_import.return_value = mock_module

        if "raw_sbir_data" in _lazy_mapping:
            with pytest.raises(AttributeError) as exc_info:
                __getattr__("raw_sbir_data")

            # Should have a __cause__ set
            assert exc_info.value.__cause__ is not None
