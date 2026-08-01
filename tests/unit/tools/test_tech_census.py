"""Tests for the Tech Census tool (all-phase, subset-taxonomy queries)."""

import pandas as pd

from sbir_analytics.tools.tech_census import ComputeTechCensusTool


def _award(
    title="",
    abstract="",
    company="Acme",
    agency="Department of Defense",
    program="SBIR",
    phase="Phase II",
    year=2024,
    amount=500_000.0,
):
    return {
        "title": title,
        "abstract": abstract,
        "company": company,
        "agency": agency,
        "program": program,
        "phase": phase,
        "award_year": year,
        "award_amount": amount,
        "agency_tracking_number": "TRACK",
        "contract": "CONTRACT",
        "source_row": 2,
    }


class TestComputeTechCensusTool:
    def test_empty_dataframe(self):
        tool = ComputeTechCensusTool()
        result = tool.run(awards_df=pd.DataFrame(), area_id="drone_manufacturing")
        assert result.data["summary"]["grand_total"] == {"n": 0, "usd": 0.0}
        assert "No awards data provided" in result.metadata.warnings

    def test_none_dataframe(self):
        tool = ComputeTechCensusTool()
        result = tool.run(area_id="drone_manufacturing")
        assert result.data["summary"]["grand_total"] == {"n": 0, "usd": 0.0}

    def test_missing_columns_warns_not_raises(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame([{"title": "Drone thing"}])  # missing most required columns
        result = tool.run(awards_df=df, area_id="drone_manufacturing")
        assert result.data["summary"]["grand_total"] == {"n": 0, "usd": 0.0}
        assert any("missing required columns" in w for w in result.metadata.warnings)

    def test_unknown_area_warns_not_raises(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame([_award(title="Drone battery")])
        result = tool.run(awards_df=df, area_id="no_such_area")
        assert result.data["summary"]["grand_total"] == {"n": 0, "usd": 0.0}
        assert any("Could not load tech-census config" in w for w in result.metadata.warnings)

    def test_classifies_and_aggregates_real_drone_config(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame(
            [
                _award(title="Drone battery hybridizer", year=2024, amount=1_000_000.0),
                _award(title="Drone gimbal payload system", year=2024, amount=500_000.0),
                _award(title="Unrelated antibiotic research", year=2024, amount=750_000.0),
            ]
        )
        result = tool.run(awards_df=df, area_id="drone_manufacturing")
        summary = result.data["summary"]
        assert summary["grand_total"] == {"n": 2, "usd": 1_500_000.0}
        assert result.data["award_count"] == 2
        assert result.data["award_dollars"] == 1_500_000.0
        assert result.metadata.record_count == 2
        assert len(result.metadata.data_sources) == 1
        assert (
            result.metadata.data_sources[0].record_count == 3
        )  # all rows passed in, not just matches

    def test_results_dataframe_shape(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame([_award(title="Drone propulsion system")])
        result = tool.run(awards_df=df, area_id="drone_manufacturing")
        results_df = result.data["results"]
        assert len(results_df) == 1
        assert set(results_df.columns) >= {"title", "company", "year", "amount", "subset"}

    def test_strict_and_broad_profiles_apply_different_program_scope(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame(
            [
                _award(title="Drone airframe", program="SBIR"),
                _award(title="Drone airframe", program="STTR"),
            ]
        )
        strict = tool.run(awards_df=df, area_id="drone_manufacturing")
        broad = tool.run(awards_df=df, area_id="uas_relevance")
        assert strict.data["award_count"] == 1
        assert strict.data["summary"]["program_exclusion_counts"] == {"STTR": 1}
        assert broad.data["award_count"] == 2

    def test_fiscal_year_filter_and_provenance_are_reported(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame(
            [
                _award(title="Drone airframe", year=2024, amount=100_000),
                _award(title="Drone airframe", year=2025, amount=200_000),
            ]
        )
        result = tool.run(
            awards_df=df,
            area_id="drone_manufacturing",
            fiscal_years=[2025],
            source_path="/data/award_data.csv",
            source_sha256="abc123",
            source_timestamp="2026-07-14T12:00:00+00:00",
            data_vintage="2026-07-14",
        )
        assert result.data["award_count"] == 1
        assert result.data["award_dollars"] == 200_000.0
        summary = result.data["summary"]
        assert summary["reporting_window"]["fiscal_years"] == [2025]
        assert summary["provenance"] == {
            "source_path": "/data/award_data.csv",
            "sha256": "abc123",
            "source_timestamp": "2026-07-14T12:00:00+00:00",
            "data_vintage": "2026-07-14",
            "source_row_count": 2,
            "reporting_row_count": 1,
        }
        assert result.metadata.data_sources[0].version == "2026-07-14"

    def test_result_rows_include_audit_columns(self):
        result = ComputeTechCensusTool().run(
            awards_df=pd.DataFrame([_award(title="Drone avionics")]),
            area_id="drone_manufacturing",
        )
        assert set(result.data["results"].columns) >= {
            "program",
            "agency_tracking_number",
            "contract",
            "source_row",
            "gate_evidence",
            "physical_evidence",
            "scope_class",
            "classification_source",
        }

    def test_nullable_and_string_years_are_normalized_before_aggregation(self):
        tool = ComputeTechCensusTool()
        df = pd.DataFrame(
            [
                _award(title="Drone airframe", year=2025, amount=100_000),
                _award(title="Drone airframe", year=None, amount=None),
                _award(title="Drone airframe", year="2024", amount="$250,000"),
            ]
        )
        result = tool.run(awards_df=df, area_id="drone_manufacturing")
        assert result.data["award_count"] == 3
        assert result.data["award_dollars"] == 350_000.0
        assert result.data["summary"]["fy_totals"] == {
            "2025": {"n": 1, "usd": 100_000.0},
            "2024": {"n": 1, "usd": 250_000.0},
        }
