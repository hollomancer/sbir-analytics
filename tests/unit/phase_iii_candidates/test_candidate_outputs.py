"""Per-signal-class artifact ownership, prior enrichment, and evidence accuracy."""

import json

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates import assets as candidate_assets
from sbir_analytics.assets.phase_iii_candidates.assets import (
    HIGH_THRESHOLD_FOLLOWON,
    WEIGHTS_FOLLOWON,
    candidates_path_for,
    combine_candidate_outputs,
    enrich_prior_awards,
    evidence_path_for,
    score_candidate_pairs,
)
from sbir_etl.models.phase_iii_candidate import SignalClass


@pytest.fixture
def isolated_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        candidate_assets, "CANDIDATES_OUTPUT_PATH", tmp_path / "phase_iii_candidates.parquet"
    )
    monkeypatch.setattr(
        candidate_assets, "EVIDENCE_OUTPUT_PATH", tmp_path / "phase_iii_evidence.ndjson"
    )
    return tmp_path


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "prior_award_id": "A-1",
                "prior_recipient_uei": "UEI000000001",
                "prior_agency": "DEFENSE",
                "prior_naics_code": "541715",
                "prior_psc_code": "AJ11",
                "prior_title": "Autonomous navigation",
                "prior_abstract": "Autonomous aircraft navigation prototype",
                "target_id": "O-1",
                "target_recipient_uei": None,
                "target_agency": "ENERGY",
                "target_naics_code": "541715",
                "target_psc_code": "ZZ99",
                "target_description": "Autonomous aircraft navigation prototype",
                "agency_match_level": None,
            }
        ]
    )


def test_evidence_records_only_observed_match_keys_and_every_subscore():
    _, evidence = score_candidate_pairs(
        _pairs(),
        signal_class=SignalClass.FOLLOWON,
        weights=WEIGHTS_FOLLOWON,
        high_threshold=HIGH_THRESHOLD_FOLLOWON,
    )

    record = evidence[0]
    # No recipient identity was matched — claiming one would misdescribe the pair.
    assert "recipient_uei" not in record["matched_keys"]
    assert record["matched_keys"] == ["naics_code"]
    assert "id_xref" in record["subscores"]
    assert record["score"] == pytest.approx(sum(record["subscores"].values()))


def test_each_signal_class_owns_its_own_artifacts(isolated_outputs):
    directed, directed_evidence = score_candidate_pairs(
        _pairs(),
        signal_class=SignalClass.DIRECTED,
        weights=candidate_assets.WEIGHTS_DIRECTED,
        high_threshold=candidate_assets.HIGH_THRESHOLD_DIRECTED,
    )
    candidate_assets._write_outputs(directed, directed_evidence, SignalClass.DIRECTED)
    followon, followon_evidence = score_candidate_pairs(
        _pairs(),
        signal_class=SignalClass.FOLLOWON,
        weights=WEIGHTS_FOLLOWON,
        high_threshold=HIGH_THRESHOLD_FOLLOWON,
    )
    candidate_assets._write_outputs(followon, followon_evidence, SignalClass.FOLLOWON)

    # Writers never touch each other's files, in either materialization order.
    assert len(pd.read_parquet(candidates_path_for(SignalClass.DIRECTED))) == 1
    assert len(pd.read_parquet(candidates_path_for(SignalClass.FOLLOWON))) == 1

    combined = combine_candidate_outputs()
    assert sorted(combined["signal_class"]) == ["directed", "followon"]
    lines = candidate_assets.EVIDENCE_OUTPUT_PATH.read_text().splitlines()
    assert sorted(json.loads(line)["signal_class"] for line in lines) == ["directed", "followon"]


def test_empty_result_clears_the_previous_rows(isolated_outputs):
    rows, evidence = score_candidate_pairs(
        _pairs(),
        signal_class=SignalClass.FOLLOWON,
        weights=WEIGHTS_FOLLOWON,
        high_threshold=HIGH_THRESHOLD_FOLLOWON,
    )
    candidate_assets._write_outputs(rows, evidence, SignalClass.FOLLOWON)
    candidate_assets._write_outputs(pd.DataFrame(), [], SignalClass.FOLLOWON)

    assert pd.read_parquet(candidates_path_for(SignalClass.FOLLOWON)).empty
    assert evidence_path_for(SignalClass.FOLLOWON).read_text() == ""
    assert combine_candidate_outputs().empty


def test_enrich_prior_awards_adds_the_fields_the_phase_ii_contract_lacks():
    priors = pd.DataFrame([{"award_id": "A-1", "recipient_uei": "UEI000000001"}])
    detail = pd.DataFrame(
        [
            {
                "award_id": "A-1",
                "award_title": "Autonomous navigation",
                "abstract": "Prototype",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "office": "NAVAIR",
                "cet": "Autonomy",
            }
        ]
    )

    enriched = enrich_prior_awards(priors, detail)

    assert enriched.loc[0, "title"] == "Autonomous navigation"
    assert enriched.loc[0, "naics_code"] == "541715"
    assert enriched.loc[0, "cet"] == "Autonomy"
    assert len(enriched) == len(priors)
