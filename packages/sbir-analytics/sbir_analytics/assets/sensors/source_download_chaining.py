"""Chain pipeline execution onto successful source downloads.

The retired ``etl-pipeline.yml`` workflow ran the SBIR, USAspending, and USPTO
pipelines on a weekly cron. Rather than re-creating blind crons, these sensors
fire the corresponding pipeline as soon as its download job succeeds, so a
pipeline only runs when there is fresh input to process.

Each sensor defaults to STOPPED for the same reason the download schedules do:
the runbook requires a successful manual run on the host before automation is
enabled. Enable one with
``SBIR_ETL__DAGSTER__SENSORS__<NAME>_ENABLED=true``.
"""

import os

from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    RunRequest,
    SkipReason,
    run_status_sensor,
)

from ..jobs.source_downloads import (
    sbir_awards_download_job,
    usaspending_download_job,
    uspto_download_job,
)


def _sensor_status(name: str) -> DefaultSensorStatus:
    """Resolve a sensor's default status from an environment toggle."""
    raw = os.getenv(f"SBIR_ETL__DAGSTER__SENSORS__{name.upper()}_ENABLED", "false")
    enabled = raw.strip().lower() in ("true", "1", "yes", "on")
    return DefaultSensorStatus.RUNNING if enabled else DefaultSensorStatus.STOPPED


def _pipeline_job(name: str):
    """Look up a pipeline job, tolerating heavy-asset gating on the server."""
    from .. import iter_public_jobs

    for job in iter_public_jobs():
        if job.name == name:
            return job
    return None


_phase_transition = _pipeline_job("phase_transition_latency_job")
_pt_archive = _pipeline_job("phase_transition_archive_job")
_sbir_pipeline = _pipeline_job("sbir_weekly_refresh_job")
_uspto_pipeline = _pipeline_job("uspto_validation_job")
_usaspending_pipeline = _pipeline_job("usaspending_iterative_enrichment_job")


if _sbir_pipeline is not None:

    @run_status_sensor(
        run_status=DagsterRunStatus.SUCCESS,
        monitored_jobs=[sbir_awards_download_job],
        request_job=_sbir_pipeline,
        name="sbir_pipeline_after_download",
        default_status=_sensor_status("sbir_pipeline_after_download"),
        description="Run the SBIR refresh pipeline after a successful awards download",
    )
    def sbir_pipeline_after_download(context):
        # The download job reports changed=False when the upstream file is
        # unchanged; re-running the pipeline on identical input wastes hours.
        if _download_was_unchanged(context):
            return SkipReason("SBIR awards unchanged upstream; skipping pipeline run")
        return RunRequest(run_key=context.dagster_run.run_id)


if _uspto_pipeline is not None:

    @run_status_sensor(
        run_status=DagsterRunStatus.SUCCESS,
        monitored_jobs=[uspto_download_job],
        request_job=_uspto_pipeline,
        name="uspto_pipeline_after_download",
        default_status=_sensor_status("uspto_pipeline_after_download"),
        description="Run USPTO validation after a successful USPTO download",
    )
    def uspto_pipeline_after_download(context):
        return RunRequest(run_key=context.dagster_run.run_id)


if _usaspending_pipeline is not None:

    @run_status_sensor(
        run_status=DagsterRunStatus.SUCCESS,
        monitored_jobs=[usaspending_download_job],
        request_job=_usaspending_pipeline,
        name="usaspending_pipeline_after_download",
        default_status=_sensor_status("usaspending_pipeline_after_download"),
        description="Run USAspending enrichment after a successful dump download",
    )
    def usaspending_pipeline_after_download(context):
        return RunRequest(run_key=context.dagster_run.run_id)


def _download_was_unchanged(context) -> bool:
    """True when the monitored download reported no upstream change."""
    try:
        records = context.instance.all_logs(context.dagster_run.run_id)
    except Exception:
        return False
    for record in records:
        event = getattr(record, "dagster_event", None)
        data = getattr(event, "event_specific_data", None) if event else None
        metadata = getattr(getattr(data, "materialization", None), "metadata", None)
        if metadata and "changed" in metadata:
            value = metadata["changed"]
            return getattr(value, "value", value) is False
    return False


if _phase_transition is not None and _pt_archive is not None:

    @run_status_sensor(
        run_status=DagsterRunStatus.SUCCESS,
        monitored_jobs=[_phase_transition],
        request_job=_pt_archive,
        name="phase_transition_archive_after_analysis",
        default_status=_sensor_status("phase_transition_archive_after_analysis"),
        description="Archive phase-transition outputs to a dated directory after each run",
    )
    def phase_transition_archive_after_analysis(context):
        return RunRequest(run_key=context.dagster_run.run_id)
