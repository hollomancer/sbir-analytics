"""
Mission B: Statutory Performance Benchmarks (Observable Signals).

Build second. Consumes the cross-agency entity map and CET-classified award
universe from Mission A. Adds the statutory benchmark calculation layer and
observable commercialization signal.

New tools (2):
- compute_transition_rate: Statutory Phase I → II transition rate (Benchmark 1)
- compute_observable_commercialization: Three-prong enhanced benchmark (Benchmark 2)
"""

from .compute_observable_commercialization import ComputeObservableCommercializationTool
from .compute_transition_rate import ComputeTransitionRateTool

__all__ = [
    "ComputeTransitionRateTool",
    "ComputeObservableCommercializationTool",
]
