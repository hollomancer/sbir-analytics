"""Local data-file discovery and resolution.

Formerly an S3-first resolver. The server now stores all source data on local
disk (see docs/deployment/aws-decommission-plan.md), so these helpers locate
files under the configured data root instead.

The module and its public function names are unchanged because many call sites
import from here; only the storage backend changed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"


def get_data_root() -> Path:
    """Root directory for all source data, overridable per deployment."""
    return Path(os.getenv(DATA_ROOT_ENV, DEFAULT_DATA_ROOT))


def resolve_data_path(
    path: str | Path,
    local_fallback: Path | None = None,
    prefer_local: bool = False,
) -> Path:
    """Resolve a data file path, falling back to *local_fallback* if needed.

    Args:
        path: Path to the desired file.
        local_fallback: Alternative path to use when *path* does not exist.
        prefer_local: Check *local_fallback* before *path*.

    Returns:
        Path to an existing file.

    Raises:
        FileNotFoundError: If neither path exists.
    """
    if prefer_local and local_fallback and local_fallback.exists():
        logger.debug(f"Using local file (prefer_local=True): {local_fallback}")
        return local_fallback

    primary = Path(path)
    if primary.exists():
        return primary

    if local_fallback and local_fallback.exists():
        logger.info(f"Using local fallback: {local_fallback}")
        return local_fallback

    raise FileNotFoundError(f"File not found: {primary}")


def _newest(paths: list[Path]) -> Path | None:
    """Newest path by modification time, or None when nothing exists."""
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def find_latest_sbir_awards(root: Path | None = None) -> str | None:
    """Find the most recent SBIR awards CSV.

    Prefers the canonical ``award_data.csv`` and falls back to the newest dated
    vintage under ``history/`` (see docs/data/awards-refresh.md).
    """
    base = (root or get_data_root()) / "raw" / "sbir"

    canonical = base / "award_data.csv"
    if canonical.is_file():
        return str(canonical)

    vintages = sorted(
        (d for d in (base / "history").glob("*") if (d / "award_data.csv").is_file()),
        key=lambda d: d.name,
    )
    if vintages:
        latest = vintages[-1] / "award_data.csv"
        logger.info(f"Using SBIR awards vintage: {latest}")
        return str(latest)

    logger.warning(f"No SBIR awards CSV found under {base}")
    return None


def find_latest_usaspending_dump(
    root: Path | None = None,
    database_type: str = "full",
) -> str | None:
    """Find the most recent USAspending database dump.

    Args:
        root: Data root; defaults to the configured data root.
        database_type: ``"full"`` or ``"test"`` (the subset dump).
    """
    if database_type == "full":
        pattern = "usaspending-db_*.zip"
    elif database_type == "test":
        pattern = "usaspending-db-subset_*.zip"
    else:
        logger.warning(f"Unknown database_type: {database_type}")
        return None

    base = (root or get_data_root()) / "usaspending"
    latest = _newest(list(base.rglob(pattern)))
    if latest is None:
        logger.warning(f"No USAspending {database_type} dump found under {base}")
        return None

    logger.info(f"Found latest USAspending {database_type} dump: {latest}")
    return str(latest)


def find_latest_recipient_lookup_parquet(root: Path | None = None) -> str | None:
    """Find the most recent recipient_lookup parquet.

    This is the extracted recipient data rather than the full dump.
    """
    base = (root or get_data_root()) / "raw" / "usaspending" / "recipient_lookup"
    latest = _newest(list(base.rglob("*.parquet")))
    if latest is None:
        logger.warning(f"No recipient_lookup parquet found under {base}")
        return None

    logger.info(f"Found latest recipient_lookup parquet: {latest}")
    return str(latest)


def find_latest_sam_gov_parquet(root: Path | None = None) -> str | None:
    """Find the most recent SAM.gov entity parquet.

    Prefers the canonical file over the partial one that a short paginated
    fallback writes, so an incomplete dataset never shadows a full one.
    """
    base = (root or get_data_root()) / "raw" / "sam_gov"

    canonical = base / "sam_entity_records.parquet"
    if canonical.is_file():
        return str(canonical)

    # A short paginated fallback writes sam_entity_records_partial.parquet;
    # it must never become the enrichment source on a host with no canonical
    # file, which would defeat the downloader's overwrite guard.
    dated = _newest(
        [
            path
            for path in base.glob("sam_entity_records_*.parquet")
            if path.name != "sam_entity_records_partial.parquet"
        ]
    )
    if dated is not None:
        logger.info(f"Found SAM.gov parquet: {dated}")
        return str(dated)

    logger.warning(f"No SAM.gov parquet found under {base}")
    return None


@dataclass
class SbirAwardsSource:
    """Metadata about a resolved SBIR awards CSV source."""

    path: Path
    origin: str  # "local", "vintage", or "download"
    vintage_date: str | None = None


def _sidecar_date(csv_path: Path) -> str | None:
    """Read the download date from a CSV's ``.meta.json`` sidecar, if present."""
    import json

    sidecar = csv_path.with_name(csv_path.stem + ".meta.json")
    if not sidecar.is_file():
        return None
    try:
        downloaded = json.loads(sidecar.read_text()).get("downloaded_at", "")
        return downloaded[:10] or None
    except (OSError, json.JSONDecodeError):
        return None


def resolve_sbir_awards_csv(
    download_url: str = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
    local_path: Path | None = None,
) -> SbirAwardsSource:
    """Resolve the SBIR awards CSV: local first, then download.

    Resolution order:
    1. The canonical CSV or newest vintage under the data root
    2. Direct HTTP download from *download_url*
    3. *local_path* if provided and it exists

    Raises:
        FileNotFoundError: If no source could be resolved.
    """
    import re
    import tempfile

    import httpx

    found = find_latest_sbir_awards()
    if found:
        path = Path(found)
        date_match = re.search(r"history/(\d{4}-\d{2}-\d{2})/", found)
        if date_match:
            return SbirAwardsSource(path=path, origin="vintage", vintage_date=date_match.group(1))
        # The canonical file carries its date in a sidecar rather than its path.
        return SbirAwardsSource(path=path, origin="local", vintage_date=_sidecar_date(path))

    logger.info(f"No local CSV available; downloading from {download_url}")
    try:
        with httpx.Client(timeout=600, follow_redirects=True) as client:
            response = client.get(download_url)
            response.raise_for_status()

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", prefix="sbir_awards_", delete=False
        ) as tmp_file:
            tmp_file.write(response.content)
            tmp = Path(tmp_file.name)
        size_mb = tmp.stat().st_size / 1024 / 1024
        logger.info(f"Downloaded {size_mb:.1f} MB to {tmp}")
        return SbirAwardsSource(path=tmp, origin="download")
    except Exception as e:
        logger.warning(f"Download failed: {e}")

    if local_path and local_path.exists():
        logger.info(f"Using local fallback: {local_path}")
        return SbirAwardsSource(path=local_path, origin="local")

    raise FileNotFoundError(
        f"Could not resolve SBIR awards CSV locally, by download ({download_url}), "
        f"or at {local_path}"
    )


def check_sbir_data_freshness(
    source: SbirAwardsSource,
    max_award_date: str | None,
    days: int,
    *,
    vintage_slack_days: int = 3,
    data_slack_days: int = 14,
) -> list[str]:
    """Check whether SBIR bulk data is fresh enough for a reporting window.

    Runs two independent checks:
    1. **Vintage date** — did the scheduled download job run recently?
    2. **Max award date in data** — is the underlying SBIR.gov dataset current?

    Args:
        source: Resolved data source with an optional vintage date.
        max_award_date: The most recent ``Proposal Award Date`` in the dataset.
        days: The reporting window in days (e.g. 7 for weekly).
        vintage_slack_days: Allowed slack beyond *days* for the vintage date.
        data_slack_days: Allowed slack beyond *days* for max award date.

    Returns:
        List of warning strings (empty if data is fresh).
    """
    from datetime import UTC, datetime

    from .date_utils import parse_date

    warnings: list[str] = []
    now = datetime.now(UTC).replace(tzinfo=None)

    if source.vintage_date:
        key_dt = parse_date(source.vintage_date)
        if key_dt:
            key_datetime = datetime(key_dt.year, key_dt.month, key_dt.day)
            age_days = (now - key_datetime).days
            if age_days > days + vintage_slack_days:
                warnings.append(
                    f"Local data is {age_days} days old (vintage: {source.vintage_date}). "
                    f"The scheduled download job may have failed."
                )

    if max_award_date:
        max_dt = parse_date(max_award_date)
        if max_dt:
            max_datetime = datetime(max_dt.year, max_dt.month, max_dt.day)
            data_age = (now - max_datetime).days
            if data_age > days + data_slack_days:
                warnings.append(
                    f"Most recent award in data is from {max_award_date} "
                    f"({data_age} days ago). SBIR.gov bulk data may not have "
                    f"been updated recently."
                )

    return warnings
