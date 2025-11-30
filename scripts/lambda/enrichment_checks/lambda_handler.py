"""Lambda function to run SBIR enrichment coverage analysis.

DEPRECATED: This function requires pandas and src.enrichers which are not available
in the Lambda environment. Enrichment checks should be run via Dagster Cloud instead.

See: src/assets/jobs/sbir_weekly_refresh_job.py
"""

import json
from typing import Any


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Return deprecation notice."""
    return {
        "statusCode": 501,
        "body": {
            "status": "deprecated",
            "message": "Enrichment checks have been migrated to Dagster Cloud. "
            "Use the sbir_weekly_refresh_job instead.",
            "dagster_job": "sbir_weekly_refresh_job",
        },
    }
