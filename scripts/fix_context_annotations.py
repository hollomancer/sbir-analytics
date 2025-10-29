#!/usr/bin/env python3
"""
Fix Dagster AssetExecutionContext type annotations.

Dagster 1.7+ doesn't allow explicit AssetExecutionContext type annotations
on context parameters. This script removes them.
"""

import re
from pathlib import Path


def fix_file(file_path: Path) -> int:
    """Remove AssetExecutionContext annotations from context parameters."""
    content = file_path.read_text()

    # Pattern to match: context: AssetExecutionContext
    pattern = r"\bcontext:\s*AssetExecutionContext\b"
    replacement = "context"

    new_content = re.sub(pattern, replacement, content)

    if new_content != content:
        file_path.write_text(new_content)
        count = len(re.findall(pattern, content))
        print(f"Fixed {count} annotations in {file_path}")
        return count
    else:
        print(f"No changes needed in {file_path}")
        return 0


if __name__ == "__main__":
    assets_dir = Path(__file__).parent.parent / "src" / "assets"

    # Fix transition_assets.py
    transition_assets = assets_dir / "transition_assets.py"
    if transition_assets.exists():
        count = fix_file(transition_assets)
        print(f"\nTotal: Fixed {count} context annotations")
    else:
        print(f"File not found: {transition_assets}")
