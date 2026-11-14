"""Deterministic identity for candidate transition assertions.

This module exists to replace non-deterministic assertion identity. The legacy
producer in ``packages/sbir-analytics/sbir_analytics/assets/transition/utils.py``
minted ``f"TRANS-{uuid4().hex[:12].upper()}"`` per row, so the same input
produced a different identifier on every run. That made a published derivation
impossible to content-address, diff across runs, or pin from a study contract.

Two identities are defined (ADR-005 §"Minimum viable schema"):

``assertion_id``
    Logical identity. Stable across detector methods and revisions. Derived
    from the claim family, the Phase II source row key, and the namespaced
    contract key. Detector method is deliberately excluded so that two
    detectors making the same claim collide on one logical assertion (§10).

``assertion_revision_id``
    Immutable payload identity. Derived from the full canonical payload,
    including method and every dimension assessment. Any payload change yields
    a new revision.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from sbir_etl.assertions.enums import ContractKeyMethod

__all__ = [
    "AssertionIdentityError",
    "CLAIM_FAMILY",
    "LEGACY_NAMESPACE",
    "USASPENDING_NAMESPACE",
    "assertion_id",
    "assertion_revision_id",
    "canonical_payload_digest",
    "resolve_contract_key",
]

CLAIM_FAMILY: Final = "phase_ii_source_row__federal_prime_contract_award"

USASPENDING_NAMESPACE: Final = "USASPENDING:"
LEGACY_NAMESPACE: Final = "LEGACY:"

_LEGACY_COMPONENT_ORDER: Final = ("awarding_agency_code", "parent_award_id", "piid")


class AssertionIdentityError(ValueError):
    """Raised when identity cannot be resolved and publication must be blocked."""


def _normalize(value: object, *, field: str) -> str:
    """Normalize an identifier component to a non-empty canonical string."""
    if value is None:
        raise AssertionIdentityError(f"{field} is required and was None")
    text = str(value).strip().upper()
    if not text or text in {"NONE", "NAN", "NULL", "NA", "<NA>"}:
        raise AssertionIdentityError(f"{field} is required and was empty ({value!r})")
    return text


def resolve_contract_key(
    *,
    generated_unique_award_id: object = None,
    awarding_agency_code: object = None,
    parent_award_id: object = None,
    piid: object = None,
) -> tuple[str, ContractKeyMethod]:
    """Resolve one namespaced federal prime contract award key.

    Returns the namespaced key and the method used. ``generated_unique_award_id``
    is always preferred. The legacy composite requires *all three* components;
    a bare PIID is refused outright rather than silently accepted, because a
    PIID is not unique across agencies and IDVs (ADR-005 §2).

    Raises:
        AssertionIdentityError: if no key can be resolved, which blocks
            publication rather than emitting a null endpoint.
    """
    try:
        generated = _normalize(generated_unique_award_id, field="generated_unique_award_id")
    except AssertionIdentityError:
        generated = ""

    if generated:
        return f"{USASPENDING_NAMESPACE}{generated}", ContractKeyMethod.GENERATED_UNIQUE_AWARD_ID

    components: dict[str, str] = {}
    missing: list[str] = []
    for field, value in (
        ("awarding_agency_code", awarding_agency_code),
        ("parent_award_id", parent_award_id),
        ("piid", piid),
    ):
        try:
            components[field] = _normalize(value, field=field)
        except AssertionIdentityError:
            missing.append(field)

    if missing:
        if set(missing) == {"awarding_agency_code", "parent_award_id"} and "piid" in components:
            raise AssertionIdentityError(
                "bare PIID is never a valid contract key; "
                "generated_unique_award_id is unavailable and the legacy composite "
                "is missing awarding_agency_code and parent_award_id"
            )
        raise AssertionIdentityError(
            "cannot resolve contract key: generated_unique_award_id is unavailable "
            f"and the legacy composite is missing {sorted(missing)}"
        )

    composite = "|".join(components[field] for field in _LEGACY_COMPONENT_ORDER)
    method = ContractKeyMethod.LEGACY_COMPOSITE
    return f"{LEGACY_NAMESPACE}{method.value}|{composite}", method


def _digest(parts: object) -> str:
    payload = json.dumps(
        parts,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assertion_id(*, source_row_key: object, contract_key: str) -> str:
    """Return the deterministic logical identity for one claim.

    Method is excluded by design: two detectors asserting the same
    source-row/contract pair share one logical assertion and differ only by
    revision (ADR-005 §10).
    """
    normalized_source = _normalize(source_row_key, field="source_row_key")
    normalized_contract = _normalize(contract_key, field="contract_key")
    if not normalized_contract.startswith((USASPENDING_NAMESPACE, LEGACY_NAMESPACE)):
        raise AssertionIdentityError(
            f"contract_key must be namespaced with {USASPENDING_NAMESPACE!r} or "
            f"{LEGACY_NAMESPACE!r}; got {contract_key!r}"
        )
    return _digest(
        {
            "claim_family": CLAIM_FAMILY,
            "source_row_key": normalized_source,
            "contract_key": normalized_contract,
        }
    )


def canonical_payload_digest(payload: dict[str, Any]) -> str:
    """Return a stable digest over a canonical assertion payload."""
    return _digest(payload)


def assertion_revision_id(*, logical_id: str, payload: dict[str, Any]) -> str:
    """Return the immutable payload identity for one revision of a claim."""
    return _digest({"assertion_id": logical_id, "payload": payload})
