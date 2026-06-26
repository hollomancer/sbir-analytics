"""Classify external OT Phase III transition claim strength.

The classifier is intentionally benchmark-neutral: it evaluates the strength of
an externally supplied Phase III transition assertion and does not apply SBA
commercialization benchmark thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class OTTransitionClaimClassification:
    """Tiered classification for an external OT Phase III transition claim."""

    tier: str
    benchmark_neutral: bool
    matched_signals: tuple[str, ...]


def classify_external_ot_transition_claim(claim_text: str | None) -> OTTransitionClaimClassification:
    """Classify analyst/vendor/source assertions into generic T1-T4 claim tiers.

    T1 is strongest (explicit OT + Phase III + transition/follow-on language).
    T4 is weakest (no recognizable external OT Phase III transition assertion).
    """

    text = (claim_text or "").lower()
    signals: list[str] = []

    has_ot = bool(
        re.search(r"\b(other transaction|ota|ot agreement|ot consortium|consortium)\b", text)
    )
    has_phase_iii = bool(re.search(r"\b(phase iii|phase 3|phase three)\b", text))
    has_transition = bool(
        re.search(
            r"\b(transition(?:ed)?|follow-?on|production|prototype|derives from|commerciali[sz]ation)\b",
            text,
        )
    )
    has_lineage = bool(
        re.search(r"\b(sbir|sttr|phase ii|phase 2|prior award|prior effort)\b", text)
    )

    if has_ot:
        signals.append("ot_vehicle")
    if has_phase_iii:
        signals.append("phase_iii")
    if has_transition:
        signals.append("transition_language")
    if has_lineage:
        signals.append("sbir_sttr_lineage")

    if has_ot and has_phase_iii and has_transition:
        tier = "T1"
    elif has_phase_iii and has_transition and has_lineage:
        tier = "T2"
    elif has_phase_iii or (has_ot and has_transition):
        tier = "T3"
    else:
        tier = "T4"

    return OTTransitionClaimClassification(
        tier=tier,
        benchmark_neutral=True,
        matched_signals=tuple(signals),
    )
