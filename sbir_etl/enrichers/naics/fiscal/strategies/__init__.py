"""NAICS enrichment strategies.

Epistemic tier: pipelines (package default). The exploratory
``TextInferenceStrategy`` is deliberately not re-exported here so importing this
package does not pull in contestable inference; its callers import
``sbir_etl.enrichers.naics.fiscal.strategies.text_inference`` directly (spec
epistemic-tier-enforcement, T1.2 edge 5).

Epistemic tier: pipelines. This is the package default that ``sbir_etl.enrichers``
states for deterministic retrieval and enrichment clients.
"""

from __future__ import annotations

from .base import EnrichmentStrategy, NAICSEnrichmentResult
from .simple_strategies import (
    AgencyDefaultsStrategy,
    OriginalDataStrategy,
    SectorFallbackStrategy,
    TopicCodeStrategy,
)
from .usaspending_dataframe import USAspendingDataFrameStrategy

EPISTEMIC_TIER = "pipelines"

__all__ = [
    "EnrichmentStrategy",
    "NAICSEnrichmentResult",
    "OriginalDataStrategy",
    "TopicCodeStrategy",
    "AgencyDefaultsStrategy",
    "SectorFallbackStrategy",
    "USAspendingDataFrameStrategy",
]
