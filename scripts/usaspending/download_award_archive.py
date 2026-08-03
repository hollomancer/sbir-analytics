#!/usr/bin/env python3
"""Discover and download a public USAspending Award Data Archive file."""

import argparse
import json
from pathlib import Path

from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.extractors.usaspending_award_archive import (
    discover_full_award_archive,
    download_award_archive,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a public USAspending Contracts_Full or Assistance_Full archive"
    )
    parser.add_argument(
        "--fiscal-year",
        type=int,
        required=True,
        help="Federal fiscal year (explicit because October starts the next fiscal year)",
    )
    parser.add_argument(
        "--type",
        choices=("contracts", "assistance"),
        default="contracts",
        dest="award_type",
    )
    parser.add_argument("--agency", default="all", help="USAspending agency id or 'all'")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    agency = args.agency if args.agency == "all" else int(args.agency)
    destination = args.destination
    if destination is None:
        destination = get_config().paths.resolve_path("transition_award_archive_dir")

    source = discover_full_award_archive(
        args.fiscal_year,
        args.award_type,
        agency=agency,
    )
    logger.info(
        f"USAspending selected {source.file_name} (updated {source.updated_date}); "
        f"downloading to {destination}"
    )
    archive, metadata = download_award_archive(source, destination, force=args.force)
    logger.success(f"Archive ready: {archive}")
    logger.info(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
