"""Statistical reporting utilities for pipeline analysis.

Epistemic tier: pipelines. This is the package default that ``sbir_etl.utils`` states
for deterministic shared helpers.
"""

from .script_helpers import (
    render_metric_table,
    serialize_dagster_metadata,
    write_gha_outputs,
)

EPISTEMIC_TIER = "pipelines"

__all__ = [
    "render_metric_table",
    "serialize_dagster_metadata",
    "write_gha_outputs",
]
