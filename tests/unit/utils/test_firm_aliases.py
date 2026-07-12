"""Tests for firm alias-graph construction (sbir_etl.utils.firm_aliases)."""

import pytest

from sbir_etl.utils.firm_aliases import (
    AliasEdge,
    alias_edges_from_shared_uei,
    build_alias_index,
    classify_conveyance,
    make_alias_edge,
)

pytestmark = pytest.mark.fast


class TestMakeAliasEdge:
    def test_genuine_rename_produces_edge(self):
        edge = make_alias_edge(
            "Microlab", "MAGFUSION, INC.", source="patent_assignment", relation="namechg"
        )
        assert edge is not None
        assert edge.firm_normalized == "microlab"
        assert edge.alias_normalized == "magfusion"
        assert edge.relation == "namechg"

    def test_suffix_only_difference_is_dropped(self):
        # The bug caught in reconnaissance: ceramem -> CERAMEM CORPORATION
        # normalizes to the same token and carries no matching power.
        assert (
            make_alias_edge(
                "Ceramem", "CERAMEM CORPORATION", source="patent_assignment", relation="merger"
            )
            is None
        )

    def test_empty_names_dropped(self):
        assert make_alias_edge("", "Acme", source="s", relation="r") is None
        assert make_alias_edge("Acme", "  ", source="s", relation="r") is None

    def test_state_corroboration_is_uppercased(self):
        edge = make_alias_edge(
            "Kionix",
            "Calient Networks",
            source="patent_assignment",
            relation="merger",
            corrob_state="ca",
        )
        assert edge is not None
        assert edge.corrob_state == "CA"


class TestClassifyConveyance:
    @pytest.mark.parametrize("ct", ["namechg", "merger", "NAMECHG", " Merger "])
    def test_alias_conveyances(self, ct):
        assert classify_conveyance(ct) == "alias"

    def test_assignment_is_lead_not_alias(self):
        assert classify_conveyance("assignment") == "lead"

    @pytest.mark.parametrize("ct", ["security", "govern", "release", "", "correct"])
    def test_other_conveyances_ignored(self, ct):
        assert classify_conveyance(ct) == "ignore"


class TestSharedUei:
    def test_distinct_names_under_one_uei_produce_edge(self):
        edges = alias_edges_from_shared_uei(
            {"UEI1": {"RADIABEAM SYSTEMS, LLC", "RADIABEAM TECHNOLOGIES, LLC"}}
        )
        assert len(edges) == 1
        assert {edges[0].firm_normalized, edges[0].alias_normalized} == {
            "radiabeam systems",
            "radiabeam technologies",
        }

    def test_suffix_variants_under_one_uei_collapse(self):
        # "QORTEK INC" and "QORTEK INC." -> same node, no edge
        edges = alias_edges_from_shared_uei({"UEI1": {"QORTEK INC", "QORTEK INC."}})
        assert edges == []

    def test_single_name_uei_produces_nothing(self):
        assert alias_edges_from_shared_uei({"UEI1": {"ONLY ONE NAME"}}) == []

    def test_three_names_produce_three_pairs(self):
        edges = alias_edges_from_shared_uei({"U": {"Alpha Corp", "Beta Labs", "Gamma Systems"}})
        assert len(edges) == 3


class TestBuildAliasIndex:
    def test_single_edge_symmetric(self):
        edges = [
            AliasEdge("microlab", "Magfusion", "magfusion", "patent_assignment", "namechg", "", "")
        ]
        index = build_alias_index(edges)
        assert index["microlab"] == {"microlab", "magfusion"}
        assert index["magfusion"] == {"microlab", "magfusion"}

    def test_transitive_chain_forms_one_component(self):
        # A -> B -> C should resolve every member to {A, B, C}
        edges = [
            AliasEdge("a", "B", "b", "patent_assignment", "namechg", "", ""),
            AliasEdge("b", "C", "c", "patent_assignment", "merger", "", ""),
        ]
        index = build_alias_index(edges)
        assert index["a"] == {"a", "b", "c"}
        assert index["c"] == {"a", "b", "c"}

    def test_disjoint_components_stay_separate(self):
        edges = [
            AliasEdge("a", "B", "b", "s", "namechg", "", ""),
            AliasEdge("x", "Y", "y", "s", "namechg", "", ""),
        ]
        index = build_alias_index(edges)
        assert index["a"] == {"a", "b"}
        assert index["x"] == {"x", "y"}
        assert "a" not in index["x"]

    def test_empty_edges(self):
        assert build_alias_index([]) == {}
