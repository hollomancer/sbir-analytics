import json
import os
from pathlib import Path

import pandas as pd


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


def _assert_artifact_exists(base_path: Path) -> Path:
    """
    Assert that either a parquet artifact exists at base_path, or a .ndjson fallback exists.

    Returns the path that exists.
    """
    if base_path.exists():
        return base_path
    ndjson = base_path.with_suffix(".ndjson")
    assert ndjson.exists(), f"Expected {base_path} or {ndjson} to exist"
    return ndjson


def test_transition_mvp_chain_shimmed(tmp_path, monkeypatch):
    """
    Tiny integration test for the Transition MVP chain using import shims (no Dagster required).

    Flow:
      - Prepare minimal contracts and enriched awards DataFrames
      - Run vendor_resolution -> transition_scores_v1 -> transition_evidence_v1
      - Assert basic shapes, outputs, and side-effect artifacts (checks JSON, NDJSON)
    """
    # Isolate all IO under a temp working directory
    monkeypatch.chdir(tmp_path)

    # Loosen fuzzy threshold slightly to be robust to tokenization variants
    monkeypatch.setenv("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", "0.7")

    # Import assets and shim context from the transition assets module
    from src.assets.transition_assets import (  # noqa: WPS433 (local import for test isolation)
        AssetExecutionContext,
        transition_evidence_v1,
        transition_scores_v1,
        vendor_resolution,
    )

    # Contracts sample:
    # - C1: UEI exact match candidate
    # - C2: fuzzy name match candidate
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

    # Enriched SBIR awards minimal fields used by the assets:
    # - A1: same UEI as C1
    # - A2: name that should fuzzy-match C2
    awards_df = pd.DataFrame(
        [
            {"award_id": "A1", "Company": "UEI Vendor Inc", "UEI": "UEI123", "Duns": None},
            {"award_id": "A2", "Company": "Acme Corp", "UEI": None, "Duns": None},
        ]
    )

    ctx = AssetExecutionContext()

    # 1) Vendor resolution
    vendor_res_out = vendor_resolution(ctx, contracts_df, awards_df)
    vendor_res_df, vendor_meta = _unwrap_output(vendor_res_out)
    assert isinstance(vendor_res_df, pd.DataFrame)
    assert {"contract_id", "matched_vendor_id", "match_method", "confidence"}.issubset(
        set(vendor_res_df.columns)
    )
    # Expect two rows (one per contract)
    assert len(vendor_res_df) == 2

    # Validate matches by method
    row_c1 = vendor_res_df.loc[vendor_res_df["contract_id"] == "C1"].iloc[0]
    assert row_c1["match_method"] == "uei"
    assert row_c1["matched_vendor_id"] == "uei:UEI123"
    assert float(row_c1["confidence"]) == 1.0

    row_c2 = vendor_res_df.loc[vendor_res_df["contract_id"] == "C2"].iloc[0]
    assert row_c2["match_method"] == "name_fuzzy"
    assert str(row_c2["matched_vendor_id"]).startswith("name:")
    assert float(row_c2["confidence"]) >= 0.7

    # Side effects: artifacts should be written
    vendor_map_art = _assert_artifact_exists(Path("data/processed/vendor_resolution.parquet"))
    assert vendor_map_art.exists()
    assert Path("data/processed/vendor_resolution.checks.json").exists()

    # 2) Transition scores
    scores_out = transition_scores_v1(ctx, vendor_res_df, contracts_df, awards_df)
    scores_df, scores_meta = _unwrap_output(scores_out)
    assert isinstance(scores_df, pd.DataFrame)
    assert {"award_id", "contract_id", "score", "method", "computed_at"}.issubset(
        set(scores_df.columns)
    )
    # Two candidates expected: A1↔C1 (uei), A2↔C2 (name_fuzzy)
    assert len(scores_df) == 2

    s1 = scores_df.loc[(scores_df["award_id"] == "A1") & (scores_df["contract_id"] == "C1")].iloc[0]
    assert s1["method"] == "uei"
    # UEI weight is 0.9 in the simple rule-based scorer
    assert abs(float(s1["score"]) - 0.9) < 1e-6

    s2 = scores_df.loc[(scores_df["award_id"] == "A2") & (scores_df["contract_id"] == "C2")].iloc[0]
    assert s2["method"] == "name_fuzzy"
    # Fuzzy weight is 0.7 in the simple rule-based scorer
    assert abs(float(s2["score"]) - 0.7) < 1e-6

    # Side effects: artifacts should be written
    trans_art = _assert_artifact_exists(Path("data/processed/transitions.parquet"))
    assert trans_art.exists()
    assert Path("data/processed/transitions.checks.json").exists()

    # 3) Evidence emission
    evidence_out = transition_evidence_v1(ctx, scores_df, contracts_df)
    evidence_path_str, evidence_meta = _unwrap_output(evidence_out)
    ev_path = Path(evidence_path_str)
    assert ev_path.exists()
    lines = ev_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(scores_df)

    # Validate shape of evidence entries
    entry = json.loads(lines[0])
    for key in ["award_id", "contract_id", "score", "method", "matched_keys", "contract_snapshot"]:
        assert key in entry

    # Sanity: ensure files were created under the temp directory
    # and no unexpected writes occurred elsewhere
    cwd = Path(os.getcwd()).resolve()
    assert str(ev_path.resolve()).startswith(str(cwd))
    assert str(vendor_map_art.resolve()).startswith(str(cwd))
    assert str(trans_art.resolve()).startswith(str(cwd))
