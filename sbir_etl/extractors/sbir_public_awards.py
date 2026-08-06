"""Canonical materialization of the public SBIR.gov award CSV.

Epistemic tier: pipelines. The materializer faithfully normalizes source
columns and collapses published editions using the versioned award identity;
it does not classify technology or infer outcomes.
"""

import hashlib
import logging
from pathlib import Path

import pandas as pd

from sbir_etl.identity.sbir_awards import (
    SBIR_AWARD_KEY_VERSION,
    sbir_award_grain_key,
    stable_sbir_award_id,
)


EPISTEMIC_TIER = "pipelines"
logger = logging.getLogger(__name__)

NORMALIZED_SBIR_AWARD_COLUMNS = (
    "award_id",
    "award_key",
    "award_key_version",
    "agency_tracking_number",
    "contract_number",
    "company",
    "title",
    "agency",
    "branch",
    "phase",
    "program",
    "award_date",
    "recorded_end_date",
    "uei",
    "amount",
    "abstract",
    "row_hash",
    "source_edition_count",
    "source_edition_variants",
    "public_id_award_count",
    "naics_code",
    "psc_code",
    "office",
    "cet",
    "source_url",
    "solicitation_number",
    "topic_code",
    "duns",
    "award_year",
    "solicitation_year",
    "source_row",
)


def _pick(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([None] * len(df), index=df.index)


def _nullable_year(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("Int64")


def _normalize_source_rows(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    out["award_id"] = raw.apply(stable_sbir_award_id, axis=1)
    out["award_key"] = raw.apply(sbir_award_grain_key, axis=1)
    out["award_key_version"] = SBIR_AWARD_KEY_VERSION
    out["agency_tracking_number"] = _pick(raw, "Agency Tracking Number", "agency_tracking_number")
    out["contract_number"] = _pick(raw, "Contract", "contract_number", "contract")
    out["company"] = _pick(raw, "Company", "company", "recipient_name")
    out["title"] = _pick(raw, "Award Title", "title")
    out["agency"] = _pick(raw, "Agency", "agency")
    out["branch"] = _pick(raw, "Branch", "branch", "sub_agency")
    out["phase"] = _pick(raw, "Phase", "phase")
    out["program"] = _pick(raw, "Program", "program")
    out["award_date"] = pd.to_datetime(
        _pick(raw, "Proposal Award Date", "award_date", "proposal_award_date"),
        errors="coerce",
    ).dt.date
    out["recorded_end_date"] = pd.to_datetime(
        _pick(
            raw,
            "Contract End Date",
            "period_of_performance_end",
            "recorded_end_date",
            "contract_end_date",
        ),
        errors="coerce",
    ).dt.date
    out["uei"] = _pick(raw, "UEI", "uei", "recipient_uei")
    out["amount"] = pd.to_numeric(
        _pick(raw, "Award Amount", "amount").astype(str).str.replace(r"[$,]", "", regex=True),
        errors="coerce",
    )
    out["abstract"] = _pick(raw, "Abstract", "abstract")
    out["naics_code"] = _pick(raw, "NAICS", "naics_code")
    out["psc_code"] = _pick(raw, "PSC", "psc_code", "product_or_service_code")
    out["office"] = _pick(raw, "Office", "office", "awarding_office_name")
    out["cet"] = _pick(raw, "CET", "cet")
    out["source_url"] = _pick(raw, "source_url", "SBIR URL")
    out["solicitation_number"] = _pick(raw, "Solicitation Number", "solicitation_number")
    out["topic_code"] = _pick(raw, "Topic Code", "topic_code")

    # Preserve the procurement packet's established row-hash contract. Extra
    # canonical source fields below do not alter change detection.
    row_hash_columns = list(out.columns)
    material = out[row_hash_columns].astype("string").fillna("").agg("|".join, axis=1)
    out["row_hash"] = material.map(lambda value: hashlib.sha256(value.encode()).hexdigest())

    out["duns"] = _pick(raw, "Duns", "duns", "recipient_duns")
    source_year = _nullable_year(_pick(raw, "Award Year", "award_year"))
    date_year = pd.to_datetime(out["award_date"], errors="coerce").dt.year.astype("Int64")
    out["award_year"] = source_year.combine_first(date_year)
    out["solicitation_year"] = _nullable_year(_pick(raw, "Solicitation Year", "solicitation_year"))
    out["source_row"] = pd.to_numeric(_pick(raw, "source_row"), errors="coerce").astype("Int64")
    return out


def _collapse_source_editions(out: pd.DataFrame) -> pd.DataFrame:
    """Collapse normalized source rows without re-normalizing their identity."""

    edition_counts = out.groupby("award_key")["award_key"].transform("size")
    edition_variants = out.groupby("award_key")["row_hash"].transform("nunique")
    out["source_edition_count"] = edition_counts
    out["source_edition_variants"] = edition_variants
    duplicate_editions = edition_counts.gt(1)
    if duplicate_editions.any():
        logger.warning(
            "Collapsing %d SBIR source rows across %d stable award keys",
            int(duplicate_editions.sum()),
            int(out.loc[duplicate_editions, "award_key"].nunique()),
        )
        out = (
            out.assign(
                _end_sort=pd.to_datetime(out["recorded_end_date"], errors="coerce"),
                _amount_sort=pd.to_numeric(out["amount"], errors="coerce"),
            )
            .sort_values(
                ["award_key", "_end_sort", "_amount_sort", "row_hash"],
                kind="stable",
                na_position="first",
            )
            .drop_duplicates("award_key", keep="last")
            .drop(columns=["_end_sort", "_amount_sort"])
        )
    out["public_id_award_count"] = out.groupby("award_id")["award_key"].transform("nunique")
    return out.loc[:, list(NORMALIZED_SBIR_AWARD_COLUMNS)].reset_index(drop=True)


def normalize_sbir_awards(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize SBIR.gov rows and collapse source editions to award grain."""

    if raw.empty:
        return pd.DataFrame(columns=NORMALIZED_SBIR_AWARD_COLUMNS)
    return _collapse_source_editions(_normalize_source_rows(raw))


def load_sbir_awards_csv(path: Path, *, chunk_size: int = 50_000) -> pd.DataFrame:
    """Load a public export in bounded raw-data chunks.

    Source identifiers remain strings, and edition collapse happens only after
    all chunks are normalized so the result is independent of chunk boundaries.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    chunks: list[pd.DataFrame] = []
    source_row = 2
    reader = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        chunksize=chunk_size,
        low_memory=False,
    )
    for raw in reader:
        raw["source_row"] = pd.Series(
            range(source_row, source_row + len(raw)),
            index=raw.index,
            dtype="Int64",
        )
        source_row += len(raw)
        chunks.append(_normalize_source_rows(raw))

    if not chunks:
        return pd.DataFrame(columns=NORMALIZED_SBIR_AWARD_COLUMNS)
    return _collapse_source_editions(pd.concat(chunks, ignore_index=True))


__all__ = [
    "EPISTEMIC_TIER",
    "NORMALIZED_SBIR_AWARD_COLUMNS",
    "load_sbir_awards_csv",
    "normalize_sbir_awards",
]
