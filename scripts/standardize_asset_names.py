#!/usr/bin/env python3
"""
Script to standardize asset names across the SBIR ETL pipeline.

This script applies the standardized naming conventions defined in
src/assets/asset_naming_standards.py to all asset files.

Usage:
    python scripts/standardize_asset_names.py [--dry-run] [--file <specific_file>]
"""

import argparse
import re
from pathlib import Path

from src.assets.asset_naming_standards import ASSET_RENAMING_MAP, GROUP_RENAMING_MAP


def find_asset_files() -> list[Path]:
    """Find all asset files in the src/assets directory."""
    assets_dir = Path("src/assets")
    return [
        f
        for f in assets_dir.glob("*.py")
        if f.name != "__init__.py" and f.name != "asset_naming_standards.py"
    ]


def update_asset_definitions(file_path: Path, dry_run: bool = False) -> list[str]:
    """
    Update asset definitions in a file to use standardized names.

    Returns:
        List of changes made
    """
    changes = []

    with open(file_path) as f:
        content = f.read()

    original_content = content

    # Update @asset decorators and function definitions
    for old_name, new_name in ASSET_RENAMING_MAP.items():
        if old_name == new_name:
            continue

        # Update function definitions
        func_pattern = rf"def {re.escape(old_name)}\("
        if re.search(func_pattern, content):
            content = re.sub(func_pattern, f"def {new_name}(", content)
            changes.append(f"Renamed function: {old_name} -> {new_name}")

        # Update asset name parameters in decorators
        name_pattern = rf'name="{re.escape(old_name)}"'
        if re.search(name_pattern, content):
            content = re.sub(name_pattern, f'name="{new_name}"', content)
            changes.append(f"Updated asset name parameter: {old_name} -> {new_name}")

        # Update asset references in dependencies
        dep_patterns = [
            rf'AssetIn\("{re.escape(old_name)}"\)',
            rf'asset="{re.escape(old_name)}"',
            rf'deps=\["{re.escape(old_name)}"\]',
            rf'"{re.escape(old_name)}"',
        ]

        for pattern in dep_patterns:
            if re.search(pattern, content):
                content = re.sub(pattern, pattern.replace(old_name, new_name), content)
                changes.append(f"Updated asset reference: {old_name} -> {new_name}")

    # Update group names
    for old_group, new_group in GROUP_RENAMING_MAP.items():
        if old_group == new_group:
            continue

        group_pattern = rf'group_name="{re.escape(old_group)}"'
        if re.search(group_pattern, content):
            content = re.sub(group_pattern, f'group_name="{new_group}"', content)
            changes.append(f"Updated group name: {old_group} -> {new_group}")

    # Write changes if not dry run
    if not dry_run and content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        changes.append(f"File updated: {file_path}")

    return changes


def update_job_definitions(dry_run: bool = False) -> list[str]:
    """Update job definitions to use new asset names."""
    changes = []
    jobs_dir = Path("src/assets/jobs")

    for job_file in jobs_dir.glob("*.py"):
        with open(job_file) as f:
            content = f.read()

        original_content = content

        # Update asset selections and imports
        for old_name, new_name in ASSET_RENAMING_MAP.items():
            if old_name == new_name:
                continue

            # Update import statements
            import_pattern = rf"from .* import .*{re.escape(old_name)}"
            if re.search(import_pattern, content):
                content = re.sub(re.escape(old_name), new_name, content)
                changes.append(f"Updated import in {job_file}: {old_name} -> {new_name}")

            # Update AssetSelection.keys()
            key_pattern = rf'"{re.escape(old_name)}"'
            if re.search(key_pattern, content):
                content = re.sub(key_pattern, f'"{new_name}"', content)
                changes.append(f"Updated asset key in {job_file}: {old_name} -> {new_name}")

        # Update group selections
        for old_group, new_group in GROUP_RENAMING_MAP.items():
            if old_group == new_group:
                continue

            group_pattern = rf'AssetSelection\.groups\("{re.escape(old_group)}"\)'
            if re.search(group_pattern, content):
                content = re.sub(group_pattern, f'AssetSelection.groups("{new_group}")', content)
                changes.append(f"Updated group selection in {job_file}: {old_group} -> {new_group}")

        if not dry_run and content != original_content:
            with open(job_file, "w") as f:
                f.write(content)
            changes.append(f"Job file updated: {job_file}")

    return changes


def main():
    """Main function to run the standardization script."""
    parser = argparse.ArgumentParser(description="Standardize asset names in SBIR ETL pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--file", help="Process only a specific file")

    args = parser.parse_args()

    all_changes = []

    if args.file:
        # Process specific file
        file_path = Path(args.file)
        if file_path.exists():
            changes = update_asset_definitions(file_path, args.dry_run)
            all_changes.extend(changes)
        else:
            print(f"File not found: {args.file}")
            return
    else:
        # Process all asset files
        asset_files = find_asset_files()

        for file_path in asset_files:
            print(f"Processing {file_path}...")
            changes = update_asset_definitions(file_path, args.dry_run)
            all_changes.extend(changes)

        # Update job definitions
        print("Processing job definitions...")
        job_changes = update_job_definitions(args.dry_run)
        all_changes.extend(job_changes)

    # Print summary
    if args.dry_run:
        print(f"\nDRY RUN - {len(all_changes)} changes would be made:")
    else:
        print(f"\n{len(all_changes)} changes made:")

    for change in all_changes:
        print(f"  - {change}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
