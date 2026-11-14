"""Stable Markdown rendering for exploratory Jev triage results."""

from .models import TriageResult


EPISTEMIC_TIER = "exploratory"


def render_triage_summary(result: TriageResult) -> str:
    """Render observable decisions without claiming hidden model reasoning."""

    decision = result.decision
    outcome = result.policy_outcome
    return "\n".join(
        [
            "## Experimental CI failure triage",
            "",
            "> This is a non-blocking triage decision, not an explanation of hidden model reasoning.",
            "",
            f"- Check: `{result.envelope.check_name}`",
            f"- Failure class: `{decision.failure_class.value}` "
            f"({decision.failure_class_confidence:.1%})",
            f"- Owner area: `{decision.owner_area.value}` "
            f"({decision.owner_area_confidence:.1%})",
            f"- Changed code implicated: {decision.changed_code_implicated_probability:.1%}",
            f"- External service implicated: {decision.external_service_implicated_probability:.1%}",
            f"- Known flake: {decision.known_flake_probability:.1%}",
            f"- Retry likely to succeed: {decision.retry_success_probability:.1%}",
            f"- Policy action: `{outcome.action.value}` (`{outcome.reason.value}`)",
            "",
        ]
    )
