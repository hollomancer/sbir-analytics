"""Tests for CompanyCETAggregator transformer."""

import pandas as pd
import pytest

from sbir_etl.transformers.company_cet_aggregator import CompanyCETAggregator


pytestmark = pytest.mark.fast


class TestCompanyCETAggregatorInitialization:
    """Tests for CompanyCETAggregator initialization."""

    def test_initialization_with_dataframe(self):
        """Test initialization with pandas DataFrame."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c2"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [85.0, 90.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert isinstance(aggregator.df, pd.DataFrame)
        assert len(aggregator.df) == 2

    def test_initialization_with_dict_iterable(self):
        """Test initialization with list of dicts."""
        awards = [
            {"award_id": "a1", "company_id": "c1", "primary_cet": "cet1", "primary_score": 85.0},
            {"award_id": "a2", "company_id": "c2", "primary_cet": "cet2", "primary_score": 90.0},
        ]

        aggregator = CompanyCETAggregator(awards)

        assert isinstance(aggregator.df, pd.DataFrame)
        assert len(aggregator.df) == 2

    def test_initialization_adds_missing_columns(self):
        """Test that initialization adds missing default columns."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should add default columns
        expected_cols = [
            "award_id",
            "company_id",
            "company_name",
            "primary_cet",
            "primary_score",
            "supporting_cets",
            "classified_at",
            "taxonomy_version",
            "award_date",
            "phase",
        ]

        for col in expected_cols:
            assert col in aggregator.df.columns

    def test_initialization_preserves_existing_data(self):
        """Test that initialization preserves existing data."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c2"],
                "company_name": ["Company 1", "Company 2"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [85.0, 90.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert aggregator.df["company_name"].tolist() == ["Company 1", "Company 2"]
        assert aggregator.df["primary_cet"].tolist() == ["cet1", "cet2"]


class TestExtractCETRows:
    """Tests for _extract_cet_rows_from_award method."""

    def test_extract_primary_cet_only(self):
        """Test extracting primary CET only."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": 85.0,
            "supporting_cets": [],
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 1
        assert rows[0] == ("cet1", 85.0, "a1")

    def test_extract_primary_and_supporting_cets(self):
        """Test extracting primary and supporting CETs."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": 85.0,
            "supporting_cets": [
                {"cet_id": "cet2", "score": 70.0},
                {"cet_id": "cet3", "score": 65.0},
            ],
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 3
        assert ("cet1", 85.0, "a1") in rows
        assert ("cet2", 70.0, "a1") in rows
        assert ("cet3", 65.0, "a1") in rows

    def test_extract_with_missing_primary_score(self):
        """Test extraction with missing primary score defaults to 0.0."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": None,
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 1
        assert rows[0] == ("cet1", 0.0, "a1")

    def test_extract_with_no_primary_cet(self):
        """Test extraction with no primary CET."""
        row = {
            "award_id": "a1",
            "primary_cet": None,
            "primary_score": 85.0,
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 0

    def test_extract_supporting_cets_tuple_format(self):
        """Test extraction with supporting CETs as tuples."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": 85.0,
            "supporting_cets": [
                ("cet2", 70.0),
                ("cet3", 65.0),
            ],
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 3
        assert ("cet2", 70.0, "a1") in rows
        assert ("cet3", 65.0, "a1") in rows

    def test_extract_with_invalid_score_format(self):
        """Test extraction handles invalid score format gracefully."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": "not_a_number",
            "supporting_cets": [
                {"cet_id": "cet2", "score": "also_invalid"},
            ],
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        # Should convert invalid scores to 0.0
        assert len(rows) == 2
        assert rows[0] == ("cet1", 0.0, "a1")
        assert rows[1] == ("cet2", 0.0, "a1")

    def test_extract_with_alternative_supporting_dict_keys(self):
        """Test extraction with alternative dict keys for supporting CETs."""
        row = {
            "award_id": "a1",
            "primary_cet": "cet1",
            "primary_score": 85.0,
            "supporting_cets": [
                {"cet": "cet2", "score": 70.0},  # Using 'cet' instead of 'cet_id'
            ],
        }

        rows = CompanyCETAggregator._extract_cet_rows_from_award(row)

        assert len(rows) == 2
        assert ("cet2", 70.0, "a1") in rows


class TestCompanyCETMatrix:
    """Tests for _build_company_cet_matrix method."""

    def test_build_matrix_simple(self):
        """Test building CET matrix with simple data."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c2"],
                "company_name": ["Company 1", "Company 2"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [85.0, 90.0],
                "supporting_cets": [[], []],
            }
        )

        aggregator = CompanyCETAggregator(df)
        matrix = aggregator._build_company_cet_matrix()

        assert isinstance(matrix, pd.DataFrame)
        assert len(matrix) == 2
        assert "company_id" in matrix.columns
        assert "cet_id" in matrix.columns
        assert "score" in matrix.columns

    def test_build_matrix_with_supporting_cets(self):
        """Test matrix includes supporting CETs."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "company_name": ["Company 1"],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
                "supporting_cets": [
                    [
                        {"cet_id": "cet2", "score": 70.0},
                        {"cet_id": "cet3", "score": 65.0},
                    ]
                ],
            }
        )

        aggregator = CompanyCETAggregator(df)
        matrix = aggregator._build_company_cet_matrix()

        assert len(matrix) == 3  # Primary + 2 supporting
        assert "cet1" in matrix["cet_id"].values
        assert "cet2" in matrix["cet_id"].values
        assert "cet3" in matrix["cet_id"].values

    def test_build_matrix_with_no_cets(self):
        """Test matrix handles awards with no CETs."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "company_name": ["Company 1"],
                "primary_cet": [None],
                "primary_score": [None],
                "supporting_cets": [[]],
            }
        )

        aggregator = CompanyCETAggregator(df)
        matrix = aggregator._build_company_cet_matrix()

        # Should create placeholder row
        assert len(matrix) == 1
        assert matrix.iloc[0]["has_cet"] == False  # noqa: E712


class TestCompanyCETAggregatorEdgeCases:
    """Tests for edge cases in CompanyCETAggregator."""

    def test_empty_dataframe(self):
        """Test handling empty DataFrame."""
        df = pd.DataFrame()

        aggregator = CompanyCETAggregator(df)

        assert isinstance(aggregator.df, pd.DataFrame)
        # Should add default columns even to empty DataFrame
        assert "award_id" in aggregator.df.columns

    def test_single_award(self):
        """Test processing single award."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert len(aggregator.df) == 1

    def test_multiple_awards_same_company(self):
        """Test processing multiple awards for same company."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": ["c1", "c1", "c1"],
                "primary_cet": ["cet1", "cet2", "cet1"],
                "primary_score": [85.0, 90.0, 88.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert len(aggregator.df) == 3
        assert (aggregator.df["company_id"] == "c1").all()

    def test_award_date_parsing(self):
        """Test award date parsing."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c2"],
                "award_date": ["2023-01-15", "2023-06-20"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [85.0, 90.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should have parsed award_date_parsed column
        assert "award_date_parsed" in aggregator.df.columns
        assert not aggregator.df["award_date_parsed"].isna().all()

    def test_award_date_parsing_invalid(self):
        """Test award date parsing with invalid dates."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "award_date": ["not-a-date"],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should handle gracefully, setting to NaT
        assert "award_date_parsed" in aggregator.df.columns

    def test_phase_field_preserved(self):
        """Test that phase field is preserved."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": ["c1", "c1", "c2"],
                "phase": ["I", "II", "I"],
                "primary_cet": ["cet1", "cet2", "cet3"],
                "primary_score": [85.0, 90.0, 88.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert aggregator.df["phase"].tolist() == ["I", "II", "I"]

    def test_supporting_cets_normalization(self):
        """Test supporting_cets field normalization."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": ["c1", "c2", "c3"],
                "primary_cet": ["cet1", "cet2", "cet3"],
                "primary_score": [85.0, 90.0, 88.0],
                "supporting_cets": [
                    [],
                    None,  # Should be normalized to []
                    [{"cet_id": "cet4", "score": 70.0}],
                ],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # All supporting_cets should be list-like
        for val in aggregator.df["supporting_cets"]:
            assert isinstance(val, list | tuple)

    def test_zero_scores(self):
        """Test handling of zero scores."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2"],
                "company_id": ["c1", "c2"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [0.0, 0.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should preserve zero scores
        assert (aggregator.df["primary_score"] == 0.0).all()

    def test_high_scores(self):
        """Test handling of scores at upper bound."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "primary_cet": ["cet1"],
                "primary_score": [100.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert aggregator.df["primary_score"].iloc[0] == 100.0

    def test_mixed_data_types(self):
        """Test handling of mixed data types in company_id."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a2", "a3"],
                "company_id": [1, "c2", 3.0],  # Mixed int, str, float
                "primary_cet": ["cet1", "cet2", "cet3"],
                "primary_score": [85.0, 90.0, 88.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should handle mixed types
        assert len(aggregator.df) == 3


class TestCompanyCETAggregatorDataQuality:
    """Tests for data quality handling in CompanyCETAggregator."""

    def test_missing_company_id(self):
        """Test handling of missing company_id."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": [None],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert len(aggregator.df) == 1

    def test_missing_award_id(self):
        """Test handling of missing award_id."""
        df = pd.DataFrame(
            {
                "award_id": [None],
                "company_id": ["c1"],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        assert len(aggregator.df) == 1

    def test_duplicate_award_ids(self):
        """Test handling of duplicate award IDs."""
        df = pd.DataFrame(
            {
                "award_id": ["a1", "a1"],  # Duplicate
                "company_id": ["c1", "c1"],
                "primary_cet": ["cet1", "cet2"],
                "primary_score": [85.0, 90.0],
            }
        )

        aggregator = CompanyCETAggregator(df)

        # Should preserve both rows
        assert len(aggregator.df) == 2

    def test_empty_cet_id_in_supporting(self):
        """Test handling of empty CET IDs in supporting CETs."""
        df = pd.DataFrame(
            {
                "award_id": ["a1"],
                "company_id": ["c1"],
                "primary_cet": ["cet1"],
                "primary_score": [85.0],
                "supporting_cets": [
                    [
                        {"cet_id": "", "score": 70.0},  # Empty cet_id
                        {"cet_id": None, "score": 65.0},  # None cet_id
                    ]
                ],
            }
        )

        aggregator = CompanyCETAggregator(df)
        matrix = aggregator._build_company_cet_matrix()

        # Should skip empty/None cet_ids
        # Only primary CET should remain
        assert len(matrix) == 1


class TestToDataframe:
    """Tests for to_dataframe output aggregation."""

    def test_aggregate_single_company_basic(self):
        """Basic aggregation for a single company with coverage, dominant CET,
        cet_scores, specialization (HHI) and date range."""
        from datetime import datetime

        data = [
            {
                "award_id": "A1",
                "company_id": "C1",
                "company_name": "Acme Corp",
                "primary_cet": "cet_a",
                "primary_score": 80,
                "supporting_cets": [],
                "award_date": "2020-01-15",
                "classified_at": "2020-01-16",
            },
            {
                "award_id": "A2",
                "company_id": "C1",
                "company_name": "Acme Corp",
                "primary_cet": "cet_b",
                "primary_score": 20,
                "supporting_cets": [],
                "award_date": "2021-06-01",
                "classified_at": "2021-06-02",
            },
            {
                "award_id": "A3",
                "company_id": "C1",
                "company_name": "Acme Corp",
                "primary_cet": None,
                "primary_score": None,
                "supporting_cets": [],
                "award_date": "2022-03-10",
                "classified_at": None,
            },
        ]

        df = pd.DataFrame(data)
        agg = CompanyCETAggregator(df)
        df_comp = agg.to_dataframe()

        assert len(df_comp) == 1

        row = df_comp.iloc[0]
        assert row["company_id"] == "C1"
        assert row["company_name"] == "Acme Corp"
        assert row["total_awards"] == 3
        assert row["awards_with_cet"] == 2
        assert pytest.approx(row["coverage"]) == 2 / 3

        expected_scores = {"cet_a": 80.0, "cet_b": 20.0}
        assert row["cet_scores"] == expected_scores
        assert row["dominant_cet"] == "cet_a"
        assert pytest.approx(row["dominant_score"]) == 80.0

        # HHI: (0.8^2 + 0.2^2) = 0.64 + 0.04 = 0.68
        assert pytest.approx(row["specialization_score"], rel=1e-6) == pytest.approx(
            0.68, rel=1e-6
        )

        assert pd.to_datetime(row["first_award_date"]).date() == datetime(2020, 1, 15).date()
        assert pd.to_datetime(row["last_award_date"]).date() == datetime(2022, 3, 10).date()

        assert isinstance(row["cet_trend"], dict)
        assert "2020" in row["cet_trend"]
        assert "2021" in row["cet_trend"]

    def test_include_supporting_cets_affects_scores_and_specialization(self):
        """Supporting CETs contribute to per-CET aggregates."""
        data = [
            {
                "award_id": "B1",
                "company_id": "C2",
                "company_name": "Beta LLC",
                "primary_cet": "cet_x",
                "primary_score": 60,
                "supporting_cets": [
                    {"cet_id": "cet_y", "score": 40},
                    {"cet_id": "cet_x", "score": 20},
                ],
                "award_date": "2019-05-20",
            }
        ]

        df = pd.DataFrame(data)
        agg = CompanyCETAggregator(df)
        df_comp = agg.to_dataframe()

        assert len(df_comp) == 1
        row = df_comp.iloc[0]
        cet_scores = row["cet_scores"]
        assert pytest.approx(cet_scores["cet_x"]) == 40.0
        assert pytest.approx(cet_scores["cet_y"]) == 40.0

        assert pytest.approx(row["specialization_score"], rel=1e-6) == pytest.approx(
            0.5, rel=1e-6
        )

    def test_no_cets_results_in_empty_scores_and_zero_coverage(self):
        """Company with no CETs produces coverage=0, empty cet_scores, no dominant CET."""
        data = [
            {"award_id": "C1", "company_id": "C3", "company_name": "Gamma Inc", "primary_cet": None},
            {"award_id": "C2", "company_id": "C3", "company_name": "Gamma Inc", "primary_cet": None},
        ]
        df = pd.DataFrame(data)
        agg = CompanyCETAggregator(df)
        df_comp = agg.to_dataframe()

        assert len(df_comp) == 1
        row = df_comp.iloc[0]
        assert row["total_awards"] == 2
        assert row["awards_with_cet"] == 0
        assert row["coverage"] == 0.0
        assert row["cet_scores"] == {}
        assert row["dominant_cet"] is None
        assert row["dominant_score"] is None
        assert row["specialization_score"] == 0.0

    def test_trend_by_phase_preference_over_year(self):
        """When awards contain a phase value, trend is keyed by phase rather than year."""
        data = [
            {
                "award_id": "D1",
                "company_id": "C4",
                "company_name": "Delta Co",
                "primary_cet": "cet_m",
                "primary_score": 50,
                "phase": "I",
                "award_date": "2018-02-02",
            },
            {
                "award_id": "D2",
                "company_id": "C4",
                "company_name": "Delta Co",
                "primary_cet": "cet_n",
                "primary_score": 50,
                "phase": "II",
                "award_date": "2019-07-07",
            },
        ]
        df = pd.DataFrame(data)
        agg = CompanyCETAggregator(df)
        df_comp = agg.to_dataframe()

        assert len(df_comp) == 1
        row = df_comp.iloc[0]

        assert "I" in row["cet_trend"]
        assert "II" in row["cet_trend"]

        phase_i = row["cet_trend"]["I"]
        assert isinstance(phase_i, dict)
        assert pytest.approx(sum(phase_i.values()), rel=1e-6) == pytest.approx(1.0, rel=1e-6)
        assert "cet_m" in phase_i

        phase_ii = row["cet_trend"]["II"]
        assert pytest.approx(sum(phase_ii.values()), rel=1e-6) == pytest.approx(1.0, rel=1e-6)
        assert "cet_n" in phase_ii
