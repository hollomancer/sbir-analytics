"""Publication gates for candidate transition assertions (ADR-005).

These are fail-closed checks. A producer that cannot satisfy them must not
publish a partial assertion: the legacy path emitted null award and contract
endpoints and let ``RESULTED_IN`` create a sparse contract node even when
``TRANSITIONED_TO`` was suppressed, which published half a topology as if it
were whole.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sbir_etl.assertions.enums import (
    ActionRole,
    ClaimStatus,
    ContractKeyMethod,
    PermittedUse,
    SupportClass,
)
from sbir_etl.assertions.identifiers import (
    assertion_id,
    assertion_revision_id,
    resolve_contract_key,
)
from sbir_etl.assertions.models import (
    ActionReference,
    AssertionRecord,
    DimensionAssessment,
)

__all__ = [
    "AssertionValidationError",
    "build_assertion_record",
    "contract_key_method_counts",
    "validate_snapshot_cardinality",
    "validate_v1_semantics",
]

_V1_CLAIM_STATUS = ClaimStatus.CANDIDATE
_V1_SUPPORT_CLASS = SupportClass.C
_V1_PERMITTED_USE = PermittedUse.INVESTIGATIVE_ONLY


class AssertionValidationError(ValueError):
    """Raised when an assertion or snapshot fails a publication gate."""


def validate_v1_semantics(record: AssertionRecord) -> None:
    """Reject anything outside candidate-only V1 semantics (ADR-005 §9)."""
    if record.claim_status is not _V1_CLAIM_STATUS:
        raise AssertionValidationError(
            f"V1 may only emit claim_status={_V1_CLAIM_STATUS.value!r}; "
            f"got {record.claim_status.value!r}. ACCEPTED and REJECTED are reserved "
            "and require a separate decision with a named consumer."
        )
    if record.support_class is not _V1_SUPPORT_CLASS:
        raise AssertionValidationError(
            f"V1 may only emit support_class={_V1_SUPPORT_CLASS.value!r}; "
            f"got {record.support_class.value!r}"
        )
    if record.permitted_use is not _V1_PERMITTED_USE:
        raise AssertionValidationError(
            f"V1 may only emit permitted_use={_V1_PERMITTED_USE.value!r}; "
            f"got {record.permitted_use.value!r}"
        )


def validate_snapshot_cardinality(records: Sequence[AssertionRecord]) -> None:
    """Enforce one current revision per logical assertion (ADR-005 §10).

    Detector method is excluded from logical identity, so two detectors
    asserting the same pair collide here by design. V1 has no fusion or
    selection rule, so the collision is an error rather than a silent pick.
    """
    seen: dict[str, AssertionRecord] = {}
    for record in records:
        existing = seen.get(record.assertion_id)
        if existing is None:
            seen[record.assertion_id] = record
            continue
        if existing.assertion_revision_id == record.assertion_revision_id:
            continue
        raise AssertionValidationError(
            f"logical assertion {record.assertion_id} has multiple current revisions "
            f"({existing.assertion_revision_id} from {existing.detector_method!r} and "
            f"{record.assertion_revision_id} from {record.detector_method!r}); "
            "V1 permits one current revision per logical assertion and defines no "
            "detector fusion or selection rule"
        )


def contract_key_method_counts(records: Iterable[AssertionRecord]) -> dict[str, int]:
    """Count key-resolution methods so ``LEGACY:`` use is visible, never silent."""
    counts = Counter(record.contract_key_method.value for record in records)
    for method in ContractKeyMethod:
        counts.setdefault(method.value, 0)
    return dict(counts)


def build_assertion_record(
    *,
    source_row_key: str,
    detector_method: str,
    method_run_id: str,
    dimensions: Sequence[DimensionAssessment],
    actions: Sequence[ActionReference],
    detector_selected_action_key: str,
    earliest_award_action_key: str,
    created_at: datetime,
    generated_unique_award_id: object = None,
    awarding_agency_code: object = None,
    parent_award_id: object = None,
    piid: object = None,
    earliest_award_action_date: object = None,
    earliest_positive_obligation_action_key: str | None = None,
    earliest_positive_obligation_action_date: object = None,
    award_anchor_latency_days: int | None = None,
    cet_area: str | None = None,
) -> AssertionRecord:
    """Construct one validated assertion with deterministic identity.

    This is the only supported way to build an :class:`AssertionRecord`.
    Identity is derived, never supplied, so a caller cannot mint one.

    ``award_anchor_latency_days`` is passed through with its sign preserved and
    no filtering: a negative latency (contract action before the award anchor)
    is a real observation and a downstream study decides whether to exclude it.
    """
    contract_key, contract_key_method = resolve_contract_key(
        generated_unique_award_id=generated_unique_award_id,
        awarding_agency_code=awarding_agency_code,
        parent_award_id=parent_award_id,
        piid=piid,
    )

    roles = {action.role for action in actions}
    if ActionRole.DETECTOR_SELECTED not in roles:
        raise AssertionValidationError("actions must retain the detector-selected action")
    if ActionRole.EARLIEST_AWARD not in roles:
        raise AssertionValidationError("actions must retain the earliest award action")

    logical_id = assertion_id(source_row_key=source_row_key, contract_key=contract_key)

    draft: dict[str, Any] = {
        "assertion_id": logical_id,
        "assertion_revision_id": "0" * 64,
        "source_row_key": source_row_key,
        "contract_key": contract_key,
        "contract_key_method": contract_key_method,
        "detector_method": detector_method,
        "method_run_id": method_run_id,
        "dimensions": tuple(dimensions),
        "actions": tuple(actions),
        "detector_selected_action_key": detector_selected_action_key,
        "earliest_award_action_key": earliest_award_action_key,
        "earliest_award_action_date": earliest_award_action_date,
        "earliest_positive_obligation_action_key": earliest_positive_obligation_action_key,
        "earliest_positive_obligation_action_date": earliest_positive_obligation_action_date,
        "award_anchor_latency_days": award_anchor_latency_days,
        "cet_area": cet_area,
        "created_at": created_at,
    }

    provisional = AssertionRecord.model_construct(**draft)
    revision_id = assertion_revision_id(
        logical_id=logical_id, payload=provisional.revision_payload()
    )
    record = AssertionRecord.model_validate({**draft, "assertion_revision_id": revision_id})
    validate_v1_semantics(record)
    return record
