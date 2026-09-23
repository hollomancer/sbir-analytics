"""Candidate transition assertions stored as the durable analytical contract.

ADR-005 makes a content-addressed Parquet snapshot of typed candidate
assertions the authoritative record for inferred award-to-contract
derivations.

Everything published through this package is candidate-only:
``CANDIDATE`` / ``C`` / ``INVESTIGATIVE_ONLY``, and not citable.
"""

from __future__ import annotations

from sbir_etl.assertions.enums import (
    ActionRole,
    ClaimStatus,
    ContractKeyMethod,
    DimensionStatus,
    PermittedUse,
    SignalAbsentReason,
    SupportClass,
)
from sbir_etl.assertions.identifiers import (
    CLAIM_FAMILY,
    LEGACY_NAMESPACE,
    USASPENDING_NAMESPACE,
    AssertionIdentityError,
    assertion_id,
    assertion_revision_id,
    resolve_contract_key,
)
from sbir_etl.assertions.models import (
    ActionReference,
    AssertionRecord,
    AssertionSnapshotManifest,
    DimensionAssessment,
    InputReference,
)
from sbir_etl.assertions.snapshots import (
    SnapshotExistsError,
    read_snapshot,
    snapshot_id_for,
    write_snapshot,
)
from sbir_etl.assertions.validation import (
    AssertionValidationError,
    build_assertion_record,
    contract_key_method_counts,
    validate_snapshot_cardinality,
    validate_v1_semantics,
)

__all__ = [
    "CLAIM_FAMILY",
    "LEGACY_NAMESPACE",
    "USASPENDING_NAMESPACE",
    "ActionReference",
    "ActionRole",
    "AssertionIdentityError",
    "AssertionRecord",
    "AssertionSnapshotManifest",
    "AssertionValidationError",
    "ClaimStatus",
    "ContractKeyMethod",
    "DimensionAssessment",
    "DimensionStatus",
    "InputReference",
    "PermittedUse",
    "SignalAbsentReason",
    "SnapshotExistsError",
    "SupportClass",
    "assertion_id",
    "assertion_revision_id",
    "build_assertion_record",
    "contract_key_method_counts",
    "read_snapshot",
    "resolve_contract_key",
    "snapshot_id_for",
    "validate_snapshot_cardinality",
    "validate_v1_semantics",
    "write_snapshot",
]
