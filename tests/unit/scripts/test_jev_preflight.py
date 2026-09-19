"""Tests for deterministic study preflight and the optional Jev shadow."""

import argparse
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from scripts.jev_preflight.annual_report import build_annual_report_preflight
from scripts.jev_preflight.engine import assess_readiness
from scripts.jev_preflight.cli import run_annual_report
from scripts.jev_preflight.evaluate import evaluate_matrix, evaluate_shadow_matrix, load_matrix
from scripts.jev_preflight.jev import (
    BlockerChoiceAnswer,
    ChoiceAnswer,
    FakeJevClient,
    JevPrediction,
    NoulAnswer,
    PrivateShadowBundle,
    ShadowBlocker,
    TypeSafeJevClient,
    Usage,
    build_request,
    parse_response,
    run_shadow,
)
from scripts.jev_preflight.models import (
    BlockerCode,
    ClaimContract,
    ReadinessStatus,
    SourceOutcome,
)
from scripts.jev_preflight.render import render_result


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MATRIX = REPOSITORY_ROOT / "tests" / "fixtures" / "jev_preflight" / "readiness-matrix.jsonl"


def _prediction(
    status: ReadinessStatus = ReadinessStatus.GO,
    blocker: ShadowBlocker = ShadowBlocker.NONE,
) -> JevPrediction:
    return JevPrediction(
        model="jev-test",
        readiness=ChoiceAnswer(
            type="choice",
            choice=status,
            confidence=0.9,
            probabilities={
                ReadinessStatus.GO: 0.9 if status is ReadinessStatus.GO else 0.02,
                ReadinessStatus.NARROW: 0.9 if status is ReadinessStatus.NARROW else 0.02,
                ReadinessStatus.REDESIGN: 0.9 if status is ReadinessStatus.REDESIGN else 0.03,
                ReadinessStatus.STOP: 0.9 if status is ReadinessStatus.STOP else 0.03,
            },
        ),
        first_blocker=BlockerChoiceAnswer(
            type="choice",
            choice=blocker,
            confidence=0.9,
            probabilities={option: 0.9 if option is blocker else 0.01 for option in ShadowBlocker},
        ),
        atomic_facts={
            name: NoulAnswer(type="noul", noul=0.9)
            for name in (
                "source_outcome_available",
                "inputs_pinned",
                "definitions_complete",
                "validation_complete",
            )
        },
        usage=Usage(input_tokens=100, output_tokens=20),
    )


def test_frozen_matrix_covers_and_matches_all_statuses() -> None:
    cases = load_matrix(MATRIX)
    report = evaluate_matrix(cases)

    assert {case.expected_status for case in cases} == set(ReadinessStatus)
    assert report.case_count == 4
    assert report.correct_count == 4
    assert report.incorrect_case_ids == []
    assert report.citable is False
    assert report.synthetic_fixture is True


def _matching_shadow_bundle() -> PrivateShadowBundle:
    results = []
    for case in load_matrix(MATRIX):
        deterministic = assess_readiness(case.input)
        blocker = (
            ShadowBlocker(deterministic.first_blocker.code.value)
            if deterministic.first_blocker
            else ShadowBlocker.NONE
        )
        results.append(
            run_shadow(
                case.input,
                client=FakeJevClient(_prediction(deterministic.status, blocker)),
            )
        )
    return PrivateShadowBundle(results=results)


def test_shadow_evaluator_joins_predictions_by_case_id() -> None:
    report = evaluate_shadow_matrix(load_matrix(MATRIX), _matching_shadow_bundle())

    assert report.matched_count == 4
    assert report.full_agreement_count == 4
    assert report.missing_case_ids == []
    assert report.unexpected_case_ids == []
    assert report.status_disagreement_case_ids == []
    assert report.first_blocker_disagreement_case_ids == []
    assert report.citable is False


def test_shadow_evaluator_reports_missing_and_unexpected_ids() -> None:
    bundle = _matching_shadow_bundle()
    retained = list(bundle.results[1:])
    retained.append(
        bundle.results[0].model_copy(
            update={
                "deterministic": bundle.results[0].deterministic.model_copy(
                    update={"case_id": "unexpected-case"}
                )
            }
        )
    )

    report = evaluate_shadow_matrix(load_matrix(MATRIX), PrivateShadowBundle(results=retained))

    assert report.missing_case_ids == ["synthetic-go"]
    assert report.unexpected_case_ids == ["unexpected-case"]


def test_source_impossibility_precedes_unpinned_input() -> None:
    narrow = next(
        case for case in load_matrix(MATRIX) if case.expected_status is ReadinessStatus.NARROW
    )
    modified = narrow.input.model_copy(
        update={"facts": narrow.input.facts.model_copy(update={"inputs_pinned": False})}
    )

    result = assess_readiness(modified)

    assert result.status is ReadinessStatus.NARROW
    assert result.first_blocker is not None
    assert result.first_blocker.code is BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE
    assert [item.code for item in result.blocking_constraints] == [
        BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE,
        BlockerCode.INPUT_UNPINNED,
    ]


def test_remediable_source_outcome_requires_redesign() -> None:
    ready = next(case for case in load_matrix(MATRIX) if case.expected_status is ReadinessStatus.GO)
    modified = ready.input.model_copy(
        update={
            "facts": ready.input.facts.model_copy(
                update={"source_outcome": SourceOutcome.REMEDIABLE}
            )
        }
    )

    result = assess_readiness(modified)

    assert result.status is ReadinessStatus.REDESIGN
    assert result.first_blocker is not None
    assert result.first_blocker.code is BlockerCode.SOURCE_OUTCOME_REMEDIABLE


def test_claim_contract_rejects_unknown_and_blank_fields() -> None:
    raw = load_matrix(MATRIX)[0].input.claim.model_dump()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ClaimContract.model_validate({**raw, "approved": True})
    with pytest.raises(ValidationError, match="string_too_short"):
        ClaimContract.model_validate({**raw, "claim": ""})


def test_annual_report_reproduction_narrows_to_structural_check() -> None:
    preflight = build_annual_report_preflight(
        REPOSITORY_ROOT, "annual-report-published-reproduction"
    )

    result = assess_readiness(preflight)

    assert result.status is ReadinessStatus.NARROW
    assert result.first_blocker is not None
    assert result.first_blocker.code is BlockerCode.SOURCE_OUTCOME_IMPOSSIBLE
    assert result.allowed_claim_now
    assert any(item.label.value == "BLOCKED" for item in result.evidence)


def test_annual_report_structural_check_has_no_configured_blocker() -> None:
    preflight = build_annual_report_preflight(REPOSITORY_ROOT, "annual-report-structural-check")

    result = assess_readiness(preflight)

    assert result.status is ReadinessStatus.GO
    assert result.summary == "No configured blocker found under preflight-rules-v1."
    assert result.first_blocker is None
    assert result.citable is False


def test_render_is_stable_and_does_not_say_approved() -> None:
    result = assess_readiness(
        build_annual_report_preflight(REPOSITORY_ROOT, "annual-report-published-reproduction")
    )

    first = render_result(result)
    second = render_result(result)

    assert first == second
    assert "approved" not in first.lower()
    assert "sources.yaml#published_sample_verdict" in first


def test_annual_report_cli_outputs_are_byte_stable(tmp_path: Path) -> None:
    first_json = tmp_path / "first.json"
    second_json = tmp_path / "second.json"
    first_markdown = tmp_path / "first.md"
    second_markdown = tmp_path / "second.md"
    common = {
        "repository_root": REPOSITORY_ROOT,
        "case_id": "annual-report-published-reproduction",
    }

    assert (
        run_annual_report(
            argparse.Namespace(
                **common,
                output_json=first_json,
                output_markdown=first_markdown,
            )
        )
        == 0
    )
    assert (
        run_annual_report(
            argparse.Namespace(
                **common,
                output_json=second_json,
                output_markdown=second_markdown,
            )
        )
        == 0
    )

    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_markdown.read_bytes() == second_markdown.read_bytes()


def test_request_uses_atomic_questions_and_no_prose_reasoning() -> None:
    preflight = load_matrix(MATRIX)[0].input
    request = build_request(preflight)

    assert request["model"] == "jev-latest"
    questions = request["questions"]
    assert isinstance(questions, dict)
    assert set(questions) == {
        "readiness",
        "first_blocker",
        "source_outcome_available",
        "inputs_pinned",
        "definitions_complete",
        "validation_complete",
    }
    assert "reason" not in json.dumps(request).lower()


def test_live_client_sends_bearer_key_and_parses_response() -> None:
    preflight = load_matrix(MATRIX)[0].input

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        prediction = _prediction().model_dump(mode="json")
        answers = {
            "readiness": prediction["readiness"],
            "first_blocker": prediction["first_blocker"],
            **prediction["atomic_facts"],
        }
        return httpx.Response(
            200,
            json={"model": "jev-test", "answers": answers, "usage": prediction["usage"]},
        )

    client = TypeSafeJevClient(api_key="test-key", transport=httpx.MockTransport(handler))

    assert client.predict(preflight) == _prediction()


def test_live_client_propagates_timeout_without_changing_policy() -> None:
    preflight = load_matrix(MATRIX)[0].input

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = TypeSafeJevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    deterministic = assess_readiness(preflight)

    with pytest.raises(httpx.ReadTimeout):
        run_shadow(preflight, client=client)
    assert assess_readiness(preflight) == deterministic


def test_live_client_propagates_authentication_failure() -> None:
    preflight = load_matrix(MATRIX)[0].input

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request, json={"detail": "invalid key"})

    client = TypeSafeJevClient(api_key="test-key", transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        client.predict(preflight)
    assert exc_info.value.response.status_code == 401


def test_response_schema_rejects_unknown_readiness_choice() -> None:
    prediction = _prediction().model_dump(mode="json")
    prediction["readiness"]["choice"] = "APPROVED"
    payload = {
        "model": "jev-test",
        "answers": {
            "readiness": prediction["readiness"],
            "first_blocker": prediction["first_blocker"],
            **prediction["atomic_facts"],
        },
        "usage": prediction["usage"],
    }

    with pytest.raises(ValidationError):
        parse_response(payload)


def test_fake_shadow_is_non_authoritative() -> None:
    preflight = load_matrix(MATRIX)[0].input

    shadow = run_shadow(preflight, client=FakeJevClient(_prediction()))

    assert shadow.agreement is True
    assert shadow.status_agreement is True
    assert shadow.first_blocker_agreement is True
    assert shadow.authoritative_source == "deterministic_preflight"
    assert shadow.citable is False


def test_shadow_requires_first_blocker_agreement() -> None:
    narrow = next(
        case for case in load_matrix(MATRIX) if case.expected_status is ReadinessStatus.NARROW
    )
    prediction = _prediction(
        ReadinessStatus.NARROW,
        blocker=ShadowBlocker.EVIDENCE_STATUS_INSUFFICIENT,
    )

    shadow = run_shadow(narrow.input, client=FakeJevClient(prediction))

    assert shadow.status_agreement is True
    assert shadow.first_blocker_agreement is False
    assert shadow.agreement is False
