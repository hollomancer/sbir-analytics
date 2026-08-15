"""Probes for the D4 money/paper-trail scorer.

Exploratory tier: covers instrument-type classification, the two D4
directions independently, and the `D4MoneyTrail` combining policy -- not a
comprehensive matrix over every real-world `Contract` field format. No
network call: `score_ri_subaward_share` / `score_d4_money_trail` are always
exercised against a fake `SubawardClient`, never `UsaspendingSubawardClient`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.sttr_spinout_linkage.d4_scorer import (
    InstrumentType,
    classify_instrument_type,
    load_form_d_officer_index,
    normalize_award_id_for_search,
    score_d4_money_trail,
    score_form_d_officer_ri_affiliated,
    score_ri_subaward_share,
)
from scripts.sttr_spinout_linkage.kernel import DimensionStatus, SignalAbsentReason


pytestmark = pytest.mark.fast


class FakeSubawardClient:
    """In-memory `SubawardClient` double -- no network I/O."""

    def __init__(
        self,
        *,
        prime_award_id: str | None = "CONT_AWD_FAKE",
        subawards: list[dict[str, object]] | None = None,
        raise_on_find: bool = False,
        raise_on_fetch: bool = False,
    ) -> None:
        self._prime_award_id = prime_award_id
        self._subawards = subawards or []
        self._raise_on_find = raise_on_find
        self._raise_on_fetch = raise_on_fetch

    def find_prime_award_id(self, award_id_query: str, *, instrument: InstrumentType) -> str | None:
        if self._raise_on_find:
            raise RuntimeError("simulated network failure")
        return self._prime_award_id

    def fetch_subawards(self, prime_award_id: str) -> list[dict[str, object]]:
        if self._raise_on_fetch:
            raise RuntimeError("simulated network failure")
        return self._subawards


class TestClassifyInstrumentType:
    @pytest.mark.parametrize(
        "contract_number",
        [
            "4R42AR083779-02",  # NIH
            "2R42CA268623-02",
            "DE-AR0001984",  # DOE
            "DE-SC0024799",
            "2507534",  # NSF
            "2024-04679",  # USDA/NIFA
        ],
    )
    def test_recognized_grant_formats(self, contract_number: str) -> None:
        assert classify_instrument_type(contract_number) is InstrumentType.GRANT

    @pytest.mark.parametrize(
        "contract_number",
        [
            "N68335-26-C-0080",  # DoD PIID
            "FA8649-20-9-9043",
            "HDTRA118C0056",  # compact DoD, no dashes
            "80NSSC25CA040",  # NASA
            "NAS3-03076",  # legacy NASA
        ],
    )
    def test_recognized_contract_formats(self, contract_number: str) -> None:
        assert classify_instrument_type(contract_number) is InstrumentType.CONTRACT

    def test_blank_is_unknown(self) -> None:
        for blank in (None, "", "   ", float("nan")):
            assert classify_instrument_type(blank) is InstrumentType.UNKNOWN

    def test_unrecognized_format_is_unknown(self) -> None:
        assert classify_instrument_type("???totally-not-a-real-id???") is InstrumentType.UNKNOWN


class TestNormalizeAwardIdForSearch:
    def test_nih_grant_drops_leading_digit_and_suffix(self) -> None:
        assert (
            normalize_award_id_for_search("2R42MD014075-02", instrument=InstrumentType.GRANT)
            == "R42MD014075"
        )

    def test_doe_grant_strips_dashes_only(self) -> None:
        assert (
            normalize_award_id_for_search("DE-AR0001314", instrument=InstrumentType.GRANT)
            == "DEAR0001314"
        )

    def test_contract_strips_dashes(self) -> None:
        assert (
            normalize_award_id_for_search("N68335-19-C-0141", instrument=InstrumentType.CONTRACT)
            == "N6833519C0141"
        )


class TestLoadFormDOfficerIndex:
    def _write(self, tmp_path: Path, records: list[dict]) -> Path:
        path = tmp_path / "form_d.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        return path

    def test_missing_file_returns_empty_index(self, tmp_path) -> None:
        assert load_form_d_officer_index(tmp_path / "does-not-exist.jsonl") == {}

    def test_extracts_officer_and_director_titled_persons_only(self, tmp_path) -> None:
        path = self._write(
            tmp_path,
            [
                {
                    "company_name": "Acme Robotics Inc.",
                    "match_confidence": {"tier": "high"},
                    "offerings": [
                        {
                            "related_persons": [
                                {"name": "Jane Smith", "title": "Executive Officer, Director"},
                                {"name": "Bob Jones", "title": "Promoter"},
                            ]
                        }
                    ],
                }
            ],
        )
        index = load_form_d_officer_index(path)
        keys = list(index)
        assert len(keys) == 1
        assert index[keys[0]] == ("Jane Smith",)

    def test_low_confidence_tier_excluded_by_default(self, tmp_path) -> None:
        path = self._write(
            tmp_path,
            [
                {
                    "company_name": "Acme Robotics Inc.",
                    "match_confidence": {"tier": "medium"},
                    "offerings": [
                        {"related_persons": [{"name": "Jane Smith", "title": "Director"}]}
                    ],
                }
            ],
        )
        assert load_form_d_officer_index(path) == {}


class TestScoreFormDOfficerRiAffiliated:
    def test_blank_ri_poc_name_is_not_measurable(self) -> None:
        status, matched, reason = score_form_d_officer_ri_affiliated(
            company_name="Acme Robotics Inc.", ri_poc_name=None, form_d_index={}
        )
        assert status is DimensionStatus.NOT_MEASURABLE
        assert matched is False
        assert reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    def test_generic_token_ri_poc_name_fails_guard(self) -> None:
        status, matched, reason = score_form_d_officer_ri_affiliated(
            company_name="Acme Robotics Inc.", ri_poc_name="Dr.", form_d_index={}
        )
        assert status is DimensionStatus.NOT_MEASURABLE
        assert reason is SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED

    def test_no_index_provided_is_not_evaluated(self) -> None:
        status, matched, reason = score_form_d_officer_ri_affiliated(
            company_name="Acme Robotics Inc.", ri_poc_name="Jane Smith", form_d_index=None
        )
        assert status is DimensionStatus.NOT_EVALUATED
        assert reason is SignalAbsentReason.SOURCE_NOT_QUERIED

    def test_company_not_in_index_is_measured_negative(self) -> None:
        status, matched, reason = score_form_d_officer_ri_affiliated(
            company_name="Unlisted Firm LLC",
            ri_poc_name="Jane Smith",
            form_d_index={"acme robotics": ("John Doe",)},
        )
        assert status is DimensionStatus.MEASURED
        assert matched is False
        assert reason is None

    def test_officer_name_match_is_measured_positive(self) -> None:
        from sbir_etl.identity import CompanyNameProfile, normalize_company_name

        key = normalize_company_name(
            "Acme Robotics Inc.", profile=CompanyNameProfile.FORM_D_JOIN_V1
        )
        status, matched, reason = score_form_d_officer_ri_affiliated(
            company_name="Acme Robotics Inc.",
            ri_poc_name="Jane Q. Smith",
            form_d_index={key: ("Jane Q. Smith",)},
        )
        assert status is DimensionStatus.MEASURED
        assert matched is True


class TestScoreRiSubawardShare:
    def test_contract_instrument_is_not_applicable(self) -> None:
        status, share, reason = score_ri_subaward_share(
            contract_number="N68335-26-C-0080",
            ri_name="University of North Dakota",
            client=FakeSubawardClient(),
        )
        assert status is DimensionStatus.NOT_APPLICABLE
        assert share is None
        assert reason is SignalAbsentReason.NON_GRANT_INSTRUMENT

    def test_unknown_instrument_is_not_measurable(self) -> None:
        status, share, reason = score_ri_subaward_share(
            contract_number="???unrecognized???",
            ri_name="University of North Dakota",
            client=FakeSubawardClient(),
        )
        assert status is DimensionStatus.NOT_MEASURABLE
        assert reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    def test_no_client_is_not_evaluated(self) -> None:
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=None
        )
        assert status is DimensionStatus.NOT_EVALUATED
        assert reason is SignalAbsentReason.SOURCE_NOT_QUERIED

    def test_blank_ri_name_fails_guard(self) -> None:
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name=None, client=FakeSubawardClient()
        )
        assert status is DimensionStatus.NOT_MEASURABLE
        assert reason is SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED

    def test_prime_award_not_found_is_not_measurable(self) -> None:
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314",
            ri_name="University of North Dakota",
            client=FakeSubawardClient(prime_award_id=None),
        )
        assert status is DimensionStatus.NOT_MEASURABLE
        assert reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    def test_ri_matched_subaward_yields_positive_measured_share(self) -> None:
        client = FakeSubawardClient(
            subawards=[
                {"recipient_name": "UNIVERSITY OF NORTH DAKOTA", "amount": 856_666.0},
                {"recipient_name": "BARR ENGINEERING CO.", "amount": 172_243.0},
            ]
        )
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=client
        )
        assert status is DimensionStatus.MEASURED
        assert share == pytest.approx(856_666.0 / (856_666.0 + 172_243.0))
        assert reason is None

    def test_no_ri_match_among_subawards_is_measured_zero(self) -> None:
        client = FakeSubawardClient(
            subawards=[{"recipient_name": "SOME OTHER ENTITY", "amount": 50_000.0}]
        )
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=client
        )
        assert status is DimensionStatus.MEASURED
        assert share == 0.0

    def test_no_subawards_at_all_is_measured_zero(self) -> None:
        client = FakeSubawardClient(subawards=[])
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=client
        )
        assert status is DimensionStatus.MEASURED
        assert share == 0.0

    def test_prime_award_lookup_failure_is_evaluation_failed(self) -> None:
        client = FakeSubawardClient(raise_on_find=True)
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=client
        )
        assert status is DimensionStatus.EVALUATION_FAILED
        assert share is None

    def test_subaward_fetch_failure_is_evaluation_failed(self) -> None:
        client = FakeSubawardClient(raise_on_fetch=True)
        status, share, reason = score_ri_subaward_share(
            contract_number="DE-AR0001314", ri_name="University of North Dakota", client=client
        )
        assert status is DimensionStatus.EVALUATION_FAILED


class TestScoreD4MoneyTrail:
    def test_both_directions_measured(self) -> None:
        from sbir_etl.identity import CompanyNameProfile, normalize_company_name

        key = normalize_company_name(
            "Acme Robotics Inc.", profile=CompanyNameProfile.FORM_D_JOIN_V1
        )
        client = FakeSubawardClient(
            subawards=[{"recipient_name": "UNIVERSITY OF NORTH DAKOTA", "amount": 100.0}]
        )
        trail = score_d4_money_trail(
            ri_name="University of North Dakota",
            company_name="Acme Robotics Inc.",
            contract_number="DE-AR0001314",
            ri_poc_name="Jane Smith",
            subaward_client=client,
            form_d_index={key: ("Jane Smith",)},
        )
        assert trail.status is DimensionStatus.MEASURED
        assert trail.ri_subaward_share == 1.0
        assert trail.form_d_officer_ri_affiliated is True

    def test_contract_instrument_with_form_d_match_is_measured_not_suppressed(self) -> None:
        """The directional bug this module exists to avoid: a contract-instrument
        award (subaward direction NOT_APPLICABLE) must not suppress a real Form D
        officer match on the other, independent direction."""
        from sbir_etl.identity import CompanyNameProfile, normalize_company_name

        key = normalize_company_name(
            "Acme Robotics Inc.", profile=CompanyNameProfile.FORM_D_JOIN_V1
        )
        trail = score_d4_money_trail(
            ri_name="University of North Dakota",
            company_name="Acme Robotics Inc.",
            contract_number="N68335-26-C-0080",  # contract instrument
            ri_poc_name="Jane Smith",
            subaward_client=FakeSubawardClient(),
            form_d_index={key: ("Jane Smith",)},
        )
        assert trail.status is DimensionStatus.MEASURED
        assert trail.form_d_officer_ri_affiliated is True
        assert trail.ri_subaward_share is None

    def test_contract_instrument_with_no_form_d_match_is_not_applicable(self) -> None:
        trail = score_d4_money_trail(
            ri_name="University of North Dakota",
            company_name="Unlisted Firm LLC",
            contract_number="N68335-26-C-0080",
            ri_poc_name="Jane Smith",
            subaward_client=FakeSubawardClient(),
            form_d_index={},
        )
        assert trail.status is DimensionStatus.NOT_APPLICABLE
        assert trail.reason is SignalAbsentReason.NON_GRANT_INSTRUMENT

    def test_evaluation_failure_propagates(self) -> None:
        trail = score_d4_money_trail(
            ri_name="University of North Dakota",
            company_name="Unlisted Firm LLC",
            contract_number="DE-AR0001314",
            ri_poc_name=None,
            subaward_client=FakeSubawardClient(raise_on_find=True),
            form_d_index={},
        )
        assert trail.status is DimensionStatus.EVALUATION_FAILED

    def test_neither_direction_evaluated_prefers_the_more_specific_status(self) -> None:
        trail = score_d4_money_trail(
            ri_name="University of North Dakota",
            company_name="Unlisted Firm LLC",
            contract_number="DE-AR0001314",
            ri_poc_name=None,  # NOT_MEASURABLE / SOURCE_FIELD_UNAVAILABLE
            subaward_client=None,  # NOT_EVALUATED / SOURCE_NOT_QUERIED
            form_d_index={},
        )
        assert trail.status is DimensionStatus.NOT_MEASURABLE
        assert trail.reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE
