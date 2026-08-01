"""Behavioral unit tests for named-row contract extraction."""

from datetime import date

import pytest

from sbir_etl.extractors.contract_extractor import ContractExtractor, SourceDataError
from sbir_etl.models.transition_models import CompetitionType


pytestmark = pytest.mark.fast


class TestContractExtractorInitialization:
    def test_init_with_vendor_filters(self, sample_vendor_filters) -> None:
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters, batch_size=5000)

        assert extractor.batch_size == 5000
        assert extractor.vendor_filters == {
            "uei": {"ABC123456789", "XYZ987654321"},  # pragma: allowlist secret
            "duns": {"123456789", "987654321"},
            "company_names": {"TEST COMPANY INC", "ACME CORPORATION"},
        }

    def test_init_without_vendor_filters(self) -> None:
        extractor = ContractExtractor(vendor_filter_file=None)

        assert extractor.batch_size == 10000
        assert extractor.vendor_filters == {
            "uei": set(),
            "duns": set(),
            "company_names": set(),
        }

    def test_init_with_missing_filter_file(self, tmp_path) -> None:
        extractor = ContractExtractor(vendor_filter_file=tmp_path / "missing.json")

        assert extractor.vendor_filters == {
            "uei": set(),
            "duns": set(),
            "company_names": set(),
        }

    def test_statistics_are_initialized(self) -> None:
        extractor = ContractExtractor()

        assert all(value == 0 for value in extractor.stats.values())
        assert extractor.source_provenance == {}


class TestParseCompetitionType:
    @pytest.mark.parametrize("code", ["FULL", "FSS", "A&A", "CDO", " full "])
    def test_full_and_open_codes(self, code: str) -> None:
        assert ContractExtractor()._parse_competition_type(code) == (CompetitionType.FULL_AND_OPEN)

    @pytest.mark.parametrize("code", ["NONE", "NDO", " none "])
    def test_sole_source_codes(self, code: str) -> None:
        assert ContractExtractor()._parse_competition_type(code) == CompetitionType.SOLE_SOURCE

    @pytest.mark.parametrize("code", ["LIMITED", "LIMITED COMPETITION", "RESTRICTED"])
    def test_limited_codes(self, code: str) -> None:
        assert ContractExtractor()._parse_competition_type(code) == CompetitionType.LIMITED

    @pytest.mark.parametrize("code", [None, "", r"\N", "Not Available", "UNKNOWN"])
    def test_unknown_codes(self, code: str | None) -> None:
        assert ContractExtractor()._parse_competition_type(code) == CompetitionType.OTHER


class TestVendorFiltering:
    def test_matches_authoritative_recipient_uei(self, sample_vendor_filters) -> None:
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        assert extractor._matches_vendor_filter(
            {"recipient_uei": " ABC123456789 "}  # pragma: allowlist secret
        )
        assert not extractor._matches_vendor_filter({"recipient_uei": "NOMATCH00000"})

    @pytest.mark.parametrize("legacy_id", ["ABC123456789", "123456789"])
    def test_matches_legacy_identifier(self, sample_vendor_filters, legacy_id: str) -> None:
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        assert extractor._matches_vendor_filter({"recipient_unique_id": legacy_id})

    def test_matches_company_name_case_insensitively(self, sample_vendor_filters) -> None:
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        assert extractor._matches_vendor_filter({"recipient_name": " TeSt CoMpAnY iNc "})
        assert not extractor._matches_vendor_filter({"recipient_name": "Different Company"})

    def test_null_named_fields_do_not_match(self, sample_vendor_filters) -> None:
        extractor = ContractExtractor(vendor_filter_file=sample_vendor_filters)

        assert not extractor._matches_vendor_filter(
            {
                "recipient_uei": None,
                "recipient_unique_id": None,
                "recipient_name": None,
            }
        )

    def test_empty_filter_frame_accepts_every_named_row(self) -> None:
        extractor = ContractExtractor()

        assert extractor._matches_vendor_filter({})


class TestParseContractRow:
    def test_complete_named_row(self, sample_contract_row_full) -> None:
        contract = ContractExtractor()._parse_contract_row(sample_contract_row_full)

        assert contract.contract_id == "SPE4A924D0001"
        assert contract.piid == "SPE4A924D0001"
        assert contract.model_dump()["piid"] == "SPE4A924D0001"
        assert contract.transaction_unique_id == "TX-12345678"
        assert contract.generated_unique_award_id == "CONT_AWD_1234_9700_SPE4A924D0001"
        assert contract.agency == "Department of Defense"
        assert contract.sub_agency == "Defense Advanced Research Projects Agency"
        assert contract.vendor_name == "TEST COMPANY INC"
        assert contract.vendor_uei == "ABC123456789"  # pragma: allowlist secret
        assert contract.vendor_cage == "1A2B3"
        assert contract.obligation_amount == 250000.00
        assert contract.competition_type == CompetitionType.FULL_AND_OPEN
        assert contract.is_deobligation is False
        assert contract.action_date == date(2023, 3, 15)
        assert contract.start_date == date(2023, 3, 15)
        assert contract.end_date == date(2024, 3, 15)
        assert contract.research == "SR2"
        assert contract.naics_code == "541715"
        assert contract.product_or_service_code == "AC12"

    def test_action_date_is_independent_of_performance_start(
        self, sample_contract_row_full
    ) -> None:
        row = dict(sample_contract_row_full)
        row["action_date"] = "20221101"
        row["period_of_performance_start_date"] = "20230801"

        contract = ContractExtractor()._parse_contract_row(row)

        assert contract.action_date == date(2022, 11, 1)
        assert contract.start_date == date(2023, 8, 1)

    def test_start_date_falls_back_to_action_date(self, sample_contract_row_full) -> None:
        row = dict(sample_contract_row_full)
        row["action_date"] = "20230615"
        row["period_of_performance_start_date"] = None

        contract = ContractExtractor()._parse_contract_row(row)

        assert contract.start_date == date(2023, 6, 15)

    def test_minimal_named_row(self, sample_contract_row_minimal) -> None:
        contract = ContractExtractor()._parse_contract_row(sample_contract_row_minimal)

        assert contract.contract_id == "MIN001"
        assert contract.vendor_name == "MINIMAL COMPANY"
        assert contract.vendor_uei == "MIN000000001"
        assert contract.obligation_amount == 1000.00
        assert contract.start_date == contract.action_date

    def test_malformed_dates_stay_null(self, sample_malformed_date_row) -> None:
        contract = ContractExtractor()._parse_contract_row(sample_malformed_date_row)

        assert contract.contract_id == "MAL001"
        assert contract.action_date is None
        assert contract.start_date is None
        assert contract.end_date is None

    def test_negative_obligation_is_preserved(self, sample_negative_amount_row) -> None:
        contract = ContractExtractor()._parse_contract_row(sample_negative_amount_row)

        assert contract.obligation_amount == -50000.00
        assert contract.is_deobligation is True

    @pytest.mark.parametrize("source_value", [None, "", "NOT_A_NUMBER"])
    def test_missing_or_malformed_obligation_stays_null(
        self, sample_contract_row_full, source_value: str | None
    ) -> None:
        row = dict(sample_contract_row_full)
        row["federal_action_obligation"] = source_value

        contract = ContractExtractor()._parse_contract_row(row)

        assert contract.obligation_amount is None
        assert contract.is_deobligation is False

    def test_child_relationship(self, sample_child_contract_row) -> None:
        extractor = ContractExtractor()

        contract = extractor._parse_contract_row(sample_child_contract_row)

        assert contract.contract_id == "TASK001"
        assert contract.parent_contract_id == "IDV001"
        assert contract.parent_contract_agency == "9700"
        assert contract.metadata["parent_relationship_type"] == "child_of_idv"
        assert extractor.stats["parent_relationships"] == 1
        assert extractor.stats["child_relationships"] == 1

    def test_idv_parent_relationship(self, sample_idv_parent_row) -> None:
        extractor = ContractExtractor()

        contract = extractor._parse_contract_row(sample_idv_parent_row)

        assert contract.contract_id == "IDV001"
        assert contract.contract_award_type == "IDV-A"
        assert contract.metadata["parent_relationship_type"] == "idv_parent"
        assert extractor.stats["idv_parents"] == 1

    def test_metadata_uses_named_fields(self, sample_contract_row_full) -> None:
        contract = ContractExtractor()._parse_contract_row(sample_contract_row_full)

        assert contract.metadata == {
            "transaction_id": "TX-12345678",
            "award_id": "CONT_AWD_1234_9700_SPE4A924D0001",
            "modification_number": "0",
            "action_date": "2023-03-15",
            "source_period_of_performance_start_date": "20230315",
            "source_period_of_performance_current_end_date": "20240315",
            "end_date_suppressed_before_effective_start": False,
            "funding_agency": "Department of Defense",
            "parent_uei": "XYZ987654321",
            "recipient_state": "CA",
            "business_categories": "{small_business,woman_owned}",
            "extent_competed": "FULL",
            "contract_award_type": "A",
            "parent_idv_piid": None,
            "referenced_idv_agency": None,
            "parent_relationship_type": "standalone",
            "research": "SR2",
            "naics_code": "541715",
            "product_or_service_code": "AC12",
        }

    def test_authoritative_uei_has_priority(self, sample_contract_row_full) -> None:
        row = dict(sample_contract_row_full)
        row["recipient_uei"] = "NEW987654321"
        row["recipient_unique_id"] = "OLD123456789"

        contract = ContractExtractor()._parse_contract_row(row)

        assert contract.vendor_uei == "NEW987654321"

    def test_nine_digit_legacy_id_is_duns(self, sample_contract_row_full) -> None:
        row = dict(sample_contract_row_full)
        row["recipient_uei"] = None
        row["recipient_unique_id"] = "123456789"

        contract = ContractExtractor()._parse_contract_row(row)

        assert contract.vendor_uei is None
        assert contract.vendor_duns == "123456789"

    @pytest.mark.parametrize(
        ("missing_field", "message"),
        [
            ("transaction_unique_id", "transaction_unique_id"),
            ("generated_unique_award_id", "generated_unique_award_id"),
        ],
    )
    def test_missing_stable_identifier_fails_closed(
        self, sample_contract_row_full, missing_field: str, message: str
    ) -> None:
        row = dict(sample_contract_row_full)
        row[missing_field] = None

        with pytest.raises(SourceDataError, match=message):
            ContractExtractor()._parse_contract_row(row)


class TestContractExtractorStatistics:
    def test_relationship_identifier_sets_are_finalized_on_write(
        self, tmp_path, monkeypatch, sample_child_contract_row, sample_idv_parent_row
    ) -> None:
        extractor = ContractExtractor()
        child = extractor._parse_contract_row(sample_child_contract_row)
        parent = extractor._parse_contract_row(sample_idv_parent_row)
        monkeypatch.setattr(
            "sbir_etl.utils.data.file_io.save_dataframe_parquet",
            lambda frame, path, **kwargs: path.write_bytes(b"parquet"),
        )

        count = extractor._collect_and_write([child, parent], tmp_path / "contracts.parquet")

        assert count == 2
        assert extractor.stats["unique_parent_ids"] == 1
        assert extractor.stats["unique_idv_parents"] == 1

    def test_batch_size_configuration(self) -> None:
        assert ContractExtractor(batch_size=500).batch_size == 500
        assert ContractExtractor().batch_size == 10000
