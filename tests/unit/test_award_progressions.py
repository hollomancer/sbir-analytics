"""Tests for award progression detection (FOLLOWS relationship)."""

from datetime import date

import pytest

from src.assets.sbir_neo4j_loading import detect_award_progressions
from src.models.award import Award


pytestmark = pytest.mark.fast


class TestAwardProgressionDetection:
    """Tests for detect_award_progressions function."""

    def test_no_progressions_with_empty_list(self):
        """Test that empty award list returns no progressions."""
        progressions = detect_award_progressions([])
        assert progressions == []

    def test_no_progressions_with_single_award(self):
        """Test that single award returns no progressions."""
        award = Award(
            award_id="TEST-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        progressions = detect_award_progressions([award])
        assert progressions == []

    def test_simple_phase_i_to_ii_progression(self):
        """Test detection of Phase I → Phase II progression."""
        phase_i = Award(
            award_id="TEST-001-I",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
            principal_investigator="Dr. Jane Smith",
            topic_code="A20-001",
        )
        phase_ii = Award(
            award_id="TEST-001-II",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
            principal_investigator="Dr. Jane Smith",
            topic_code="A20-001",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])

        assert len(progressions) == 1
        prog = progressions[0]
        assert prog[0] == "FinancialTransaction"  # source label
        assert prog[1] == "award_id"  # source key
        assert prog[2] == "txn_award_TEST-001-I"  # source id (with txn_award_ prefix)
        assert prog[3] == "FinancialTransaction"  # target label
        assert prog[4] == "award_id"  # target key
        assert prog[5] == "txn_award_TEST-001-II"  # target id (with txn_award_ prefix)
        assert prog[6] == "FOLLOWS"  # relationship type
        assert prog[7]["phase_progression"] == "I_to_II"
        assert prog[7]["same_topic"] is True
        assert prog[7]["same_pi"] is True
        assert prog[7]["confidence"] == 1.0  # 0.5 + 0.3 + 0.2 = 1.0

    def test_phase_ii_to_iii_progression(self):
        """Test detection of Phase II → Phase III progression."""
        phase_ii = Award(
            award_id="TEST-002-II",
            company_name="Innovation Inc",
            company_duns="987654321",
            award_amount=1000000.0,
            award_date=date(2020, 6, 1),
            program="SBIR",
            phase="II",
            agency="NASA",
        )
        phase_iii = Award(
            award_id="TEST-002-III",
            company_name="Innovation Inc",
            company_duns="987654321",
            award_amount=5000000.0,
            award_date=date(2023, 6, 1),
            program="SBIR",
            phase="III",
            agency="NASA",
        )

        progressions = detect_award_progressions([phase_ii, phase_iii])

        assert len(progressions) == 1
        prog = progressions[0]
        assert prog[2] == "txn_award_TEST-002-II"
        assert prog[5] == "txn_award_TEST-002-III"
        assert prog[7]["phase_progression"] == "II_to_III"

    def test_full_chain_i_to_ii_to_iii(self):
        """Test detection of full Phase I → II → III chain."""
        phase_i = Award(
            award_id="CHAIN-I",
            company_name="Tech Startup",
            company_uei="CHAIN1234567",
            award_amount=150000.0,
            award_date=date(2019, 1, 1),
            program="STTR",
            phase="I",
            agency="DOE",
        )
        phase_ii = Award(
            award_id="CHAIN-II",
            company_name="Tech Startup",
            company_uei="CHAIN1234567",
            award_amount=1000000.0,
            award_date=date(2021, 1, 1),
            program="STTR",
            phase="II",
            agency="DOE",
        )
        phase_iii = Award(
            award_id="CHAIN-III",
            company_name="Tech Startup",
            company_uei="CHAIN1234567",
            award_amount=5000000.0,
            award_date=date(2024, 1, 1),
            program="STTR",
            phase="III",
            agency="DOE",
        )

        progressions = detect_award_progressions([phase_i, phase_ii, phase_iii])

        # Should find two progressions: I→II and II→III
        assert len(progressions) == 2

        # Check I→II
        i_to_ii = [p for p in progressions if p[2] == "txn_award_CHAIN-I"][0]
        assert i_to_ii[5] == "txn_award_CHAIN-II"

        # Check II→III
        ii_to_iii = [p for p in progressions if p[2] == "txn_award_CHAIN-II"][0]
        assert ii_to_iii[5] == "txn_award_CHAIN-III"

    def test_no_progression_different_companies(self):
        """Test that awards from different companies don't create progressions."""
        phase_i = Award(
            award_id="DIFF-001",
            company_name="Company A",
            company_uei="COMP1A123456",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="DIFF-002",
            company_name="Company B",
            company_uei="COMP1B654321",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert progressions == []

    def test_no_progression_different_agencies(self):
        """Test that awards from different agencies don't create progressions."""
        phase_i = Award(
            award_id="AGENCY-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="AGENCY-002",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="NASA",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert progressions == []

    def test_no_progression_different_programs(self):
        """Test that SBIR and STTR awards don't create progressions."""
        phase_i = Award(
            award_id="PROG-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="PROG-002",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="STTR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert progressions == []

    def test_no_progression_wrong_chronological_order(self):
        """Test that later awards must come after earlier awards chronologically."""
        phase_i = Award(
            award_id="CHRONO-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2022, 1, 1),  # Later date
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="CHRONO-002",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2020, 1, 1),  # Earlier date
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert progressions == []

    def test_company_matching_by_duns(self):
        """Test that progression detection works with DUNS matching."""
        phase_i = Award(
            award_id="DUNS-001",
            company_name="Test Corp",
            company_duns="123456789",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="DUNS-002",
            company_name="Test Corp",
            company_duns="123456789",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert len(progressions) == 1

    def test_company_matching_by_normalized_name(self):
        """Test that progression detection works with normalized name matching."""
        phase_i = Award(
            award_id="NAME-001",
            company_name="Acme Technologies, Inc.",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="NAME-002",
            company_name="ACME TECH LLC",  # Should normalize to same name
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert len(progressions) == 1

    def test_confidence_scoring_with_topic_and_pi(self):
        """Test confidence scoring with various matching factors."""
        phase_i = Award(
            award_id="CONF-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
            principal_investigator="Dr. John Doe",
            topic_code="A20-001",
        )
        phase_ii = Award(
            award_id="CONF-002",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2021, 6, 1),  # 1.5 years later
            program="SBIR",
            phase="II",
            agency="DOD",
            principal_investigator="Dr. John Doe",
            topic_code="A20-001",
        )

        progressions = detect_award_progressions([phase_i, phase_ii])
        assert len(progressions) == 1

        rel_props = progressions[0][7]
        # Base (0.5) + same_topic (0.3) + same_pi (0.2) + reasonable_gap (0.1) = 1.1
        assert rel_props["confidence"] == 1.1
        assert rel_props["same_topic"] is True
        assert rel_props["same_pi"] is True
        assert "years_between" in rel_props

    def test_awards_without_phase_ignored(self):
        """Test that awards without phase information are ignored."""
        no_phase = Award(
            award_id="NOPHASE-001",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            agency="DOD",
        )
        phase_ii = Award(
            award_id="NOPHASE-002",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([no_phase, phase_ii])
        assert progressions == []

    def test_only_first_matching_phase_ii_linked(self):
        """Test that Phase I links to only the first matching Phase II."""
        phase_i = Award(
            award_id="MULTI-I",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=150000.0,
            award_date=date(2020, 1, 1),
            program="SBIR",
            phase="I",
            agency="DOD",
        )
        phase_ii_a = Award(
            award_id="MULTI-II-A",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2022, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )
        phase_ii_b = Award(
            award_id="MULTI-II-B",
            company_name="Test Corp",
            company_uei="TEST12345678",
            award_amount=1000000.0,
            award_date=date(2023, 1, 1),
            program="SBIR",
            phase="II",
            agency="DOD",
        )

        progressions = detect_award_progressions([phase_i, phase_ii_a, phase_ii_b])

        # Should only link to the first Phase II
        assert len(progressions) == 1
        assert progressions[0][2] == "txn_award_MULTI-I"
        assert progressions[0][5] == "txn_award_MULTI-II-A"
