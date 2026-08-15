"""Probes for the D1 award-spine loader.

Exploratory tier: covers filter correctness (STTR + Phase II) and D1Spine
presence computation on a small synthetic frame -- not a comprehensive
column-name or real-data-file matrix. `load_d1_spine`'s freeze-guard call is
covered separately in `test_freeze_guard.py`; these tests pass
`verify_freeze=False` to stay independent of that mechanism.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.sttr_spinout_linkage.d1_spine import (
    D1SpineRecord,
    build_d1_spine_frame,
    filter_sttr_phase_ii,
    first_col,
    is_phase_ii,
    is_sttr,
    iter_d1_spine_records,
)
from scripts.sttr_spinout_linkage.kernel import D1Spine


pytestmark = pytest.mark.fast


RAW_AWARDS = pd.DataFrame(
    {
        "Program": ["STTR", "STTR", "SBIR", "STTR"],
        "Phase": ["Phase II", "Phase I", "Phase II", "II"],
        "award_id": ["A1", "A2", "A3", "A4"],
        "Agency": ["DOD", "DOD", "NSF", "NIH"],
        "Award Year": ["2020", "2019", "2021", "2022"],
        "UEI": ["U1", "U2", "U3", ""],
        "Company": ["Acme", "Beta", "Gamma", "Delta"],
        "RI Name": ["MIT", "", "Stanford", None],
        "PI Name": ["Jane Doe", "John Roe", "", "Sam Lee"],
        "Abstract": ["a widget", "b widget", "c widget", "d widget"],
    }
)


class TestFilterPredicates:
    def test_is_sttr(self) -> None:
        assert is_sttr("STTR") is True
        assert is_sttr("sttr ") is True
        assert is_sttr("SBIR") is False
        assert is_sttr(None) is False

    def test_is_phase_ii(self) -> None:
        assert is_phase_ii("Phase II") is True
        assert is_phase_ii("II") is True
        assert is_phase_ii("2") is True
        assert is_phase_ii("Phase I") is False

    def test_first_col_is_case_insensitive_and_falls_back_to_none(self) -> None:
        assert first_col(RAW_AWARDS, ("program", "Program")) == "Program"
        assert first_col(RAW_AWARDS, ("missing",)) is None


class TestFilterSttrPhaseIi:
    def test_keeps_only_sttr_phase_ii_rows(self) -> None:
        filtered = filter_sttr_phase_ii(RAW_AWARDS)
        # A2 is STTR Phase I (excluded); A3 is SBIR (excluded); A1/A4 kept.
        assert sorted(filtered["award_id"]) == ["A1", "A4"]

    def test_raises_when_program_or_phase_columns_are_absent(self) -> None:
        with pytest.raises(KeyError):
            filter_sttr_phase_ii(RAW_AWARDS.drop(columns=["Program"]))


class TestBuildD1SpineFrame:
    def test_computes_ri_pi_presence_and_d1_spine(self) -> None:
        sttr_p2 = filter_sttr_phase_ii(RAW_AWARDS)
        spine = build_d1_spine_frame(sttr_p2)
        by_id = spine.set_index("award_id")

        # A1: RI="MIT" (present), PI="Jane Doe" (present) -> complete spine.
        assert bool(by_id.loc["A1", "ri_present"]) is True
        assert bool(by_id.loc["A1", "pi_present"]) is True
        assert by_id.loc["A1", "d1_spine"] == D1Spine(ri_present=True, pi_present=True)

        # A4: RI=None (absent), PI="Sam Lee" (present) -> spine incomplete on RI.
        assert bool(by_id.loc["A4", "ri_present"]) is False
        assert bool(by_id.loc["A4", "pi_present"]) is True
        assert by_id.loc["A4", "d1_spine"] == D1Spine(ri_present=False, pi_present=True)

    def test_iter_d1_spine_records_yields_one_record_per_row(self) -> None:
        sttr_p2 = filter_sttr_phase_ii(RAW_AWARDS)
        spine = build_d1_spine_frame(sttr_p2)

        records = list(iter_d1_spine_records(spine))

        assert len(records) == len(spine)
        assert all(isinstance(record, D1SpineRecord) for record in records)
        assert {record.award_id for record in records} == {"A1", "A4"}
