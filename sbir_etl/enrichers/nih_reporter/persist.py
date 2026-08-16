"""Persist NIH RePORTER project rows to the derived award table.

Epistemic tier: pipelines. Official row id is ``appl_id``. Award-level
replace uses ``(canonical project_num, fy)``; multiple ``appl_id``s for one
upsert key are retained, not collapsed.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord
from sbir_etl.utils.cloud_storage import get_data_root
from sbir_etl.utils.data.file_io import save_dataframe_parquet
from sbir_etl.utils.path_utils import ensure_parent_dir


EPISTEMIC_TIER = "pipelines"

NIH_REPORTER_AWARDS_NAME = "nih_reporter_awards.parquet"


def nih_reporter_awards_path() -> Path:
    """Canonical location of the persisted RePORTER project table."""

    return get_data_root() / "derived" / NIH_REPORTER_AWARDS_NAME


def upsert_key_text(canonical_project_num: str, fy: int) -> str:
    """Stable string form of the award-level upsert key."""

    return f"{canonical_project_num}|{fy}"


def upsert_nih_reporter_awards(
    records: Sequence[NIHReporterRecord],
    *,
    award_id: str,
    path: Path | None = None,
) -> Path | None:
    """Replace persisted rows for each upsert key present in ``records``.

    An empty fetch does not delete existing rows. Returns the path written,
    or ``None`` when there is nothing to persist.
    """

    rows: list[dict[str, Any]] = []
    keys: set[str] = set()
    for record in records:
        key = record.upsert_key()
        if key is None:
            continue
        mapping = record.to_mapping()
        mapping["award_id"] = award_id
        mapping["project_num_canonical"] = key[0]
        mapping["upsert_key"] = upsert_key_text(key[0], key[1])
        rows.append(mapping)
        keys.add(mapping["upsert_key"])
    if not rows:
        return None

    dest = path or nih_reporter_awards_path()
    ensure_parent_dir(dest)
    existing = _load_existing(dest)
    if not existing.empty and "upsert_key" in existing.columns:
        existing = existing.loc[~existing["upsert_key"].isin(keys)].copy()
    combined = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    return save_dataframe_parquet(combined, dest, index=False)


def _load_existing(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()
