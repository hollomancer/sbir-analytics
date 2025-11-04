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


def _write_detection_config(base_dir: Path) -> Path:
    config_path = base_dir / "detection.yaml"
    config_path.write_text(
        "\n".join(
            [
                "base_score: 0.15",
                "timing_window:",
                "  min_days_after_completion: 0",
                "  max_days_after_completion: 730",
                "vendor_matching:",
                "  require_match: true",
                "  fuzzy_threshold: 0.7",
                "scoring:",
                "  agency_continuity:",
                "    enabled: true",
                "    weight: 0.25",
                "    same_agency_bonus: 0.25",
                "    cross_service_bonus: 0.125",
                "    different_dept_bonus: 0.05",
                "  timing_proximity:",
                "    enabled: true",
                "    weight: 0.20",
                "    windows:",
                "      - range: [0, 90]",
                "        score: 1.0",
                "      - range: [91, 365]",
                "        score: 0.75",
                "      - range: [366, 730]",
                "        score: 0.5",
                "  competition_type:",
                "    enabled: true",
                "    weight: 0.20",
                "    sole_source_bonus: 0.20",
                "    limited_competition_bonus: 0.10",
                "    full_and_open_bonus: 0.0",
                "  patent_signal:",
                "    enabled: false",
                "  cet_alignment:",
                "    enabled: false",
                "confidence_thresholds:",
                "  high: 0.8",
                "  likely: 0.6",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_contracts_sample_parent_child_stats(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    from src.assets.transition_assets import AssetExecutionContext, contracts_sample  # type: ignore

    sample_path = Path("data/processed/contracts_sample.parquet")
    sample_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        [
            {
                "contract_id": "C_CHILD",
                "piid": "C_CHILD",
                "parent_contract_id": "IDV-ROOT",
                "contract_award_type": "DO",
                "vendor_uei": "UEI123",
                "vendor_name": "Acme Subsidiary",
                "action_date": "2023-01-15",
            },
            {
                "contract_id": "IDV-ROOT",
                "piid": "IDV-ROOT",
                "parent_contract_id": None,
                "contract_award_type": "IDV-A",
                "vendor_uei": "UEI123",
                "vendor_name": "Acme Parent",
                "action_date": "2023-01-01",
            },
        ]
    )

    csv_path = sample_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH", str(sample_path))

    ctx = AssetExecutionContext()
    result = contracts_sample(ctx)
    sample_df, metadata = _unwrap_output(result)

    assert isinstance(sample_df, pd.DataFrame)
    assert "parent_contract_id" in sample_df.columns
    assert "contract_award_type" in sample_df.columns

    checks_path = Path(metadata["checks_path"])
    payload = json.loads(checks_path.read_text(encoding="utf-8"))

    parent_child = payload.get("parent_child") or {}
    assert parent_child.get("child_rows") == 1
    assert parent_child.get("idv_parent_rows") == 1
    assert parent_child.get("child_ratio") == pytest.approx(0.5)
    assert parent_child.get("idv_parent_ratio") == pytest.approx(0.5)


def test_vendor_resolution_exact_and_fuzzy(monkeypatch, tmp_path):
    # Run all outputs into a temp working directory
    monkeypatch.chdir(tmp_path)
    # Lower fuzzy threshold to ensure partial matches pass comfortably in all environments
    monkeypatch.setenv("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", "0.7")

    # Import locally so env/working dir changes apply
    from src.assets.transition_assets import AssetExecutionContext, vendor_resolution

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
        transition_evidence_v1,
        transition_scores_v1,
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


def test_transition_detections_pipeline_generates_transition(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = _write_detection_config(tmp_path)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__DETECTION_CONFIG", str(config_path))

    from src.assets.transition_assets import (  # type: ignore
        AssetExecutionContext,
        transition_detections,
    )

    awards_df = pd.DataFrame(
        [
            {
                "award_id": "A-001",
                "Company": "Acme Robotics",
                "UEI": "UEI1234567890",
                "completion_date": "2023-01-01",
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            }
        ]
    )

    vendor_res_df = pd.DataFrame(
        [
            {
                "contract_id": "PIID-001",
                "matched_vendor_id": "uei:UEI1234567890",
                "match_method": "uei",
                "confidence": 1.0,
            }
        ]
    )

    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "PIID-001",
                "piid": "PIID-001",
                "vendor_uei": "UEI1234567890",
                "vendor_name": "Acme Robotics",
                "action_date": "2023-03-01",
                "start_date": "2023-03-01",
                "obligated_amount": 250000,
                "competition_type": "sole_source",
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            }
        ]
    )

    scores_df = pd.DataFrame(
        [
            {
                "award_id": "A-001",
                "contract_id": "PIID-001",
                "score": 0.9,
                "method": "uei",
                "computed_at": "2024-01-01T00:00:00Z",
            }
        ]
    )

    ctx = AssetExecutionContext()
    detections_df, metadata = _unwrap_output(
        transition_detections(ctx, awards_df, vendor_res_df, contracts_df, scores_df)
    )

    assert isinstance(detections_df, pd.DataFrame)
    assert len(detections_df) == 1
    for column in ["transition_id", "award_id", "contract_id", "likelihood_score", "confidence"]:
        assert column in detections_df.columns

    assert metadata is not None
    assert metadata.get("rows") == 1
    output_path = Path(metadata.get("output_path", ""))
    fallback_path = output_path.with_suffix(".ndjson")
    assert output_path.exists() or fallback_path.exists()
    checks_path = Path(metadata.get("checks_path", ""))
    assert checks_path.exists()
    detector_metrics = metadata.get("detector_metrics") or {}
    assert detector_metrics.get("total_detections") == 1


def test_transition_detections_returns_empty_without_candidates(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = _write_detection_config(tmp_path)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__DETECTION_CONFIG", str(config_path))

    from src.assets.transition_assets import (  # type: ignore
        AssetExecutionContext,
        transition_detections,
    )

    awards_df = pd.DataFrame(
        [
            {
                "award_id": "A-001",
                "Company": "Acme Robotics",
                "UEI": "UEI1234567890",
                "completion_date": "2023-01-01",
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            }
        ]
    )
    vendor_res_df = pd.DataFrame(
        columns=["contract_id", "matched_vendor_id", "match_method", "confidence"]
    )
    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "PIID-001",
                "piid": "PIID-001",
                "vendor_uei": "UEI1234567890",
                "vendor_name": "Acme Robotics",
                "action_date": "2023-03-01",
                "start_date": "2023-03-01",
                "obligated_amount": 250000,
                "competition_type": "sole_source",
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            }
        ]
    )
    scores_df = pd.DataFrame(
        [
            {
                "award_id": "A-001",
                "contract_id": "PIID-001",
                "score": 0.9,
                "method": "uei",
                "computed_at": "2024-01-01T00:00:00Z",
            }
        ]
    )

    ctx = AssetExecutionContext()
    detections_df, metadata = _unwrap_output(
        transition_detections(ctx, awards_df, vendor_res_df, contracts_df, scores_df)
    )

    assert isinstance(detections_df, pd.DataFrame)
    assert detections_df.empty
    assert metadata is not None
    assert metadata.get("rows") == 0
    checks_path = Path(metadata.get("checks_path", ""))
    assert checks_path.exists()
    detector_metrics = metadata.get("detector_metrics") or {}
    assert detector_metrics.get("total_detections") == 0
