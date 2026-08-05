"""
Tech Census: all-phase, subset-taxonomy technology-relevance queries.

Not one of the lettered statutory-benchmark missions (A/B/C) -- a standing
capability for "how many SBIR awards, and how many dollars, are relevant to
technology area X" questions, broken into technology subsets, by fiscal
year. First area: drone manufacturing.

Tools (1):
- compute_tech_census: classify + aggregate SBIR awards against a
  config/tech_census/<area>.yaml
"""

from .compute_tech_census import ComputeTechCensusTool

__all__ = ["ComputeTechCensusTool"]
