"""Transport boundary for the exploratory Jev CI triage pilot."""

from typing import Protocol

from .models import FailureEnvelope, JevTriageDecision


EPISTEMIC_TIER = "exploratory"


class JevTriageClient(Protocol):
    """Minimal interface that a future authenticated transport must satisfy."""

    def classify(self, envelope: FailureEnvelope) -> JevTriageDecision:
        """Return typed decisions for one sanitized failure envelope."""
        ...


class FakeJevTriageClient:
    """Hermetic transport that returns one prevalidated decision."""

    def __init__(self, decision: JevTriageDecision) -> None:
        self._decision = decision
        self.calls: list[FailureEnvelope] = []

    def classify(self, envelope: FailureEnvelope) -> JevTriageDecision:
        self.calls.append(envelope)
        return self._decision
