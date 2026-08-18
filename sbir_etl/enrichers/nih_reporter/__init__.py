"""NIH RePORTER Projects API v2 client, adapter, and record schema.

Epistemic tier: pipelines. Domain semantics (activity codes, windows,
``appl_id`` / FY grain) live here. The shared refresh runner stays in
``source_adapter``.
"""

from sbir_etl.enrichers.nih_reporter.adapter import NIHReporterSourceAdapter
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
from sbir_etl.enrichers.nih_reporter.persist import (
    nih_reporter_awards_path,
    upsert_nih_reporter_awards,
)
from sbir_etl.enrichers.nih_reporter.requests import (
    build_nih_reporter_requests,
    load_sbir_award_frame,
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
    "NIHReporterSourceAdapter",
    "NIHSearchWindow",
    "NIHWindowKind",
    "build_nih_reporter_requests",
    "canonicalize_nih_query_key",
    "load_sbir_award_frame",
    "nih_reporter_awards_path",
    "normalize_reporter_result",
    "parse_refresh_window",
    "upsert_nih_reporter_awards",
]
