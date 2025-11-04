#!/usr/bin/env python3
"""Validate Dagster setup by loading definitions and checking assets."""

import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.definitions import defs

    print("✓ Successfully imported Dagster definitions")

    # Check assets
    assets = list(defs.get_all_asset_specs())
    print(f"✓ Found {len(assets)} asset(s):")
    for asset in assets:
        print(f"  - {asset.key}")

    # Check jobs
    jobs = list(defs.get_all_job_defs())
    print(f"✓ Found {len(jobs)} job(s):")
    for job in jobs:
        print(f"  - {job.name}")

    # Check schedules
    schedules = list(defs.get_schedule_defs())
    print(f"✓ Found {len(schedules)} schedule(s):")
    for schedule in schedules:
        print(f"  - {schedule.name} (cron: {schedule.cron_schedule})")

    print("\n✓ Dagster setup is valid and ready to use!")
    print("\nTo launch the Dagster UI, run:")
    print("  dagster dev -f src/definitions.py")
    print("\nOr if using the module:")
    print("  DAGSTER_HOME=. dagster dev -m src.definitions")

except ImportError as e:
    print(f"✗ Failed to import Dagster definitions: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error validating Dagster setup: {e}")
    sys.exit(1)
