"""Frozen synthetic evaluation for deterministic readiness decisions."""

from pathlib import Path

from .engine import assess_readiness
from .jev import PrivateShadowBundle, ShadowBlocker
from .models import MatrixCase, MatrixReport, ShadowEvaluationReport


EPISTEMIC_TIER = "exploratory"


def load_matrix(path: Path) -> list[MatrixCase]:
    """Load strict JSON Lines cases and reject duplicate IDs."""

    cases: list[MatrixCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(MatrixCase.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: invalid matrix case: {exc}") from exc
    ids = [case.input.claim.case_id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case_id in preflight matrix")
    if not cases:
        raise ValueError("preflight matrix is empty")
    return cases


def evaluate_matrix(cases: list[MatrixCase]) -> MatrixReport:
    """Compare deterministic results with frozen expected statuses."""

    decisions = {
        case.input.claim.case_id: assess_readiness(case.input).status for case in cases
    }
    incorrect = sorted(
        case.input.claim.case_id
        for case in cases
        if decisions[case.input.claim.case_id] is not case.expected_status
    )
    return MatrixReport(
        case_count=len(cases),
        correct_count=len(cases) - len(incorrect),
        incorrect_case_ids=incorrect,
        decisions=decisions,
    )


def write_matrix_report(report: MatrixReport, output: Path) -> None:
    """Write one stable, non-citable JSON report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_shadow_bundle(path: Path) -> PrivateShadowBundle:
    """Load strict saved shadow results."""

    return PrivateShadowBundle.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_shadow_matrix(
    cases: list[MatrixCase],
    bundle: PrivateShadowBundle,
) -> ShadowEvaluationReport:
    """Join saved predictions by case ID and compare with fresh deterministic policy."""

    expected = {case.input.claim.case_id: assess_readiness(case.input) for case in cases}
    predictions = {result.deterministic.case_id: result for result in bundle.results}
    if len(predictions) != len(bundle.results):
        raise ValueError("duplicate case_id in shadow predictions")
    missing = sorted(set(expected) - set(predictions))
    unexpected = sorted(set(predictions) - set(expected))
    matched_ids = sorted(set(expected) & set(predictions))
    status_disagreements: list[str] = []
    blocker_disagreements: list[str] = []
    for case_id in matched_ids:
        policy = expected[case_id]
        prediction = predictions[case_id].jev
        if prediction.readiness.choice is not policy.status:
            status_disagreements.append(case_id)
        expected_blocker = (
            ShadowBlocker(policy.first_blocker.code.value)
            if policy.first_blocker
            else ShadowBlocker.NONE
        )
        if prediction.first_blocker.choice is not expected_blocker:
            blocker_disagreements.append(case_id)
    fully_agreeing = set(matched_ids) - set(status_disagreements) - set(blocker_disagreements)
    return ShadowEvaluationReport(
        case_count=len(expected),
        matched_count=len(matched_ids),
        missing_case_ids=missing,
        unexpected_case_ids=unexpected,
        status_disagreement_case_ids=status_disagreements,
        first_blocker_disagreement_case_ids=blocker_disagreements,
        full_agreement_count=len(fully_agreeing),
    )


def write_shadow_evaluation(report: ShadowEvaluationReport, output: Path) -> None:
    """Write one stable private shadow report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
