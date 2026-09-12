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
