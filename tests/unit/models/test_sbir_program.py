"""Unit tests for the SBIR/STTR program vocabulary primitives.

Covers the two direct program sources (the SBIR.gov ``Program`` column and
FPDS Element 10Q ``research`` codes), the unclassified-spelling report, and
the unknown-program exclusion policy that keeps program-less records out of
both the numerator and the denominator of a program-specific measure.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sbir_etl.models.sbir_program import (
    FPDS_RESEARCH_PROGRAM_CODES,
    SBIR_PROGRAM_VOCABULARY,
    normalize_sbir_program,
    program_from_fpds_research_code,
    program_specific_measure,
    unknown_sbir_program_values,
)


pytestmark = pytest.mark.fast


# --- FPDS Element 10Q -> program ------------------------------------------


def test_sr3_means_sbir():
    """SR3 is the Phase III SBIR code — the whole point of the plumbing."""

    assert program_from_fpds_research_code("SR3") == "SBIR"


def test_st3_means_sttr():
    """ST3 is the Phase III STTR code, and must not collapse into SBIR."""

    assert program_from_fpds_research_code("ST3") == "STTR"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("SR1", "SBIR"),
        ("SR2", "SBIR"),
        ("SR3", "SBIR"),
        ("ST1", "STTR"),
        ("ST2", "STTR"),
        ("ST3", "STTR"),
    ],
)
def test_every_classified_10q_code_maps_to_its_program(code, expected):
    assert program_from_fpds_research_code(code) == expected
    assert FPDS_RESEARCH_PROGRAM_CODES[code] == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "NONE",
        "NULL",
        "<NA>",
        float("nan"),
        "PHASE III",  # states a phase, states no program
        "PHASE 3",
        "SR4",  # not a code this repository has classified
        "XX3",
        "SBIR",  # a program name, but not a 10Q code
    ],
)
def test_uncoded_research_values_yield_no_program(value):
    assert program_from_fpds_research_code(value) is None


def test_research_code_is_case_and_whitespace_insensitive():
    assert program_from_fpds_research_code("  st3 ") == "STTR"


# --- SBIR.gov ``Program`` column -> program --------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("SBIR", "SBIR"), ("STTR", "STTR"), ("sttr", "STTR"), ("  SBIR  ", "SBIR")],
)
def test_normalize_sbir_program_accepts_the_classified_spellings(value, expected):
    assert normalize_sbir_program(value) == expected
    assert SBIR_PROGRAM_VOCABULARY[expected] == expected


@pytest.mark.parametrize("value", [None, "", "NULL", float("nan"), "Both", "N/A"])
def test_normalize_sbir_program_rejects_unclassified_values(value):
    assert normalize_sbir_program(value) is None


def test_combined_label_is_not_resolved_to_one_program():
    """ "SBIR/STTR" names two programs; picking one would invent provenance.

    This is deliberately stricter than ``Award.validate_program``, which
    substring-extracts in order to preserve a record rather than to establish
    which program an award belongs to.
    """

    assert normalize_sbir_program("SBIR/STTR") is None
    assert normalize_sbir_program("SBIR and STTR") is None


def test_unknown_program_values_reports_unclassified_spellings_only():
    values = ["SBIR", "STTR", "sbir", "", None, "SBIR/STTR", "Both", "Both"]
    assert unknown_sbir_program_values(values) == ["BOTH", "SBIR/STTR"]


# --- unknown-program exclusion policy --------------------------------------


@dataclass(frozen=True)
class _Record:
    program: object
    transitioned: bool


def _measure(records, program="STTR"):
    return program_specific_measure(
        records,
        program,
        program_of=lambda r: r.program,
        event_of=lambda r: r.transitioned,
    )


def test_unknown_program_record_enters_neither_numerator_nor_denominator():
    """The core policy: program=None is excluded from both sides of the rate.

    The unknown record here *did* transition, so a bug that leaked it into the
    numerator or into the denominator changes the reported rate.
    """

    records = [
        _Record("STTR", True),
        _Record("STTR", False),
        _Record(None, True),
    ]
    measure = _measure(records)

    assert measure.numerator == 1
    assert measure.denominator == 2
    assert measure.unknown_program == 1
    assert measure.total == 3
    assert measure.rate == pytest.approx(0.5)


@pytest.mark.parametrize("unknown_value", [None, "", "   ", "NULL", "SBIR/STTR", "Both"])
def test_every_flavour_of_unknown_is_excluded_not_just_none(unknown_value):
    records = [_Record("STTR", True), _Record(unknown_value, True)]
    measure = _measure(records)

    assert measure.numerator == 1
    assert measure.denominator == 1
    assert measure.unknown_program == 1


def test_other_known_program_is_excluded_without_being_called_unknown():
    """An SBIR record is out of an STTR measure, but it is not program-unknown."""

    records = [_Record("STTR", True), _Record("SBIR", True), _Record("SBIR", False)]
    measure = _measure(records)

    assert measure.denominator == 1
    assert measure.numerator == 1
    assert measure.unknown_program == 0
    assert measure.total == 3


def test_unknown_program_records_are_never_redistributed():
    """Excluding unknowns must not quietly reassign them to the other program."""

    records = [_Record(None, True) for _ in range(10)] + [_Record("STTR", False)]
    sttr = _measure(records, "STTR")
    sbir = _measure(records, "SBIR")

    assert sttr.denominator == 1
    assert sbir.denominator == 0
    assert sttr.unknown_program == sbir.unknown_program == 10
    # The unknowns are reported, not absorbed: neither program claims them.
    assert sttr.denominator + sbir.denominator + sttr.unknown_program == sttr.total


def test_program_coverage_is_reported_alongside_the_rate():
    records = [_Record("STTR", True), _Record("SBIR", False), _Record(None, True)]
    measure = _measure(records)

    assert measure.program_coverage == pytest.approx(2 / 3)


def test_rate_and_coverage_are_none_rather_than_zero_when_undefined():
    """An empty denominator must not be reported as a 0% transition rate."""

    empty = _measure([])
    assert empty.rate is None
    assert empty.program_coverage is None

    all_unknown = _measure([_Record(None, True), _Record(None, False)])
    assert all_unknown.rate is None
    assert all_unknown.program_coverage == pytest.approx(0.0)
