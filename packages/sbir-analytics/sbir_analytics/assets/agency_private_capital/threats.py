"""Threats-to-validity gate for Phase 2 matched cohort reporting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


REQUIRED_THREATS = (
    "safe_convertible_undercount",
    "late_stage_form_d_inclusion",
    "naics_self_report_noise",
    "cik_resolution_recall_floor",
    "selection_bias",
    "control_cohort_timing_leak",
)


@dataclass(frozen=True)
class ThreatEntry:
    id: str
    label: str
    description: str
    mitigation: str
    as_of: str


class ThreatsToValidity:
    """Validate that all required caveats are present before reporting headlines."""

    def __init__(self, entries: list[ThreatEntry] | None = None) -> None:
        self.entries = entries if entries is not None else default_threat_entries()

    def validate(self) -> dict:
        present = {entry.id for entry in self.entries}
        missing = [threat for threat in REQUIRED_THREATS if threat not in present]
        return {
            "passed": not missing,
            "required": list(REQUIRED_THREATS),
            "missing": missing,
            "entries": [asdict(entry) for entry in self.entries],
        }

    def write(self, path: Path) -> dict:
        payload = self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload


def default_threat_entries() -> list[ThreatEntry]:
    as_of = datetime.now(UTC).date().isoformat()
    return [
        ThreatEntry(
            id="safe_convertible_undercount",
            label="SAFE / convertible undercount",
            description=(
                "Form D is incomplete for some early-stage instruments and does not fully "
                "capture non-filed SAFEs, bootstrapping, bank debt, revenue, or grants."
            ),
            mitigation="Report Form-D-detected private capital only; avoid total financing claims.",
            as_of=as_of,
        ),
        ThreatEntry(
            id="late_stage_form_d_inclusion",
            label="Late-stage Form D inclusion",
            description=(
                "The control universe includes Form D issuers across stages, not only seed-stage "
                "or pre-seed venture-backed firms."
            ),
            mitigation="Match on filing vintage and decompose by offering size/security type.",
            as_of=as_of,
        ),
        ThreatEntry(
            id="naics_self_report_noise",
            label="Industry self-report noise",
            description=(
                "Current v1 matching uses Form D industry_group when NAICS-2 is unavailable; "
                "issuer-reported industry can be coarser than award-derived NAICS."
            ),
            mitigation="Publish balance tables and treat industry controls as coarse strata.",
            as_of=as_of,
        ),
        ThreatEntry(
            id="cik_resolution_recall_floor",
            label="CIK recall floor",
            description=(
                "Only firms with resolved EDGAR/Form D signals enter the matched analysis, so "
                "private-capital non-filers and unresolved CIKs are outside the estimand."
            ),
            mitigation="Report CIK/form-D coverage alongside every headline table.",
            as_of=as_of,
        ),
        ThreatEntry(
            id="selection_bias",
            label="Technical-merit vs lawyer-access selection bias",
            description=(
                "SBIR awardees are selected on agency technical merit and proposal quality; "
                "Form D controls self-select on private-market readiness and filing access."
            ),
            mitigation="Frame as descriptive comparison, not a causal SBIR treatment effect.",
            as_of=as_of,
        ),
        ThreatEntry(
            id="control_cohort_timing_leak",
            label="Control-cohort timing leak",
            description=(
                "Dropping any issuer ever matched to SBIR prevents obvious contamination but can "
                "also exclude firms whose SBIR exposure happens after the control filing."
            ),
            mitigation="Document exclusion rule; defer time-varying treatment design to v2.",
            as_of=as_of,
        ),
    ]
