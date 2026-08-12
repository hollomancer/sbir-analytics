"""Company CET profile identity contract tests."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.cet.company import (
    _attach_company_uei,
    transformed_cet_company_profiles,
)


pytestmark = pytest.mark.fast


def test_company_profile_identity_prefers_explicit_uei_over_legacy_company_id():
    classifications = pd.DataFrame(
        [{"award_id": "A-1", "company_id": "legacy-company", "primary_cet": "quantum"}]
    )
    awards = pd.DataFrame(
        [
            {
                "award_id": "A-1",
                "company_id": "different-legacy-company",
                "uei": "abcd-1234-efgh",
                "company_name": "Example Labs",
            }
        ]
    )

    result = _attach_company_uei(classifications, awards)

    assert result.loc[0, "company_uei"] == "ABCD1234EFGH"
    assert result.loc[0, "company_id"] == "ABCD1234EFGH"
    assert result.loc[0, "company_name"] == "Example Labs"


def test_company_profile_identity_does_not_relabel_duns_as_uei():
    classifications = pd.DataFrame(
        [{"award_id": "A-1", "company_id": "legacy-company", "primary_cet": "quantum"}]
    )
    awards = pd.DataFrame(
        [{"award_id": "A-1", "company_id": "legacy-company", "duns": "123456789"}]
    )

    result = _attach_company_uei(classifications, awards)

    assert result["company_uei"].isna().all()
    assert result["company_id"].isna().all()


def test_company_profile_artifact_emits_explicit_company_uei(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "cet_award_classifications.ndjson").write_text(
        json.dumps(
            {
                "award_id": "A-1",
                "company_id": "legacy-company",
                "primary_cet": "quantum",
                "primary_score": 0.9,
                "supporting_cets": [],
            }
        )
        + "\n"
    )
    (processed / "enriched_sbir_awards.ndjson").write_text(
        json.dumps(
            {
                "award_id": "A-1",
                "company_id": "different-legacy-company",
                "uei": "abcd-1234-efgh",
                "company_name": "Example Labs",
            }
        )
        + "\n"
    )

    output = transformed_cet_company_profiles()

    output_path = Path(output.value)
    if output_path.suffix == ".parquet":
        profiles = pd.read_parquet(output_path)
    else:
        profiles = pd.read_json(output_path, lines=True)
    assert profiles.loc[0, "company_uei"] == "ABCD1234EFGH"
    assert profiles.loc[0, "company_id"] == "ABCD1234EFGH"
