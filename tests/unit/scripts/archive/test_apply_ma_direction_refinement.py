import json

import pytest

from scripts.archive.data.apply_ma_direction_refinement import (
    apply_refinements,
    load_jsonl,
    write_jsonl_atomic,
)


def _event(name: str, confidence: str, **signals: bool) -> dict:
    return {
        "company_name": name,
        "confidence": confidence,
        "signals": {
            "form_d_business_combination": False,
            "efts_subsidiary": False,
            "efts_acquisition_text": False,
            "efts_ma_definitive": False,
            **signals,
        },
        "source_detail": {"preserved": True},
    }


def _refinement(
    name: str,
    direction: str,
    *,
    complete: bool = True,
    reasons: list[str] | None = None,
) -> dict:
    return {
        "company_name": name,
        "direction": direction,
        "context_classification_complete": complete,
        "context_incomplete_reasons": reasons or [],
    }


def test_apply_refinements_uses_frozen_rules_and_preserves_provenance() -> None:
    events = [
        _event("High", "high", efts_subsidiary=True),
        _event("Acquisition target", "medium", efts_acquisition_text=True),
        _event("Acquisition incomplete", "medium", efts_acquisition_text=True),
        _event("Definitive target", "low", efts_ma_definitive=True),
        _event("Definitive ambiguous", "low", efts_ma_definitive=True),
    ]
    refinements = [
        _refinement("Acquisition target", "target"),
        _refinement(
            "Acquisition incomplete",
            "context_incomplete",
            complete=False,
            reasons=["mention_search_failed"],
        ),
        _refinement("Definitive target", "target"),
        _refinement("Definitive ambiguous", "ambiguous"),
    ]

    output, stats = apply_refinements(events, refinements)
    by_name = {row["company_name"]: row for row in output}

    assert [row["company_name"] for row in output] == [row["company_name"] for row in events]
    assert by_name["High"]["confidence"] == "high"
    assert "directional_refinement_applied" not in by_name["High"]
    assert by_name["Acquisition target"]["confidence"] == "medium"
    assert by_name["Acquisition incomplete"]["confidence"] == "low"
    assert by_name["Acquisition incomplete"]["context_incomplete_reasons"] == [
        "mention_search_failed"
    ]
    assert by_name["Definitive target"]["confidence"] == "medium"
    assert by_name["Definitive ambiguous"]["confidence"] == "low"
    assert all(row["source_detail"] == {"preserved": True} for row in output)
    assert stats["medium_to_low"] == 1
    assert stats["low_to_medium"] == 1


@pytest.mark.parametrize(
    ("refinements", "message"),
    [
        ([], "missing"),
        (
            [_refinement("Alpha", "target"), _refinement("Alpha", "target")],
            "duplicate refinement",
        ),
        ([_refinement("Alpha", "target"), _refinement("Other", "target")], "unexpected"),
    ],
)
def test_apply_refinements_fails_closed_on_bad_coverage(refinements, message: str) -> None:
    events = [_event("Alpha", "medium", efts_acquisition_text=True)]

    with pytest.raises(ValueError, match=message):
        apply_refinements(events, refinements)


@pytest.mark.parametrize(
    "refinement",
    [
        {"company_name": "Alpha", "direction": "target"},
        _refinement("Alpha", "target", complete=False),
        _refinement("Alpha", "target", complete=True, reasons=["fetch_failed"]),
        _refinement("Alpha", "target", complete=False, reasons=["fetch_failed"]),
        _refinement("Alpha", "context_incomplete", complete=True),
        {
            "company_name": "Alpha",
            "direction": "target",
            "context_classification_complete": True,
            "context_incomplete_reasons": "",
        },
        _refinement("Alpha", "context_incomplete", complete=False, reasons=[""]),
    ],
)
def test_apply_refinements_requires_consistent_completeness(refinement: dict) -> None:
    events = [_event("Alpha", "medium", efts_acquisition_text=True)]

    with pytest.raises(ValueError, match="complet|reason"):
        apply_refinements(events, [refinement])


def test_atomic_writer_preserves_existing_output_on_serialization_error(tmp_path) -> None:
    output = tmp_path / "events.jsonl"
    output.write_text('{"old":true}\n')

    with pytest.raises(TypeError):
        write_jsonl_atomic(output, [{"not_json": {"a", "set"}}])

    assert output.read_text() == '{"old":true}\n'
    assert not list(tmp_path.glob(".events.jsonl.*.tmp"))


@pytest.mark.parametrize("contents", ["\n", "not-json\n", "[]\n"])
def test_jsonl_loader_rejects_invalid_records(tmp_path, contents: str) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(contents)

    with pytest.raises(ValueError):
        load_jsonl(path)


def test_atomic_writer_emits_deterministic_json(tmp_path) -> None:
    output = tmp_path / "events.jsonl"
    write_jsonl_atomic(output, [{"b": 2, "a": 1}])

    assert json.loads(output.read_text()) == {"a": 1, "b": 2}
    assert output.read_text() == '{"a":1,"b":2}\n'


def test_acquirer_side_rows_are_kept_away_from_the_bridge_grading() -> None:
    """The bridge grades a Form D combination `high` for every direction.

    ``confidence_after_directional_refinement`` returns ``high`` whenever
    ``form_d_business_combination`` is set, whatever direction the refinement
    found — including ``not_target``. That is only sound because an
    acquirer-side-only row never reaches the bridge, and two independent
    upstream guards keep it away: the detector routes it to the non-exit
    sibling, and it is not direction-sensitive, so no refinement is written for
    it and the coverage check would reject one.

    This pins the dependency. If either guard is relaxed, the inflation #735
    removed returns through the grading line rather than through the detector,
    which is the harder place to notice it.
    """
    from scripts.archive.data.detect_sbir_ma_events import is_acquirer_side_only
    from scripts.archive.data.refine_ma_medium_tier import (
        confidence_after_directional_refinement,
        needs_directional_refinement,
    )

    acquirer_side = {"signals": {"form_d_business_combination": True}}

    # Guard one: the detector routes it out of the exit artifact.
    assert is_acquirer_side_only(acquirer_side["signals"]) is True
    # Guard two: it is not direction-sensitive, so no refinement is written.
    assert needs_directional_refinement(acquirer_side) is False

    # The behavior both guards exist to keep unreachable: every direction,
    # including an explicit not_target, would still grade high.
    for direction in ("target", "not_target", "comparator", "ambiguous"):
        assert (
            confidence_after_directional_refinement(
                acquirer_side, direction=direction, context_complete=True
            )
            == "high"
        )

    # A row carrying target-side EFTS evidence is what legitimately reaches the
    # bridge, and it is not acquirer-side-only.
    with_target_side = {"signals": {"form_d_business_combination": True, "efts_subsidiary": True}}
    assert is_acquirer_side_only(with_target_side["signals"]) is False
