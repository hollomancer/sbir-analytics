"""Tests for the Tech Census tool (all-phase, subset-taxonomy queries)."""

import pandas as pd

from sbir_analytics.tools.tech_census import ComputeTechCensusTool


def _award(
    title="",
    abstract="",
    company="Acme",
    agency="Department of Defense",
    phase="Phase II",
    year=2024,
    amount=500_000.0,
):
    return {
        "title": title,
        "abstract": abstract,
        "company": company,
        "agency": agency,
        "phase": phase,
        "award_year": year,
        "award_amount": amount,
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
