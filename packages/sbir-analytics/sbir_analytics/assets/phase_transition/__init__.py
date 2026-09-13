"""Phase II -> Phase III transition latency assets.

This package measures the elapsed time between a firm's Phase II
period-of-performance end and its subsequent Phase III contract action date.

Pipeline:

1. ``validated_phase_ii_awards`` — unified Phase II population across
   FPDS/USAspending contracts, USAspending assistance grants, reconciled
   against SBIR.gov when federal-system phase coding is missing.
2. ``validated_phase_iii_contracts`` — FPDS contracts flagged as Phase III
   (an incomplete coding channel; agency coverage is logged).
3. ``transformed_phase_ii_iii_pairs`` — matched pairs joined on
   ``recipient_uei`` (primary) with DUNS crosswalk fallback for pre-2022
   rows. Emits every valid pair; downstream views derive (a) earliest Phase
   III per Phase II and (b) any Phase III within 5 years.
4. ``transformed_phase_transition_survival`` — one row per Phase II with an
   event indicator + signed completion-relative event-or-cutoff time. Rows
   with negative event time require a pre-completion stratum or a different
   nonnegative origin before Kaplan-Meier.

See ``README.md`` in this directory for threats to validity and method knobs.
"""

from __future__ import annotations

from .pairs import (
    transformed_phase_ii_iii_pairs,
    transformed_phase_transition_survival,
)
from .phase_ii import validated_phase_ii_awards
from .phase_iii import validated_phase_iii_contracts


__all__ = [
    "validated_phase_ii_awards",
    "validated_phase_iii_contracts",
    "transformed_phase_ii_iii_pairs",
    "transformed_phase_transition_survival",
]
