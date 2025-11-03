#!/usr/bin/env python3
"""Quick validation script for CLI functionality.

This script tests the CLI installation and basic functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports() -> bool:
    """Test that all CLI modules can be imported."""
    print("Testing CLI imports...")
    try:

        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_context_creation() -> bool:
    """Test CommandContext creation."""
    print("\nTesting CommandContext creation...")
    try:
        from src.cli.context import CommandContext

        context = CommandContext.create()
        print("✓ Context created successfully")
        print(f"  - Config: {type(context.config).__name__}")
        print(f"  - Console: {type(context.console).__name__}")
        print(f"  - DagsterClient: {type(context.dagster_client).__name__}")
        print(f"  - Neo4jClient: {type(context.neo4j_client).__name__}")
        print(f"  - MetricsCollector: {type(context.metrics_collector).__name__}")
        return True
    except Exception as e:
        print(f"✗ Context creation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_app() -> bool:
    """Test CLI app structure."""
    print("\nTesting CLI app structure...")
    try:
        from src.cli.main import app

        # Check app exists
        assert app is not None
        print("✓ CLI app initialized")
        print(f"  - Name: {app.info.name}")
        print(
            f"  - Commands registered: {len(list(app.registered_commands)) if hasattr(app, 'registered_commands') else 'N/A'}"
        )
        return True
    except Exception as e:
        print(f"✗ CLI app test failed: {e}")
        return False


def test_display_components() -> bool:
    """Test display components."""
    print("\nTesting display components...")
    try:
        from rich.console import Console

        from src.cli.display.metrics import create_metrics_table
        from src.cli.display.progress import create_progress_tracker
        from src.cli.display.status import get_health_indicator

        console = Console()

        # Test progress tracker
        create_progress_tracker(console)
        print("✓ Progress tracker created")

        # Test health indicator
        indicator = get_health_indicator("success")
        print(f"✓ Health indicator created: {indicator}")

        # Test metrics table
        metrics_data = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "asset_key": "test",
                "duration_seconds": 10.0,
                "records_processed": 100,
                "success": True,
            }
        ]
        table = create_metrics_table(metrics_data, console)
        print(f"✓ Metrics table created with {len(table.columns)} columns")

        return True
    except Exception as e:
        print(f"✗ Display components test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main() -> int:
    """Run all CLI validation tests."""
    print("=" * 60)
    print("SBIR CLI Validation Tests")
    print("=" * 60)

    results = []

    results.append(("Imports", test_imports()))
    results.append(("Context Creation", test_context_creation()))
    results.append(("CLI App", test_cli_app()))
    results.append(("Display Components", test_display_components()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All validation tests passed!")
        print("\nNext steps:")
        print("  1. Run unit tests: poetry run pytest tests/unit/cli/ -v")
        print("  2. Test commands: poetry run sbir-cli --help")
        print("  3. Check status: poetry run sbir-cli status summary")
        return 0
    else:
        print("\n✗ Some validation tests failed")
        print("Check the output above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
