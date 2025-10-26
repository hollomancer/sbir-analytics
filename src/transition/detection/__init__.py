"""
Transition detection pipeline modules for SBIR technology transition analysis.

This package provides:
- TransitionScorer: Scoring algorithm for transition likelihood
- EvidenceGenerator: Evidence bundle generation (future)
- TransitionDetector: Main detection pipeline (future)
"""

from .scoring import TransitionScorer

__all__ = ["TransitionScorer"]
