"""Fail-closed quarantine-key coverage for unresolved SBIR/STTR awards."""

import re
import unicodedata
from enum import StrEnum
from typing import Any

import pandas as pd

from .identity import IdentityRecoveryError, RecoveryStatus


class QuarantineKeyCoverage(StrEnum):
    """Exhaustive key-availability categories for one unresolved source row."""

    BOTH = "both"
    NAME_STATE_ONLY = "name_state_only"
    ADDRESS_ZIP_ONLY = "address_zip_only"
    NEITHER = "neither"


_SOURCE_REQUIRED = frozenset(
    {
        "source_row_sha256",
        "company_name",
        "state",
        "address1",
        "address2",
        "zip",
    }
)
_RECOVERY_REQUIRED = frozenset({"source_row_sha256", "recovery_status"})
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})
_ZIP_PATTERN = re.compile(r"^(\d{5})(?:[- ]?(\d{4}))?$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CATEGORY_ORDER = tuple(category.value for category in QuarantineKeyCoverage)


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.upper() in _NULL_TEXT else text


def normalize_quarantine_component(value: Any) -> str:
    """Apply the frozen NFKC, uppercase, punctuation, and whitespace rules."""

    text = _text(value)
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text).upper()
    punctuation_spaced = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(punctuation_spaced.split())


def normalize_zip5(value: Any) -> str:
    """Return the first five digits from a valid frozen ZIP or ZIP+4 form."""

    text = unicodedata.normalize("NFKC", _text(value))
    match = _ZIP_PATTERN.fullmatch(text)
    return match.group(1) if match else ""


def _require_columns(frame: pd.DataFrame, required: frozenset[str], *, label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise IdentityRecoveryError(f"{label} is missing required columns: {missing}")


def _fingerprints(frame: pd.DataFrame, *, label: str) -> pd.Series:
    values = frame["source_row_sha256"].map(_text).str.lower()
    if not values.map(lambda value: bool(_FINGERPRINT_PATTERN.fullmatch(value))).all():
        raise IdentityRecoveryError(
            f"{label}.source_row_sha256 must contain complete lowercase SHA-256 values"
        )
    if values.duplicated().any():
        raise IdentityRecoveryError(f"{label}.source_row_sha256 values must be unique")
    return values


def _coverage_category(has_name_state: bool, has_address_zip: bool) -> str:
    if has_name_state and has_address_zip:
        return QuarantineKeyCoverage.BOTH.value
    if has_name_state:
        return QuarantineKeyCoverage.NAME_STATE_ONLY.value
    if has_address_zip:
        return QuarantineKeyCoverage.ADDRESS_ZIP_ONLY.value
    return QuarantineKeyCoverage.NEITHER.value


def build_unresolved_quarantine_key_audit(
    sbir_awards: pd.DataFrame,
    recovery_audit: pd.DataFrame,
) -> pd.DataFrame:
    """Audit exact quarantine-key availability at unresolved source-row grain.

    The function never uses names or addresses to resolve an award identity. It
    reads them only after final recovery status is known and only to establish
    whether an unresolved award can quarantine a colliding control candidate.
    """

    _require_columns(sbir_awards, _SOURCE_REQUIRED, label="SBIR source frame")
    _require_columns(recovery_audit, _RECOVERY_REQUIRED, label="recovery audit")
    source_fingerprints = _fingerprints(sbir_awards, label="SBIR source frame")
    recovery_fingerprints = _fingerprints(recovery_audit, label="recovery audit")

    valid_statuses = {status.value for status in RecoveryStatus}
    statuses = recovery_audit["recovery_status"].map(_text)
    if invalid := sorted(set(statuses) - valid_statuses):
        raise IdentityRecoveryError(f"recovery audit contains invalid statuses: {invalid}")

    source = sbir_awards.loc[:, list(_SOURCE_REQUIRED)].copy()
    source["source_row_sha256"] = source_fingerprints
    recovery = recovery_audit.copy()
    recovery["source_row_sha256"] = recovery_fingerprints
    missing_source_rows = sorted(set(recovery_fingerprints) - set(source_fingerprints))
    if missing_source_rows:
        raise IdentityRecoveryError(
            "recovery audit contains source-row fingerprints absent from the SBIR source"
        )

    unresolved = recovery.loc[
        statuses.ne(RecoveryStatus.RESOLVED_AUTHORITATIVE.value),
        [
            column
            for column in (
                "source_row_sha256",
                "recovery_status",
                "agency",
                "award_year",
                "attempted_adapters",
            )
            if column in recovery.columns
        ],
    ].copy()
    unresolved = unresolved.merge(
        source,
        on="source_row_sha256",
        how="left",
        validate="one_to_one",
        sort=False,
    )

    records: list[dict[str, Any]] = []
    for row in unresolved.itertuples(index=False):
        company_name = normalize_quarantine_component(row.company_name)
        state = normalize_quarantine_component(row.state)
        address_parts = [
            normalized
            for normalized in (
                normalize_quarantine_component(row.address1),
                normalize_quarantine_component(row.address2),
            )
            if normalized
        ]
        address = " ".join(address_parts)
        zip5 = normalize_zip5(row.zip)
        has_name_state = bool(company_name and state)
        has_address_zip = bool(address and zip5)

        record = {
            "source_row_sha256": row.source_row_sha256,
            "recovery_status": row.recovery_status,
            "company_name_key": company_name or None,
            "state_key": state or None,
            "address_key": address or None,
            "zip5_key": zip5 or None,
            "name_state_key": (f"{company_name}|{state}" if has_name_state else None),
            "address_zip_key": f"{address}|{zip5}" if has_address_zip else None,
            "has_name_state_key": has_name_state,
            "has_address_zip_key": has_address_zip,
            "coverage_category": _coverage_category(
                has_name_state,
                has_address_zip,
            ),
        }
        for column in ("agency", "award_year", "attempted_adapters"):
            if hasattr(row, column):
                record[column] = getattr(row, column)
        records.append(record)

    optional_columns = [
        column
        for column in ("agency", "award_year", "attempted_adapters")
        if column in unresolved.columns
    ]
    columns = [
        "source_row_sha256",
        "recovery_status",
        *optional_columns,
        "company_name_key",
        "state_key",
        "address_key",
        "zip5_key",
        "name_state_key",
        "address_zip_key",
        "has_name_state_key",
        "has_address_zip_key",
        "coverage_category",
    ]
    return pd.DataFrame.from_records(records, columns=columns)


def summarize_quarantine_key_coverage(audit: pd.DataFrame) -> pd.DataFrame:
    """Return all four preregistered key-availability categories."""

    required = frozenset({"coverage_category", "has_name_state_key", "has_address_zip_key"})
    _require_columns(audit, required, label="quarantine-key audit")
    counts = audit["coverage_category"].value_counts()
    invalid = sorted(set(counts.index) - set(_CATEGORY_ORDER))
    if invalid:
        raise IdentityRecoveryError(f"quarantine-key audit contains invalid categories: {invalid}")
    for row in audit.itertuples(index=False):
        expected = _coverage_category(
            bool(row.has_name_state_key),
            bool(row.has_address_zip_key),
        )
        if row.coverage_category != expected:
            raise IdentityRecoveryError(
                "quarantine-key audit category disagrees with its key-availability flags"
            )
    return pd.DataFrame(
        {
            "coverage_category": _CATEGORY_ORDER,
            "has_name_state_key": (True, True, False, False),
            "has_address_zip_key": (True, False, True, False),
            "source_rows": tuple(int(counts.get(category, 0)) for category in _CATEGORY_ORDER),
        }
    )


def quarantine_key_gate(audit: pd.DataFrame) -> dict[str, int | bool]:
    """Report the zero-tolerance unresolved-row completeness gate."""

    coverage = summarize_quarantine_key_coverage(audit)
    neither_rows = int(
        coverage.loc[
            coverage["coverage_category"].eq(QuarantineKeyCoverage.NEITHER.value),
            "source_rows",
        ].iloc[0]
    )
    return {
        "passed": neither_rows == 0,
        "unresolved_source_rows": int(len(audit)),
        "unquarantinable_source_rows": neither_rows,
    }


def require_complete_unresolved_quarantine_keys(audit: pd.DataFrame) -> None:
    """Stop before control construction if any unresolved row lacks both keys."""

    gate = quarantine_key_gate(audit)
    if not gate["passed"]:
        raise IdentityRecoveryError(
            "Unresolved-award quarantine-key gate failed: "
            f"{gate['unquarantinable_source_rows']} source rows have neither a complete "
            "name-plus-state key nor a complete address-plus-ZIP key"
        )
