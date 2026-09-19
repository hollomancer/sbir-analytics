"""Hermetic tests for the exploratory Jev CI failure-triage boundary."""

import pytest
from pydantic import ValidationError

from scripts.ci.jev_triage.classify import classify_failure
from scripts.ci.jev_triage.client import FakeJevTriageClient
from scripts.ci.jev_triage.models import (
    FailureClass,
    FailureEnvelope,
    JevTriageDecision,
    OwnerArea,
    PolicyReason,
    RecommendedAction,
    RetryPolicy,
)
from scripts.ci.jev_triage.policy import select_action
from scripts.ci.jev_triage.render import render_triage_summary
from scripts.ci.jev_triage.sanitize import failure_envelope_from_junit


def _envelope(*, attempt_number: int = 1) -> FailureEnvelope:
    return FailureEnvelope(
        check_name="Fast Tests (1/4)",
        command_family="pytest",
        exit_code=1,
        failed_test_ids=["tests.unit.test_example::test_failure"],
        exception_types=["ConnectionError"],
        diagnostic_excerpts=["connection refused"],
        changed_path_groups=["tests/unit"],
        runner_os="ubuntu-latest",
        attempt_number=attempt_number,
    )


def _decision(
    *,
    failure_class: FailureClass = FailureClass.KNOWN_FLAKE,
    known_flake_probability: float = 0.98,
    retry_success_probability: float = 0.94,
) -> JevTriageDecision:
    return JevTriageDecision(
        failure_class=failure_class,
        failure_class_confidence=0.96,
        owner_area=OwnerArea.CI_INFRASTRUCTURE,
        owner_area_confidence=0.89,
        changed_code_implicated_probability=0.08,
        external_service_implicated_probability=0.87,
        known_flake_probability=known_flake_probability,
        retry_success_probability=retry_success_probability,
    )


def test_junit_envelope_redacts_credentials_and_keeps_only_failed_cases() -> None:
    junit = """\
<testsuite tests="2" failures="1">
  <testcase classname="tests.unit.test_api" name="test_success" />
  <testcase classname="tests.unit.test_api" name="test_failure">
    <failure type="ConnectionError">Authorization: Bearer ghp_abcdefghijklmnop
password=hunter2
https://alice:secret@example.test/path
request failed with sk-abcdefghijklmnop</failure>
  </testcase>
</testsuite>
"""

    envelope = failure_envelope_from_junit(
        junit,
        check_name="Fast Tests (2/4)",
        exit_code=1,
        changed_path_groups=["sbir_etl/identity", "tests/unit/identity"],
        runner_os="ubuntu-latest",
    )

    assert envelope.failed_test_ids == ["tests.unit.test_api::test_failure"]
    assert envelope.exception_types == ["ConnectionError"]
    assert envelope.changed_path_groups == ["sbir_etl/identity", "tests/unit/identity"]
    excerpt = envelope.diagnostic_excerpts[0]
    assert "hunter2" not in excerpt
    assert "ghp_abcdefghijklmnop" not in excerpt
    assert "alice:secret" not in excerpt
    assert "sk-abcdefghijklmnop" not in excerpt
    assert excerpt.count("[REDACTED]") == 4


def test_junit_envelope_truncates_lists_deterministically() -> None:
    cases = "".join(
        f'<testcase classname="suite" name="test_{index}">'
        f'<failure type="Failure{index}">failure {index}</failure></testcase>'
        for index in range(25)
    )
    junit = f'<testsuite tests="25" failures="25">{cases}</testsuite>'

    first = failure_envelope_from_junit(
        junit,
        check_name="Fast Tests",
        exit_code=1,
        runner_os="ubuntu-latest",
    )
    second = failure_envelope_from_junit(
        junit,
        check_name="Fast Tests",
        exit_code=1,
        runner_os="ubuntu-latest",
    )

    assert len(first.failed_test_ids) == 20
    assert len(first.exception_types) == 20
    assert len(first.diagnostic_excerpts) == 20
    assert first == second


def test_junit_envelope_rejects_malformed_xml() -> None:
    with pytest.raises(ValueError, match="malformed JUnit XML"):
        failure_envelope_from_junit(
            "<testsuite>",
            check_name="Fast Tests",
            exit_code=1,
            runner_os="ubuntu-latest",
        )


def test_junit_envelope_rejects_oversized_input() -> None:
    oversized = f"<testsuite>{'x' * 2_000_001}</testsuite>"

    with pytest.raises(ValueError, match="exceeds the 2000000-byte input limit"):
        failure_envelope_from_junit(
            oversized,
            check_name="Fast Tests",
            exit_code=1,
            runner_os="ubuntu-latest",
        )


def test_contracts_reject_extra_fields_and_invalid_probabilities() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        FailureEnvelope.model_validate({**_envelope().model_dump(), "raw_log": "not allowed"})

    with pytest.raises(ValidationError, match="less_than_equal"):
        JevTriageDecision.model_validate(
            {**_decision().model_dump(), "retry_success_probability": 1.1}
        )


def test_policy_recommends_one_retry_only_above_both_thresholds() -> None:
    outcome = select_action(_envelope(), _decision(), policy=RetryPolicy())

    assert outcome.action is RecommendedAction.RETRY_ONCE
    assert outcome.reason is PolicyReason.ELIGIBLE_KNOWN_FLAKE

    low_retry = select_action(
        _envelope(),
        _decision(retry_success_probability=0.89),
        policy=RetryPolicy(),
    )
    assert low_retry.action is RecommendedAction.HUMAN_TRIAGE
    assert low_retry.reason is PolicyReason.THRESHOLD_NOT_MET


def test_policy_refuses_retry_after_first_attempt() -> None:
    outcome = select_action(_envelope(attempt_number=2), _decision(), policy=RetryPolicy())

    assert outcome.action is RecommendedAction.HUMAN_TRIAGE
    assert outcome.reason is PolicyReason.ATTEMPT_LIMIT_REACHED


def test_fake_transport_and_renderer_are_hermetic_and_stable() -> None:
    envelope = _envelope()
    client = FakeJevTriageClient(_decision())

    result = classify_failure(envelope, client=client)
    first = render_triage_summary(result)
    second = render_triage_summary(result)

    assert client.calls == [envelope]
    assert first == second
    assert "non-blocking triage decision" in first
    assert "not an explanation of hidden model reasoning" in first
    assert "`known_flake` (96.0%)" in first
    assert "`retry_once` (`eligible_known_flake`)" in first
