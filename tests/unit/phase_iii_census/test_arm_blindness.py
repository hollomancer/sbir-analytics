"""The census filter must not be able to tell the SBIR arm from the control arm.

The negative-control design (`specs/phase-iii-negative-controls/design.md`, and the
frozen downstream invariants in `specs/phase-iii-census/design.md`) runs *the same*
criteria over two arms: SBIR firms, and matched non-SBIR controls carrying a copied
pseudo-index. The whole evidentiary value of that comparison rests on the filter being
unable to distinguish them. A filter that can branch on arm membership will produce
whatever separation is asked of it, so any gap it reports stops being evidence — which is
why the design calls an ``if is_control:`` inclusion path a *design failure* rather than a
style preference.

That property holds today by construction and by nothing else. These tests make it hold
by enforcement. They need none of the data the negative-control and placebo work is
blocked on: they run against synthetic pairs and the criteria module's own source.

The behavioural test below is the one that matters — it does not care what an arm column
is *named*, only that adding one cannot change the output. The two structural tests are
cheaper tripwires that fail closer to the mistake.
"""

import ast
import inspect
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census import criteria as criteria_module
from sbir_analytics.assets.phase_iii_census.criteria import (
    CORE_CLAUSES,
    apply_core_clauses,
    build_dropoff_ladder,
    build_sensitivity_grid,
)


pytestmark = pytest.mark.fast

CUT = date(2025, 12, 31)

#: Substrings that would expose arm membership if they appeared in a *parameter* name.
#: ``label`` is deliberately absent — the module uses it for diagnostic fold names.
_ARM_PARAM_TOKENS = (
    "arm",
    "control",
    "is_sbir",
    "treated",
    "treatment",
    "cohort",
    "placebo",
)

#: Whole words that would expose arm membership if they appeared as an identifier,
#: attribute, or string literal in the module. Matched on word boundaries and kept
#: deliberately tight: bare "control" and "treated" are ordinary English ("quality
#: control", "cannot be treated as"), and flagging them would make this test a nuisance
#: rather than a signal. The behavioural tests above are what catch a creatively named
#: leak; these two are cheap tripwires that fail closer to the mistake.
_ARM_WORD_PATTERN = re.compile(
    r"\b("
    r"arm|arms|arm_label|"
    r"is_control|control_arm|is_sbir|sbir_arm|"
    r"is_placebo|placebo_arm|"
    r"treatment_group|treatment_arm|is_treated"
    r")\b",
    re.IGNORECASE,
)


def _pair(row_id: int = 1, **overrides: object) -> dict[str, object]:
    """One valid census pair row. Mirrors the fixture in ``test_criteria.py``."""

    row: dict[str, object] = {
        "prior_award_id": f"PRIOR-{row_id}",
        "prior_recipient_uei": f"UEI-{row_id}",
        "prior_agency": "DEPARTMENT A",
        "prior_sub_agency": "COMPONENT A",
        "prior_naics_code": "541715",
        "prior_psc_code": "AC13",
        "prior_period_of_performance_end": "2020-12-31",
        "target_recipient_uei": f"UEI-{row_id}",
        "target_id": f"PIID-{row_id}",
        "target_agency": "DEPARTMENT A",
        "target_sub_agency": "COMPONENT A",
        "target_naics_code": "541715",
        "target_psc_code": "AC13",
        "target_action_date": "2021-01-01",
        "target_obligated_amount": 100,
        "target_research": None,
        "target_sbir_phase": None,
        "target_transaction_id": f"TRANSACTION-{row_id}",
        "target_contract_key": f"GENERATED-AWARD-{row_id}",
        "target_competition_type": "FULL AND OPEN COMPETITION",
        "agency_match_level": "office",
    }
    row.update(overrides)
    return row


def _mixed_arm_pairs() -> pd.DataFrame:
    """Pairs that survive to different rungs, so a branch has something to change.

    Rows 1-2 clear the full ladder; row 3 dies on the lineage clause; row 4 dies on the
    post-completion clause. If a criterion branched on arm, the ladder counts would move.
    """

    return pd.DataFrame(
        [
            _pair(1),
            _pair(2),
            _pair(3, target_naics_code="999999", target_psc_code="ZZ99"),
            _pair(4, target_action_date="2019-01-01"),
        ]
    )


def _arm_labels(n: int) -> list[str]:
    return ["control" if index % 2 else "sbir" for index in range(n)]


def _with_arm_columns() -> pd.DataFrame:
    """Pairs carrying every arm spelling a leak might reach for.

    Both a boolean ``is_control`` and the string-labelled ``arm``/``treatment_group``,
    so a branch on any one of them is caught. Shared by the ladder and sensitivity
    tests: covering only one column in one of them would leave the other free to branch
    on the two it omits.
    """

    pairs = _mixed_arm_pairs()
    labels = _arm_labels(len(pairs))
    pairs["is_control"] = [label == "control" for label in labels]
    pairs["arm"] = labels
    pairs["treatment_group"] = labels
    return pairs


def test_adding_arm_columns_cannot_change_the_ladder():
    """Behavioural: the ladder must be bit-identical with and without arm columns.

    This is the test that actually enforces the design requirement. It makes no
    assumption about how a leak would be spelled — only that the filter's output is a
    function of the pair fields, and arm membership is not one of them.
    """

    baseline = build_dropoff_ladder(_mixed_arm_pairs(), CUT)

    pd.testing.assert_frame_equal(build_dropoff_ladder(_with_arm_columns(), CUT), baseline)

    # The ladder must also not survive by accident because every arm got the same answer:
    # the fixture has to actually discriminate, or this test proves nothing.
    assert baseline["surviving_pairs"].iloc[0] > baseline["surviving_pairs"].iloc[-1]


def test_adding_arm_columns_cannot_change_the_sensitivity_grid():
    """The six pre-registered cells are arm-blind too, not just the core ladder."""

    baseline = build_sensitivity_grid(_mixed_arm_pairs(), CUT)

    pd.testing.assert_frame_equal(build_sensitivity_grid(_with_arm_columns(), CUT), baseline)


def test_flipping_arm_labels_cannot_change_which_rows_survive():
    """Same rows, opposite arms: every clause must keep the identical survivor set.

    Deliberately uses ``cohort_flag`` rather than an obvious name. The lexical scans
    below would never flag that identifier, so this test is what stands between the repo
    and a value-level leak wearing an innocuous name — verified by mutation: a
    ``result & pairs["cohort_flag"].ne("control")`` injected into the lineage clause
    fails here and passes both source scans.
    """

    sbir_first = _mixed_arm_pairs()
    sbir_first["cohort_flag"] = _arm_labels(len(sbir_first))

    control_first = _mixed_arm_pairs()
    control_first["cohort_flag"] = [
        "sbir" if label == "control" else "control" for label in _arm_labels(len(control_first))
    ]

    for (left_id, _, left), (right_id, _, right) in zip(
        apply_core_clauses(sbir_first, CUT),
        apply_core_clauses(control_first, CUT),
        strict=True,
    ):
        assert left_id == right_id
        assert list(left["prior_award_id"]) == list(right["prior_award_id"]), (
            f"clause {left_id!r} kept different rows depending on arm membership"
        )


def test_criteria_functions_take_no_arm_argument():
    """Structural: no function in the module may accept arm membership as a parameter."""

    source = Path(inspect.getfile(criteria_module)).read_text(encoding="utf-8")
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        parameters = [
            argument.arg
            for argument in (*node.args.args, *node.args.posonlyargs, *node.args.kwonlyargs)
        ]
        offenders.extend(
            f"{node.name}({parameter})"
            for parameter in parameters
            if any(token in parameter.lower() for token in _ARM_PARAM_TOKENS)
        )

    assert not offenders, (
        "census criteria must be arm-blind, but these parameters expose arm membership: "
        f"{offenders}"
    )


def test_core_clause_predicates_keep_the_frozen_two_argument_signature():
    """Every frozen clause takes exactly ``(pairs, data_cut_date)`` — nothing else."""

    for clause in CORE_CLAUSES:
        parameters = list(inspect.signature(clause.predicate).parameters)
        assert len(parameters) == 2, (
            f"clause {clause.clause_id!r} takes {parameters}; the frozen signature is "
            "(pairs, data_cut_date) and a third argument is where arm membership gets in"
        )


def test_criteria_module_never_references_an_arm_column():
    """No identifier or string literal in the module may name an arm concept."""

    source = Path(inspect.getfile(criteria_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and _ARM_WORD_PATTERN.search(node.id):
            offenders.append(f"name {node.id!r}")
        elif isinstance(node, ast.Attribute) and _ARM_WORD_PATTERN.search(node.attr):
            offenders.append(f"attribute {node.attr!r}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _ARM_WORD_PATTERN.search(node.value):
                offenders.append(f"string {node.value!r}")

    assert not offenders, (
        f"census criteria must not reference arm membership, but the module mentions: {offenders}"
    )
