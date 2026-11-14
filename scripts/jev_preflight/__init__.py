"""Exploratory study-readiness preflight with an optional Jev shadow."""

from .engine import assess_readiness
from .models import PreflightInput, ReadinessResult, ReadinessStatus


EPISTEMIC_TIER = "exploratory"

__all__ = ["PreflightInput", "ReadinessResult", "ReadinessStatus", "assess_readiness"]
