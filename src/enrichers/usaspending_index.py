"""Utilities for inspecting a USAspending pg_dump zip and extracting table -> dat file mapping.

This module provides lightweight helpers to parse the included `pruned_data_store_api_dump/toc.dat`
and map logical table names (e.g. `rpt.award_search`, `public.naics`) to the dumped `.dat` files
found inside the provided zip archive. It also provides a convenience to extract a small sample
of a table's data for schema inspection.

Note: This is a pragmatic, defensive parser (we treat the toc as text via `strings()`-style
filtering) and uses heuristics to associate `.dat` filenames with subsequent `TABLE DATA` blocks.
It avoids requiring a running Postgres instance to restore the SQL dump.
"""
from __future__ import annotations

import gzip
import io
import logging
import zipfile
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _read_toc_strings(zip_path: str) -> List[str]:
    """Read the toc.dat file from the zip and return a list of printable string lines.

    We decode with errors='ignore' and split on newlines. This mirrors `strings` to make
    parsing simpler.
    """
    toc_path = "pruned_data_store_api_dump/toc.dat"
    lines: List[str] = []
    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(toc_path) as fh:
            raw = fh.read()
            text = raw.decode("utf-8", errors="ignore")
            # splitlines keeps things tidy
            lines = text.splitlines()
    return lines


def parse_toc_table_dat_map(zip_path: str) -> Dict[str, str]:
    """Parse `toc.dat` in the provided zip and return a mapping {table_name: dat_filename}.

    Heuristic algorithm:
    - Walk lines; keep the most recent line that looks like '<digits>.dat' as `last_dat`.
    - When encountering a line that looks like a fully-qualified table name (contains '.') followed
      by the line 'TABLE DATA' on the next non-empty line, map that table -> last_dat.

    This matches the structure observed in the dump included with this workspace.
    """
    lines = _read_toc_strings(zip_path)
    mapping: Dict[str, str] = {}
    last_dat: Optional[str] = None
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].strip()
        # detect dat filename lines like '5475.dat' or '5525.dat'
        if line.endswith(".dat"):
            last_dat = line
            i += 1
            continue

        # candidate table name (heuristic: contains a dot and no spaces)
        if "." in line and " " not in line and i + 1 < n:
            # check next non-empty line for 'TABLE DATA'
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and lines[j].strip().upper() == "TABLE DATA":
                table_name = line
                if last_dat:
                    mapping[table_name] = last_dat
                else:
                    logger.debug("Found TABLE DATA for %s but no recent .dat file seen", table_name)
                i = j + 1
                continue

        i += 1

    return mapping


def extract_table_sample(zip_path: str, dat_filename: str, n_lines: int = 20) -> List[str]:
    """Extract the first `n_lines` of the given `.dat.gz` entry inside the zip.

    Returns a list of decoded lines (strings). The caller can inspect to infer column layout.
    """
    internal = f"pruned_data_store_api_dump/{dat_filename}"
    sample: List[str] = []
    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(internal) as fh:
            # the files are .gz-compressed streams
            raw = fh.read()
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                    # read as text and split
                    text = gz.read().decode("utf-8", errors="ignore")
                    sample = text.splitlines()[:n_lines]
            except OSError:
                # not a gzip stream; attempt to decode raw bytes
                text = raw.decode("utf-8", errors="ignore")
                sample = text.splitlines()[:n_lines]
    return sample


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", help="Path to usaspending zip file")
    parser.add_argument("--show", help="Table to show sample for (e.g. public.naics)")
    args = parser.parse_args()

    mapping = parse_toc_table_dat_map(args.zip_path)
    print(json.dumps(mapping, indent=2))
    if args.show:
        dat = mapping.get(args.show)
        if not dat:
            print("Table not found in mapping")
        else:
            sample = extract_table_sample(args.zip_path, dat, n_lines=50)
            for ln in sample:
                print(ln)
