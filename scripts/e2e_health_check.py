#!/usr/bin/env python3
"""
E2E Environment Health Check Script

Validates that all required services and dependencies are available
for E2E testing before running the test suite.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_neo4j_connection() -> tuple[bool, str]:
    """Check Neo4j database connectivity."""
    try:
        from neo4j import GraphDatabase

        uri = os.getenv("SBIR_ETL__NEO4J__BOLT_URL", "bolt://neo4j-e2e:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "e2e-password")

        driver = GraphDatabase.driver(uri, auth=(username, password))

        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record and record["test"] == 1:
                driver.close()
                return True, f"Neo4j connection successful at {uri}"
            else:
                driver.close()
                return False, "Neo4j query returned unexpected result"

    except ImportError:
        return False, "Neo4j driver not available (pip install neo4j)"
    except Exception as e:
        return False, f"Neo4j connection failed: {str(e)}"


def check_environment_variables() -> tuple[bool, str]:
    """Check required environment variables."""
    required_vars = [
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "SBIR_ETL__NEO4J__BOLT_URL",
        "ENVIRONMENT",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        return False, f"Missing environment variables: {', '.join(missing_vars)}"

    return True, f"All {len(required_vars)} required environment variables present"


def check_test_data_availability() -> tuple[bool, str]:
    """Check if test data and fixtures are available."""
    test_data_paths = [
        Path("/app/test-data"),
        Path("tests/fixtures"),
        Path("data/raw"),
    ]

    available_paths = []
    for path in test_data_paths:
        if path.exists():
            available_paths.append(str(path))

    if not available_paths:
        return False, "No test data directories found"

    return True, f"Test data available at: {', '.join(available_paths)}"


def check_python_dependencies() -> tuple[bool, str]:
    """Check if required Python packages are available."""
    required_packages = [
        "dagster",
        "pandas",
        "neo4j",
        "pytest",
        "pydantic",
    ]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        return False, f"Missing Python packages: {', '.join(missing_packages)}"

    return True, f"All {len(required_packages)} required packages available"


def check_resource_constraints() -> tuple[bool, str]:
    """Check MacBook Air resource constraints."""
    macbook_air_mode = os.getenv("MACBOOK_AIR_MODE", "true").lower() == "true"

    if not macbook_air_mode:
        return True, "MacBook Air mode disabled - no resource constraints"

    memory_limit_gb = float(os.getenv("MEMORY_LIMIT_GB", "8"))
    cpu_limit = float(os.getenv("CPU_LIMIT", "2.0"))

    warnings = []
    if memory_limit_gb > 8:
        warnings.append(f"Memory limit ({memory_limit_gb}GB) > 8GB")
    if cpu_limit > 2.0:
        warnings.append(f"CPU limit ({cpu_limit}) > 2.0")

    if warnings:
        return False, f"Resource constraints exceeded: {'; '.join(warnings)}"

    return True, f"Resource constraints OK (Memory: {memory_limit_gb}GB, CPU: {cpu_limit})"


def run_health_checks() -> dict[str, tuple[bool, str]]:
    """Run all health checks and return results."""
    checks = {
        "Environment Variables": check_environment_variables,
        "Python Dependencies": check_python_dependencies,
        "Test Data": check_test_data_availability,
        "Resource Constraints": check_resource_constraints,
        "Neo4j Connection": check_neo4j_connection,
    }

    results = {}
    for check_name, check_func in checks.items():
        print(f"🔍 Checking {check_name}...")
        try:
            success, message = check_func()
            results[check_name] = (success, message)

            if success:
                print(f"   ✅ {message}")
            else:
                print(f"   ❌ {message}")

        except Exception as e:
            results[check_name] = (False, f"Check failed with exception: {str(e)}")
            print(f"   💥 Check failed: {str(e)}")

    return results


def main():
    """Main entry point for health check."""
    print("🏥 E2E Environment Health Check")
    print("=" * 50)

    results = run_health_checks()

    print("\n" + "=" * 50)
    print("📋 Health Check Summary")
    print("=" * 50)

    passed = 0
    failed = 0

    for check_name, (success, _message) in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{check_name:20} {status}")
        if success:
            passed += 1
        else:
            failed += 1

    print("-" * 50)
    print(f"Total: {passed + failed}, Passed: {passed}, Failed: {failed}")

    if failed == 0:
        print("\n🎉 All health checks passed! E2E environment is ready.")
        return 0
    else:
        print(f"\n💥 {failed} health check(s) failed. Please fix issues before running E2E tests.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
