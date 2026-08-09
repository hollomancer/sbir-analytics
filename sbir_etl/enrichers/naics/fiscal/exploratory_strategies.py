"""Exploratory composition of the fiscal NAICS strategy chain.

Epistemic tier: exploratory. Keyword-based text inference of NAICS codes is
contestable, so it is composed here rather than in the pipelines
``strategy_registry``: this is the exploratory wiring point that injects
``TextInferenceStrategy`` into the deterministic default order (spec
epistemic-tier-enforcement, T1.2 edges 5-6). Callers that want the historical
six-strategy chain (the fiscal Dagster assets) build it through this module.
"""

from __future__ import annotations

import pandas as pd

from .strategies.base import EnrichmentStrategy
from .strategies.text_inference import TextInferenceStrategy
from .strategy_registry import default_strategies


EPISTEMIC_TIER = "exploratory"


def fiscal_strategies_with_text_inference(
    usaspending_df: pd.DataFrame | None = None,
) -> list[EnrichmentStrategy]:
    """Default deterministic strategies plus the exploratory text-inference step.

    Reproduces the historical six-strategy order (text inference at 0.65
    confidence, between topic-code and agency-default fallbacks) by injecting
    ``TextInferenceStrategy`` into the pipelines default via ``extra_strategies``.
    """

    return default_strategies(
        usaspending_df=usaspending_df,
        extra_strategies=[TextInferenceStrategy()],
    )


__all__ = ["fiscal_strategies_with_text_inference"]
