"""Strategy registry for the fiscal NAICS enricher.

Single source of truth for the default strategy order. Tests and assets
that want a custom ordering can build their own list; this factory exists
so the default is in one place instead of buried in FiscalNAICSEnricher.__init__.

Epistemic tier: pipelines. The deterministic strategies live here; the
contestable text-inference strategy is NOT imported or registered here.
Exploratory callers that want keyword-based NAICS inference inject it through
``extra_strategies`` (see ``exploratory_strategies``), keeping this registry
free of the exploratory dependency (spec epistemic-tier-enforcement, T1.2
edges 5-6).
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .strategies.base import EnrichmentStrategy
from .strategies.simple_strategies import (
    AgencyDefaultsStrategy,
    OriginalDataStrategy,
    SectorFallbackStrategy,
    TopicCodeStrategy,
)
from .strategies.usaspending_dataframe import USAspendingDataFrameStrategy


def default_strategies(
    usaspending_df: pd.DataFrame | None = None,
    *,
    extra_strategies: Sequence[EnrichmentStrategy] | None = None,
) -> list[EnrichmentStrategy]:
    """Return the default ordered list of NAICS enrichment strategies.

    Order is by confidence — highest first, fallback last:

    1. OriginalDataStrategy (0.95)
    2. USAspendingDataFrameStrategy (0.85)
    3. TopicCodeStrategy (0.75)
    4. ``extra_strategies`` (e.g. exploratory TextInferenceStrategy at 0.65),
       inserted here so an injected mid-confidence strategy keeps its slot
    5. AgencyDefaultsStrategy (0.50)
    6. SectorFallbackStrategy ("5415" — Computer Systems Design Services, 0.30)

    ``extra_strategies`` is the injection point for strategies this pipelines
    registry must not depend on; deterministic-only callers omit it.
    """
    return [
        OriginalDataStrategy(),
        USAspendingDataFrameStrategy(usaspending_df=usaspending_df, confidence=0.85),
        TopicCodeStrategy(),
        *(extra_strategies or ()),
        AgencyDefaultsStrategy(),
        SectorFallbackStrategy(fallback_code="5415"),
    ]
