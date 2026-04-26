"""Integration test for the Phase III RETROSPECTIVE candidate asset.

Materializes the asset against a 100-row synthetic fixture (known
Phase-III-coded, known Phase-III-uncoded positives, known non-Phase-III)
and asserts:

- the parquet schema (PhaseIIICandidate column contract);
- the evidence NDJSON line count and required keys;
- the precision gate (HIGH precision ≥ 0.85) on the synthetic positives.

The fixture is engineered so that every uncoded positive scores ≥ 0.85 by
hitting agency_continuity (office), timing_proximity (within 24 months),
competition_type (sole-source), cet_alignment (same CET), text_similarity
(NAICS+PSC+token overlap), and lineage_language (statutory phrases). Coded
contracts (FPDS ``research`` ``SR3``) are excluded by the pair filter and
must NOT appear in output. Non-Phase-III negatives differ on agency / vendor
so they fail the structural pair filter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_candidates.assets import (
    CANDIDATES_OUTPUT_PATH,
    EVIDENCE_OUTPUT_PATH,
    HIGH_THRESHOLD_RETROSPECTIVE,
    WEIGHTS_RETROSPECTIVE,
    build_candidate_asset,
)
from sbir_analytics.assets.phase_iii_candidates.pairing import pair_filter_s1
from sbir_etl.models.phase_iii_candidate import PhaseIIICandidate, SignalClass


pytestmark = [pytest.mark.integration]


PRIOR_ABSTRACT = (
    "Reinforcement learning pipeline for autonomous unmanned aerial vehicle obstacle "
    "avoidance and route planning under contested electromagnetic conditions."
)
TARGET_DESCRIPTION_POSITIVE = (
    "Phase III continuation of autonomous unmanned aerial vehicle obstacle avoidance "
    "research; sole-source prototype transition to follow-on production with delivery "
    "of the technical data package and interface control document for the navigation "
    "subsystem."
)
TARGET_DESCRIPTION_CODED = (
    "Phase III sustainment award for autonomous UAV navigation; interface control "
    "document delivery."
)
TARGET_DESCRIPTION_NEGATIVE = (
    "Janitorial services for office building maintenance, including supplies and "
    "scheduled cleaning."
)


def _make_uei(n: int) -> str:
    base = f"UEI{n:09d}"
    # 12 chars, all alnum, uppercase.
    return base[:12].upper()


def _build_fixture():
    """Return (priors_df, contracts_df) with 50 priors and 100 contract targets.

    Layout:
      - priors[i] for i in 0..49, each with a unique UEI.
      - contracts split:
        * 0..29   uncoded Phase III positives (one per first 30 priors)
        * 30..49  already-coded Phase III (research=SR3) — must be excluded
        * 50..69  unrelated negatives — wrong vendor and different agency
        * 70..99  uncoded but non-Phase-III content (negative content,
                  same vendor, but extent_competed full-and-open and POP gap
                  long enough to drop the timing window — should still
                  generate candidates but score below threshold)
    """

    priors = []
    for i in range(50):
        priors.append(
            {
                "award_id": f"P-{i:03d}",
                "recipient_uei": _make_uei(i),
                "agency": "DEPARTMENT OF DEFENSE",
                "sub_agency": "DEPARTMENT OF THE NAVY",
                "office": "NAVAIR",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "title": "Autonomous UAV navigation",
                "abstract": PRIOR_ABSTRACT,
                "period_of_performance_end": "2022-06-01",
                "cet": "AI",
            }
        )
    priors_df = pd.DataFrame(priors)

    contracts = []

    # Uncoded positives (0..29): same vendor, same office, same NAICS/PSC,
    # same CET, sole-source, within 24 months, full lineage language.
    for i in range(30):
        contracts.append(
            {
                "contract_id": f"C-pos-{i:03d}",
                "vendor_uei": _make_uei(i),
                "awarding_agency_name": "DEPARTMENT OF DEFENSE",
                "awarding_sub_tier_agency_name": "DEPARTMENT OF THE NAVY",
                "awarding_office_name": "NAVAIR",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "transaction_description": TARGET_DESCRIPTION_POSITIVE,
                "action_date": "2023-03-15",
                "extent_competed": "G",  # sole source
                "federal_action_obligation": 5_000_000,
                "research": None,
                "sbir_phase": None,
                # Augment for cet alignment via target_cet.
                "target_cet": "AI",
            }
        )

    # Already-coded Phase III (30..49): SR3. Must be excluded by pair filter.
    for i in range(30, 50):
        contracts.append(
            {
                "contract_id": f"C-coded-{i:03d}",
                "vendor_uei": _make_uei(i),
                "awarding_agency_name": "DEPARTMENT OF DEFENSE",
                "awarding_sub_tier_agency_name": "DEPARTMENT OF THE NAVY",
                "awarding_office_name": "NAVAIR",
                "naics_code": "541715",
                "psc_code": "AJ11",
                "transaction_description": TARGET_DESCRIPTION_CODED,
                "action_date": "2023-04-01",
                "extent_competed": "G",
                "federal_action_obligation": 4_000_000,
                "research": "SR3",
                "sbir_phase": "Phase III",
                "target_cet": "AI",
            }
        )

    # Unrelated negatives: different vendor + different agency. The pair
    # filter joins on UEI so these contribute zero candidate rows.
    for i in range(50, 70):
        contracts.append(
            {
                "contract_id": f"C-neg-{i:03d}",
                "vendor_uei": _make_uei(900 + i),  # not in priors
                "awarding_agency_name": "GENERAL SERVICES ADMINISTRATION",
                "awarding_sub_tier_agency_name": "FEDERAL ACQUISITION SERVICE",
                "awarding_office_name": "REGION 5",
                "naics_code": "722110",
                "psc_code": "S201",
                "transaction_description": TARGET_DESCRIPTION_NEGATIVE,
                "action_date": "2023-05-01",
                "extent_competed": "A",  # full and open
                "federal_action_obligation": 80_000,
                "research": None,
                "sbir_phase": None,
                "target_cet": None,
            }
        )

    # Uncoded same-vendor non-Phase-III content: SHOULD pass the pair
    # filter (same UEI + same agency hierarchy) but score below the HIGH
    # threshold (full-and-open, no lineage phrases, neutral description).
    for i in range(30):
        contracts.append(
            {
                "contract_id": f"C-low-{i:03d}",
                "vendor_uei": _make_uei(i),
                "awarding_agency_name": "DEPARTMENT OF DEFENSE",
                "awarding_sub_tier_agency_name": "DEPARTMENT OF THE NAVY",
                "awarding_office_name": "NAVAIR",
                "naics_code": "722110",
                "psc_code": "S201",
                "transaction_description": TARGET_DESCRIPTION_NEGATIVE,
                "action_date": "2023-08-15",
                "extent_competed": "A",
                "federal_action_obligation": 50_000,
                "research": None,
                "sbir_phase": None,
                "target_cet": None,
            }
        )

    contracts_df = pd.DataFrame(contracts)
    assert len(contracts_df) == 100, "fixture should be 100 rows"
    return priors_df, contracts_df


def _patched_pair_filter(priors: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    """Run S1 then re-attach ``target_cet`` from the raw contracts frame.

    The canonical pair filter does not project ``target_cet`` because the
    production contracts parquet doesn't carry one. The integration fixture
    pre-classifies CET to exercise that signal, so this thin wrapper joins
    the value back onto the pair frame on contract id.
    """

    pairs = pair_filter_s1(priors, contracts)
    if pairs.empty or "target_cet" not in contracts.columns:
        return pairs
    cet_lookup = (
        contracts.loc[:, ["contract_id", "target_cet"]]
        .rename(columns={"contract_id": "target_id"})
        .drop_duplicates(subset=["target_id"])
    )
    return pairs.merge(cet_lookup, on="target_id", how="left")


def test_phase_iii_retrospective_asset_materializes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    priors_df, contracts_df = _build_fixture()

    asset_fn = build_candidate_asset(
        signal_class=SignalClass.RETROSPECTIVE,
        pair_filter=_patched_pair_filter,
        weights=WEIGHTS_RETROSPECTIVE,
        high_threshold=HIGH_THRESHOLD_RETROSPECTIVE,
        asset_name="phase_iii_retrospective_candidates_test",
        target_loader=lambda _ctx: contracts_df,
    )

    out = asset_fn(context=None, validated_phase_ii_awards=priors_df)
    df = out.value if hasattr(out, "value") else out
    assert isinstance(df, pd.DataFrame)

    # Coded contracts excluded by pair filter; positives + low-content
    # contracts both produce one candidate per matching UEI.
    assert len(df) == 60, f"expected 60 candidates (30 positives + 30 low), got {len(df)}"

    # Schema: must match PhaseIIICandidate row contract.
    expected_cols = {
        "candidate_id",
        "signal_class",
        "prior_award_id",
        "target_type",
        "target_id",
        "candidate_score",
        "is_high_confidence",
        "evidence_ref",
        "agency_continuity_score",
        "timing_proximity_score",
        "competition_type_score",
        "patent_signal_score",
        "cet_alignment_score",
        "text_similarity_score",
        "lineage_language_score",
        "generated_at",
    }
    assert expected_cols.issubset(set(df.columns))
    # Round-trip a sample row through the model to confirm the contract holds.
    PhaseIIICandidate(**df.iloc[0].to_dict())

    # No coded contracts in output.
    assert not df["target_id"].astype(str).str.startswith("C-coded-").any()

    # Parquet was written and matches the dataframe.
    parquet_path = Path(tmp_path) / CANDIDATES_OUTPUT_PATH
    assert parquet_path.exists(), f"missing parquet at {parquet_path}"
    parquet_df = pd.read_parquet(parquet_path)
    assert len(parquet_df) == len(df)
    assert (parquet_df["signal_class"] == SignalClass.RETROSPECTIVE.value).all()

    # Evidence NDJSON: one line per candidate, with the documented key shape.
    evidence_path = Path(tmp_path) / EVIDENCE_OUTPUT_PATH
    assert evidence_path.exists(), f"missing evidence file at {evidence_path}"
    lines = evidence_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(df)
    sample = json.loads(lines[0])
    for required in (
        "candidate_id",
        "signal_class",
        "award_id",
        "contract_id",
        "score",
        "method",
        "matched_keys",
        "dates",
        "amounts",
        "agencies",
        "subscores",
        "topical_similarity",
        "generated_at",
    ):
        assert required in sample, f"evidence record missing key {required!r}"

    # Precision gate: HIGH precision over the engineered positives must be
    # at or above the spec threshold of 0.85.
    positives = df.loc[df["target_id"].astype(str).str.startswith("C-pos-")]
    assert len(positives) == 30
    high_positives = int(positives["is_high_confidence"].sum())
    precision = high_positives / len(positives)
    assert precision >= HIGH_THRESHOLD_RETROSPECTIVE, (
        f"HIGH precision {precision:.4f} below threshold {HIGH_THRESHOLD_RETROSPECTIVE} "
        f"({high_positives}/{len(positives)} positives flagged HIGH)"
    )

    # Low-content same-vendor contracts should NOT be high-confidence.
    low = df.loc[df["target_id"].astype(str).str.startswith("C-low-")]
    assert len(low) == 30
    assert int(low["is_high_confidence"].sum()) == 0


def test_pair_filter_s1_excludes_already_coded_phase_iii():
    priors_df, contracts_df = _build_fixture()
    pairs = pair_filter_s1(priors_df, contracts_df)
    assert not pairs.empty
    target_ids = pairs["target_id"].astype(str).tolist()
    assert not any(t.startswith("C-coded-") for t in target_ids)
    # Negatives (different vendor) are dropped by the UEI inner join.
    assert not any(t.startswith("C-neg-") for t in target_ids)
    # Both the positives and the low-content same-vendor contracts pass.
    assert sum(1 for t in target_ids if t.startswith("C-pos-")) == 30
    assert sum(1 for t in target_ids if t.startswith("C-low-")) == 30
    # Office is the finest agency match.
    assert (pairs["agency_match_level"] == "office").all()
