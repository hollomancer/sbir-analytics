"""Deterministic readiness policy for Jev Preflight."""

from sbir_etl.quality.study_manifest import EvidenceStatus

from .models import (
    BlockerCode,
    BlockingConstraint,
    PreflightInput,
    ReadinessResult,
    ReadinessStatus,
    SourceOutcome,
)


EPISTEMIC_TIER = "exploratory"

_EVIDENCE_RANK = {
    EvidenceStatus.RETIRED: -1,
    EvidenceStatus.EXPLORATORY: 0,
    EvidenceStatus.REPRODUCIBLE: 1,
    EvidenceStatus.VALIDATED: 2,
    EvidenceStatus.CITABLE: 3,
}


def _source_constraint(preflight: PreflightInput) -> BlockingConstraint | None:
    if preflight.facts.source_outcome is not SourceOutcome.IMPOSSIBLE:
        return None
    if preflight.claim.narrower_claim:
        return BlockingConstraint(
            code=BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE,
            status=ReadinessStatus.NARROW,
            message="The source outcome required by this claim is permanently unavailable.",
            minimum_next_test="Use the declared narrower claim without implying the unavailable outcome.",
            evidence_fact_ids=["source_outcome"],
        )
    return BlockingConstraint(
        code=BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE,
        status=ReadinessStatus.STOP,
        message="The source outcome required by this claim is permanently unavailable.",
        minimum_next_test="Stop this claim unless a new authoritative source changes coverage.",
        evidence_fact_ids=["source_outcome"],
    )


def _constraints(preflight: PreflightInput) -> list[BlockingConstraint]:
    constraints: list[BlockingConstraint] = []
    source = _source_constraint(preflight)
    if source is not None:
        constraints.append(source)
    elif preflight.facts.source_outcome is SourceOutcome.REMEDIABLE:
        constraints.append(
            BlockingConstraint(
                code=BlockerCode.SOURCE_OUTCOME_REMEDIABLE,
                status=ReadinessStatus.REDESIGN,
                message="The required source outcome is not yet available but may be recovered.",
                minimum_next_test="Run the cheapest source-recovery test before further analysis.",
                evidence_fact_ids=["source_outcome"],
            )
        )
    if preflight.claim.inputs_must_be_pinned and not preflight.facts.inputs_pinned:
        constraints.append(
            BlockingConstraint(
                code=BlockerCode.INPUT_UNPINNED,
                status=ReadinessStatus.REDESIGN,
                message="A required input is not pinned or its recorded hash does not match.",
                minimum_next_test="Pin the input and verify its hash before analysis.",
                evidence_fact_ids=["inputs_pinned"],
            )
        )
    if preflight.claim.definitions_must_be_complete and not preflight.facts.definitions_complete:
        constraints.append(
            BlockingConstraint(
                code=BlockerCode.DEFINITION_MISSING,
                status=ReadinessStatus.REDESIGN,
                message="A required measurement definition is absent.",
                minimum_next_test="Recover or explicitly decide the first missing definition.",
                evidence_fact_ids=["definitions_complete"],
            )
        )
    if preflight.claim.validation_required and not preflight.facts.validation_complete:
        constraints.append(
            BlockingConstraint(
                code=BlockerCode.VALIDATION_INCOMPLETE,
                status=ReadinessStatus.REDESIGN,
                message="The claim requires validation that the study has not completed.",
                minimum_next_test="Run the frozen validation design before promoting the claim.",
                evidence_fact_ids=["validation_complete"],
            )
        )
    current = _EVIDENCE_RANK[preflight.facts.current_evidence_status]
    target = _EVIDENCE_RANK[preflight.claim.target_evidence_status]
    if current < target:
        status = ReadinessStatus.NARROW if preflight.claim.narrower_claim else ReadinessStatus.REDESIGN
        constraints.append(
            BlockingConstraint(
                code=BlockerCode.EVIDENCE_STATUS_INSUFFICIENT,
                status=status,
                message=(
                    f"The study is {preflight.facts.current_evidence_status.value}, below the "
                    f"claim's {preflight.claim.target_evidence_status.value} target."
                ),
                minimum_next_test="Use a currently permitted claim or complete the next evidence gate.",
                evidence_fact_ids=["current_evidence_status"],
            )
        )
    return constraints


def assess_readiness(preflight: PreflightInput) -> ReadinessResult:
    """Return the first material blocker under the versioned policy."""

    constraints = _constraints(preflight)
    first = constraints[0] if constraints else None
    if first is None:
        status = ReadinessStatus.GO
        summary = "No configured blocker found under preflight-rules-v1."
    else:
        status = first.status
        summary = first.message

    narrower = preflight.claim.narrower_claim
    return ReadinessResult(
        case_id=preflight.claim.case_id,
        status=status,
        summary=summary,
        first_blocker=first,
        blocking_constraints=constraints,
        allowed_claim_now=[narrower] if narrower and status is ReadinessStatus.NARROW else [],
        not_allowed_now=[preflight.claim.claim] if status is not ReadinessStatus.GO else [],
        minimum_next_test=[first.minimum_next_test] if first else [],
        evidence=preflight.evidence,
    )
