"""Strategy registry for the fiscal NAICS enricher.

Single source of truth for the default strategy order. Tests and assets
that want a custom ordering can build their own list; this factory exists
so the default is in one place instead of buried in FiscalNAICSEnricher.__init__.
"""

from __future__ import annotations

import pandas as pd

from .strategies.base import EnrichmentStrategy
from .strategies.simple_strategies import (
    AgencyDefaultsStrategy,
    OriginalDataStrategy,
    SectorFallbackStrategy,
    TopicCodeStrategy,
)
from .strategies.text_inference import TextInferenceStrategy
from .strategies.usaspending_dataframe import USAspendingDataFrameStrategy


def default_strategies(usaspending_df: pd.DataFrame | None = None) -> list[EnrichmentStrategy]:
    """Return the default ordered list of NAICS enrichment strategies.

    Order is by confidence — highest first, fallback last:

    1. OriginalDataStrategy (0.95)
    2. USAspendingDataFrameStrategy (0.85)
    3. TopicCodeStrategy
    4. TextInferenceStrategy
    5. AgencyDefaultsStrategy
    6. SectorFallbackStrategy ("5415" — Computer Systems Design Services)
    """
    return [
        OriginalDataStrategy(),
        USAspendingDataFrameStrategy(usaspending_df=usaspending_df, confidence=0.85),
        TopicCodeStrategy(),
        TextInferenceStrategy(),
        AgencyDefaultsStrategy(),
        SectorFallbackStrategy(fallback_code="5415"),
    ]
