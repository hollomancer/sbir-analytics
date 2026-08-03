"""Source-specific exact award-key adapters for identity recovery."""

import hashlib
import re
import unicodedata
from collections.abc import Callable
from typing import Any

import pandas as pd

from .identity import IdentityRecoveryError


USA_PIID_ADAPTER = "usaspending_piid"
USA_FAIN_ADAPTER = "usaspending_fain"
USA_URI_ADAPTER = "usaspending_uri"
NIH_PROJECT_ADAPTER = "nih_reporter_project_num"
NIH_CORE_PROJECT_ADAPTER = "nih_reporter_core_project_num"
ANY_YEAR = "ANY"

_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})
_USA_SBIR_REQUIRED = frozenset(
    {"source_row_sha256", "agency", "contract", "agency_tracking_number"}
)
_USA_OFFICIAL_REQUIRED = frozenset(
    {
        "official_record_id",
        "awarding_agency",
        "piid",
        "fain",
        "uri",
        "recipient_uei",
        "recipient_duns",
    }
)
_NIH_SBIR_REQUIRED = frozenset(
    {
        "source_row_sha256",
        "agency",
        "contract",
        "agency_tracking_number",
        "award_year",
    }
)
_NIH_OFFICIAL_REQUIRED = frozenset(
    {
        "official_record_id",
        "project_num",
        "core_project_num",
        "fiscal_year",
        "recipient_uei",
        "recipient_duns",
    }
)


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return "" if normalized.upper() in _NULL_TEXT else normalized


def _require_columns(frame: pd.DataFrame, required: frozenset[str], *, label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise IdentityRecoveryError(f"{label} is missing required columns: {missing}")


def canonicalize_agency(value: Any) -> str | None:
    """Canonicalize an agency label without alias inference."""

    text = _text(value)
    if not text:
        return None
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split()) or None


def canonicalize_piid(value: Any) -> str | None:
    """Canonicalize a PIID to its uppercase alphanumeric representation."""

    text = _text(value)
    if not text:
        return None
    return re.sub(r"[^A-Z0-9]", "", text.upper()) or None


def canonicalize_fain_or_uri(value: Any) -> str | None:
    """Canonicalize FAIN/URI text while preserving internal punctuation."""

    text = _text(value).strip(" ,")
    if not text:
        return None
    return " ".join(text.upper().split()) or None


def canonicalize_nih_project_number(value: Any) -> str | None:
    """Canonicalize an NIH project number for an exact structured-key join."""

    text = _text(value)
    if not text:
        return None
    return re.sub(r"[^A-Z0-9]", "", text.upper()) or None


def canonicalize_year(value: Any) -> str | None:
    """Return one four-digit year without deriving or binning it."""

    text = _text(value)
    if re.fullmatch(r"\d{4}", text):
        return text
    return None


def _attempt_record(
    source_row_sha256: str,
    source_key_field: str,
    source_award_key: str,
    adapter: str,
    agency_key: str,
    award_year_key: str,
    canonical_award_key: str,
) -> dict[str, str]:
    serialized = "\x1f".join(
        (
            source_row_sha256,
            source_key_field,
            adapter,
            agency_key,
            award_year_key,
            canonical_award_key,
        )
    )
    return {
        "source_row_sha256": source_row_sha256,
        "recovery_attempt_id": hashlib.sha256(serialized.encode()).hexdigest(),
        "source_key_field": source_key_field,
        "source_award_key": source_award_key,
        "adapter": adapter,
        "agency_key": agency_key,
        "award_year_key": award_year_key,
        "canonical_award_key": canonical_award_key,
    }


def build_usaspending_sbir_attempts(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Create PIID/FAIN/URI attempts from both declared SBIR award-key fields."""

    _require_columns(sbir_awards, _USA_SBIR_REQUIRED, label="SBIR award frame")
    records: list[dict[str, str]] = []
    adapters: tuple[tuple[str, Callable[[Any], str | None]], ...] = (
        (USA_PIID_ADAPTER, canonicalize_piid),
        (USA_FAIN_ADAPTER, canonicalize_fain_or_uri),
        (USA_URI_ADAPTER, canonicalize_fain_or_uri),
    )
    for row in sbir_awards.itertuples(index=False):
        fingerprint = _text(row.source_row_sha256).lower()
        agency = canonicalize_agency(row.agency)
        if not fingerprint or agency is None:
            raise IdentityRecoveryError("SBIR award source fingerprint and agency must be present")
        for source_field in ("contract", "agency_tracking_number"):
            source_value = getattr(row, source_field)
            for adapter, canonicalizer in adapters:
                if award_key := canonicalizer(source_value):
                    records.append(
                        _attempt_record(
                            fingerprint,
                            source_field,
                            _text(source_value),
                            adapter,
                            agency,
                            ANY_YEAR,
                            award_key,
                        )
                    )
    records = list({record["recovery_attempt_id"]: record for record in records}.values())
    return pd.DataFrame.from_records(
        records,
        columns=[
            "source_row_sha256",
            "recovery_attempt_id",
            "source_key_field",
            "source_award_key",
            "adapter",
            "agency_key",
            "award_year_key",
            "canonical_award_key",
        ],
    )


def build_usaspending_official_keys(
    official_awards: pd.DataFrame,
    *,
    source_digest: str,
    snapshot_date: str,
) -> pd.DataFrame:
    """Expand February award-search rows to exact PIID/FAIN/URI key rows."""

    _require_columns(
        official_awards,
        _USA_OFFICIAL_REQUIRED,
        label="USAspending official award frame",
    )
    digest = _text(source_digest).lower()
    snapshot = _text(snapshot_date)
    if not digest or not snapshot:
        raise IdentityRecoveryError("USAspending source digest and snapshot date are required")

    records: list[dict[str, Any]] = []
    adapters: tuple[tuple[str, str, Callable[[Any], str | None]], ...] = (
        (USA_PIID_ADAPTER, "piid", canonicalize_piid),
        (USA_FAIN_ADAPTER, "fain", canonicalize_fain_or_uri),
        (USA_URI_ADAPTER, "uri", canonicalize_fain_or_uri),
    )
    for row in official_awards.itertuples(index=False):
        agency = canonicalize_agency(row.awarding_agency)
        record_id = _text(row.official_record_id)
        if agency is None or not record_id:
            raise IdentityRecoveryError(
                "Every USAspending official award must have agency and record ID"
            )
        for adapter, column, canonicalizer in adapters:
            if award_key := canonicalizer(getattr(row, column)):
                records.append(
                    {
                        "adapter": adapter,
                        "agency_key": agency,
                        "award_year_key": ANY_YEAR,
                        "canonical_award_key": award_key,
                        "official_record_id": record_id,
                        "recipient_uei": row.recipient_uei,
                        "recipient_duns": row.recipient_duns,
                        "source_digest": digest,
                        "snapshot_date": snapshot,
                    }
                )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "adapter",
            "agency_key",
            "award_year_key",
            "canonical_award_key",
            "official_record_id",
            "recipient_uei",
            "recipient_duns",
            "source_digest",
            "snapshot_date",
        ],
    )


def build_nih_sbir_attempts(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Create exact NIH project-number attempts for HHS SBIR award keys."""

    _require_columns(sbir_awards, _NIH_SBIR_REQUIRED, label="HHS SBIR award frame")
    records: list[dict[str, str]] = []
    for row in sbir_awards.itertuples(index=False):
        fingerprint = _text(row.source_row_sha256).lower()
        agency = canonicalize_agency(row.agency)
        year = canonicalize_year(row.award_year)
        if not fingerprint or agency is None:
            raise IdentityRecoveryError("HHS source fingerprint and agency must be present")
        for source_field in ("contract", "agency_tracking_number"):
            award_key = canonicalize_nih_project_number(getattr(row, source_field))
            if award_key is None:
                continue
            if year is None:
                raise IdentityRecoveryError("NIH project recovery requires a four-digit award year")
            for adapter in (NIH_PROJECT_ADAPTER, NIH_CORE_PROJECT_ADAPTER):
                records.append(
                    _attempt_record(
                        fingerprint,
                        source_field,
                        _text(getattr(row, source_field)),
                        adapter,
                        agency,
                        year,
                        award_key,
                    )
                )
    records = list({record["recovery_attempt_id"]: record for record in records}.values())
    return pd.DataFrame.from_records(
        records,
        columns=[
            "source_row_sha256",
            "recovery_attempt_id",
            "source_key_field",
            "source_award_key",
            "adapter",
            "agency_key",
            "award_year_key",
            "canonical_award_key",
        ],
    )


def build_nih_official_keys(
    official_projects: pd.DataFrame,
    *,
    source_digest: str,
    snapshot_date: str,
) -> pd.DataFrame:
    """Convert normalized NIH RePORTER project rows to resolver input."""

    _require_columns(
        official_projects,
        _NIH_OFFICIAL_REQUIRED,
        label="NIH RePORTER official project frame",
    )
    digest = _text(source_digest).lower()
    snapshot = _text(snapshot_date)
    if not digest or not snapshot:
        raise IdentityRecoveryError("NIH source digest and snapshot date are required")

    records: list[dict[str, Any]] = []
    for row in official_projects.itertuples(index=False):
        year = canonicalize_year(row.fiscal_year)
        record_id = _text(row.official_record_id)
        if year is None or not record_id:
            raise IdentityRecoveryError("Every NIH project must have fiscal_year and record ID")
        for adapter, source_column in (
            (NIH_PROJECT_ADAPTER, "project_num"),
            (NIH_CORE_PROJECT_ADAPTER, "core_project_num"),
        ):
            award_key = canonicalize_nih_project_number(getattr(row, source_column))
            if award_key is None:
                continue
            records.append(
                {
                    "adapter": adapter,
                    "agency_key": canonicalize_agency("Department of Health and Human Services"),
                    "award_year_key": year,
                    "canonical_award_key": award_key,
                    "official_record_id": record_id,
                    "recipient_uei": row.recipient_uei,
                    "recipient_duns": row.recipient_duns,
                    "source_digest": digest,
                    "snapshot_date": snapshot,
                }
            )
    return pd.DataFrame.from_records(
        records,
        columns=[
            "adapter",
            "agency_key",
            "award_year_key",
            "canonical_award_key",
            "official_record_id",
            "recipient_uei",
            "recipient_duns",
            "source_digest",
            "snapshot_date",
        ],
    )
