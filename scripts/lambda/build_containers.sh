#!/bin/bash
# DEPRECATED: Container-based Lambda functions have been migrated to Dagster Cloud
# This script is kept for reference only and should not be used.
#
# The following functions have been migrated:
# - ingestion-checks → Now part of sbir_weekly_refresh_job in Dagster Cloud
# - load-neo4j → Now part of sbir_weekly_refresh_job in Dagster Cloud
#
# See: src/assets/jobs/sbir_weekly_refresh_job.py
# See: docs/deployment/lambda-to-dagster-migration.md

echo "ERROR: Container-based Lambda functions have been migrated to Dagster Cloud."
echo "This script is deprecated and should not be used."
echo ""
echo "To trigger the weekly refresh workflow, use the trigger-dagster-refresh Lambda function"
echo "or trigger sbir_weekly_refresh_job directly in Dagster Cloud."
echo ""
echo "For more information, see: docs/deployment/lambda-to-dagster-migration.md"
exit 1
