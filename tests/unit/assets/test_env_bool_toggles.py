"""Boolean and integer environment toggles keep their defaults and reject bad values.

Each read goes through ``sbir_etl.config.loader.env_bool`` / ``env_int`` (issue #874).
An unset or blank variable must give the same default as before. Every accepted
true or false word must work. Any other value must raise a ``ValueError`` that
names the variable, instead of being read silently as false.
"""

import importlib

import pytest
from dagster import DefaultScheduleStatus, build_asset_context, build_op_context

import sbir_analytics.assets as assets_pkg
from sbir_analytics.assets import nsf_defense_lineage as lineage
from sbir_analytics.assets.jobs import weekly_awards_report as weekly
from sbir_analytics.definitions_factory import schedule_status


pytestmark = [pytest.mark.fast, pytest.mark.unit]

TRUE_WORDS = ["1", "true", "TRUE", "yes", "Yes", "on", " on "]
FALSE_WORDS = ["0", "false", "False", "no", "NO", "off", " off "]
BAD_WORDS = ["ture", "enabled", "2"]

HEAVY = "DAGSTER_LOAD_HEAVY_ASSETS"
TOGGLE = "SBIR_ETL__TEST__SCHEDULE_TOGGLE_ENABLED"
FETCH_PRIME = "SBIR_ETL__NSF_DEFENSE_LINEAGE__FETCH_PRIME_API"
NSF_WORKERS = "SBIR_ETL__NSF_DEFENSE_LINEAGE__NSF_MAX_WORKERS"
RELEASE_AGE = "SBIR_ETL__NSF_DEFENSE_LINEAGE__MAX_RELEASE_AGE_DAYS"
SCHEDULE_PREFIX = "SBIR_ETL__DAGSTER__SCHEDULES__"

# Every schedule the primary profile registers. All are STOPPED unless enabled.
SCHEDULE_TOGGLES = {
    "weekly_core_refresh": "WEEKLY_CORE_REFRESH_ENABLED",
    "weekly_sbir_awards_download": "WEEKLY_SBIR_AWARDS_DOWNLOAD_ENABLED",
    "monthly_sam_gov_download": "MONTHLY_SAM_GOV_DOWNLOAD_ENABLED",
    "monthly_usaspending_download": "MONTHLY_USASPENDING_DOWNLOAD_ENABLED",
    "monthly_uspto_download": "MONTHLY_USPTO_DOWNLOAD_ENABLED",
    "monthly_phase_transition": "MONTHLY_PHASE_TRANSITION_ENABLED",
    "weekly_awards_report": "WEEKLY_AWARDS_REPORT_ENABLED",
    "monthly_nsf_defense_lineage_refresh": "MONTHLY_NSF_DEFENSE_LINEAGE_REFRESH_ENABLED",
}


# ---- definitions_factory.schedule_status ----


@pytest.mark.parametrize("default_running", [True, False])
@pytest.mark.parametrize("raw", [None, "", "   "])
def test_schedule_status_unset_or_blank_uses_default(monkeypatch, default_running, raw):
    if raw is None:
        monkeypatch.delenv(TOGGLE, raising=False)
    else:
        monkeypatch.setenv(TOGGLE, raw)

    expected = DefaultScheduleStatus.RUNNING if default_running else DefaultScheduleStatus.STOPPED
    assert schedule_status(TOGGLE, default_running=default_running) == expected


@pytest.mark.parametrize("raw", TRUE_WORDS)
def test_schedule_status_true_words_run(monkeypatch, raw):
    monkeypatch.setenv(TOGGLE, raw)
    assert schedule_status(TOGGLE, default_running=False) == DefaultScheduleStatus.RUNNING


@pytest.mark.parametrize("raw", FALSE_WORDS)
def test_schedule_status_false_words_stop(monkeypatch, raw):
    monkeypatch.setenv(TOGGLE, raw)
    assert schedule_status(TOGGLE, default_running=True) == DefaultScheduleStatus.STOPPED


@pytest.mark.parametrize("raw", BAD_WORDS)
def test_schedule_status_rejects_bad_value(monkeypatch, raw):
    monkeypatch.setenv(TOGGLE, raw)
    with pytest.raises(ValueError, match=TOGGLE):
        schedule_status(TOGGLE, default_running=False)


@pytest.fixture
def restore_definitions(monkeypatch):
    """Reload the definitions with every schedule toggle unset after the test."""
    import sbir_analytics.definitions as definitions

    yield definitions
    for suffix in SCHEDULE_TOGGLES.values():
        monkeypatch.delenv(f"{SCHEDULE_PREFIX}{suffix}", raising=False)
    importlib.reload(definitions)


def test_every_schedule_is_stopped_when_unset(monkeypatch, restore_definitions):
    for suffix in SCHEDULE_TOGGLES.values():
        monkeypatch.delenv(f"{SCHEDULE_PREFIX}{suffix}", raising=False)

    module = importlib.reload(restore_definitions)

    statuses = {schedule.name: schedule.default_status for schedule in module.bundle.schedules}
    assert set(statuses) == set(SCHEDULE_TOGGLES)
    assert set(statuses.values()) == {DefaultScheduleStatus.STOPPED}


@pytest.mark.parametrize("suffix", SCHEDULE_TOGGLES.values())
def test_bad_schedule_toggle_stops_definitions_load(monkeypatch, restore_definitions, suffix):
    key = f"{SCHEDULE_PREFIX}{suffix}"
    monkeypatch.setenv(key, "ture")

    with pytest.raises(ValueError, match=key):
        importlib.reload(restore_definitions)


# ---- assets/__init__.should_load_heavy_assets ----


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_heavy_assets_load_when_unset_or_blank(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(HEAVY, raising=False)
    else:
        monkeypatch.setenv(HEAVY, raw)
    assert assets_pkg.should_load_heavy_assets() is True


@pytest.mark.parametrize("raw", TRUE_WORDS)
def test_heavy_assets_true_words(monkeypatch, raw):
    monkeypatch.setenv(HEAVY, raw)
    assert assets_pkg.should_load_heavy_assets() is True


@pytest.mark.parametrize("raw", FALSE_WORDS)
def test_heavy_assets_false_words(monkeypatch, raw):
    monkeypatch.setenv(HEAVY, raw)
    assert assets_pkg.should_load_heavy_assets() is False


@pytest.mark.parametrize("raw", BAD_WORDS)
def test_heavy_assets_reject_bad_value(monkeypatch, raw):
    monkeypatch.setenv(HEAVY, raw)
    with pytest.raises(ValueError, match=HEAVY):
        assets_pkg.should_load_heavy_assets()


@pytest.fixture
def restore_uspto_package(monkeypatch):
    """Reload the USPTO asset package with the toggle unset after the test."""
    import sbir_analytics.assets.uspto as uspto_pkg

    yield uspto_pkg
    monkeypatch.delenv(HEAVY, raising=False)
    importlib.reload(uspto_pkg)


def test_heavy_toggle_bad_value_fails_uspto_import(monkeypatch, restore_uspto_package):
    monkeypatch.setenv(HEAVY, "ture")

    with pytest.raises(ValueError, match=HEAVY):
        importlib.reload(restore_uspto_package)


# ---- assets/nsf_defense_lineage.py ----


def test_lineage_bool_env_default_when_unset(monkeypatch):
    monkeypatch.delenv(FETCH_PRIME, raising=False)
    assert lineage._bool_env("FETCH_PRIME_API") is False
    assert lineage._bool_env("FETCH_PRIME_API", default=True) is True


@pytest.mark.parametrize(
    ("raw", "expected"), [(w, True) for w in TRUE_WORDS] + [(w, False) for w in FALSE_WORDS]
)
def test_lineage_bool_env_words(monkeypatch, raw, expected):
    monkeypatch.setenv(FETCH_PRIME, raw)
    assert lineage._bool_env("FETCH_PRIME_API") is expected


@pytest.mark.parametrize("raw", BAD_WORDS)
def test_lineage_bool_env_rejects_bad_value(monkeypatch, raw):
    monkeypatch.setenv(FETCH_PRIME, raw)
    with pytest.raises(ValueError, match=FETCH_PRIME):
        lineage._bool_env("FETCH_PRIME_API")


class _Captured(Exception):
    """Stops an asset at its first external call and keeps the call's arguments."""

    def __init__(self, kwargs):
        super().__init__("captured")
        self.kwargs = kwargs


def _capture(**kwargs):
    raise _Captured(kwargs)


def test_lineage_max_workers_default_when_unset(monkeypatch, tmp_path):
    import sbir_etl.supply_chain.nsf_release as nsf_release

    monkeypatch.setenv("SBIR_ETL__NSF_DEFENSE_LINEAGE__OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv(NSF_WORKERS, raising=False)
    monkeypatch.setattr(nsf_release, "build_release", _capture)

    with pytest.raises(_Captured) as captured:
        lineage.nsf_direct_award_release(build_asset_context())

    assert captured.value.kwargs["max_workers"] == 8


def test_lineage_max_workers_reject_bad_value(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_ETL__NSF_DEFENSE_LINEAGE__OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv(NSF_WORKERS, "8.0")

    with pytest.raises(ValueError, match=NSF_WORKERS):
        lineage.nsf_direct_award_release(build_asset_context())


def test_lineage_release_age_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_ETL__NSF_DEFENSE_LINEAGE__OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv(RELEASE_AGE, raising=False)
    monkeypatch.setattr(
        lineage, "validate_nsf_defense_lineage_release", lambda *_args, **kw: _capture(**kw)
    )

    with pytest.raises(_Captured) as captured:
        lineage.nsf_defense_lineage_validation(build_asset_context(), {})

    assert captured.value.kwargs["max_release_age_days"] == 45


def test_lineage_release_age_reject_bad_value(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_ETL__NSF_DEFENSE_LINEAGE__OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv(RELEASE_AGE, "45d")

    with pytest.raises(ValueError, match=RELEASE_AGE):
        lineage.nsf_defense_lineage_validation(build_asset_context(), {})


# ---- jobs/weekly_awards_report.py ----


class _CapturingBuilder:
    kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).kwargs = kwargs

    def run(self):
        return "# Weekly awards\n"


@pytest.fixture
def weekly_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SBIR_ETL__PATHS__DATA_ROOT", str(tmp_path))
    monkeypatch.delenv(weekly.LOOKBACK_DAYS_ENV, raising=False)
    monkeypatch.delenv("SKIP_SBIR_API", raising=False)
    monkeypatch.delenv("REPORT_TIMEOUT", raising=False)
    monkeypatch.setattr(weekly, "WeeklyAwardsReportBuilder", _CapturingBuilder)


def test_weekly_skip_api_and_timeout_default_when_unset(weekly_env):
    weekly.generate_weekly_awards_report_op(build_op_context())

    assert _CapturingBuilder.kwargs["skip_sbir_api"] is False
    assert _CapturingBuilder.kwargs["timeout"] == 720


@pytest.mark.parametrize(
    ("raw", "expected"), [(w, True) for w in TRUE_WORDS] + [(w, False) for w in FALSE_WORDS]
)
def test_weekly_skip_api_words(monkeypatch, weekly_env, raw, expected):
    monkeypatch.setenv("SKIP_SBIR_API", raw)

    weekly.generate_weekly_awards_report_op(build_op_context())

    assert _CapturingBuilder.kwargs["skip_sbir_api"] is expected


@pytest.mark.parametrize(("key", "raw"), [("SKIP_SBIR_API", "ture"), ("REPORT_TIMEOUT", "12m")])
def test_weekly_toggles_reject_bad_value(monkeypatch, weekly_env, key, raw):
    monkeypatch.setenv(key, raw)

    with pytest.raises(ValueError, match=key):
        weekly.generate_weekly_awards_report_op(build_op_context())
