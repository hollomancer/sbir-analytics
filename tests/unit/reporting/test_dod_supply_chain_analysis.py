from pathlib import Path

import pandas as pd

from sbir_etl.reporting.dod_supply_chain_analysis import (
    build_classifier_validation_sample,
    build_initial_analysis_markdown,
    split_classifier_validation_sample,
    write_initial_analysis,
)


def test_validation_sample_spans_cets_score_bands_and_unclassified_cases() -> None:
    awards = pd.DataFrame(
        [
            {
                "award_id": f"A{index}",
                "title": f"Award {index}",
                "abstract": "Test abstract",
                "topic_code": "TEST",
                "branch": "Air Force" if index % 2 else "Navy",
                "phase": "Phase II" if index % 3 else "Phase I",
                "award_year": 2024,
            }
            for index in range(10)
        ]
    )
    classifications = pd.DataFrame(
        [
            {
                "award_id": "A0",
                "primary_cet": "area_one",
                "primary_score": 50.0,
                "evidence": "[]",
                "classifier_version": "TEST",
            },
            {
                "award_id": "A1",
                "primary_cet": "area_one",
                "primary_score": 60.0,
                "evidence": "[]",
                "classifier_version": "TEST",
            },
            {
                "award_id": "A2",
                "primary_cet": "area_one",
                "primary_score": 80.0,
                "evidence": "[]",
                "classifier_version": "TEST",
            },
            {
                "award_id": "A3",
                "primary_cet": "area_two",
                "primary_score": 75.0,
                "evidence": "[]",
                "classifier_version": "TEST",
            },
        ]
    )

    sample = build_classifier_validation_sample(
        awards,
        classifications,
        classified_per_cet=3,
        unclassified_count=4,
        seed=7,
    )

    positive = sample[sample["classifier_decision"] == "classified"]
    negative = sample[sample["classifier_decision"] == "unclassified"]
    assert set(positive["primary_cet"]) == {"area_one", "area_two"}
    assert set(positive.loc[positive["primary_cet"] == "area_one", "score_band"]) == {
        "screening_50_54",
        "medium_55_69",
        "high_70_plus",
    }
    assert len(negative) == 4
    assert not set(negative["award_id"]) & set(classifications["award_id"])
    assert {"reviewer_primary_cet", "reviewer_confidence", "reviewer_notes"} <= set(sample.columns)
    assert sample["review_id"].is_unique
    assert sample["sample_weight"].gt(0).all()

    blinded, key = split_classifier_validation_sample(sample)
    assert "primary_cet" not in blinded
    assert "classifier_decision" not in blinded
    assert {"primary_cet", "classifier_decision", "sample_weight"} <= set(key.columns)
    assert blinded["review_id"].tolist() == key["review_id"].tolist()


def test_initial_analysis_reports_scope_and_limitations() -> None:
    facts = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "fiscal_year": 2025,
                "award_amount": 100.0,
                "cet_area": "artificial_intelligence",
                "dod_component": "Air Force",
            }
        ]
    )
    metrics = pd.DataFrame(
        [
            {
                "period_type": "latest_complete_window",
                "period_start_fy": 2021,
                "period_end_fy": 2025,
                "cet_area": "artificial_intelligence",
                "award_count": 1,
                "distinct_firms": 1,
                "award_dollars": 100.0,
                "dollar_hhi": 1.0,
                "top1_dollar_share": 1.0,
                "top3_dollar_share": 1.0,
                "state_dollar_hhi": 1.0,
                "entrant_firm_share": 1.0,
                "dod_cta14": ["trusted_ai_and_autonomy"],
                "dod_sc8": ["cyber_posture"],
            }
        ]
    )
    metadata = {
        "as_of_date": "2026-07-23",
        "min_fiscal_year": 2012,
        "classifier_versions": ["TEST"],
        "taxonomy_versions": ["TEST-TAXONOMY"],
        "transition_status": "not_computed",
        "award_fact_rows": 1,
        "minimum_primary_cet_score": 40.0,
        "identity_policy": "test identity",
        "defense_crosswalk_version": "TEST-XWALK",
    }
    manifest = {
        "classification_coverage": 0.5,
        "award_rows": 2,
        "source_sha256": "abc123",
    }

    report = build_initial_analysis_markdown(facts, metrics, metadata, manifest)

    assert "exploratory descriptive baseline" in report
    assert "50.0%" in report
    assert "transition status is\n  **not_computed**" in report
    assert "not evidence\nof a sole-source physical dependency" in report
    assert "rows are **not additive**" in report


def test_write_initial_analysis(tmp_path: Path) -> None:
    report_path = tmp_path / "docs" / "analysis.md"
    sample_path = tmp_path / "data" / "sample.csv"
    key_path = tmp_path / "data" / "key.csv"
    sample = pd.DataFrame([{"award_id": "A1"}])
    key = pd.DataFrame([{"award_id": "A1", "primary_cet": "area_one"}])

    write_initial_analysis(
        "# Analysis\n",
        sample,
        key,
        report_path=report_path,
        validation_path=sample_path,
        validation_key_path=key_path,
    )

    assert report_path.read_text() == "# Analysis\n"
    assert pd.read_csv(sample_path).to_dict("records") == [{"award_id": "A1"}]
    assert pd.read_csv(key_path).to_dict("records") == [
        {"award_id": "A1", "primary_cet": "area_one"}
    ]
