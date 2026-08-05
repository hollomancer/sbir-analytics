"""Guards for the _HOST_SCHEDULES table in definitions.py.

`definitions.py` builds each host schedule with:

    _discovered = _get_job(_job_name)
    if _discovered is None:
        LOG.warning("Job %s not discovered; skipping schedule", _job_name)
        continue

A typo in a job name therefore does not fail — it logs and silently drops the
schedule. On the server every schedule defaults to STOPPED, so a dropped
schedule is indistinguishable from a disabled one until someone notices months
of missing output. That is the same silent-rot shape that kept a broken
weekly.yml unnoticed, so it gets a test.
"""

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_every_host_schedule_resolves_to_a_real_job():
    """No _HOST_SCHEDULES entry may name a job that does not exist."""
    from sbir_analytics.definitions import _HOST_SCHEDULES, auto_jobs, source_download_schedules

    missing = [job_name for job_name, *_ in _HOST_SCHEDULES if job_name not in auto_jobs]
    assert not missing, (
        f"_HOST_SCHEDULES names jobs that were not discovered: {missing}. "
        "definitions.py skips these with only a log warning, so the schedule "
        "would silently not exist."
    )
    # Belt and braces: the skip path would also shorten this list.
    assert len(source_download_schedules) == len(_HOST_SCHEDULES)


def test_host_schedules_have_unique_names_and_valid_crons():
    """Duplicate names would have one schedule silently shadow another."""
    from sbir_analytics.definitions import _HOST_SCHEDULES

    names = [schedule_name for _, schedule_name, *_ in _HOST_SCHEDULES]
    assert len(names) == len(set(names))

    for _, schedule_name, cron, _label in _HOST_SCHEDULES:
        fields = cron.split()
        assert len(fields) == 5, f"{schedule_name}: {cron!r} is not a 5-field cron"


def test_host_schedules_default_to_stopped():
    """The runbook requires a manual run on the host before enabling."""
    from dagster import DefaultScheduleStatus

    from sbir_analytics.definitions import source_download_schedules

    running = [
        s.name
        for s in source_download_schedules
        if s.default_status != DefaultScheduleStatus.STOPPED
    ]
    assert not running, f"host schedules must default to STOPPED: {running}"
