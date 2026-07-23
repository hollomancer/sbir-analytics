from pathlib import Path

import pandas as pd
import pytest
import yaml

from sbir_etl.reporting.local_cet_classifier import load_local_cet_rule_classifier


def test_rule_classifier_emits_versioned_keyword_evidence() -> None:
    classifier = load_local_cet_rule_classifier()
    awards = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "title": "Hypersonic scramjet inlet control",
                "abstract": "A vehicle operating above Mach 5 uses a scramjet.",
                "topic_code": "",
            }
        ]
    )

    result = classifier.classify_frame(awards)

    assert result.loc[0, "primary_cet"] == "hypersonics"
    assert result.loc[0, "primary_score"] >= 40
    assert result.loc[0, "taxonomy_version"] == "NSTC-2025Q1"
    assert result.loc[0, "classifier_version"] == "CET-RULES-2026Q3"
    assert {item["source"] for item in result.loc[0, "evidence"]} <= {
        "title",
        "topic_code",
        "abstract",
    }


def test_short_ambiguous_abbreviation_does_not_classify() -> None:
    classifier = load_local_cet_rule_classifier()
    awards = pd.DataFrame(
        [{"award_id": "A1", "title": "AI study", "abstract": "AI", "topic_code": ""}]
    )

    assert classifier.classify_frame(awards).empty


def test_negative_application_phrase_suppresses_ai_primary() -> None:
    classifier = load_local_cet_rule_classifier()
    awards = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "title": "AI medical imaging diagnostic",
                "abstract": "Using machine learning for an AI-powered diagnostic device.",
                "topic_code": "",
            }
        ]
    )

    result = classifier.classify_frame(awards)

    assert result.empty or result.loc[0, "primary_cet"] != "artificial_intelligence"


def test_loader_rejects_taxonomy_version_mismatch(tmp_path: Path) -> None:
    config = yaml.safe_load(Path("config/cet/local_rule_classifier.yaml").read_text())
    config["taxonomy_version"] = "wrong"
    config_path = tmp_path / "classifier.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ValueError, match="expects taxonomy"):
        load_local_cet_rule_classifier(config_path=config_path)
