#!/usr/bin/env python3
"""
E2E Test Runner Script

This script orchestrates end-to-end testing of the SBIR ETL pipeline with
resource monitoring and scenario-based test execution optimized for MacBook Air.

Usage:
    python scripts/run_e2e_tests.py [--scenario SCENARIO] [--timeout TIMEOUT]

Scenarios:
    minimal     - Quick smoke tests (< 2 minutes)
    standard    - Full E2E validation (5-8 minutes)
    large       - Performance testing (8-10 minutes)
    edge-cases  - Robustness testing (3-5 minutes)
"""

import argparse
import importlib
import os
import sys
import time
from pathlib import Path
from typing import Any


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def get_test_config(scenario: str) -> dict[str, Any]:
    """Get test configuration for the specified scenario."""
    configs = {
        "minimal": {
            "description": "Quick smoke tests for basic functionality",
            "timeout": 120,
            "test_markers": "not slow and not large_dataset",
            "expected_duration": "< 2 minutes",
            "memory_limit": "2GB",
        },
        "standard": {
            "description": "Full E2E validation with representative data",
            "timeout": 480,
            "test_markers": "not large_dataset",
            "expected_duration": "5-8 minutes",
            "memory_limit": "4GB",
        },
        "large": {
            "description": "Performance testing with larger datasets",
            "timeout": 600,
            "test_markers": "",
            "expected_duration": "8-10 minutes",
            "memory_limit": "6GB",
        },
        "edge-cases": {
            "description": "Robustness testing with edge cases",
            "timeout": 300,
            "test_markers": "edge_case",
            "expected_duration": "3-5 minutes",
            "memory_limit": "3GB",
        },
    }
    return configs.get(scenario, configs["standard"])


def check_environment() -> bool:
    """Check if the environment is properly configured for E2E testing."""
    required_vars = [
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "SBIR_ETL__NEO4J__BOLT_URL",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False

    print("✅ Environment configuration validated")
    return True


def check_macbook_air_resources() -> bool:
    """Check if system resources are suitable for MacBook Air testing."""
    macbook_air_mode = os.getenv("MACBOOK_AIR_MODE", "true").lower() == "true"

    if not macbook_air_mode:
        print("ℹ️  MacBook Air optimizations disabled")
        return True

    print("🍎 MacBook Air mode enabled - checking resource constraints...")

    # Check memory limit
    memory_limit_gb = float(os.getenv("MEMORY_LIMIT_GB", "8"))
    if memory_limit_gb > 8:
        print(f"⚠️  Memory limit ({memory_limit_gb}GB) exceeds MacBook Air recommendation (8GB)")

    # Check CPU limit
    cpu_limit = float(os.getenv("CPU_LIMIT", "2.0"))
    if cpu_limit > 2.0:
        print(f"⚠️  CPU limit ({cpu_limit}) exceeds MacBook Air recommendation (2.0)")

    print("✅ Resource constraints validated for MacBook Air")
    return True


def _is_pytest_timeout_available() -> bool:
    """Return True if pytest-timeout plugin is installed."""

    try:
        importlib.import_module("pytest_timeout")
        return True
    except ModuleNotFoundError:
        return False


def run_e2e_tests(scenario: str, timeout: int) -> int:
    """Run E2E tests for the specified scenario."""
    config = get_test_config(scenario)

    print("\n🚀 Starting E2E Tests")
    print(f"   Scenario: {scenario}")
    print(f"   Description: {config['description']}")
    print(f"   Expected Duration: {config['expected_duration']}")
    print(f"   Memory Limit: {config['memory_limit']}")
    print(f"   Timeout: {timeout}s")
    print("-" * 60)

    # Set environment variables for the test run
    env = os.environ.copy()
    env["E2E_TEST_SCENARIO"] = scenario
    env["E2E_TEST_TIMEOUT"] = str(timeout)

    # Build pytest command
    pytest_args = [
        "python",
        "-m",
        "pytest",
        "tests/e2e/",
        "-v",
        "--tb=short",
    ]

    if _is_pytest_timeout_available():
        pytest_args.extend(
            [
                f"--timeout={timeout}",
                "--timeout-method=thread",
            ]
        )
    else:
        print(
            "⚠️  pytest-timeout plugin not found; skipping --timeout flags. "
            "Install pytest-timeout to re-enable per-test timeouts."
        )

    # Add test markers if specified
    if config["test_markers"]:
        pytest_args.extend(["-m", config["test_markers"]])

    # Add coverage if not in minimal mode
    if scenario != "minimal":
        pytest_args.extend(
            [
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-report=html:/app/artifacts/htmlcov",
            ]
        )

    print(f"Running: {' '.join(pytest_args)}")
    print()

    # Record start time
    start_time = time.time()

    # Run tests
    import subprocess

    try:
        result = subprocess.run(pytest_args, env=env, timeout=timeout)
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        print(f"\n❌ Tests timed out after {timeout} seconds")
        exit_code = 124
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        exit_code = 1

    # Calculate duration
    duration = time.time() - start_time

    print("\n" + "=" * 60)
    print("📊 E2E Test Results")
    print(f"   Scenario: {scenario}")
    print(f"   Duration: {duration:.1f}s")
    print(f"   Exit Code: {exit_code}")

    if exit_code == 0:
        print("   Status: ✅ PASSED")
    elif exit_code == 124:
        print("   Status: ⏰ TIMEOUT")
    else:
        print("   Status: ❌ FAILED")

    print("=" * 60)

    return exit_code


def main():
    """Main entry point for E2E test runner."""
    parser = argparse.ArgumentParser(
        description="Run E2E tests for SBIR ETL pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  minimal     Quick smoke tests (< 2 minutes)
  standard    Full E2E validation (5-8 minutes) [default]
  large       Performance testing (8-10 minutes)
  edge-cases  Robustness testing (3-5 minutes)

Examples:
  python scripts/run_e2e_tests.py
  python scripts/run_e2e_tests.py --scenario minimal
  python scripts/run_e2e_tests.py --scenario large --timeout 900
        """,
    )

    parser.add_argument(
        "--scenario",
        choices=["minimal", "standard", "large", "edge-cases"],
        default=os.getenv("E2E_TEST_SCENARIO", "standard"),
        help="Test scenario to run (default: standard)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("E2E_TEST_TIMEOUT", "600")),
        help="Test timeout in seconds (default: 600)",
    )

    args = parser.parse_args()

    print("🧪 SBIR ETL E2E Test Runner")
    print("=" * 60)

    # Environment checks
    if not check_environment():
        return 1

    if not check_macbook_air_resources():
        return 1

    # Run tests
    exit_code = run_e2e_tests(args.scenario, args.timeout)

    # Final status
    if exit_code == 0:
        print("\n🎉 All E2E tests completed successfully!")
    else:
        print(f"\n💥 E2E tests failed with exit code {exit_code}")
        print("Check the logs above for details.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
