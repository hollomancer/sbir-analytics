import pandas as pd
import pytest


pytestmark = pytest.mark.fast

pytest.importorskip("dagster")
from dagster import build_asset_context


def _unwrap_output(result):
    """
    Helper to unwrap Dagster Output-like objects to (value, metadata).
    The transition assets return Output(value=..., metadata=...).
    """
    if hasattr(result, "value"):
        return result.value, getattr(result, "metadata", None)
    return result, None


def _drop_dynamic_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize DataFrame by dropping dynamic columns that vary across runs
    (e.g., timestamps), preserving relative row order for top-k checks.
    """
    cols = list(df.columns)
    dyn = [c for c in ("computed_at",) if c in cols]
    return df.drop(columns=dyn)


def test_transition_scores_topk_deterministic_across_runs(monkeypatch, tmp_path):
    """
    Assert that transition_scores_v1 produces deterministic top-k ordering
    for an award, regardless of the input rows ordering.

    Strategy:
      - Create one award (A1) and two candidate contracts (C1, C2) that match
        the same vendor via name_fuzzy.
      - Run transition_scores_v1 multiple times with input permutations:
          1) original
          2) vendor_resolution rows reversed
          3) contracts_sample rows reversed
      - For each run, capture the per-award ordered list of (contract_id, score, method)
      - Verify that the ordering within the top-k for award A1 is stable across runs.
      - Verify idempotence on identical inputs (after dropping dynamic columns).
    """
    # Isolate all IO under a temp working directory
    monkeypatch.chdir(tmp_path)

    # Import the asset locally (import-safe without Dagster installed)
    from src.assets.transition_assets import transformed_transition_scores  # type: ignore

    # Award A1 identified by name (no UEI/DUNS), so vendor id becomes "name:acme co"
    awards_df = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "Company": "Acme Co",
                "UEI": None,
                "Duns": None,
                "Agency": "DEPT OF DEFENSE",
                "award_date": "2022-01-01",
            }
        ]
    )

    # Two contracts for same vendor "Acme Co" with different action dates.
    # Both will be linked by vendor_resolution (name_fuzzy).
    # Scoring in the simple MVP is primarily method-based; timing/agency
    # metadata is included to ensure the function can process consistently.
    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Co",
                "action_date": "2022-01-15",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Co",
                "action_date": "2023-01-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
        ]
    )

    # Vendor resolution mapping: both contracts matched via fuzzy name to the
    # award's vendor identifier ("name:acme co").
    vendor_res_df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "matched_vendor_id": "name:acme co",
                "match_method": "name_fuzzy",
                "confidence": 0.90,
            },
            {
                "contract_id": "C2",
                "matched_vendor_id": "name:acme co",
                "match_method": "name_fuzzy",
                "confidence": 0.88,
            },
        ]
    )

    ctx = build_asset_context()
    # Call the asset directly - Dagster assets are callable

    # Run 1: original order
    out1, _ = _unwrap_output(
        transformed_transition_scores(
            context=ctx,
            enriched_vendor_resolution=vendor_res_df,
            validated_contracts_sample=contracts_df,
            enriched_sbir_awards=awards_df,
        )
    )
    out1 = _drop_dynamic_columns(out1)

    # Run 2: vendor_resolution rows reversed
    vr_rev = vendor_res_df.iloc[::-1].reset_index(drop=True)
    out2, _ = _unwrap_output(
        transformed_transition_scores(
            context=ctx,
            enriched_vendor_resolution=vr_rev,
            validated_contracts_sample=contracts_df,
            enriched_sbir_awards=awards_df,
        )
    )
    out2 = _drop_dynamic_columns(out2)

    # Run 3: contracts rows reversed
    contracts_rev = contracts_df.iloc[::-1].reset_index(drop=True)
    out3, _ = _unwrap_output(
        transformed_transition_scores(
            context=ctx,
            enriched_vendor_resolution=vendor_res_df,
            validated_contracts_sample=contracts_rev,
            enriched_sbir_awards=awards_df,
        )
    )
    out3 = _drop_dynamic_columns(out3)

    # Helper to extract the ordered top-k for award A1 as emitted by the asset
    def topk_for_award(df: pd.DataFrame, award_id: str):
        df_award = df[df["award_id"] == award_id].reset_index(drop=True)
        # Preserve output order to assert stability
        return [
            (str(r["contract_id"]), float(r["score"]), str(r["method"]))
            for _, r in df_award.iterrows()
        ]

    top1 = topk_for_award(out1, "A1")
    top2 = topk_for_award(out2, "A1")
    top3 = topk_for_award(out3, "A1")

    # Top-k stability across permutations: identical content and ordering
    assert top1 == top2 == top3

    # Idempotence on identical inputs: running again should yield same rows (ignoring dynamic fields)
    out1b, _ = _unwrap_output(
        transformed_transition_scores(
            context=ctx,
            enriched_vendor_resolution=vendor_res_df,
            validated_contracts_sample=contracts_df,
            enriched_sbir_awards=awards_df,
        )
    )
    out1b = _drop_dynamic_columns(out1b)
    # Compare as lists of row dicts for robustness
    rows1 = out1.to_dict(orient="records")
    rows1b = out1b.to_dict(orient="records")
    assert rows1 == rows1b
