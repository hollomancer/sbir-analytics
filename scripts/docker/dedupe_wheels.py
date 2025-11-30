#!/usr/bin/env python3
"""Remove duplicate wheel versions, keeping only the latest."""
import re
from pathlib import Path
from collections import defaultdict

def parse_version(v):
    """Parse version string into comparable tuple."""
    return tuple(int(x) if x.isdigit() else x for x in re.split(r'[.-]', v))

wheels_dir = Path('/wheels')
packages = defaultdict(list)

for wheel in wheels_dir.glob('*.whl'):
    match = re.match(r'^([a-zA-Z0-9_]+)-([0-9.]+[a-zA-Z0-9.]*)-', wheel.name)
    if match:
        pkg_name = match.group(1).lower().replace('_', '-')
        version = match.group(2)
        packages[pkg_name].append((version, wheel))

for pkg_name, versions in packages.items():
    if len(versions) > 1:
        versions.sort(key=lambda x: parse_version(x[0]), reverse=True)
        for _, wheel_path in versions[1:]:
            print(f'Removing duplicate: {wheel_path.name}')
            wheel_path.unlink()
