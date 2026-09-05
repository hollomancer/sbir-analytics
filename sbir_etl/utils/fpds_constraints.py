"""Source-system constraints that affect FPDS analytical interpretation.

These constants describe the FPDS ``Description of Requirement`` field, not
an analytical quality standard.  Keeping them in one shared module prevents
research scripts from treating thresholds above the source-system limit as if
they were uniformly observable outcomes.
"""

from __future__ import annotations

from datetime import date


FPDS_DESCRIPTION_REQUIRED = True
FPDS_DESCRIPTION_MAX_CHARS = 250
FPDS_DESCRIPTION_CAP_EFFECTIVE_DATE = date(2019, 6, 28)
FPDS_DESCRIPTION_RULE_URL = "https://beta.fpds.gov/downloads/Manuals/FPDS_User_Manual_V1.5.pdf"

# These are descriptive cut points within the current source-system range.
# They are not statutory requirements or minimum-quality floors.
FPDS_DESCRIPTION_DIAGNOSTIC_THRESHOLDS: tuple[int, ...] = (
    40,
    150,
    FPDS_DESCRIPTION_MAX_CHARS,
)


def threshold_is_uniformly_observable(threshold: int) -> bool:
    """Return whether a description threshold fits the post-2019 FPDS field.

    Legacy descriptions entered before the cap can remain longer than 250
    characters on later modifications.  That grandfathering does not make a
    larger threshold uniformly observable for newly entered descriptions.
    """

    if threshold < 0:
        raise ValueError("description thresholds must be nonnegative")
    return threshold <= FPDS_DESCRIPTION_MAX_CHARS


__all__ = [
    "FPDS_DESCRIPTION_CAP_EFFECTIVE_DATE",
    "FPDS_DESCRIPTION_DIAGNOSTIC_THRESHOLDS",
    "FPDS_DESCRIPTION_MAX_CHARS",
    "FPDS_DESCRIPTION_REQUIRED",
    "FPDS_DESCRIPTION_RULE_URL",
    "threshold_is_uniformly_observable",
]
