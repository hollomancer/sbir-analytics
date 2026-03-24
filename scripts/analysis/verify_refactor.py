import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path.cwd()))

try:
    print("Checking imports...")

    from sbir_etl.validators.district import validate_district_resolution  # noqa: F401

    print("✅ Successfully imported src.validators.district.validate_district_resolution")

    from sbir_etl.enrichers.matching import ResearcherMatcher  # noqa: F401

    print("✅ Successfully imported src.enrichers.matching.ResearcherMatcher")

    from sbir_etl.utils.monitoring.alerts import AlertCollector  # noqa: F401

    print("✅ Successfully imported src.utils.monitoring.alerts.AlertCollector")

    from sbir_etl.utils.statistical_reporter import StatisticalReporter  # noqa: F401

    print("✅ Successfully imported src.utils.statistical_reporter.StatisticalReporter")

    print("\nAll imports successful!")

except ImportError as e:
    print(f"\n❌ Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    sys.exit(1)
