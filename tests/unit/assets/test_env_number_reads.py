"""Numeric SBIR_ETL__* environment reads keep their defaults and reject bad values.

Each read goes through ``sbir_etl.config.loader.env_float`` / ``env_int``. An unset
variable must give the same literal default as before the migration. A bad value
must raise a ``ValueError`` that names the variable.
"""

import importlib
import json

import pytest
from dagster import build_op_context

from sbir_analytics.assets.cet.classifications import cet_award_classifications_quality_check
from sbir_analytics.assets.cet.validation import (
    raw_cet_human_sampling,
    validated_cet_drift_detection,
)
from sbir_analytics.assets.jobs import weekly_awards_report as weekly
from sbir_analytics.assets.uspto import utils as uspto_utils


pytestmark = [pytest.mark.fast, pytest.mark.unit]

HIGH_CONF = "SBIR_ETL__CET__CLASSIFICATION__HIGH_CONF_THRESHOLD"
EVIDENCE_COV = "SBIR_ETL__CET__CLASSIFICATION__EVIDENCE_COVERAGE_THRESHOLD"
SAMPLE_SIZE = "SBIR_ETL__CET__SAMPLE_SIZE"
SAMPLE_SEED = "SBIR_ETL__CET__SAMPLE_SEED"
SCORE_JS = "SBIR_ETL__CET__DRIFT__SCORE_JS_THRESHOLD"
LABEL_JS = "SBIR_ETL__CET__DRIFT__LABEL_JS_THRESHOLD"
TRANSFORM_SUCCESS = "SBIR_ETL__USPTO__TRANSFORM_SUCCESS_THRESHOLD"
LINKAGE = "SBIR_ETL__USPTO__LINKAGE_TARGET"


# ---- cet/classifications.py ----


def _write_classification_checks(tmp_path) -> None:
    path = tmp_path / "data/processed/cet_award_classifications.checks.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"high_conf_rate": 0.7, "evidence_coverage_rate": 0.9, "reason": "success"})
    )


def test_classification_thresholds_default_when_unset(monkeypatch, tmp_path, mock_context):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(HIGH_CONF, raising=False)
    monkeypatch.delenv(EVIDENCE_COV, raising=False)
    _write_classification_checks(tmp_path)

    result = cet_award_classifications_quality_check(mock_context)

    assert result.metadata["target_high_conf_rate"].value == 0.60
    assert result.metadata["target_evidence_coverage_rate"].value == 0.80


@pytest.mark.parametrize(("key", "raw"), [(HIGH_CONF, "abc"), (EVIDENCE_COV, "0,8")])
def test_classification_thresholds_reject_bad_value(monkeypatch, tmp_path, mock_context, key, raw):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(key, raw)
    _write_classification_checks(tmp_path)

    with pytest.raises(ValueError, match=key):
        cet_award_classifications_quality_check(mock_context)


# ---- cet/validation.py ----


def test_human_sampling_size_and_seed_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(SAMPLE_SIZE, raising=False)
    monkeypatch.delenv(SAMPLE_SEED, raising=False)
    input_path = tmp_path / "data/processed/cet_award_classifications.ndjson"
    input_path.parent.mkdir(parents=True)
    rows = [{"award_id": f"A-{i}", "primary_cet": "quantum"} for i in range(60)]
    input_path.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    raw_cet_human_sampling()

    checks = json.loads((tmp_path / "data/processed/cet_human_sample.checks.json").read_text())
    assert checks["sampled_rows"] == 50
    assert checks["seed"] == 42


def test_drift_thresholds_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(SCORE_JS, raising=False)
    monkeypatch.delenv(LABEL_JS, raising=False)

    result = validated_cet_drift_detection()

    assert result.value["score_threshold"] == 0.15
    assert result.value["label_threshold"] == 0.10


def test_drift_thresholds_blank_value_uses_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SCORE_JS, "  ")
    monkeypatch.delenv(LABEL_JS, raising=False)

    result = validated_cet_drift_detection()

    assert result.value["score_threshold"] == 0.15


@pytest.mark.parametrize(
    ("asset_fn", "key", "raw"),
    [
        (raw_cet_human_sampling, SAMPLE_SIZE, "5.0"),
        (raw_cet_human_sampling, SAMPLE_SEED, "abc"),
        (validated_cet_drift_detection, SCORE_JS, "nan"),
        (validated_cet_drift_detection, LABEL_JS, "0,1"),
    ],
)
def test_validation_env_reads_reject_bad_value(monkeypatch, tmp_path, asset_fn, key, raw):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(key, raw)

    with pytest.raises(ValueError, match=key):
        asset_fn()


# ---- uspto/utils.py (module-level constants, read at import) ----


@pytest.fixture
def restore_uspto_utils(monkeypatch):
    """Reload the module with the variables unset after the test changes them."""
    yield
    monkeypatch.delenv(TRANSFORM_SUCCESS, raising=False)
    monkeypatch.delenv(LINKAGE, raising=False)
    importlib.reload(uspto_utils)


def test_uspto_thresholds_default_when_unset(monkeypatch, restore_uspto_utils):
    monkeypatch.delenv(TRANSFORM_SUCCESS, raising=False)
    monkeypatch.delenv(LINKAGE, raising=False)

    module = importlib.reload(uspto_utils)

    assert module.TRANSFORM_SUCCESS_THRESHOLD == 0.98
    assert module.LINKAGE_TARGET == 0.60


@pytest.mark.parametrize(("key", "raw"), [(TRANSFORM_SUCCESS, "abc"), (LINKAGE, "inf")])
def test_uspto_thresholds_reject_bad_value_at_import(monkeypatch, restore_uspto_utils, key, raw):
    monkeypatch.setenv(key, raw)

    with pytest.raises(ValueError, match=key):
        importlib.reload(uspto_utils)


# ---- jobs/weekly_awards_report.py ----


class _CapturingBuilder:
    kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).kwargs = kwargs

    def run(self):
        return "# Weekly awards\n"


def test_weekly_lookback_days_default_when_unset(monkeypatch, tmp_path):
    monkeypatch.setenv(weekly.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.delenv(weekly.LOOKBACK_DAYS_ENV, raising=False)
    monkeypatch.setattr(weekly, "WeeklyAwardsReportBuilder", _CapturingBuilder)

    weekly.generate_weekly_awards_report_op(build_op_context())

    assert _CapturingBuilder.kwargs["days"] == 7


def test_weekly_lookback_days_reject_bad_value(monkeypatch, tmp_path):
    monkeypatch.setenv(weekly.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setenv(weekly.LOOKBACK_DAYS_ENV, "7d")
    monkeypatch.setattr(weekly, "WeeklyAwardsReportBuilder", _CapturingBuilder)

    with pytest.raises(ValueError, match=weekly.LOOKBACK_DAYS_ENV):
        weekly.generate_weekly_awards_report_op(build_op_context())
