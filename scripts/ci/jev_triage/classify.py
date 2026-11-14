"""Transport-neutral orchestration for one hermetic triage decision."""

from .client import JevTriageClient
from .models import FailureEnvelope, RetryPolicy, TriageResult
from .policy import select_action


EPISTEMIC_TIER = "exploratory"


def classify_failure(
    envelope: FailureEnvelope,
    *,
    client: JevTriageClient,
    policy: RetryPolicy | None = None,
) -> TriageResult:
    """Classify one sanitized failure and apply deterministic local policy."""

    active_policy = policy or RetryPolicy()
    decision = client.classify(envelope)
    outcome = select_action(envelope, decision, policy=active_policy)
    return TriageResult(envelope=envelope, decision=decision, policy_outcome=outcome)
