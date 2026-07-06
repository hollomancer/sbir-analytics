"""Unit tests for scripts/archive/data/audit_form_d_pif_cross_links.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "archive"
    / "data"
    / "audit_form_d_pif_cross_links.py"
)
_spec = importlib.util.spec_from_file_location("audit_form_d_pif_cross_links", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_form_d_pif_cross_links"] = _mod
_spec.loader.exec_module(_mod)


def _record(
    company: str,
    tier: str,
    *,
    has_pif: bool,
    has_non_pif: bool,
    persons: list[str],
    ciks: list[str] | None = None,
    raised: float = 0.0,
    person_score: float | None = None,
    address_score: float | None = None,
    state_score: float | None = None,
) -> dict:
    """Construct a Form D record-shaped dict for the audit's expected schema."""
    return {
        "company_name": company,
        "tier": tier,
        "has_pif": has_pif,
        "has_non_pif": has_non_pif,
        "persons": set(persons),
        "ciks": set(ciks or []),
        "raised_counted": raised,
        "person_score": person_score,
        "address_score": address_score,
        "state_score": state_score,
    }


class TestFindCrossLinks:
    def test_no_cross_link_when_no_shared_person(self):
        records = [
            _record("PIF_A", "low", has_pif=True, has_non_pif=False, persons=["ALICE"]),
            _record("OP_B", "high", has_pif=False, has_non_pif=True, persons=["BOB"]),
        ]
        assert _mod.find_cross_links(records) == []

    def test_finds_person_based_cross_link(self):
        records = [
            _record("PIF_A", "low", has_pif=True, has_non_pif=False, persons=["ALICE"]),
            _record(
                "OP_B",
                "high",
                has_pif=False,
                has_non_pif=True,
                persons=["ALICE", "BOB"],
                raised=1_000_000.0,
            ),
        ]
        xl = _mod.find_cross_links(records)
        assert len(xl) == 1
        assert xl[0]["pif_company"] == "PIF_A"
        assert xl[0]["op_company"] == "OP_B"
        assert xl[0]["link_type"] == "person"
        assert xl[0]["link_value"] == "ALICE"
        assert xl[0]["op_tier"] == "high"

    def test_finds_cik_based_cross_link(self):
        records = [
            _record("PIF_A", "low", has_pif=True, has_non_pif=False, persons=["X"], ciks=["123"]),
            _record("OP_B", "medium", has_pif=False, has_non_pif=True, persons=["Y"], ciks=["123"]),
        ]
        xl = _mod.find_cross_links(records)
        assert len(xl) == 1
        assert xl[0]["link_type"] == "cik"
        assert xl[0]["link_value"] == "123"

    def test_dedupes_pif_op_pair_across_signal_types(self):
        """Same (PIF, op) pair sharing both a person AND a CIK should produce
        only one cross-link row to avoid double-counting in the summary."""
        records = [
            _record(
                "PIF_A", "low", has_pif=True, has_non_pif=False, persons=["ALICE"], ciks=["999"]
            ),
            _record(
                "OP_B",
                "high",
                has_pif=False,
                has_non_pif=True,
                persons=["ALICE"],
                ciks=["999"],
                raised=1.0,
            ),
        ]
        xl = _mod.find_cross_links(records)
        assert len(xl) == 1

    def test_mixed_record_is_treated_as_operating_co(self):
        """A record with both PIF and non-PIF offerings is counted-in-cohort
        (via its non-PIF offerings) and should be eligible as a cross-link target."""
        records = [
            _record("PURE_PIF", "low", has_pif=True, has_non_pif=False, persons=["SHARED"]),
            _record(
                "MIXED", "medium", has_pif=True, has_non_pif=True, persons=["SHARED"], raised=500.0
            ),
        ]
        xl = _mod.find_cross_links(records)
        assert len(xl) == 1
        assert xl[0]["pif_company"] == "PURE_PIF"
        assert xl[0]["op_company"] == "MIXED"

    def test_pure_pif_is_not_a_cross_link_target(self):
        """Two pure-PIF records sharing a person should NOT cross-link to each other —
        cross-links only flow PIF → operating-co."""
        records = [
            _record("PIF_X", "low", has_pif=True, has_non_pif=False, persons=["SHARED"]),
            _record("PIF_Y", "low", has_pif=True, has_non_pif=False, persons=["SHARED"]),
        ]
        assert _mod.find_cross_links(records) == []


class TestClassifyHighTierRobustness:
    def _xl_with_op(self, op_company, person, address, state, raised=1.0):
        return {
            "pif_company": "PIF",
            "op_company": op_company,
            "link_type": "person",
            "link_value": "X",
            "op_tier": "high",
            "op_raised_counted": raised,
            "op_person_score": person,
            "op_address_score": address,
            "op_state_score": state,
        }

    def test_both_signals_safe(self):
        xl = [self._xl_with_op("OP", person=0.9, address=1.0, state=1.0)]
        profile = _mod.classify_high_tier_robustness(xl, [])
        assert len(profile["both_signals"]) == 1
        assert len(profile["zip_only"]) == 0
        assert len(profile["person_only_at_risk"]) == 0

    def test_zip_only_safe(self):
        xl = [self._xl_with_op("OP", person=0.3, address=1.0, state=1.0)]
        profile = _mod.classify_high_tier_robustness(xl, [])
        assert len(profile["zip_only"]) == 1
        assert len(profile["both_signals"]) == 0

    def test_person_only_at_risk(self):
        xl = [self._xl_with_op("OP", person=0.9, address=0.0, state=1.0)]
        profile = _mod.classify_high_tier_robustness(xl, [])
        assert len(profile["person_only_at_risk"]) == 1
        assert len(profile["both_signals"]) == 0
        assert len(profile["zip_only"]) == 0

    def test_low_scores_classified_as_neither(self):
        xl = [self._xl_with_op("OP", person=0.5, address=0.0, state=0.0)]
        profile = _mod.classify_high_tier_robustness(xl, [])
        assert len(profile["neither_full"]) == 1

    def test_none_scores_treated_as_zero(self):
        xl = [self._xl_with_op("OP", person=None, address=1.0, state=None)]
        profile = _mod.classify_high_tier_robustness(xl, [])
        # person None → 0 → ZIP-only path
        assert len(profile["zip_only"]) == 1

    def test_multiple_cross_links_for_same_op_collapse(self):
        """If an op is in multiple cross-links, it should be classified once."""
        xl = [
            self._xl_with_op("SAME_OP", person=0.9, address=1.0, state=1.0, raised=100.0),
            self._xl_with_op("SAME_OP", person=0.9, address=1.0, state=1.0, raised=100.0),
        ]
        profile = _mod.classify_high_tier_robustness(xl, [])
        # Only one entry across all profile categories
        total = sum(len(v) for v in profile.values())
        assert total == 1


class TestSummarize:
    def _make_records_and_xl(self):
        """Construct a minimal scenario:
        - PIF_A (low, pif) shares ALICE with OP_HIGH (high), raised=$100M
        - PIF_B (low, pif) shares BOB with OP_MED (medium), raised=$50M
        - OP_HIGH has person=0.9, ZIP=0 → at-risk
        - OP_MED has person=0.9, ZIP=0 → not in high-tier robustness check
        """
        records = [
            _record("PIF_A", "low", has_pif=True, has_non_pif=False, persons=["ALICE"]),
            _record("PIF_B", "low", has_pif=True, has_non_pif=False, persons=["BOB"]),
            _record(
                "OP_HIGH",
                "high",
                has_pif=False,
                has_non_pif=True,
                persons=["ALICE"],
                raised=100_000_000.0,
                person_score=0.9,
                address_score=0.0,
                state_score=1.0,
            ),
            _record(
                "OP_MED",
                "medium",
                has_pif=False,
                has_non_pif=True,
                persons=["BOB"],
                raised=50_000_000.0,
                person_score=0.9,
                address_score=0.0,
                state_score=1.0,
            ),
        ]
        cross_links = _mod.find_cross_links(records)
        return records, cross_links

    def test_summary_counts_cross_links_and_dollars(self):
        records, xl = self._make_records_and_xl()
        s = _mod.summarize(xl, records, high_headline_usd=10e9, hm_headline_usd=15e9)
        assert s["n_cross_link_pairs"] == 2
        assert s["distinct_high_tier_ops_with_cross_link"] == 1
        assert s["distinct_medium_tier_ops_with_cross_link"] == 1
        assert s["high_tier_counted_dollars_at_cross_link_op_side"] == 100_000_000.0
        assert s["hm_tier_counted_dollars_at_cross_link_op_side"] == 150_000_000.0

    def test_summary_percentages(self):
        records, xl = self._make_records_and_xl()
        s = _mod.summarize(
            xl, records, high_headline_usd=10_000_000_000.0, hm_headline_usd=15_000_000_000.0
        )
        # $100M / $10B = 1.0%
        assert s["high_tier_pct_of_headline"] == pytest.approx(1.0)
        # $150M / $15B = 1.0%
        assert s["hm_pct_of_headline"] == pytest.approx(1.0)

    def test_summary_at_risk_quantification(self):
        records, xl = self._make_records_and_xl()
        s = _mod.summarize(
            xl, records, high_headline_usd=10_000_000_000.0, hm_headline_usd=15_000_000_000.0
        )
        # OP_HIGH has person=0.9, ZIP=0 → at-risk
        assert s["at_risk_dollars_usd"] == 100_000_000.0
        assert s["at_risk_pct_of_high_headline"] == pytest.approx(1.0)
        assert len(s["at_risk_ops"]) == 1
        assert s["at_risk_ops"][0]["op_company"] == "OP_HIGH"

    def test_summary_handles_zero_headline_without_div_by_zero(self):
        records, xl = self._make_records_and_xl()
        s = _mod.summarize(xl, records, high_headline_usd=0.0, hm_headline_usd=0.0)
        # Should not crash
        assert s["high_tier_pct_of_headline"] == 0.0
        assert s["hm_pct_of_headline"] == 0.0
        assert s["at_risk_pct_of_high_headline"] == 0.0

    def test_cik_only_cross_link_does_not_count_as_at_risk(self):
        """Regression: at-risk is defined as person-based cross-links where
        the shared person could be the deciding match signal. A CIK-only
        cross-link can't make a shared person the deciding signal — there
        is no shared person. Verify CIK-only cross-links to person-only-
        confirmed high-tier ops do NOT contribute to at_risk_dollars_usd
        or at_risk_ops."""
        # PIF_CIK (low, pif) shares CIK "999" with OP_HIGH_CIK (high)
        # OP_HIGH_CIK is person-only confirmed (person=0.9, ZIP=0) — would
        # be at-risk if the cross-link were person-based. Since it's
        # CIK-based, it must NOT be counted as at-risk.
        records = [
            _record("PIF_CIK", "low", has_pif=True, has_non_pif=False, persons=["A"], ciks=["999"]),
            _record(
                "OP_HIGH_CIK",
                "high",
                has_pif=False,
                has_non_pif=True,
                persons=["B"],  # no person overlap with PIF_CIK
                ciks=["999"],  # shared CIK is the link signal
                raised=100_000_000.0,
                person_score=0.9,
                address_score=0.0,
                state_score=1.0,
            ),
        ]
        xl = _mod.find_cross_links(records)
        # Confirm we found one CIK-based cross-link
        assert len(xl) == 1
        assert xl[0]["link_type"] == "cik"

        s = _mod.summarize(
            xl, records, high_headline_usd=10_000_000_000.0, hm_headline_usd=15_000_000_000.0
        )
        # Op IS in the high-tier cross-link cohort dollar exposure
        assert s["high_tier_counted_dollars_at_cross_link_op_side"] == 100_000_000.0
        # But it must NOT contribute to at-risk (which is person-based only)
        assert s["at_risk_dollars_usd"] == 0.0
        assert s["at_risk_ops"] == []


class TestNormName:
    def test_uppercase(self):
        assert _mod._norm_name("Alice Smith") == "ALICE SMITH"

    def test_strip(self):
        assert _mod._norm_name("  Alice  ") == "ALICE"

    def test_none(self):
        assert _mod._norm_name(None) == ""

    def test_empty(self):
        assert _mod._norm_name("") == ""
