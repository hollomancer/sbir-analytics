"""Tests for the raw-corpus same-work award detector."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "find_same_work_awards.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("find_same_work_awards", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_script()


BASE = {
    "Company": "Acme Research, Inc.",
    "Award Title": "Advanced adaptive propulsion controller",
    "Agency": "Department of Defense",
    "Branch": "Air Force",
    "Phase": "Phase I",
    "Program": "SBIR",
    "Agency Tracking Number": "TRACK-1",
    "Contract": "CONTRACT-1",
    "Proposal Award Date": "2022-01-01",
    "Contract End Date": "2022-12-31",
    "Solicitation Number": "SOL-1",
    "Topic Code": "TOPIC-1",
    "Award Year": "2022",
    "Award Amount": "100000",
    "UEI": "ABCDEFGHIJKL",
    "Duns": "012345678",
    "State": "VA",
    "Abstract": (
        "This project develops an adaptive propulsion controller with robust sensing "
        "and real-time fault tolerance for advanced flight vehicles. The effort integrates "
        "embedded estimation, resilient guidance software, and hardware-in-the-loop testing "
        "to demonstrate stable operation under representative vibration, thermal, and "
        "communications constraints. The resulting prototype will be evaluated against "
        "repeatable mission scenarios and documented performance requirements."
    ),
    "PI Name": "Jane Researcher",
}


def _award(**updates):
    row = BASE.copy()
    row.update(updates)
    return row


def _prepare(rows):
    return mod.prepare_awards(pd.DataFrame(rows))


def test_exact_title_and_abstract_cross_agency_is_exact_pair():
    rows = [
        _award(),
        _award(
            Agency="National Aeronautics and Space Administration",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert pair["match_tier"] == "exact"
    assert pair["match_basis"] == "exact_abstract+exact_title"
    assert bool(pair["cross_agency"])
    assert bool(pair["contemporaneous_same_phase"])
    assert bool(pair["priority_review"])


def test_exact_abstract_only_with_dissimilar_title_is_review():
    rows = [
        _award(),
        _award(
            Agency="National Aeronautics and Space Administration",
            **{
                "Award Title": "Fault-tolerant controls for flight systems",
                "Agency Tracking Number": "TRACK-2",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert pair["match_tier"] == "review"
    assert pair["match_basis"] == "exact_abstract"
    assert bool(pair["cross_agency"])
    assert pair["relationship_context"] == "cross_agency_overlap"


def test_long_exact_abstract_with_similar_title_is_strong():
    rows = [
        _award(),
        _award(
            Agency="Department of Energy",
            **{
                "Award Title": "Advanced adaptive propulsion controllers",
                "Agency Tracking Number": "TRACK-2",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert pair["match_tier"] == "strong"
    assert pair["match_basis"] == "exact_abstract"
    assert pair["exact_abstract_chars"] >= 300


def test_exact_title_different_topic_is_retained_for_review():
    rows = [
        _award(),
        _award(
            **{
                "Topic Code": "TOPIC-2",
                "Solicitation Number": "SOL-2",
                "Agency Tracking Number": "TRACK-2",
                "Abstract": (
                    "A materially different technical approach studies thermal coatings and "
                    "manufacturing processes for hypersonic structures."
                ),
            }
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert pair["match_tier"] == "review"
    assert pair["match_basis"] == "exact_title"
    assert bool(pair["different_topic"])
    assert pair["relationship_context"] == "same_agency_different_topic"


def test_near_title_and_abstract_can_be_strong():
    rows = [
        _award(),
        _award(
            Agency="Department of Energy",
            **{
                "Award Title": "Advanced adaptive propulsion controllers",
                "Agency Tracking Number": "TRACK-2",
                "Abstract": (
                    "This project develops an adaptive propulsion controller with robust "
                    "sensors and real-time fault tolerance for advanced flight vehicles. "
                    "The effort integrates embedded estimation, resilient guidance software, "
                    "and hardware-in-the-loop tests to demonstrate stable operation under "
                    "representative vibration, thermal, and communications constraints. The "
                    "resulting prototype will be evaluated against repeatable mission scenarios "
                    "and documented performance requirements."
                ),
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    assert pairs.iloc[0]["match_tier"] == "strong"
    assert pairs.iloc[0]["match_basis"] == "near_title+near_abstract"


def test_unrelated_work_and_same_scope_are_excluded():
    rows = [
        _award(),
        _award(
            **{
                "Agency Tracking Number": "TRACK-2",
                "Award Title": "Novel cancer immunotherapy using engineered T cells",
                "Abstract": (
                    "The team will develop a cellular immunotherapy for solid tumors using "
                    "engineered receptors and a new manufacturing workflow."
                ),
            }
        ),
        _award(**{"Agency Tracking Number": "TRACK-3"}),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert pairs.empty


def test_blank_topic_is_unknown_not_different():
    rows = [
        _award(**{"Topic Code": "", "Solicitation Number": ""}),
        _award(
            **{
                "Topic Code": "TOPIC-2",
                "Agency Tracking Number": "TRACK-2",
            }
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert pairs.empty


def test_branch_prefixed_topic_alias_is_not_a_different_topic():
    rows = [
        _award(**{"Topic Code": "A08-060"}),
        _award(
            **{
                "Topic Code": "Army 08-060",
                "Agency Tracking Number": "TRACK-2",
            }
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert pairs.empty


def test_placeholder_and_float_artifact_topic_codes_are_not_different():
    assert mod.normalize_topic_code("N/A") == ""
    assert mod.normalize_topic_code("null") == ""
    assert mod.normalize_topic_code("8.3") == mod.normalize_topic_code("8.300000000000001")

    rows = [
        _award(**{"Topic Code": "8.3"}),
        _award(
            **{
                "Topic Code": "8.300000000000001",
                "Agency Tracking Number": "TRACK-2",
            }
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert pairs.empty


def test_likely_phase_progression_requires_linkage_and_sane_dates():
    rows = [
        _award(),
        _award(
            Phase="Phase II",
            **{
                "Topic Code": "TOPIC-2",
                "Agency Tracking Number": "TRACK-2",
                "Contract": "CONTRACT-2",
                "Proposal Award Date": "2023-01-01",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert bool(pair["sequential_phase_pair"])
    assert bool(pair["likely_phase_progression"])
    assert pair["phase_progression_status"] == "likely_progression"
    assert "similar_title" in pair["phase_progression_basis"]


def test_reverse_phase_dates_are_not_called_likely_progression():
    rows = [
        _award(**{"Proposal Award Date": "2024-01-01"}),
        _award(
            Phase="Phase II",
            **{
                "Topic Code": "TOPIC-2",
                "Agency Tracking Number": "TRACK-2",
                "Contract": "CONTRACT-2",
                "Proposal Award Date": "2023-01-01",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert bool(pair["sequential_phase_pair"])
    assert not bool(pair["likely_phase_progression"])
    assert pair["phase_progression_status"] == "phase_sequence_reverse_dates"


def test_missing_phase_date_is_unknown_without_exact_source_reference():
    rows = [
        _award(**{"Proposal Award Date": ""}),
        _award(
            Phase="Phase II",
            **{
                "Topic Code": "TOPIC-2",
                "Agency Tracking Number": "TRACK-2",
                "Contract": "CONTRACT-2",
                "Proposal Award Date": "2023-01-01",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert not bool(pair["likely_phase_progression"])
    assert pair["phase_progression_status"] == "phase_sequence_unknown"


def test_exact_abstract_alone_does_not_link_a_phase_sequence():
    rows = [
        _award(),
        _award(
            Phase="Phase II",
            **{
                "Award Title": "Unrelated grid monitoring platform",
                "Topic Code": "TOPIC-2",
                "Agency Tracking Number": "TRACK-2",
                "Contract": "CONTRACT-2",
                "Proposal Award Date": "2023-01-01",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert bool(pair["sequential_phase_pair"])
    assert not bool(pair["likely_phase_progression"])
    assert pair["phase_progression_status"] == "phase_sequence_no_project_link"


def test_cross_agency_sequence_can_be_a_likely_progression():
    rows = [
        _award(Agency="National Aeronautics and Space Administration"),
        _award(
            Agency="Department of Defense",
            Phase="Phase II",
            **{
                "Agency Tracking Number": "TRACK-2",
                "Contract": "CONTRACT-2",
                "Proposal Award Date": "2023-01-01",
            },
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    pair = pairs.iloc[0]
    assert bool(pair["cross_agency"])
    assert bool(pair["sequential_phase_pair"])
    assert bool(pair["likely_phase_progression"])
    assert "cross_agency" in pair["phase_progression_basis"]
    assert not bool(pair["priority_review"])


def test_same_text_different_firm_is_excluded():
    rows = [
        _award(),
        _award(
            Company="Different Research LLC",
            Agency="Department of Energy",
            UEI="MNOPQRSTUVWX",
            Duns="876543210",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    assert pairs.empty


def test_duns_only_row_bridges_to_single_uei():
    rows = [
        _award(),
        _award(
            Company="Acme Research Corporation",
            Agency="Department of Energy",
            UEI="",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
    ]
    prepared = _prepare(rows)
    assert prepared.loc[0, "_firm_key"] == prepared.loc[1, "_firm_key"]
    assert prepared.loc[1, "_firm_key_method"] == "duns_to_uei"
    pairs = mod.find_same_work_pairs(prepared, config=mod.MatchConfig(workers=1))
    assert len(pairs) == 1
    assert pairs.iloc[0]["firm_match_basis"] == "duns_exact"


def test_ambiguous_duns_is_not_transitively_merged():
    rows = [
        _award(UEI="ABCDEFGHIJKL", Company="Alpha Labs Inc"),
        _award(
            UEI="MNOPQRSTUVWX",
            Company="Beta Labs Inc",
            Agency="Department of Energy",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
        _award(
            UEI="",
            Company="Gamma Labs Inc",
            Agency="National Science Foundation",
            **{"Agency Tracking Number": "TRACK-3"},
        ),
    ]
    prepared = _prepare(rows)
    assert prepared["_firm_key"].nunique() == 3
    assert prepared.loc[2, "_firm_key_method"] == "name_state_ambiguous_duns"


def test_reused_tracking_number_preserves_both_source_records():
    rows = [
        _award(),
        _award(
            Agency="Department of Energy",
            **{
                "Topic Code": "TOPIC-2",
                "Solicitation Number": "SOL-2",
            },
        ),
    ]
    prepared = _prepare(rows)
    pairs = mod.find_same_work_pairs(prepared, config=mod.MatchConfig(workers=1))
    pairs, clusters = mod.add_ids_and_clusters(prepared, pairs, list(pd.DataFrame(rows).columns))
    records = mod.build_record_output(prepared, pairs, clusters, list(pd.DataFrame(rows).columns))
    assert len(pairs) == 1
    assert len(records) == 2
    assert records["source_record_number"].tolist() == [1, 2]
    assert records["Agency Tracking Number"].tolist() == ["TRACK-1", "TRACK-1"]


def test_identical_source_rows_remain_distinct_when_both_are_implicated():
    rows = [
        _award(),
        _award(),
        _award(
            Agency="Department of Energy",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
    ]
    source_columns = list(pd.DataFrame(rows).columns)
    prepared = _prepare(rows)
    pairs = mod.find_same_work_pairs(prepared, config=mod.MatchConfig(workers=1))
    pairs, clusters = mod.add_ids_and_clusters(prepared, pairs, source_columns)
    records = mod.build_record_output(prepared, pairs, clusters, source_columns)
    assert len(records) == 3
    assert records["record_id"].nunique() == 3


def test_minimum_strong_drops_review_pairs():
    rows = [
        _award(),
        _award(
            **{
                "Topic Code": "TOPIC-2",
                "Solicitation Number": "SOL-2",
                "Agency Tracking Number": "TRACK-2",
                "Abstract": (
                    "A materially different technical approach studies thermal coatings and "
                    "manufacturing processes for hypersonic structures."
                ),
            }
        ),
    ]
    pairs = mod.find_same_work_pairs(
        _prepare(rows),
        config=mod.MatchConfig(workers=1),
        minimum_tier="strong",
    )
    assert pairs.empty


def test_name_state_bridged_pair_is_not_reported_as_high_confidence():
    """A name+state bridge to an identifier is name-based evidence, not identifier evidence.

    Row 2 carries no usable identifier and is attached to the UEI-backed firm by
    normalized name+state. Paired against row 1 — same firm by UEI, but a
    different name+state key — it matches on neither UEI, DUNS, nor an identical
    name+state, so it lands on the bridge branch. That evidence is name-based and
    must not be reported at the confidence of a shared UEI.
    """

    rows = [
        _award(),
        _award(
            Agency="National Aeronautics and Space Administration",
            State="MD",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
        _award(
            Agency="Department of Energy",
            UEI="",
            Duns="",
            **{"Agency Tracking Number": "TRACK-3"},
        ),
    ]
    prepared = _prepare(rows)
    assert prepared.loc[2, "_firm_key_method"] == "name_state_to_id"
    assert prepared["_firm_key"].nunique() == 1

    pairs = mod.find_same_work_pairs(prepared, config=mod.MatchConfig(workers=1))
    bridged = pairs.loc[(pairs["_left_index"] == 1) & (pairs["_right_index"] == 2)]
    assert len(bridged) == 1
    assert bridged.iloc[0]["firm_match_basis"] == "name_state_bridge"
    assert bridged.iloc[0]["firm_match_confidence"] == "medium"


def test_shared_uei_pair_is_still_high_confidence():
    rows = [
        _award(),
        _award(
            Agency="National Aeronautics and Space Administration",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
    ]
    pairs = mod.find_same_work_pairs(_prepare(rows), config=mod.MatchConfig(workers=1))
    pair = pairs.iloc[0]
    assert pair["firm_match_basis"] == "uei_exact"
    assert pair["firm_match_confidence"] == "high"


def test_non_range_index_frame_is_rejected_rather_than_mismatching_rows():
    """Positional and label lookups are mixed; a filtered frame would silently disagree."""

    import pytest

    rows = [
        _award(),
        _award(
            Agency="National Aeronautics and Space Administration",
            **{"Agency Tracking Number": "TRACK-2"},
        ),
        _award(Agency="Department of Energy", **{"Agency Tracking Number": "TRACK-3"}),
    ]
    prepared = _prepare(rows)
    # Dropping the *first* row leaves labels [1, 2] — positions 0 and 1.
    filtered = prepared.loc[prepared["Agency"] != "Department of Defense"]
    assert list(filtered.index) == [1, 2]

    with pytest.raises(ValueError, match="RangeIndex"):
        mod.find_same_work_pairs(filtered, config=mod.MatchConfig(workers=1))

    # The same rows, re-indexed, are accepted.
    assert len(mod.find_same_work_pairs(filtered.reset_index(drop=True))) == 1
