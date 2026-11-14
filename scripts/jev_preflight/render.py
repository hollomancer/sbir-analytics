"""Stable human-readable rendering for deterministic preflight results."""

from .models import ReadinessResult


EPISTEMIC_TIER = "exploratory"


def render_result(result: ReadinessResult) -> str:
    """Render only observable rules and evidence; never hidden reasoning."""

    lines = [
        "# Study preflight",
        "",
        f"- Case: `{result.case_id}`",
        f"- Status: `{result.status.value}`",
        f"- Ruleset: `{result.ruleset_version}`",
        f"- Finding: {result.summary}",
        "- Citability: exploratory and non-citable",
    ]
    if result.first_blocker:
        lines.extend(
            [
                f"- First blocker: `{result.first_blocker.code.value}`",
                f"- Minimum next test: {result.first_blocker.minimum_next_test}",
            ]
        )
    if result.allowed_claim_now:
        lines.extend(["", "## Allowed claim now", ""])
        lines.extend(f"- {claim}" for claim in result.allowed_claim_now)
    if result.not_allowed_now:
        lines.extend(["", "## Not allowed now", ""])
        lines.extend(f"- {claim}" for claim in result.not_allowed_now)
    lines.extend(["", "## Evidence", ""])
    for item in result.evidence:
        refs = ", ".join(f"`{ref.path}#{ref.field}`" for ref in item.references)
        lines.append(f"- `{item.label.value}` `{item.fact_id}`: {item.detail} ({refs})")
    return "\n".join(lines) + "\n"
