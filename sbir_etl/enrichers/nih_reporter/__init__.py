"""NIH RePORTER Projects API v2 client and record schema.

Epistemic tier: pipelines. Domain semantics (activity codes, windows,
``appl_id`` / FY grain) live here. The shared refresh runner is a later PR.
"""

from sbir_etl.enrichers.nih_reporter.client import (
    NIH_ACTIVITY_CODES,
    NIH_PAGE_SIZE,
    NIH_REPORTER_CITATION,
    NIH_REPORTER_ENDPOINT,
    NIHReporterAPIClient,
    NIHReporterPage,
)
from sbir_etl.enrichers.nih_reporter.keys import (
    NIHSearchWindow,
    NIHWindowKind,
    canonicalize_nih_query_key,
    parse_refresh_window,
)
from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord, normalize_reporter_result


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "NIH_ACTIVITY_CODES",
    "NIH_PAGE_SIZE",
    "NIH_REPORTER_CITATION",
    "NIH_REPORTER_ENDPOINT",
    "NIHReporterAPIClient",
    "NIHReporterPage",
    "NIHReporterRecord",
    "NIHSearchWindow",
    "NIHWindowKind",
    "canonicalize_nih_query_key",
    "normalize_reporter_result",
    "parse_refresh_window",
]
