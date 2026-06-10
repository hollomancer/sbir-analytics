"""
Mission A: Cross-Agency Portfolio Analysis tools.

Build first. Forces construction of the full award corpus, topic extraction,
and CET classification across all agencies. Produces the cross-agency dataset
that Mission B consumes for benchmark analysis.

New tools (4):
- extract_topics: Solicitation topic extraction from SBIR.gov
- cluster_topics: Semantic topic clustering for overlap detection
- detect_gaps: CET coverage gap analysis
- compute_portfolio_metrics: HHI, overlap, concentration, trends
"""

from .cluster_topics import ClusterTopicsTool
from .compute_portfolio_metrics import ComputePortfolioMetricsTool
from .detect_gaps import DetectGapsTool
from .extract_topics import ExtractTopicsTool

__all__ = [
    "ExtractTopicsTool",
    "ClusterTopicsTool",
    "DetectGapsTool",
    "ComputePortfolioMetricsTool",
]
