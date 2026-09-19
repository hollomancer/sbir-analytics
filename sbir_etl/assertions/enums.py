"""Typed vocabularies for candidate transition assertions.

Every enum here is closed. A producer that cannot map its state onto one of
these members must fail rather than fall back to a default, because a default
is indistinguishable from a measurement once written to Parquet (ADR-005 §7).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ActionRole",
    "ClaimStatus",
    "ContractKeyMethod",
    "DimensionStatus",
    "PermittedUse",
    "SignalAbsentReason",
    "SupportClass",
]


class ClaimStatus(StrEnum):
    """Lifecycle state of a logical assertion.

    V1 producers may only emit ``CANDIDATE``. ``ACCEPTED`` and ``REJECTED`` are
    reserved so the schema does not change when an acceptance process is
    decided, but no V1 producer, graph projection, or study may emit or infer
    them (ADR-005 §9).
    """

    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SupportClass(StrEnum):
    """Strength of evidential support for a claim.

    V1 emits only ``C``. Stronger classes are reserved and require a separate
    decision plus a named consumer (ADR-005 §9).
    """

    A = "a"
    B = "b"
    C = "c"


class PermittedUse(StrEnum):
    """What a consumer is allowed to do with a claim.

    V1 emits only ``INVESTIGATIVE_ONLY``. Nothing published under ADR-005 is
    citable; that is the intended state, not a gap.
    """

    INVESTIGATIVE_ONLY = "investigative_only"
    REPORTABLE = "reportable"
    CITABLE = "citable"


class DimensionStatus(StrEnum):
    """Per-dimension epistemic state.

    ``MEASURED`` requires a bounded, finite score. Zero is a measured
    no-signal, not an absence. Every other status means the dimension was not,
    or could not be, measured. Missing or null data never stands in for one of
    these states (ADR-005 §7).
    """

    MEASURED = "measured"
    NOT_MEASURABLE = "not_measurable"
    NOT_APPLICABLE = "not_applicable"
    NOT_EVALUATED = "not_evaluated"
    EVALUATION_FAILED = "evaluation_failed"

    @property
    def is_measured(self) -> bool:
        return self is DimensionStatus.MEASURED


class SignalAbsentReason(StrEnum):
    """Typed reason a dimension carries no signal, distinct from a negative.

    Modeled on the typed-absence pattern in
    :class:`sbir_etl.identity.exact_awards.RecoveryStatus`. Attached to a
    non-``MEASURED`` dimension status; never a substitute for a ``MEASURED``
    zero.
    """

    SPINE_INCOMPLETE = "spine_incomplete"
    SOURCE_UNAVAILABLE = "source_unavailable"
    IDENTITY_UNRESOLVED = "identity_unresolved"
    OUT_OF_SCOPE_FOR_METHOD = "out_of_scope_for_method"
    DETECTOR_NOT_RUN = "detector_not_run"
    DETECTOR_ERROR = "detector_error"
    UPSTREAM_SCHEMA_DRIFT = "upstream_schema_drift"


class ContractKeyMethod(StrEnum):
    """How a federal prime contract award key was resolved.

    ``GENERATED_UNIQUE_AWARD_ID`` is canonical and produces a ``USAID:`` key.
    ``LEGACY_COMPOSITE`` produces a namespaced, method-tagged ``LEGACY:`` key
    and is permitted only when the generated key is genuinely unavailable.
    Bare PIID is never a method; it is a validation failure (ADR-005 §2).
    """

    GENERATED_UNIQUE_AWARD_ID = "generated_unique_award_id"
    LEGACY_COMPOSITE = "legacy_composite"


class ActionRole(StrEnum):
    """Role a contract action plays in supporting an assertion.

    These stay distinct and are never collapsed into a single "date" or
    "amount" field (ADR-005 §5).
    """

    ASSOCIATED = "associated"
    DETECTOR_SELECTED = "detector_selected"
    EARLIEST_AWARD = "earliest_award"
    EARLIEST_POSITIVE_OBLIGATION = "earliest_positive_obligation"
