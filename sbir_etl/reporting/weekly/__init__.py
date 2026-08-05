"""Weekly SBIR awards report workflow.

Epistemic tier: exploratory. Generated reports carry an explicit non-citable
notice because enrichment and LLM stages have no evidence-tier contract.

Extracted from scripts/data/weekly_awards_report.py (spec:
weekly-awards-report-refactor). The CLI script remains the entry point;
it drives :class:`sbir_etl.reporting.weekly.orchestrator.WeeklyAwardsReportBuilder`.
"""

EPISTEMIC_TIER = "exploratory"
