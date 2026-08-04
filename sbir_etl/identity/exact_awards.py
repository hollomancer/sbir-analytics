"""Exact award-key recovery for identifier-poor SBIR/STTR award rows.

Epistemic tier: primitives. This module does not read sources, construct
controls, match firms, or run a study. Source adapters canonicalize their
official award keys before calling :func:`resolve_award_identities`.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, cast

import pandas as pd

from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


EPISTEMIC_TIER = "primitives"


class ExactAwardIdentityProfile(StrEnum):
    """Named, immutable exact-key resolution behavior."""

    EXACT_AWARD_KEY_V1 = "exact-award-key-v1"


EXACT_AWARD_IDENTITY_VERSION = ExactAwardIdentityProfile.EXACT_AWARD_KEY_V1.value


class IdentityRecoveryError(ValueError):
    """Raised when an input cannot support fail-closed identity recovery."""


class RecoveryStatus(StrEnum):
    """Exhaustive outcomes for one SBIR source-row recovery attempt."""

    RESOLVED_AUTHORITATIVE = "resolved_authoritative"
    UNRESOLVED_NO_MATCH = "unresolved_no_match"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    UNRESOLVED_MISSING_IDENTIFIER = "unresolved_missing_identifier"


_JOIN_COLUMNS = ("adapter", "agency_key", "award_year_key", "canonical_award_key")
_SBIR_REQUIRED = frozenset({"source_row_sha256", "recovery_attempt_id", *_JOIN_COLUMNS})
_OFFICIAL_REQUIRED = frozenset(
    {
        *_JOIN_COLUMNS,
        "official_record_id",
        "recipient_uei",
        "recipient_duns",
        "source_digest",
        "snapshot_date",
    }
)
_ATTEMPT_AUDIT_REQUIRED = frozenset(
    {
        "source_row_sha256",
        "adapter",
        "recovery_status",
        "resolved_ueis",
        "resolved_duns",
        "official_record_ids",
        "official_source_digests",
        "official_snapshot_dates",
    }
)
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})


def _require_profile(profile: ExactAwardIdentityProfile) -> ExactAwardIdentityProfile:
    try:
        return ExactAwardIdentityProfile(profile)
    except ValueError as exc:
        raise IdentityRecoveryError(f"unsupported exact award identity profile: {profile}") from exc


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip()
    return "" if normalized.upper() in _NULL_TEXT else normalized


def _require_columns(frame: pd.DataFrame, required: frozenset[str], *, label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise IdentityRecoveryError(f"{label} is missing required columns: {missing}")


def _require_nonblank(frame: pd.DataFrame, columns: Iterable[str], *, label: str) -> None:
    for column in columns:
        if frame[column].map(_text).eq("").any():
            raise IdentityRecoveryError(f"{label}.{column} contains a blank value")


def _normalized_join_key(row: pd.Series) -> tuple[str, str, str, str]:
    return tuple(_text(row[column]).upper() for column in _JOIN_COLUMNS)  # type: ignore[return-value]


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self.parent[second] = first


def _classify_identifiers(
    matches: pd.DataFrame,
) -> tuple[RecoveryStatus, tuple[str, ...], tuple[str, ...]]:
    identifiers = _DisjointSet()
    normalized_rows: list[tuple[str | None, str | None]] = []

    for row in matches.itertuples(index=False):
        uei = normalize_uei(row.recipient_uei)
        duns = normalize_duns(row.recipient_duns)
        if uei is None and duns is None:
            return RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER, (), ()
        normalized_rows.append((uei, duns))
        tokens = [
            token
            for token in (
                f"UEI:{uei}" if uei else None,
                f"DUNS:{duns}" if duns else None,
            )
            if token
        ]
        for token in tokens:
            identifiers.add(token)
        if len(tokens) == 2:
            identifiers.union(tokens[0], tokens[1])

    components = {identifiers.find(token) for token in identifiers.parent}
    if len(components) != 1:
        return RecoveryStatus.UNRESOLVED_CONFLICT, (), ()

    ueis = tuple(sorted({uei for uei, _ in normalized_rows if uei is not None}))
    duns_values = tuple(sorted({duns for _, duns in normalized_rows if duns is not None}))
    return RecoveryStatus.RESOLVED_AUTHORITATIVE, ueis, duns_values


def resolve_award_identities(
    sbir_awards: pd.DataFrame,
    official_awards: pd.DataFrame,
    *,
    profile: ExactAwardIdentityProfile = ExactAwardIdentityProfile.EXACT_AWARD_KEY_V1,
) -> pd.DataFrame:
    """Resolve SBIR source rows through exact canonical official award keys.

    The caller is responsible for source-specific award-key canonicalization.
    This function joins only the four declared key columns and never reads a
    company name, address, title, abstract, or other similarity signal.
    """

    profile = _require_profile(profile)
    _require_columns(sbir_awards, _SBIR_REQUIRED, label="SBIR recovery frame")
    _require_columns(official_awards, _OFFICIAL_REQUIRED, label="official award frame")
    _require_nonblank(
        sbir_awards,
        ("source_row_sha256", "recovery_attempt_id", *_JOIN_COLUMNS),
        label="SBIR recovery frame",
    )
    _require_nonblank(
        official_awards,
        (*_JOIN_COLUMNS, "official_record_id", "source_digest", "snapshot_date"),
        label="official award frame",
    )

    attempt_ids = sbir_awards["recovery_attempt_id"].map(_text).str.lower()
    if attempt_ids.duplicated().any():
        raise IdentityRecoveryError("SBIR recovery_attempt_id values must be unique")

    official = official_awards.copy()
    official["_join_key"] = official.apply(_normalized_join_key, axis=1)
    grouped: dict[tuple[str, str, str, str], pd.DataFrame] = {
        cast(tuple[str, str, str, str], key): group.drop(columns="_join_key")
        for key, group in official.groupby("_join_key", sort=False)
    }

    records: list[dict[str, Any]] = []
    for position, (_, source_row) in enumerate(sbir_awards.iterrows()):
        key = _normalized_join_key(source_row)
        matches = grouped.get(key)
        if matches is None:
            status = RecoveryStatus.UNRESOLVED_NO_MATCH
            ueis: tuple[str, ...] = ()
            duns_values: tuple[str, ...] = ()
            official_ids: tuple[str, ...] = ()
            digests: tuple[str, ...] = ()
            snapshots: tuple[str, ...] = ()
        else:
            status, ueis, duns_values = _classify_identifiers(matches)
            official_ids = tuple(sorted({_text(value) for value in matches["official_record_id"]}))
            digests = tuple(sorted({_text(value).lower() for value in matches["source_digest"]}))
            snapshots = tuple(sorted({_text(value) for value in matches["snapshot_date"]}))

        records.append(
            {
                "_source_position": position,
                "recovery_status": status.value,
                "resolved_ueis": ueis,
                "resolved_duns": duns_values,
                "official_record_ids": official_ids,
                "official_source_digests": digests,
                "official_snapshot_dates": snapshots,
            }
        )

    audit = pd.DataFrame.from_records(records).set_index("_source_position")
    output = sbir_awards.reset_index(drop=True).join(audit)
    if len(output) != len(sbir_awards):
        raise IdentityRecoveryError("Identity recovery changed the SBIR source-row count")
    output["identity_profile"] = profile.value
    return output


def _tuple_values(value: Any, *, label: str) -> tuple[str, ...]:
    if isinstance(value, tuple):
        items = value
    elif isinstance(value, list):
        items = tuple(value)
    else:
        tolist = getattr(value, "tolist", None)
        converted = tolist() if callable(tolist) else None
        if not isinstance(converted, list):
            raise IdentityRecoveryError(f"{label} must contain ordered arrays")
        items = tuple(converted)
    return tuple(_text(item) for item in items if _text(item))


def _resolved_attempt_identity(
    attempts: pd.DataFrame,
) -> tuple[RecoveryStatus, tuple[str, ...], tuple[str, ...]]:
    identifier_rows: list[dict[str, str | None]] = []
    for row in attempts.itertuples(index=False):
        ueis = _tuple_values(row.resolved_ueis, label="resolved_ueis")
        duns_values = _tuple_values(row.resolved_duns, label="resolved_duns")
        if not ueis and not duns_values:
            return RecoveryStatus.UNRESOLVED_CONFLICT, (), ()
        if ueis and duns_values:
            for uei in ueis:
                for duns in duns_values:
                    identifier_rows.append({"recipient_uei": uei, "recipient_duns": duns})
        elif ueis:
            identifier_rows.extend({"recipient_uei": uei, "recipient_duns": None} for uei in ueis)
        else:
            identifier_rows.extend(
                {"recipient_uei": None, "recipient_duns": duns} for duns in duns_values
            )
    return _classify_identifiers(pd.DataFrame.from_records(identifier_rows))


def reconcile_award_identity_attempts(
    attempt_audits: pd.DataFrame,
    *,
    profile: ExactAwardIdentityProfile = ExactAwardIdentityProfile.EXACT_AWARD_KEY_V1,
) -> pd.DataFrame:
    """Collapse source-specific attempts to one fail-closed result per SBIR row.

    No source receives priority. Conflicting authoritative matches, or an exact
    match with missing recipient identifiers alongside a resolved match, are
    quarantined rather than selected.
    """

    profile = _require_profile(profile)
    _require_columns(
        attempt_audits,
        _ATTEMPT_AUDIT_REQUIRED,
        label="identity attempt audit",
    )
    _require_nonblank(
        attempt_audits,
        ("source_row_sha256", "adapter", "recovery_status"),
        label="identity attempt audit",
    )
    valid_statuses = {status.value for status in RecoveryStatus}
    invalid_statuses = sorted(set(attempt_audits["recovery_status"].map(_text)) - valid_statuses)
    if invalid_statuses:
        raise IdentityRecoveryError(
            f"identity attempt audit contains invalid statuses: {invalid_statuses}"
        )
    if "identity_profile" in attempt_audits.columns:
        _require_nonblank(
            attempt_audits,
            ("identity_profile",),
            label="identity attempt audit",
        )
        profiles = set(attempt_audits["identity_profile"].map(_text))
        if profiles != {profile.value}:
            raise IdentityRecoveryError(
                f"identity attempt audit profiles {sorted(profiles)} do not match {profile.value}"
            )

    records: list[dict[str, Any]] = []
    for fingerprint, attempts in attempt_audits.groupby(
        attempt_audits["source_row_sha256"].map(_text).str.lower(),
        sort=False,
    ):
        statuses = set(attempts["recovery_status"].map(_text))
        resolved = attempts.loc[
            attempts["recovery_status"].map(_text) == RecoveryStatus.RESOLVED_AUTHORITATIVE.value
        ]

        if RecoveryStatus.UNRESOLVED_CONFLICT.value in statuses:
            status = RecoveryStatus.UNRESOLVED_CONFLICT
            ueis: tuple[str, ...] = ()
            duns_values: tuple[str, ...] = ()
        elif not resolved.empty:
            if RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER.value in statuses:
                status = RecoveryStatus.UNRESOLVED_CONFLICT
                ueis = ()
                duns_values = ()
            else:
                status, ueis, duns_values = _resolved_attempt_identity(resolved)
        elif RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER.value in statuses:
            status = RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER
            ueis = ()
            duns_values = ()
        else:
            status = RecoveryStatus.UNRESOLVED_NO_MATCH
            ueis = ()
            duns_values = ()

        def combined_tuple(frame: pd.DataFrame, column: str) -> tuple[str, ...]:
            return tuple(
                sorted(
                    {item for value in frame[column] for item in _tuple_values(value, label=column)}
                )
            )

        records.append(
            {
                "source_row_sha256": fingerprint,
                "identity_profile": profile.value,
                "recovery_status": status.value,
                "resolved_ueis": ueis,
                "resolved_duns": duns_values,
                "attempted_adapters": tuple(sorted(set(attempts["adapter"].map(_text)))),
                "attempt_statuses": tuple(sorted(statuses)),
                "official_record_ids": combined_tuple(attempts, "official_record_ids"),
                "official_source_digests": combined_tuple(attempts, "official_source_digests"),
                "official_snapshot_dates": combined_tuple(attempts, "official_snapshot_dates"),
            }
        )

    return pd.DataFrame.from_records(records)


__all__ = [
    "EPISTEMIC_TIER",
    "EXACT_AWARD_IDENTITY_VERSION",
    "ExactAwardIdentityProfile",
    "IdentityRecoveryError",
    "RecoveryStatus",
    "reconcile_award_identity_attempts",
    "resolve_award_identities",
]
