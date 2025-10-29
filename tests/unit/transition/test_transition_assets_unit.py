import json
from pathlib import Path

import pandas as pd
import pytest


def _unwrap_output(result):
    """
    Helper to unwrap Dagster Output or bare values.

    The transition assets return an Output(value=..., metadata=...).
    In case Dagster isn't installed (shim), the object still has 'value'.
    If behavior changes, fall back to returning the object itself.
    """
    if hasattr(result, "value"):
        return result.value, getattr(result, "metadata", None)
    return result, None


def test_vendor_resolution_exact_and_fuzzy(monkeypatch, tmp_path):
    # Run all outputs into a temp working directory
    monkeypatch.chdir(tmp_path)
    # Lower fuzzy threshold to ensure partial matches pass comfortably in all environments
    monkeypatch.setenv("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", "0.7")

    # Import locally so env/working dir changes apply
    from src.assets.transition_assets import (
        AssetExecutionContext,
        vendor_resolution,
    )

    # Prepare a tiny contracts_sample DataFrame:
    # - C1 matches UEI exactly
    # - C2 should match by fuzzy company name
    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": "UEI123",
                "vendor_duns": None,
                "vendor_name": "UEI Vendor Inc",
                "action_date": "2023-01-01",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
            },
        ]
    )

    # Prepare enriched SBIR awards minimal surface:
    # - A1 carries the same UEI as C1
    # - A2 derives vendor id from Company name to enable name_fuzzy for C2
    awards_df = pd.DataFrame(
        [
            {"award_id": "A1", "Company": "UEI Vendor Inc", "UEI": "UEI123", "Duns": None},
            {"award_id": "A2", "Company": "Acme Corp", "UEI": None, "Duns": None},
        ]
    )

    ctx = AssetExecutionContext()
    result = vendor_resolution(ctx, contracts_df, awards_df)
    resolved_df, _ = _unwrap_output(result)

    # Basic shape expectations
    assert isinstance(resolved_df, pd.DataFrame)
    assert {"contract_id", "matched_vendor_id", "match_method", "confidence"}.issubset(
        set(resolved_df.columns)
    )
    # We should have two rows corresponding to C1 and C2
    assert len(resolved_df) == 2

    # Row for C1 should be UEI exact match
    row_c1 = resolved_df.loc[resolved_df["contract_id"] == "C1"].iloc[0]
    assert row_c1["match_method"] == "uei"
    assert row_c1["matched_vendor_id"] == "uei:UEI123"
    assert float(row_c1["confidence"]) == 1.0

    # Row for C2 should be fuzzy name match to company-based vendor id
    row_c2 = resolved_df.loc[resolved_df["contract_id"] == "C2"].iloc[0]
    assert row_c2["match_method"] == "name_fuzzy"
    assert str(row_c2["matched_vendor_id"]).startswith("name:")
    assert float(row_c2["confidence"]) >= 0.7  # per threshold override


def test_transition_scores_and_evidence(monkeypatch, tmp_path):
    # Run all outputs into a temp working directory
    monkeypatch.chdir(tmp_path)

    from src.assets.transition_assets import (
        AssetExecutionContext,
        transition_scores_v1,
        transition_evidence_v1,
    )

    # Reuse consistent fixtures (contracts + awards + vendor_resolution outputs)
    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": "UEI123",
                "vendor_duns": None,
                "vendor_name": "UEI Vendor Inc",
                "action_date": "2023-01-01",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
            },
        ]
    )
    awards_df = pd.DataFrame(
        [
            {"award_id": "A1", "Company": "UEI Vendor Inc", "UEI": "UEI123", "Duns": None},
            {"award_id": "A2", "Company": "Acme Corp", "UEI": None, "Duns": None},
        ]
    )
    vendor_res_df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "matched_vendor_id": "uei:UEI123",
                "match_method": "uei",
                "confidence": 1.0,
            },
            {
                "contract_id": "C2",
                "matched_vendor_id": "name:acme corp",
                "match_method": "name_fuzzy",
                "confidence": 0.9,
            },
        ]
    )

    ctx = AssetExecutionContext()
    scores_out = transition_scores_v1(ctx, vendor_res_df, contracts_df, awards_df)
    scores_df, _ = _unwrap_output(scores_out)

    # Expect 2 candidates (A1↔C1 via UEI, A2↔C2 via fuzzy)
    assert isinstance(scores_df, pd.DataFrame)
    assert {"award_id", "contract_id", "score", "method", "computed_at"}.issubset(
        set(scores_df.columns)
    )
    assert len(scores_df) == 2

    s1 = scores_df.loc[(scores_df["award_id"] == "A1") & (scores_df["contract_id"] == "C1")].iloc[0]
    assert s1["method"] == "uei"
    # Rule-based weight for UEI exact is 0.9
    assert abs(float(s1["score"]) - 0.9) < 1e-6

    s2 = scores_df.loc[(scores_df["award_id"] == "A2") & (scores_df["contract_id"] == "C2")].iloc[0]
    assert s2["method"] == "name_fuzzy"
    # Rule-based weight for fuzzy is 0.7
    assert abs(float(s2["score"]) - 0.7) < 1e-6

    # Evidence generation should produce one NDJSON line per candidate
    ev_out = transition_evidence_v1(ctx, scores_df, contracts_df)
    ev_path, _ = _unwrap_output(ev_out)
    ev_path = Path(ev_path)
    assert ev_path.exists()
    lines = ev_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(scores_df)

    # Validate basic structure of NDJSON entry
    entry = json.loads(lines[0])
    for key in ["award_id", "contract_id", "score", "method", "matched_keys", "contract_snapshot"]:
        assert key in entry


def test_transition_detections_persists_metrics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    from src.assets.transition_assets import (  # type: ignore
        AssetExecutionContext,
        transition_detections,
    )

    scores_df = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "contract_id": "C1",
                "score": 0.9,
                "method": "uei",
                "computed_at": "2024-01-01T00:00:00Z",
            },
            {
                "award_id": "A2",
                "contract_id": "C2",
                "score": 0.4,
                "method": "name_fuzzy",
                "computed_at": "2024-01-02T00:00:00Z",
            },
        ]
    )

    ctx = AssetExecutionContext()
    detections_df, metadata = _unwrap_output(transition_detections(ctx, scores_df))

    assert isinstance(detections_df, pd.DataFrame)
    assert len(detections_df) == 2
    assert metadata is not None
    assert metadata.get("high_confidence_candidates") == 1
    assert pytest.approx(metadata.get("avg_score", 0.0), rel=1e-6) == 0.65

    output_path = Path(metadata.get("output_path", ""))
    ndjson_fallback = output_path.with_suffix(".ndjson")
    assert output_path.exists() or ndjson_fallback.exists()
    by_method = metadata.get("by_method") or {}
    assert by_method.get("uei") == 1
    assert by_method.get("name_fuzzy") == 1


def test_transition_detections_fills_missing_columns(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    from src.assets.transition_assets import (  # type: ignore
        AssetExecutionContext,
        transition_detections,
    )

    minimal_df = pd.DataFrame([{"award_id": "A1", "contract_id": "C1", "score": 0.75}])

    ctx = AssetExecutionContext()
    detections_df, metadata = _unwrap_output(transition_detections(ctx, minimal_df))

    assert isinstance(detections_df, pd.DataFrame)
    for column in ["method", "computed_at"]:
        assert column in detections_df.columns
    assert detections_df.loc[0, "method"] is None
    assert metadata is not None
    assert metadata.get("rows") == 1
    assert metadata.get("high_confidence_candidates") == 1
