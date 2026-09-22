"""Deterministic action policy for typed Jev triage decisions."""

from .models import (
    FailureClass,
    FailureEnvelope,
    JevTriageDecision,
    PolicyOutcome,
    PolicyReason,
    RecommendedAction,
    RetryPolicy,
)


EPISTEMIC_TIER = "exploratory"


def select_action(
    envelope: FailureEnvelope,
    decision: JevTriageDecision,
    *,
    policy: RetryPolicy,
) -> PolicyOutcome:
    """Select one bounded action without changing the CI check conclusion."""

    if envelope.attempt_number > 1:
        return PolicyOutcome(
            action=RecommendedAction.HUMAN_TRIAGE,
            reason=PolicyReason.ATTEMPT_LIMIT_REACHED,
        )

    eligible = (
        decision.failure_class is FailureClass.KNOWN_FLAKE
        and decision.known_flake_probability >= policy.known_flake_threshold
        and decision.retry_success_probability >= policy.retry_success_threshold
    )
    if eligible:
        return PolicyOutcome(
            action=RecommendedAction.RETRY_ONCE,
            reason=PolicyReason.ELIGIBLE_KNOWN_FLAKE,
        )
    return PolicyOutcome(
        action=RecommendedAction.HUMAN_TRIAGE,
        reason=PolicyReason.THRESHOLD_NOT_MET,
    )
