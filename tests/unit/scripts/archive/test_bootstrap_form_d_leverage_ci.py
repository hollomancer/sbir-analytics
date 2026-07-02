"""Unit tests for scripts/archive/data/bootstrap_form_d_leverage_ci.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


# Load the script as a module (it lives outside the package tree).
SCRIPT_PATH = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "archive"
    / "data"
    / "bootstrap_form_d_leverage_ci.py"
)
_spec = importlib.util.spec_from_file_location("bootstrap_form_d_leverage_ci", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_form_d_leverage_ci"] = _mod
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# _parse_amount: defensive Award Amount parsing
# ---------------------------------------------------------------------------


class TestParseAmount:
    """The codebase elsewhere strips ``$`` and commas from SBIR Award Amount
    strings (see sbir_etl/enrichers/award_history.py:52,
    sbir_etl/enrichers/inflation_adjuster.py:375). This script must do the
    same so it doesn't undercount on bulk-file format variations."""

    def test_plain_numeric(self):
        assert _mod._parse_amount("100000") == 100000.0
        assert _mod._parse_amount("100000.00") == 100000.0

    def test_with_dollar_sign(self):
        assert _mod._parse_amount("$100000") == 100000.0
        assert _mod._parse_amount("$1234567.89") == 1234567.89

    def test_with_commas(self):
        assert _mod._parse_amount("1,234,567") == 1234567.0
        assert _mod._parse_amount("100,000") == 100000.0

    def test_with_dollar_and_commas(self):
        assert _mod._parse_amount("$1,234,567") == 1234567.0
        assert _mod._parse_amount("$1,234,567.89") == 1234567.89

    def test_whitespace_stripped(self):
        assert _mod._parse_amount("  $1,000  ") == 1000.0
        assert _mod._parse_amount("\t100\n") == 100.0

    def test_returns_none_on_failure(self):
        assert _mod._parse_amount(None) is None
        assert _mod._parse_amount("") is None
        assert _mod._parse_amount("   ") is None
        assert _mod._parse_amount("not a number") is None
        assert _mod._parse_amount("abc") is None

    def test_zero_and_negative_pass_through(self):
        # Caller is responsible for filtering <= 0; parser just parses.
        assert _mod._parse_amount("0") == 0.0
        assert _mod._parse_amount("-100") == -100.0


# ---------------------------------------------------------------------------
# _norm_name: company-name normalization for the join
# ---------------------------------------------------------------------------


class TestNormName:
    def test_uppercases(self):
        assert _mod._norm_name("Acme Corp") == "ACME CORP"

    def test_strips_whitespace(self):
        assert _mod._norm_name("  Acme Corp  ") == "ACME CORP"

    def test_handles_none(self):
        assert _mod._norm_name(None) == ""

    def test_handles_empty(self):
        assert _mod._norm_name("") == ""


# ---------------------------------------------------------------------------
# bootstrap_two_views: ratio computation and CI bounds
# ---------------------------------------------------------------------------


class TestBootstrapTwoViews:
    """Bootstrap CIs against a synthetic cohort where the true ratio is known."""

    def _synthetic_cohort(self, n: int, mean_raised: float, mean_sbir: float, seed: int = 0):
        """Generate a synthetic firm cohort with known mean ratio."""
        rng = np.random.default_rng(seed)
        # Use lognormal-ish positive draws to mimic real cohort skew.
        raised = rng.gamma(shape=2.0, scale=mean_raised / 2.0, size=n)
        sbir = rng.gamma(shape=2.0, scale=mean_sbir / 2.0, size=n)
        return raised, sbir

    def test_program_level_point_estimate_matches_aggregate(self):
        """Point estimate must equal sum(raised) / program_denominator exactly."""
        raised = np.array([100.0, 200.0, 300.0])
        sbir = np.array([10.0, 20.0, 30.0])
        program = 1000.0
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(raised, sbir, program, n_iter=100, rng=rng)
        # 600 / 1000 = 0.6
        assert result["program_level"]["point_estimate"] == pytest.approx(0.6)

    def test_per_firm_point_estimate_matches_aggregate(self):
        """Per-firm point estimate must equal sum(raised) / sum(matched_sbir) exactly."""
        raised = np.array([100.0, 200.0, 300.0])
        sbir = np.array([10.0, 20.0, 30.0])
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(
            raised, sbir, program_denominator=1000.0, n_iter=100, rng=rng
        )
        # 600 / 60 = 10.0
        assert result["per_matched_firm"]["point_estimate"] == pytest.approx(10.0)

    def test_compute_per_firm_false_omits_per_firm(self):
        """The all-matched cohort path uses compute_per_firm=False to avoid
        the hybrid-number issue Copilot's docstring critique flagged."""
        raised = np.array([100.0, 200.0])
        sbir = np.array([10.0, 0.0])
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(
            raised, sbir, program_denominator=500.0, n_iter=100, rng=rng, compute_per_firm=False
        )
        assert "program_level" in result
        assert "per_matched_firm" not in result

    def test_ci_brackets_point_estimate(self):
        """For a non-degenerate cohort, the bootstrap CI should bracket the
        point estimate. This is a basic sanity check on the bootstrap loop."""
        raised, sbir = self._synthetic_cohort(n=200, mean_raised=1000.0, mean_sbir=100.0)
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(
            raised, sbir, program_denominator=10000.0, n_iter=1000, rng=rng
        )
        for key in ("program_level", "per_matched_firm"):
            r = result[key]
            assert r["ci_lo"] <= r["point_estimate"] <= r["ci_hi"], (
                f"{key} CI [{r['ci_lo']}, {r['ci_hi']}] does not bracket "
                f"point estimate {r['point_estimate']}"
            )

    def test_seed_determinism(self):
        """Same seed must produce identical bootstrap output (regression
        guard against accidental non-determinism in the resampling loop)."""
        raised, sbir = self._synthetic_cohort(n=100, mean_raised=500.0, mean_sbir=50.0, seed=7)
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        r1 = _mod.bootstrap_two_views(raised, sbir, 5000.0, n_iter=500, rng=rng1)
        r2 = _mod.bootstrap_two_views(raised, sbir, 5000.0, n_iter=500, rng=rng2)
        assert r1["program_level"]["ci_lo"] == r2["program_level"]["ci_lo"]
        assert r1["program_level"]["ci_hi"] == r2["program_level"]["ci_hi"]
        assert r1["per_matched_firm"]["ci_lo"] == r2["per_matched_firm"]["ci_lo"]
        assert r1["per_matched_firm"]["ci_hi"] == r2["per_matched_firm"]["ci_hi"]

    def test_empty_cohort(self):
        raised = np.array([], dtype=float)
        sbir = np.array([], dtype=float)
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(
            raised, sbir, program_denominator=100.0, n_iter=10, rng=rng
        )
        assert result["n_firms"] == 0
        assert result["program_level"]["point_estimate"] == 0.0
        assert result["per_matched_firm"]["point_estimate"] == 0.0

    def test_zero_program_denominator(self):
        raised = np.array([100.0])
        sbir = np.array([10.0])
        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(raised, sbir, program_denominator=0.0, n_iter=10, rng=rng)
        # Program ratio is undefined; should not crash and should produce 0.
        assert result["program_level"]["point_estimate"] == 0.0


# ---------------------------------------------------------------------------
# cohort_arrays: tier and require_sbir filtering
# ---------------------------------------------------------------------------


class TestCohortArrays:
    def _make_cohort(self):
        return [
            {
                "name": "A",
                "tier": "high",
                "raised": 100.0,
                "award_total": 10.0,
                "has_sbir_in_window": True,
            },
            {
                "name": "B",
                "tier": "high",
                "raised": 200.0,
                "award_total": 0.0,
                "has_sbir_in_window": False,
            },
            {
                "name": "C",
                "tier": "medium",
                "raised": 300.0,
                "award_total": 30.0,
                "has_sbir_in_window": True,
            },
            {
                "name": "D",
                "tier": "low",
                "raised": 400.0,
                "award_total": 40.0,
                "has_sbir_in_window": True,
            },
        ]

    def test_tier_filter_high_only(self):
        raised, sbir = _mod.cohort_arrays(self._make_cohort(), {"high"}, require_sbir=False)
        # A and B are high. raised = [100, 200], sbir = [10, 0]
        assert sorted(raised.tolist()) == [100.0, 200.0]
        assert sorted(sbir.tolist()) == [0.0, 10.0]

    def test_tier_filter_high_plus_medium(self):
        raised, sbir = _mod.cohort_arrays(
            self._make_cohort(), {"high", "medium"}, require_sbir=False
        )
        # A, B, C. raised = [100, 200, 300]
        assert sorted(raised.tolist()) == [100.0, 200.0, 300.0]

    def test_require_sbir_excludes_zero_sbir(self):
        """When require_sbir=True, firms without in-window SBIR (B) are dropped."""
        raised, sbir = _mod.cohort_arrays(self._make_cohort(), {"high"}, require_sbir=True)
        # Only A remains in the high cohort with SBIR in window
        assert raised.tolist() == [100.0]
        assert sbir.tolist() == [10.0]

    def test_low_tier_excluded_by_default_filter(self):
        """The default filters {high} and {high, medium} both exclude low tier."""
        raised, _ = _mod.cohort_arrays(self._make_cohort(), {"high"}, require_sbir=False)
        # D (low) must be absent
        assert 400.0 not in raised.tolist()


# ---------------------------------------------------------------------------
# End-to-end: small synthetic cohort, deterministic ratio reproduction
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_synthetic_cohort_reproduces_known_ratios(self):
        """Construct a tiny cohort with known sums; verify the script's
        bootstrap_two_views reproduces the expected ratios exactly at the
        point estimate level and within CI at the bootstrap level."""
        # 5 firms in the cohort. Total raised = $5M, total SBIR = $1M.
        # Per-firm ratio: 5.0x. Program-level ratio against $10M total: 0.5x.
        raised = np.array([1_000_000.0, 500_000.0, 2_000_000.0, 1_500_000.0, 0.0])
        sbir = np.array([100_000.0, 200_000.0, 300_000.0, 400_000.0, 0.0])
        assert raised.sum() == 5_000_000.0
        assert sbir.sum() == 1_000_000.0

        rng = np.random.default_rng(42)
        result = _mod.bootstrap_two_views(
            raised, sbir, program_denominator=10_000_000.0, n_iter=500, rng=rng
        )

        assert result["per_matched_firm"]["point_estimate"] == pytest.approx(5.0)
        assert result["program_level"]["point_estimate"] == pytest.approx(0.5)
        # CIs should bracket the points
        assert result["per_matched_firm"]["ci_lo"] <= 5.0 <= result["per_matched_firm"]["ci_hi"]
        assert result["program_level"]["ci_lo"] <= 0.5 <= result["program_level"]["ci_hi"]
