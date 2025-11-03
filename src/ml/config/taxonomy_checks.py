"""
CLI utility to run CET taxonomy completeness checks.

This module provides a small command-line interface to:
- load the CET taxonomy via `TaxonomyLoader`
- run lightweight completeness checks
- print a human-readable summary
- optionally persist a checks JSON file suitable for CI / automated asset checks
- optionally fail (non-zero exit) when issues are detected

Usage (from repository root):
    python -m src.ml.config.taxonomy_checks --config-dir config/cet --output data/processed/cet_taxonomy_checks.json --fail-on-issues

The CLI is intentionally small and has minimal dependencies so it can be executed
in CI containers that have the project installed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Import the project's TaxonomyLoader. This module lives under src/ml/config and
# depends on the project's models (Pydantic) to validate the taxonomy.
from src.ml.config.taxonomy_loader import TaxonomyConfig, TaxonomyLoader

logger = logging.getLogger("taxonomy_checks")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def run_taxonomy_checks(config_dir: Path | None = None) -> dict[str, Any]:
    """
    Load taxonomy and run completeness checks.

    Args:
        config_dir: Optional path to `config/cet`. If None, TaxonomyLoader default is used.

    Returns:
        A dictionary of results. Keys:
          - version: taxonomy version string
          - cet_count: number of CET areas loaded
          - completeness: the dictionary produced by TaxonomyLoader.validate_taxonomy_completeness
    """
    loader = TaxonomyLoader(config_dir=config_dir) if config_dir else TaxonomyLoader()
    taxonomy: TaxonomyConfig = loader.load_taxonomy()

    # Use loader helper to compute completeness metrics (non-fatal)
    completeness = loader.validate_taxonomy_completeness(taxonomy)

    result: dict[str, Any] = {
        "version": taxonomy.version,
        "cet_count": len(taxonomy.cet_areas),
        "last_updated": taxonomy.last_updated,
        "description": taxonomy.description,
        "completeness": completeness,
    }
    return result


def pretty_print_checks(checks: dict[str, Any], out=None) -> None:
    """
    Print a human-friendly summary of taxonomy checks.

    Args:
        checks: dictionary returned by run_taxonomy_checks()
        out: optional file-like object to write to (defaults to sys.stdout)
    """
    if out is None:
        out = sys.stdout

    version = checks.get("version", "<unknown>")
    cet_count = checks.get("cet_count", 0)
    completeness = checks.get("completeness", {})

    print(f"CET Taxonomy version: {version}", file=out)
    print(f"Total CET areas: {cet_count}", file=out)
    print("", file=out)

    # Present the most useful completeness metrics if present
    total_areas = completeness.get("total_areas", cet_count)
    missing_kw = completeness.get(
        "areas_missing_keywords_count", completeness.get("areas_missing_keywords", [])
    )
    missing_def_count = completeness.get(
        "areas_missing_definition_count", completeness.get("areas_missing_definition", [])
    )
    missing_required = completeness.get("missing_required_fields", False)
    areas_with_parent = completeness.get("areas_with_parent_count", 0)

    # Normalize counts
    try:
        missing_kw_count = (
            int(missing_kw) if isinstance(missing_kw, int | float) else len(missing_kw)
        )
    except Exception:
        missing_kw_count = 0

    try:
        missing_def_count_val = (
            int(missing_def_count)
            if isinstance(missing_def_count, int | float)
            else len(missing_def_count)
        )
    except Exception:
        missing_def_count_val = 0

    print("Completeness summary:", file=out)
    print(f"  - total_areas (reported): {total_areas}", file=out)
    print(f"  - areas_missing_keywords_count: {missing_kw_count}", file=out)
    print(f"  - areas_missing_definition_count: {missing_def_count_val}", file=out)
    print(f"  - areas_with_parent_count: {areas_with_parent}", file=out)
    print(f"  - missing_required_fields: {bool(missing_required)}", file=out)
    print("", file=out)

    # If there are specific area lists include a short sample for debugging
    sample_limit = 10
    mk = completeness.get("areas_missing_keywords", [])
    if mk:
        sample = mk[:sample_limit]
        print(f"  - sample areas missing keywords (up to {sample_limit}): {sample}", file=out)

    md = completeness.get("areas_missing_definition", [])
    if md:
        sample = md[:sample_limit]
        print(f"  - sample areas missing definition (up to {sample_limit}): {sample}", file=out)

    # If the loader provided any free-form issues list include it
    issues = completeness.get("issues") or completeness.get("details") or []
    if issues:
        print("", file=out)
        print("Additional issues:", file=out)
        # If issues is a dict or list, print a concise view
        if isinstance(issues, dict):
            print(json.dumps(issues, indent=2), file=out)
        else:
            for i, it in enumerate(issues):
                if i >= sample_limit:
                    print(f"  ... and {len(issues) - sample_limit} more", file=out)
                    break
                print(f"  - {it}", file=out)


def save_checks_json(checks: dict[str, Any], dest: Path) -> None:
    """
    Save checks dictionary to the provided destination as JSON.

    Args:
        checks: dictionary to write
        dest: Path to output JSON file
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2, ensure_ascii=False)
    logger.info("Wrote taxonomy checks JSON", path=str(dest))


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CET taxonomy completeness checks")
    parser.add_argument(
        "--config-dir",
        "-c",
        type=Path,
        default=None,
        help="Path to `config/cet` directory (defaults to project config/cet)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/processed/cet_taxonomy_checks.json"),
        help="Path to write checks JSON (default: data/processed/cet_taxonomy_checks.json)",
    )
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit with non-zero code if completeness checks report issues",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=21,
        help="Minimum expected CET area count (default: 21). Treated as an issue if fewer areas exist.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable output; still writes checks JSON if --output provided",
    )
    return parser.parse_args(argv)


def main(argv: list | None = None) -> int:
    """
    Execute the CLI. Returns exit code:
      0: no issues (or --fail-on-issues not specified)
      1: failure to load taxonomy or unexpected exception
      2: issues detected and --fail-on-issues specified
    """
    args = parse_args(argv)
    try:
        checks = run_taxonomy_checks(config_dir=args.config_dir)
    except Exception as exc:
        logger.exception("Failed to run taxonomy checks: %s", exc)
        return 1

    # Decide whether the run is considered OK
    completeness = checks.get("completeness", {})
    total_areas = completeness.get("total_areas", checks.get("cet_count", 0))

    # Compute simple issue conditions
    areas_missing_keywords_count = completeness.get("areas_missing_keywords_count", 0)
    areas_missing_definition_count = completeness.get("areas_missing_definition_count", 0)
    missing_required_fields = bool(completeness.get("missing_required_fields", False))

    issues_present = False
    issue_reasons = []

    # If total less than expected threshold
    if args.min_count is not None and int(total_areas) < int(args.min_count):
        issues_present = True
        issue_reasons.append(f"taxonony area count {total_areas} < min_count {args.min_count}")

    if areas_missing_keywords_count and int(areas_missing_keywords_count) > 0:
        issues_present = True
        issue_reasons.append(f"{areas_missing_keywords_count} areas missing keywords")

    if areas_missing_definition_count and int(areas_missing_definition_count) > 0:
        issues_present = True
        issue_reasons.append(f"{areas_missing_definition_count} areas missing definitions")

    if missing_required_fields:
        issues_present = True
        issue_reasons.append("missing required fields detected")

    # Persist checks to output if requested
    if args.output:
        try:
            save_checks_json(checks, args.output)
        except Exception:
            logger.exception("Failed to write checks JSON to %s", args.output)
            return 1

    if not args.quiet:
        pretty_print_checks(checks)

    if issues_present and args.fail_on_issues:
        logger.error("Completeness check failed: %s", "; ".join(issue_reasons))
        return 2

    # Success
    if issues_present:
        logger.warning("Completeness check returned warnings: %s", "; ".join(issue_reasons))
    else:
        logger.info("Completeness check passed")

    return 0


if __name__ == "__main__":
    # When invoked as a script, exit with the CLI result code.
    sys.exit(main())
