"""Unit tests for SBIR.gov cross-reference code.

Tests cover:
- SbirGovLookupIndex construction and lookup behavior
- SbirGovClient.build_lookup_index() static method
- _crossref_dataframe_with_sbir_gov() DataFrame enrichment
"""

import numpy as np
import pandas as pd
import pytest

from src.assets.usaspending_database_enrichment import _crossref_dataframe_with_sbir_gov
from src.extractors.sbir_gov_api import SbirGovClient, SbirGovLookupIndex


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_awards():
    """A small list of SBIR.gov award dicts with contract, UEI, and DUNS."""
    return [
        {
            "contract": "W911NF-20-C-0001",
            "uei": "ABC123456789",
            "duns": "123456789",
            "program": "SBIR",
            "phase": 1,
            "topic_code": "A20-001",
            "firm": "Acme Research Inc",
        },
        {
            "contract": "DE-SC0012345",
            "uei": "DEF987654321",
            "duns": "987-654-321",
            "program": "STTR",
            "phase": 2,
            "topic_code": "DOE-T100",
            "firm": "Energy Solutions LLC",
        },
        {
            "contract": "NNX17AA00A",
            "uei": "GHI111222333",
            "duns": "",
            "program": "SBIR",
            "phase": 1,
            "topic_code": "NASA-H01",
            "firm": "Space Widgets Corp",
        },
    ]


@pytest.fixture
def lookup_index(sample_awards):
    """Build a SbirGovLookupIndex from sample awards."""
    return SbirGovLookupIndex(sample_awards)


# ---------------------------------------------------------------------------
# SbirGovLookupIndex — construction
# ---------------------------------------------------------------------------


class TestSbirGovLookupIndexConstruction:
    """Tests for building the lookup index."""

    def test_build_from_empty_list(self):
        idx = SbirGovLookupIndex([])
        assert len(idx) == 0
        assert bool(idx) is False

    def test_build_from_awards_populates_contract_index(self, lookup_index, sample_awards):
        assert len(lookup_index) == len(sample_awards)
        assert bool(lookup_index) is True
        # All three awards have non-empty contract fields
        assert len(lookup_index.by_contract) == 3

    def test_build_from_awards_populates_uei_index(self, lookup_index):
        # All three awards have non-empty UEI
        assert len(lookup_index.by_uei) == 3

    def test_build_from_awards_populates_duns_index(self, lookup_index):
        # Third award has empty DUNS, second has dashes → digits extracted
        # Only the first two should be in the DUNS index
        assert len(lookup_index.by_duns) == 2

    def test_deduplication_last_wins_no_crash(self):
        """Same contract from two records: last one wins, no crash."""
        awards = [
            {"contract": "SAME-001", "program": "SBIR", "phase": 1, "firm": "First"},
            {"contract": "SAME-001", "program": "STTR", "phase": 2, "firm": "Second"},
        ]
        idx = SbirGovLookupIndex(awards)
        assert len(idx) == 2  # _size counts all records fed in
        # The second record should overwrite the first in the contract dict
        hit = idx.lookup(contract="SAME-001")
        assert hit is not None
        assert hit["firm"] == "Second"


# ---------------------------------------------------------------------------
# SbirGovLookupIndex — lookup behavior
# ---------------------------------------------------------------------------


class TestSbirGovLookupIndexLookup:
    """Tests for lookup() method."""

    def test_lookup_by_contract(self, lookup_index):
        hit = lookup_index.lookup(contract="W911NF-20-C-0001")
        assert hit is not None
        assert hit["firm"] == "Acme Research Inc"

    def test_lookup_contract_case_insensitive(self, lookup_index):
        hit = lookup_index.lookup(contract="w911nf-20-c-0001")
        assert hit is not None
        assert hit["firm"] == "Acme Research Inc"

    def test_lookup_by_uei(self, lookup_index):
        hit = lookup_index.lookup(uei="DEF987654321")
        assert hit is not None
        assert hit["firm"] == "Energy Solutions LLC"

    def test_lookup_uei_case_insensitive(self, lookup_index):
        hit = lookup_index.lookup(uei="def987654321")
        assert hit is not None
        assert hit["firm"] == "Energy Solutions LLC"

    def test_lookup_by_duns(self, lookup_index):
        hit = lookup_index.lookup(duns="123456789")
        assert hit is not None
        assert hit["firm"] == "Acme Research Inc"

    def test_lookup_duns_strips_non_digits(self, lookup_index):
        """DUNS with dashes/spaces should still match after digit extraction."""
        hit = lookup_index.lookup(duns="987-654-321")
        assert hit is not None
        assert hit["firm"] == "Energy Solutions LLC"

    def test_lookup_duns_digit_extraction_at_lookup_time(self, lookup_index):
        """Pass DUNS with non-digit chars at lookup time; should still resolve."""
        hit = lookup_index.lookup(duns="DUNS: 123-456-789")
        assert hit is not None
        assert hit["firm"] == "Acme Research Inc"

    def test_lookup_contract_takes_precedence_over_uei(self, lookup_index):
        """When contract matches one record and UEI matches another, contract wins."""
        hit = lookup_index.lookup(
            contract="W911NF-20-C-0001",  # → Acme Research
            uei="DEF987654321",           # → Energy Solutions
        )
        assert hit is not None
        assert hit["firm"] == "Acme Research Inc"

    def test_lookup_contract_takes_precedence_over_duns(self, lookup_index):
        hit = lookup_index.lookup(
            contract="DE-SC0012345",  # → Energy Solutions
            duns="123456789",         # → Acme Research
        )
        assert hit is not None
        assert hit["firm"] == "Energy Solutions LLC"

    def test_lookup_uei_takes_precedence_over_duns(self, lookup_index):
        """When contract is None but UEI and DUNS both present, UEI wins."""
        hit = lookup_index.lookup(
            uei="GHI111222333",  # → Space Widgets
            duns="123456789",    # → Acme Research
        )
        assert hit is not None
        assert hit["firm"] == "Space Widgets Corp"

    def test_lookup_returns_none_when_no_match(self, lookup_index):
        hit = lookup_index.lookup(
            contract="NONEXISTENT",
            uei="ZZZZZZZZZ",
            duns="0000000",
        )
        assert hit is None

    def test_lookup_returns_none_with_all_none_args(self, lookup_index):
        assert lookup_index.lookup() is None

    def test_lookup_returns_none_with_empty_strings(self, lookup_index):
        assert lookup_index.lookup(contract="", uei="", duns="") is None


# ---------------------------------------------------------------------------
# SbirGovClient.build_lookup_index()
# ---------------------------------------------------------------------------


class TestSbirGovClientBuildLookupIndex:
    """Verify the static method delegates to SbirGovLookupIndex."""

    def test_returns_lookup_index_instance(self, sample_awards):
        idx = SbirGovClient.build_lookup_index(sample_awards)
        assert isinstance(idx, SbirGovLookupIndex)
        assert len(idx) == len(sample_awards)

    def test_empty_list_returns_empty_index(self):
        idx = SbirGovClient.build_lookup_index([])
        assert isinstance(idx, SbirGovLookupIndex)
        assert len(idx) == 0


# ---------------------------------------------------------------------------
# _crossref_dataframe_with_sbir_gov
# ---------------------------------------------------------------------------


class TestCrossrefDataframeWithSbirGov:
    """Tests for the DataFrame cross-reference helper."""

    def _make_index(self):
        """Build a small index for DataFrame tests."""
        awards = [
            {
                "contract": "AWARD-001",
                "uei": "UEI111",
                "duns": "111111111",
                "program": "SBIR",
                "phase": 1,
                "topic_code": "T-001",
                "firm": "Match Firm A",
            },
            {
                "contract": "AWARD-002",
                "uei": "UEI222",
                "duns": "222222222",
                "program": "STTR",
                "phase": 2,
                "topic_code": "T-002",
                "firm": "Match Firm B",
            },
        ]
        return SbirGovLookupIndex(awards)

    def test_matching_and_nonmatching_rows(self):
        index = self._make_index()
        df = pd.DataFrame({
            "award_id": ["AWARD-001", "AWARD-002", "NO-MATCH"],
            "recipient_uei": ["UEI111", "UEI222", "UEIXXX"],
            "recipient_duns": ["111111111", "222222222", "999999999"],
        })
        result = _crossref_dataframe_with_sbir_gov(df, index)

        assert result["sbir_gov_confirmed"].tolist() == [True, True, False]
        assert result["sbir_gov_program"].tolist() == ["SBIR", "STTR", ""]
        assert result["sbir_gov_phase"].tolist() == ["1", "2", ""]
        assert result["sbir_gov_topic_code"].tolist() == ["T-001", "T-002", ""]
        assert result["sbir_gov_firm"].tolist() == ["Match Firm A", "Match Firm B", ""]

    def test_all_five_output_columns_added(self):
        index = self._make_index()
        df = pd.DataFrame({
            "award_id": ["AWARD-001"],
            "recipient_uei": ["UEI111"],
            "recipient_duns": ["111111111"],
        })
        result = _crossref_dataframe_with_sbir_gov(df, index)

        expected_cols = {
            "sbir_gov_confirmed",
            "sbir_gov_program",
            "sbir_gov_phase",
            "sbir_gov_topic_code",
            "sbir_gov_firm",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_nan_none_values_handled(self):
        """NaN / None in award_id, uei, duns should not raise."""
        index = self._make_index()
        df = pd.DataFrame({
            "award_id": [None, np.nan, "AWARD-001"],
            "recipient_uei": [np.nan, None, "UEI111"],
            "recipient_duns": [np.nan, np.nan, "111111111"],
        })
        result = _crossref_dataframe_with_sbir_gov(df, index)

        assert len(result) == 3
        # First two rows should not match
        assert result["sbir_gov_confirmed"].iloc[0] is False or result["sbir_gov_confirmed"].iloc[0] == False  # noqa: E712
        assert result["sbir_gov_confirmed"].iloc[1] is False or result["sbir_gov_confirmed"].iloc[1] == False  # noqa: E712
        # Third row should match
        assert result["sbir_gov_confirmed"].iloc[2] == True  # noqa: E712

    def test_empty_dataframe_returns_empty_with_new_columns(self):
        index = self._make_index()
        df = pd.DataFrame({
            "award_id": pd.Series([], dtype="object"),
            "recipient_uei": pd.Series([], dtype="object"),
            "recipient_duns": pd.Series([], dtype="object"),
        })
        result = _crossref_dataframe_with_sbir_gov(df, index)

        assert len(result) == 0
        expected_cols = {
            "sbir_gov_confirmed",
            "sbir_gov_program",
            "sbir_gov_phase",
            "sbir_gov_topic_code",
            "sbir_gov_firm",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_custom_column_name_parameters(self):
        """Custom col names for award_id, uei, duns should work."""
        index = self._make_index()
        df = pd.DataFrame({
            "my_award": ["AWARD-001", "NO-MATCH"],
            "my_uei": ["UEI111", "UEIXXX"],
            "my_duns": ["111111111", "999999999"],
        })
        result = _crossref_dataframe_with_sbir_gov(
            df,
            index,
            award_id_col="my_award",
            uei_col="my_uei",
            duns_col="my_duns",
        )

        assert result["sbir_gov_confirmed"].tolist() == [True, False]
        assert result["sbir_gov_firm"].tolist() == ["Match Firm A", ""]

    def test_does_not_mutate_original_dataframe(self):
        """The function returns a copy; original should be untouched."""
        index = self._make_index()
        df = pd.DataFrame({
            "award_id": ["AWARD-001"],
            "recipient_uei": ["UEI111"],
            "recipient_duns": ["111111111"],
        })
        original_cols = set(df.columns)
        _crossref_dataframe_with_sbir_gov(df, index)
        assert set(df.columns) == original_cols
