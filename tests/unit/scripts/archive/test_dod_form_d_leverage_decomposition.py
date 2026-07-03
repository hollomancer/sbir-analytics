"""Unit tests for scripts/archive/data/dod_form_d_leverage_decomposition.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "archive"
    / "data"
    / "dod_form_d_leverage_decomposition.py"
)
_spec = importlib.util.spec_from_file_location("dod_form_d_leverage_decomposition", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dod_form_d_leverage_decomposition"] = _mod
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# _parse_amount and _norm_name (same defensive parsing as the bootstrap script)
# ---------------------------------------------------------------------------


class TestParseAmount:
    def test_plain(self):
        assert _mod._parse_amount("100000") == 100000.0

    def test_with_dollar_and_commas(self):
        assert _mod._parse_amount("$1,234,567") == 1234567.0

    def test_handles_none(self):
        assert _mod._parse_amount(None) is None
        assert _mod._parse_amount("") is None


class TestNormName:
    def test_uppercase_strip(self):
        assert _mod._norm_name("  Acme Corp  ") == "ACME CORP"

    def test_none(self):
        assert _mod._norm_name(None) == ""


# ---------------------------------------------------------------------------
# bootstrap_program_ratio: fixed-denominator firm-level bootstrap
# ---------------------------------------------------------------------------


class TestBootstrapProgramRatio:
    def test_point_estimate_matches_aggregate(self):
        raised = np.array([100.0, 200.0, 300.0])
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_program_ratio(
            raised, program_denominator=1000.0, n_iter=100, rng=rng
        )
        # 600/1000 = 0.6
        assert result["point_estimate"] == pytest.approx(0.6)
        assert result["n_firms"] == 3

    def test_ci_brackets_point_estimate(self):
        rng_data = np.random.default_rng(7)
        raised = rng_data.gamma(2.0, 50.0, size=200)
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_program_ratio(
            raised, program_denominator=10000.0, n_iter=1000, rng=rng
        )
        assert result["ci_lo"] <= result["point_estimate"] <= result["ci_hi"]

    def test_empty_cohort_returns_zero(self):
        raised = np.array([], dtype=float)
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_program_ratio(
            raised, program_denominator=1000.0, n_iter=10, rng=rng
        )
        assert result["point_estimate"] == 0.0
        assert result["n_firms"] == 0

    def test_zero_denominator(self):
        raised = np.array([100.0])
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_program_ratio(raised, program_denominator=0.0, n_iter=10, rng=rng)
        assert result["point_estimate"] == 0.0  # not crash, not inf

    def test_seed_determinism(self):
        raised = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        r1 = _mod.bootstrap_program_ratio(raised, 1000.0, 500, np.random.default_rng(42))
        r2 = _mod.bootstrap_program_ratio(raised, 1000.0, 500, np.random.default_rng(42))
        assert r1["ci_lo"] == r2["ci_lo"]
        assert r1["ci_hi"] == r2["ci_hi"]


# ---------------------------------------------------------------------------
# load_sbir_firm_index: per-firm SBIR aggregates with branch handling
# ---------------------------------------------------------------------------


class TestLoadSbirFirmIndex:
    @pytest.fixture
    def csv_path(self, tmp_path):
        # 3 firms with DoD activity, 1 with HHS only
        rows = [
            # Acme: DoD-only, two branches (Air Force dominant)
            "Company,Award Year,Award Amount,Agency,Branch\n",
            "Acme,2020,500000,Department of Defense,Air Force\n",
            "Acme,2021,300000,Department of Defense,Navy\n",
            # Beta: multi-agency, DoD dominant
            "Beta,2020,400000,Department of Defense,Army\n",
            "Beta,2021,100000,National Science Foundation,\n",
            # Gamma: multi-agency, HHS dominant (DoD secondary)
            "Gamma,2020,200000,Department of Defense,Air Force\n",
            "Gamma,2021,1000000,Department of Health and Human Services,\n",
            # Delta: HHS only (no DoD activity at all)
            "Delta,2020,500000,Department of Health and Human Services,\n",
            # Out-of-window row (should be excluded)
            "Acme,2005,999999,Department of Defense,Air Force\n",
        ]
        p = tmp_path / "awards.csv"
        p.write_text("".join(rows))
        return p

    def test_firm_aggregates(self, csv_path):
        firms, by_agency, by_branch = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # Out-of-window row excluded → Acme total is 800K, not 800K+999999
        assert firms["ACME"]["total"] == 800000.0
        assert firms["ACME"]["n_awards"] == 2

    def test_dominant_branch_attribution(self, csv_path):
        firms, _, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # Acme: Air Force 500K, Navy 300K → Air Force dominant
        assert firms["ACME"]["dominant_dod_branch"] == "Air Force"

    def test_dod_only_vs_multi_agency_classification(self, csv_path):
        firms, _, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        assert firms["ACME"]["is_dod_only"] is True
        assert firms["ACME"]["has_any_dod"] is True
        assert firms["BETA"]["is_dod_only"] is False
        assert firms["BETA"]["has_any_dod"] is True
        assert firms["GAMMA"]["is_dod_only"] is False
        assert firms["GAMMA"]["has_any_dod"] is True
        assert firms["DELTA"]["has_any_dod"] is False

    def test_program_totals_by_agency_and_branch(self, csv_path):
        _, by_agency, by_branch = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # DoD total: 500+300+400+200 = 1,400,000
        assert by_agency["Department of Defense"] == 1_400_000.0
        # HHS total: 1,000,000 + 500,000 = 1,500,000
        assert by_agency["Department of Health and Human Services"] == 1_500_000.0
        # Air Force = Acme(500K) + Gamma(200K) = 700K; Navy = Acme(300K); Army = Beta(400K)
        assert by_branch["Air Force"] == 700_000.0
        assert by_branch["Navy"] == 300_000.0
        assert by_branch["Army"] == 400_000.0

    def test_excludes_out_of_window_year(self, csv_path):
        _, by_agency, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # The 2005 row's 999999 should not contribute
        # DoD = 500+300+400+200 = 1.4M, not 1.4M + 999999
        assert by_agency["Department of Defense"] == 1_400_000.0


# ---------------------------------------------------------------------------
# load_form_d_per_firm: tier and industry filtering
# ---------------------------------------------------------------------------


class TestLoadFormDPerFirm:
    @pytest.fixture
    def jsonl_path(self, tmp_path):
        import json

        records = [
            # High tier, normal industry, in window → counted
            {
                "company_name": "High Co",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {
                        "industry_group": "Other Technology",
                        "filing_date": "2020-05-01",
                        "total_amount_sold": 1_000_000.0,
                    },
                ],
            },
            # High tier, PIF industry → excluded
            {
                "company_name": "PIF Co",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {
                        "industry_group": "Pooled Investment Fund",
                        "filing_date": "2020-05-01",
                        "total_amount_sold": 5_000_000.0,
                    },
                ],
            },
            # Low tier → filtered out by tier_filter
            {
                "company_name": "Low Co",
                "match_confidence": {"tier": "low"},
                "offerings": [
                    {
                        "industry_group": "Other Technology",
                        "filing_date": "2020-05-01",
                        "total_amount_sold": 999_999.0,
                    },
                ],
            },
            # High tier, out-of-window filing → excluded
            {
                "company_name": "Old Co",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {
                        "industry_group": "Other Technology",
                        "filing_date": "2005-05-01",
                        "total_amount_sold": 1_000.0,
                    },
                ],
            },
        ]
        p = tmp_path / "form_d.jsonl"
        with open(p, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return p

    def test_tier_filter(self, jsonl_path):
        out = _mod.load_form_d_per_firm(jsonl_path, 2009, 2024, {"high"})
        # Only "High Co" and "PIF Co" and "Old Co" are high; Low Co excluded by tier filter
        assert "LOW CO" not in out

    def test_industry_filter_excludes_pif(self, jsonl_path):
        out = _mod.load_form_d_per_firm(jsonl_path, 2009, 2024, {"high"})
        # PIF Co is high-tier but its only offering is PIF-tagged → raised counted = 0
        assert out["PIF CO"] == 0.0

    def test_year_window(self, jsonl_path):
        out = _mod.load_form_d_per_firm(jsonl_path, 2009, 2024, {"high"})
        # Old Co's 2005 offering should be excluded → 0
        assert out["OLD CO"] == 0.0
        # High Co's 2020 offering should count → 1M
        assert out["HIGH CO"] == 1_000_000.0


# ---------------------------------------------------------------------------
# Decomposition functions
# ---------------------------------------------------------------------------


class TestDecomposition1BranchRatios:
    def _make_firms(self):
        # Two Air Force firms, one Navy firm
        return {
            "AF_1": {
                "dominant_dod_branch": "Air Force",
                "has_any_dod": True,
                "is_dod_only": True,
                "dod_dollars": 1.0,
                "non_dod_dollars": 0.0,
            },
            "AF_2": {
                "dominant_dod_branch": "Air Force",
                "has_any_dod": True,
                "is_dod_only": True,
                "dod_dollars": 1.0,
                "non_dod_dollars": 0.0,
            },
            "NAVY_1": {
                "dominant_dod_branch": "Navy",
                "has_any_dod": True,
                "is_dod_only": True,
                "dod_dollars": 1.0,
                "non_dod_dollars": 0.0,
            },
            # Non-DoD firm — should not appear in any branch decomposition
            "HHS_1": {
                "dominant_dod_branch": None,
                "has_any_dod": False,
                "is_dod_only": False,
                "dod_dollars": 0.0,
                "non_dod_dollars": 100.0,
            },
        }

    def test_attributes_by_dominant_branch(self):
        firms = self._make_firms()
        # AF_1 raised 200, AF_2 raised 300, NAVY_1 raised 50, HHS_1 raised 500 (should be ignored)
        fd = {"AF_1": 200.0, "AF_2": 300.0, "NAVY_1": 50.0, "HHS_1": 500.0}
        program = {"Air Force": 1000.0, "Navy": 500.0}
        rng = np.random.default_rng(42)
        out = _mod.decomposition_1_branch_ratios(
            firms, fd, program, n_iter=100, rng=rng, min_program_usd=0
        )
        by_branch = {r["branch"]: r for r in out}
        # Air Force: 500/1000 = 0.5
        assert by_branch["Air Force"]["point_estimate"] == pytest.approx(0.5)
        # Navy: 50/500 = 0.1
        assert by_branch["Navy"]["point_estimate"] == pytest.approx(0.1)
        # HHS_1 should not contribute to either DoD branch
        assert by_branch["Air Force"]["n_matched_firms"] == 2
        assert by_branch["Navy"]["n_matched_firms"] == 1

    def test_min_program_usd_filter(self):
        firms = self._make_firms()
        fd = {"AF_1": 200.0, "NAVY_1": 50.0}
        program = {"Air Force": 1000.0, "Navy": 500.0}
        rng = np.random.default_rng(42)
        # Filter out branches with < 600 program $ → only Air Force passes
        out = _mod.decomposition_1_branch_ratios(
            firms, fd, program, n_iter=100, rng=rng, min_program_usd=600
        )
        assert len(out) == 1
        assert out[0]["branch"] == "Air Force"


class TestDecomposition2ParticipationRates:
    def test_participation_rate(self):
        firms = {
            "A": {"has_any_dod": True, "dominant_dod_branch": "Air Force"},
            "B": {"has_any_dod": True, "dominant_dod_branch": "Air Force"},
            "C": {"has_any_dod": True, "dominant_dod_branch": "Air Force"},
            "D": {"has_any_dod": True, "dominant_dod_branch": "Navy"},
        }
        # 2 of 3 Air Force firms have Form D, 0 of 1 Navy
        fd = {"A": 100.0, "B": 200.0}
        program = {"Air Force": 1000.0, "Navy": 500.0}
        out = _mod.decomposition_2_participation_rates(firms, fd, program, min_program_usd=0)
        by_branch = {r["branch"]: r for r in out}
        assert by_branch["Air Force"]["participation_rate"] == pytest.approx(2 / 3)
        assert by_branch["Air Force"]["n_with_high_form_d"] == 2
        assert by_branch["Air Force"]["n_dod_firms"] == 3
        assert by_branch["Navy"]["participation_rate"] == 0.0
        assert by_branch["Navy"]["n_with_high_form_d"] == 0


class TestDecomposition3MaOverlap:
    def test_ma_and_fd_rates(self):
        firms = {
            "A": {"has_any_dod": True, "dominant_dod_branch": "Air Force"},
            "B": {"has_any_dod": True, "dominant_dod_branch": "Air Force"},
        }
        fd = {"A": 100.0}  # 1 of 2 in Form D
        ma = {"B": ["2020-01-01"]}  # 1 of 2 in M&A (different firm)
        program = {"Air Force": 1000.0}
        out = _mod.decomposition_3_ma_overlap(firms, ma, program, fd, min_program_usd=0)
        assert len(out) == 1
        r = out[0]
        assert r["form_d_rate"] == pytest.approx(0.5)
        assert r["ma_event_rate"] == pytest.approx(0.5)
        assert r["n_with_ma_event"] == 1
        assert r["n_with_high_form_d"] == 1


class TestDecomposition4SingleVsMulti:
    def test_correctly_splits_cohorts(self):
        firms = {
            "DOD_ONLY_1": {
                "has_any_dod": True,
                "is_dod_only": True,
                "dominant_dod_branch": "Air Force",
                "dod_dollars": 100.0,
            },
            "MULTI_1": {
                "has_any_dod": True,
                "is_dod_only": False,
                "dominant_dod_branch": "Air Force",
                "dod_dollars": 50.0,
            },
            "NON_DOD": {
                "has_any_dod": False,
                "is_dod_only": False,
                "dominant_dod_branch": None,
                "dod_dollars": 0.0,
            },
        }
        fd = {"DOD_ONLY_1": 200.0, "MULTI_1": 100.0, "NON_DOD": 9999.0}
        rng = np.random.default_rng(42)
        out = _mod.decomposition_4_single_vs_multi_agency(
            firms, fd, program_total_dod=1000.0, n_iter=100, rng=rng
        )
        # DoD-only: 1 firm, raised 200 → ratio = 0.2
        assert out["dod_only"]["n_firms"] == 1
        assert out["dod_only"]["point_estimate"] == pytest.approx(0.2)
        # Multi: 1 firm, raised 100 → ratio = 0.1
        assert out["multi_agency_with_dod"]["n_firms"] == 1
        assert out["multi_agency_with_dod"]["point_estimate"] == pytest.approx(0.1)
        # Non-DoD firms must NOT contribute
        assert out["dod_only"]["raised_total_usd"] == 200.0
        assert out["multi_agency_with_dod"]["raised_total_usd"] == 100.0


# ---------------------------------------------------------------------------
# load_ma_events: M&A data ingestion
# ---------------------------------------------------------------------------


class TestLoadMaEvents:
    @pytest.fixture
    def jsonl_path(self, tmp_path):
        import json

        records = [
            {"company_name": "Acme Inc", "event_date": "2020-01-01"},
            {"company_name": "Acme Inc", "event_date": "2021-03-15"},  # multiple events per firm
            {"company_name": "Beta Co", "event_date": "2019-06-01"},
            {"company_name": "", "event_date": "2020-01-01"},  # empty name should be skipped
            {"company_name": "Gamma LLC", "event_date": None},  # null date should be skipped
        ]
        p = tmp_path / "ma.jsonl"
        with open(p, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return p

    def test_aggregates_events_by_firm(self, jsonl_path):
        out = _mod.load_ma_events(jsonl_path)
        assert "ACME INC" in out
        assert len(out["ACME INC"]) == 2  # two events for Acme
        assert "BETA CO" in out
        assert len(out["BETA CO"]) == 1
        # Empty company name and null date should both be excluded
        assert "" not in out
        assert "GAMMA LLC" not in out

    def test_handles_invalid_json_lines(self, tmp_path):
        p = tmp_path / "broken.jsonl"
        p.write_text(
            '{"company_name":"A","event_date":"2020-01-01"}\nnot json\n{"company_name":"B","event_date":"2021-01-01"}\n'
        )
        out = _mod.load_ma_events(p)
        assert "A" in out
        assert "B" in out
