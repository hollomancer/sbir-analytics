"""Tests for congressional-district fiscal impact allocation."""

from unittest.mock import Mock

import pandas as pd
import pytest

from sbir_etl.enrichers import fiscal_bea_mapper
from sbir_etl.transformers.fiscal.district_allocator import (
    allocate_state_impacts_to_districts,
    compare_districts_within_state,
    summarize_by_district,
)


pytestmark = pytest.mark.fast


def _state_impacts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "54",
                "fiscal_year": 2024,
                "production_impact": 1000.0,
                "wage_impact": 400.0,
                "proprietor_income_impact": 100.0,
                "gross_operating_surplus": 200.0,
                "tax_impact": 80.0,
                "consumption_impact": 500.0,
                "jobs_created": 10.0,
                "confidence": 0.9,
                "model_version": "bea-v1",
            }
        ]
    )


def test_allocate_state_impacts_proportionally_and_excludes_unresolved_awards():
    awards = pd.DataFrame(
        [
            {
                "state": "CA",
                "congressional_district": "CA-01",
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 100.0,
                "congressional_district_confidence": 0.8,
            },
            {
                "state": "CA",
                "congressional_district": "CA-01",
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 50.0,
                "congressional_district_confidence": 1.0,
            },
            {
                "state": "CA",
                "congressional_district": "CA-02",
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 150.0,
                "congressional_district_confidence": 0.6,
            },
            {
                "state": "CA",
                "congressional_district": None,
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 300.0,
                "congressional_district_confidence": 0.2,
            },
        ]
    )

    result = allocate_state_impacts_to_districts(_state_impacts(), awards).set_index(
        "congressional_district"
    )

    assert set(result.index) == {"CA-01", "CA-02"}
    assert result.loc["CA-01", "district_award_total"] == 150.0
    assert result.loc["CA-01", "state_award_total_from_districts"] == 300.0
    assert result.loc["CA-01", "allocation_share"] == pytest.approx(0.5)
    assert result.loc["CA-02", "production_impact_allocated"] == pytest.approx(500.0)
    assert result.loc["CA-02", "wage_impact_allocated"] == pytest.approx(200.0)
    assert result.loc["CA-02", "tax_impact_allocated"] == pytest.approx(40.0)
    assert result.loc["CA-02", "jobs_created_allocated"] == pytest.approx(5.0)
    assert result.loc["CA-01", "allocation_confidence"] == pytest.approx(0.6885)
    assert result.loc["CA-02", "allocation_confidence"] == pytest.approx(0.459)
    assert result["allocation_method"].unique().tolist() == ["proportional_by_awards"]
    assert result["model_version"].unique().tolist() == ["bea-v1"]


def test_allocate_state_impacts_returns_empty_without_resolved_districts():
    awards = pd.DataFrame(
        [
            {
                "state": "CA",
                "congressional_district": None,
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 100.0,
                "congressional_district_confidence": 0.0,
            }
        ]
    )

    assert allocate_state_impacts_to_districts(_state_impacts(), awards).empty


def test_allocate_state_impacts_returns_empty_without_sector_source():
    awards = pd.DataFrame(
        [
            {
                "state": "CA",
                "congressional_district": "CA-01",
                "fiscal_year": 2024,
                "award_amount": 100.0,
                "congressional_district_confidence": 0.9,
            }
        ]
    )

    assert allocate_state_impacts_to_districts(_state_impacts(), awards).empty


def test_allocate_state_impacts_maps_naics_when_bea_sector_is_absent(monkeypatch):
    mapper = Mock()
    mapper.map_naics_to_bea_summary.return_value = "54"
    mapper_constructor = Mock(return_value=mapper)
    monkeypatch.setattr(fiscal_bea_mapper, "NAICSToBEAMapper", mapper_constructor)
    awards = pd.DataFrame(
        [
            {
                "state": "CA",
                "congressional_district": "CA-01",
                "naics_code": 541715,
                "fiscal_year": 2024,
                "award_amount": 100.0,
                "congressional_district_confidence": 0.9,
            }
        ]
    )

    result = allocate_state_impacts_to_districts(_state_impacts(), awards)

    mapper_constructor.assert_called_once_with()
    mapper.map_naics_to_bea_summary.assert_called_once_with("541715")
    assert result.loc[0, "bea_sector"] == "54"
    assert result.loc[0, "production_impact_allocated"] == pytest.approx(1000.0)


def test_allocate_state_impacts_fails_fast_when_district_column_is_missing():
    malformed_awards = pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "54",
                "fiscal_year": 2024,
                "award_amount": 100.0,
            }
        ]
    )

    with pytest.raises(KeyError, match="congressional_district"):
        allocate_state_impacts_to_districts(_state_impacts(), malformed_awards)


def _district_impacts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "congressional_district": "CA-01",
                "state": "CA",
                "bea_sector": "54",
                "district_award_total": 100.0,
                "production_impact_allocated": 200.0,
                "tax_impact_allocated": 10.0,
                "jobs_created_allocated": 1.0,
                "wage_impact_allocated": 80.0,
                "allocation_confidence": 0.8,
            },
            {
                "congressional_district": "CA-01",
                "state": "CA",
                "bea_sector": "62",
                "district_award_total": 50.0,
                "production_impact_allocated": 100.0,
                "tax_impact_allocated": 20.0,
                "jobs_created_allocated": 2.0,
                "wage_impact_allocated": 40.0,
                "allocation_confidence": 0.6,
            },
            {
                "congressional_district": "CA-02",
                "state": "CA",
                "bea_sector": "54",
                "district_award_total": 120.0,
                "production_impact_allocated": 240.0,
                "tax_impact_allocated": 40.0,
                "jobs_created_allocated": 2.0,
                "wage_impact_allocated": 96.0,
                "allocation_confidence": 0.9,
            },
            {
                "congressional_district": "NV-01",
                "state": "NV",
                "bea_sector": "54",
                "district_award_total": 500.0,
                "production_impact_allocated": 1000.0,
                "tax_impact_allocated": 100.0,
                "jobs_created_allocated": 10.0,
                "wage_impact_allocated": 400.0,
                "allocation_confidence": 0.7,
            },
        ]
    )


def test_summarize_by_district_aggregates_sectors_and_sorts_by_awards():
    summary = summarize_by_district(_district_impacts())

    assert summary["congressional_district"].tolist() == ["NV-01", "CA-01", "CA-02"]
    ca_01 = summary.set_index("congressional_district").loc["CA-01"]
    assert ca_01["total_awards"] == 150.0
    assert ca_01["total_production_impact"] == 300.0
    assert ca_01["total_tax_impact"] == 30.0
    assert ca_01["total_jobs_created"] == 3.0
    assert ca_01["total_wage_impact"] == 120.0
    assert ca_01["sector_count"] == 2
    assert ca_01["avg_confidence"] == pytest.approx(0.7)


def test_compare_districts_within_state_filters_and_adds_dense_rankings():
    comparison = compare_districts_within_state(_district_impacts(), "CA").set_index(
        "congressional_district"
    )

    assert set(comparison.index) == {"CA-01", "CA-02"}
    assert comparison.loc["CA-01", "tax_impact_rank"] == 2
    assert comparison.loc["CA-01", "jobs_rank"] == 1
    assert comparison.loc["CA-01", "awards_rank"] == 1
    assert comparison.loc["CA-02", "tax_impact_rank"] == 1
    assert comparison.loc["CA-02", "jobs_rank"] == 2
    assert comparison.loc["CA-02", "awards_rank"] == 2


def test_compare_districts_within_state_returns_empty_for_unknown_state():
    assert compare_districts_within_state(_district_impacts(), "TX").empty
