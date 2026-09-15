"""Map an extractor verdict onto the capital-events confidence tier.

Epistemic tier: pipelines. Deterministic rule from the discovery design;
it does not score live text.
"""

from __future__ import annotations

from sbir_etl.enrichers.ma_discovery.extractor import ExtractionVerdict, is_filled_date


EPISTEMIC_TIER = "pipelines"


def assign_confidence(verdict: ExtractionVerdict, *, source_count: int) -> str:
    """Return ``high``, ``medium``, or ``low`` for a confirmed verdict.

    Unconfirmed verdicts are ``low`` (filtered by callers). Date-unknown
    confirmations stay ``low`` so the keyword heuristic cannot enter the
    capital-events high/medium set.
    """
    if not verdict.confirmed:
        return "low"
    has_date = is_filled_date(verdict.acquisition_date)
    has_value = verdict.value_usd is not None
    if has_date and has_value and source_count >= 2:
        return "high"
    if has_date:
        return "medium"
    return "low"
