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


def test_transition_mvp_golden(tmp_path, monkeypatch):
    """
    Compare tiny-sample outputs to golden NDJSON fixtures (order-insensitive, normalized).
    """
    # Isolate IO
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", "0.7")

    from src.assets.transition_assets import (  # noqa: WPS433
        AssetExecutionContext,
        transition_evidence_v1,
        transition_scores_v1,
        vendor_resolution,
    )

    # Tiny fixtures (same as the shimmed chain test)
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
    ctx = AssetExecutionContext()

    # Run chain
    vr_df, _ = _unwrap_output(vendor_resolution(ctx, contracts_df, awards_df))
    scores_df, _ = _unwrap_output(transition_scores_v1(ctx, vr_df, contracts_df, awards_df))
    ev_path_str, _ = _unwrap_output(transition_evidence_v1(ctx, scores_df, contracts_df))
    ev_path = Path(ev_path_str)

    # Normalize transitions (actual)
    def _normalize_transitions(df: pd.DataFrame):
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "award_id": r.get("award_id"),
                    "contract_id": r.get("contract_id"),
                    "score": round(float(r.get("score")), 2),
                    "method": r.get("method"),
                    "signals": list(r.get("signals") or [r.get("method")]),
                    "computed_at": "1970-01-01T00:00:00Z",
                }
            )
        rows.sort(key=lambda x: (x["award_id"], x["contract_id"], x["method"]))
        return rows

    actual_transitions = _normalize_transitions(scores_df)

    # Load and normalize golden transitions
    golden_dir = Path(__file__).parent.parent / "data" / "transition"
    golden_transitions_path = golden_dir / "golden_transitions.ndjson"
    golden_transitions = []
    for line in golden_transitions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        obj["score"] = round(float(obj["score"]), 2)
        golden_transitions.append(obj)
    golden_transitions.sort(key=lambda x: (x["award_id"], x["contract_id"], x["method"]))

    assert actual_transitions == golden_transitions

    # Normalize evidence by stripping dynamic/large fields
    def _strip_evidence(obj: dict) -> dict:
        d = dict(obj)
        d.pop("contract_snapshot", None)
        d["generated_at"] = "1970-01-01T00:00:00Z"
        return d

    actual_evidence = []
    for line in ev_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        actual_evidence.append(_strip_evidence(json.loads(line)))
    actual_evidence.sort(key=lambda x: (x["award_id"], x["contract_id"], x["method"]))

    golden_evidence_path = golden_dir / "golden_transitions_evidence.ndjson"
    golden_evidence = []
    for line in golden_evidence_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        golden_evidence.append(_strip_evidence(json.loads(line)))
    golden_evidence.sort(key=lambda x: (x["award_id"], x["contract_id"], x["method"]))

    # Compare key fields only to avoid brittle diffs on optional fields
    def _project_ev(rec):
        mk = rec.get("matched_keys") or []
        try:
            mk = sorted(set(mk))
        except Exception:
            mk = list(mk) if isinstance(mk, (list, tuple, set)) else [mk]
        return {
            "award_id": rec.get("award_id"),
            "contract_id": rec.get("contract_id"),
            "score": round(float(rec.get("score") or 0), 2),
            "method": rec.get("method"),
            "matched_keys": mk,
            "resolver_path": rec.get("resolver_path"),
            "dates": {"contract_action_date": rec.get("dates", {}).get("contract_action_date")},
        }

    assert list(map(_project_ev, actual_evidence)) == list(map(_project_ev, golden_evidence))


def test_transition_mvp_analytics_shimmed(tmp_path, monkeypatch):
    """
    Exercise transition_analytics on the tiny shimmed fixture and validate outputs/checks.
    """
    # Isolate IO
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__FUZZY__THRESHOLD", "0.7")

    from src.assets.transition_assets import (  # noqa: WPS433
        AssetExecutionContext,
        vendor_resolution,
        transition_scores_v1,
        transition_analytics,
    )

    # Reuse tiny fixtures
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

    # Run chain subset up to analytics
    ctx = AssetExecutionContext()
    vr_df, _ = _unwrap_output(vendor_resolution(ctx, contracts_df, awards_df))
    scores_df, _ = _unwrap_output(transition_scores_v1(ctx, vr_df, contracts_df, awards_df))

    analytics_path, meta = _unwrap_output(
        transition_analytics(ctx, awards_df, scores_df, contracts_df)
    )
    p = Path(analytics_path)
    assert p.exists()

    checks_path = (
        Path(meta.get("checks_path"))
        if meta and meta.get("checks_path")
        else p.with_suffix(".checks.json")
    )
    assert checks_path.exists()

    # Load and validate basic payload shape
    summary = json.loads(p.read_text(encoding="utf-8"))
    checks = json.loads(checks_path.read_text(encoding="utf-8"))

    assert "score_threshold" in summary
    assert "award_transition_rate" in summary
    assert "company_transition_rate" in summary

    assert "counts" in checks
    counts = checks["counts"]
    assert counts.get("total_awards", 0) >= 1
    assert counts.get("total_companies", 0) >= 1
