"""Unit tests for scripts/data/dod_fpds_substitution_test.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "data" / "dod_fpds_substitution_test.py"
)
_spec = importlib.util.spec_from_file_location("dod_fpds_substitution_test", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dod_fpds_substitution_test"] = _mod
_spec.loader.exec_module(_mod)


class TestParseAmount:
    def test_dollar_and_comma(self):
        assert _mod._parse_amount("$1,234,567") == 1234567.0

    def test_none(self):
        assert _mod._parse_amount(None) is None
        assert _mod._parse_amount("") is None


class TestNormName:
    def test_uppercase_strip(self):
        assert _mod._norm_name("  Acme Corp  ") == "ACME CORP"

    def test_none(self):
        assert _mod._norm_name(None) == ""


class TestLoadDoDCohort:
    @pytest.fixture
    def fixture_paths(self, tmp_path):
        # SBIR CSV: 3 DoD firms, one with multiple branches (AF dominant);
        # 1 non-DoD firm; 1 out-of-window row
        sbir_csv = tmp_path / "sbir.csv"
        sbir_csv.write_text(
            "Company,Award Year,Award Amount,Agency,Branch\n"
            "AcmeAF,2020,500000,Department of Defense,Air Force\n"
            "AcmeAF,2021,500000,Department of Defense,Navy\n"
            "BetaNavy,2020,800000,Department of Defense,Navy\n"
            "CharlieHHS,2020,1000000,Department of Health and Human Services,\n"
            "AcmeAF,2005,999999,Department of Defense,Air Force\n"
        )
        # Form D JSONL: high tier for AcmeAF + BetaNavy + CharlieHHS;
        # CharlieHHS is excluded by the DoD inner join.
        form_d = tmp_path / "form_d.jsonl"
        records = [
            {
                "company_name": "AcmeAF",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {"industry_group": "Other Technology", "filing_date": "2020-05-01", "total_amount_sold": 1_000_000.0},
                ],
            },
            {
                "company_name": "BetaNavy",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {"industry_group": "Other Technology", "filing_date": "2021-05-01", "total_amount_sold": 500_000.0},
                ],
            },
            {
                "company_name": "CharlieHHS",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {"industry_group": "Other Technology", "filing_date": "2020-05-01", "total_amount_sold": 9_999_999.0},
                ],
            },
            # Medium-tier — must be excluded
            {
                "company_name": "MediumFirm",
                "match_confidence": {"tier": "medium"},
                "offerings": [
                    {"industry_group": "Other Technology", "filing_date": "2020-05-01", "total_amount_sold": 5_000.0},
                ],
            },
        ]
        with open(form_d, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return form_d, sbir_csv

    def test_returns_only_dod_high_tier_inner_join(self, fixture_paths):
        form_d, sbir = fixture_paths
        cohort = _mod.load_dod_cohort(form_d, sbir, 2009, 2024)
        # AcmeAF (DoD, high) and BetaNavy (DoD, high) are in cohort
        # CharlieHHS (HHS only) and MediumFirm (medium tier) are excluded
        assert set(cohort.keys()) == {"ACMEAF", "BETANAVY"}

    def test_dominant_branch_attribution(self, fixture_paths):
        form_d, sbir = fixture_paths
        cohort = _mod.load_dod_cohort(form_d, sbir, 2009, 2024)
        # AcmeAF: AF 500K + Navy 500K → tied; max() picks one deterministically
        # (Python's max on dict.items uses insertion order for ties — AF inserted first)
        assert cohort["ACMEAF"]["dominant_dod_branch"] in {"Air Force", "Navy"}
        # BetaNavy: Navy 800K only → Navy
        assert cohort["BETANAVY"]["dominant_dod_branch"] == "Navy"

    def test_out_of_window_excluded(self, fixture_paths):
        form_d, sbir = fixture_paths
        cohort = _mod.load_dod_cohort(form_d, sbir, 2009, 2024)
        # AcmeAF total should be 1M (500K + 500K), not 1M + 999999 from 2005
        assert cohort["ACMEAF"]["sbir_dod_total"] == 1_000_000.0

    def test_form_d_raised_aggregated_correctly(self, fixture_paths):
        form_d, sbir = fixture_paths
        cohort = _mod.load_dod_cohort(form_d, sbir, 2009, 2024)
        assert cohort["ACMEAF"]["form_d_raised"] == 1_000_000.0
        assert cohort["BETANAVY"]["form_d_raised"] == 500_000.0


class TestQueryUsaspendingForFirm:
    """Mock the httpx Client to verify request shape + response handling
    without hitting the live API."""

    def _build_mock_client(self, responses):
        """responses is a list of dicts that will be returned in order."""
        from unittest.mock import MagicMock
        client = MagicMock()
        post_results = []
        for body in responses:
            resp = MagicMock()
            resp.status_code = body.get("_status_code", 200)
            resp.json.return_value = body
            post_results.append(resp)
        client.post.side_effect = post_results
        return client

    def test_single_page_aggregates_total(self):
        responses = [
            {
                "results": [
                    {"Recipient Name": "ACME INC", "Award Amount": 100_000.0, "Awarding Sub Agency": "Army"},
                    {"Recipient Name": "ACME INC", "Award Amount": 50_000.0, "Awarding Sub Agency": "Air Force"},
                ],
                "page_metadata": {"hasNext": False},
            }
        ]
        client = self._build_mock_client(responses)
        result = _mod.query_usaspending_for_firm(client, "Acme Inc", 2009, 2024, sleep_between=0.0)
        assert result["error"] is None
        assert result["total_contract_usd"] == 150_000.0
        assert result["n_awards"] == 2

    def test_recipient_name_tightening_excludes_fuzzy_matches(self):
        """recipient_search_text is fuzzy; the function tightens to
        EXACT uppercased recipient-name equality to control false positives."""
        responses = [
            {
                "results": [
                    {"Recipient Name": "ACME INC", "Award Amount": 100_000.0, "Awarding Sub Agency": "Army"},
                    {"Recipient Name": "ACME RESEARCH LLC", "Award Amount": 999_999.0, "Awarding Sub Agency": "Army"},  # different firm
                ],
                "page_metadata": {"hasNext": False},
            }
        ]
        client = self._build_mock_client(responses)
        result = _mod.query_usaspending_for_firm(client, "Acme Inc", 2009, 2024, sleep_between=0.0)
        # Only the exact-match Acme Inc result should count
        assert result["total_contract_usd"] == 100_000.0
        assert result["n_awards"] == 1

    def test_pagination_walks_to_last_page(self):
        responses = [
            {
                "results": [{"Recipient Name": "ACME INC", "Award Amount": 100.0, "Awarding Sub Agency": "Army"}],
                "page_metadata": {"hasNext": True},
            },
            {
                "results": [{"Recipient Name": "ACME INC", "Award Amount": 200.0, "Awarding Sub Agency": "Navy"}],
                "page_metadata": {"hasNext": True},
            },
            {
                "results": [{"Recipient Name": "ACME INC", "Award Amount": 50.0, "Awarding Sub Agency": "Air Force"}],
                "page_metadata": {"hasNext": False},
            },
        ]
        client = self._build_mock_client(responses)
        result = _mod.query_usaspending_for_firm(client, "Acme Inc", 2009, 2024, sleep_between=0.0)
        assert result["total_contract_usd"] == 350.0
        assert result["n_awards"] == 3
        assert result["n_pages_fetched"] == 3
        # Three sub-agencies seen across pages
        assert set(result["sub_agencies"].keys()) == {"Army", "Navy", "Air Force"}

    def test_non_200_response_returns_error(self):
        responses = [{"_status_code": 503, "results": [], "page_metadata": {"hasNext": False}}]
        client = self._build_mock_client(responses)
        result = _mod.query_usaspending_for_firm(client, "Acme Inc", 2009, 2024, sleep_between=0.0)
        assert result["error"] is not None
        assert "503" in result["error"]
        assert result["total_contract_usd"] == 0.0

    def test_http_error_returns_partial_total(self):
        """If a later page errors after some pages succeeded, the partial
        total from earlier pages should still be returned (with error noted)."""
        from unittest.mock import MagicMock
        import httpx

        client = MagicMock()
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "results": [{"Recipient Name": "ACME INC", "Award Amount": 100.0, "Awarding Sub Agency": "Army"}],
            "page_metadata": {"hasNext": True},
        }
        client.post.side_effect = [ok_resp, httpx.HTTPError("network")]
        result = _mod.query_usaspending_for_firm(client, "Acme Inc", 2009, 2024, sleep_between=0.0)
        assert result["total_contract_usd"] == 100.0  # page 1 captured
        assert result["error"] is not None


class TestComputePerBranchSubstitution:
    def test_per_branch_aggregation(self):
        cohort = {
            "AF1": {"dominant_dod_branch": "Air Force", "sbir_dod_total": 1_000_000.0, "form_d_raised": 5_000_000.0, "original_name": "AF1"},
            "AF2": {"dominant_dod_branch": "Air Force", "sbir_dod_total": 500_000.0, "form_d_raised": 2_000_000.0, "original_name": "AF2"},
            "NAVY1": {"dominant_dod_branch": "Navy", "sbir_dod_total": 1_000_000.0, "form_d_raised": 500_000.0, "original_name": "NAVY1"},
        }
        contracts = {
            "AF1": {"total_contract_usd": 100_000.0},  # low FPDS
            "AF2": {"total_contract_usd": 200_000.0},
            "NAVY1": {"total_contract_usd": 10_000_000.0},  # high FPDS (substitution signal!)
        }
        program = {"Air Force": 10_000_000.0, "Navy": 5_000_000.0}
        out = _mod.compute_per_branch_substitution(cohort, contracts, program, min_program_usd=0)
        by_branch = {r["branch"]: r for r in out}

        # Air Force: FPDS 300K / program 10M = 0.03; FD 7M / 10M = 0.70
        assert by_branch["Air Force"]["fpds_program_ratio"] == pytest.approx(0.03)
        assert by_branch["Air Force"]["form_d_program_ratio"] == pytest.approx(0.70)
        # Navy: FPDS 10M / 5M = 2.0; FD 500K / 5M = 0.1
        assert by_branch["Navy"]["fpds_program_ratio"] == pytest.approx(2.0)
        assert by_branch["Navy"]["form_d_program_ratio"] == pytest.approx(0.1)
        # Substitution signal: Navy (2.0 - 0.1) / 0.1 = 19.0 — strong positive
        assert by_branch["Navy"]["substitution_signal_pct"] == pytest.approx(19.0)
        # Air Force (0.03 - 0.7) / 0.7 = -0.957 — strong negative
        assert by_branch["Air Force"]["substitution_signal_pct"] == pytest.approx(-0.957, abs=0.001)

    def test_missing_contracts_treated_as_zero(self):
        """A firm in the cohort with no entry in the contracts dict
        contributes 0 to FPDS but still counts in firm/Form-D/SBIR totals."""
        cohort = {
            "FIRM1": {"dominant_dod_branch": "Navy", "sbir_dod_total": 1_000_000.0, "form_d_raised": 500_000.0, "original_name": "FIRM1"},
            "FIRM2": {"dominant_dod_branch": "Navy", "sbir_dod_total": 500_000.0, "form_d_raised": 200_000.0, "original_name": "FIRM2"},
        }
        contracts = {"FIRM1": {"total_contract_usd": 5_000_000.0}}  # FIRM2 missing
        program = {"Navy": 5_000_000.0}
        out = _mod.compute_per_branch_substitution(cohort, contracts, program, min_program_usd=0)
        navy = next(r for r in out if r["branch"] == "Navy")
        assert navy["n_matched_firms"] == 2
        assert navy["fpds_total_usd"] == 5_000_000.0
        assert navy["form_d_total_usd"] == 700_000.0  # both firms count

    def test_excludes_branches_below_min_program(self):
        cohort = {"X": {"dominant_dod_branch": "TinyBranch", "sbir_dod_total": 1.0, "form_d_raised": 1.0, "original_name": "X"}}
        contracts = {"X": {"total_contract_usd": 1.0}}
        program = {"TinyBranch": 50_000.0}  # below 100M default
        out = _mod.compute_per_branch_substitution(cohort, contracts, program, min_program_usd=100_000.0)
        assert out == []

    def test_substitution_signal_none_when_form_d_zero(self):
        cohort = {"X": {"dominant_dod_branch": "Navy", "sbir_dod_total": 1.0, "form_d_raised": 0.0, "original_name": "X"}}
        contracts = {"X": {"total_contract_usd": 100.0}}
        program = {"Navy": 1.0}
        out = _mod.compute_per_branch_substitution(cohort, contracts, program, min_program_usd=0)
        # Form D total is zero → substitution signal is undefined (None), not div-by-zero
        navy = next(r for r in out if r["branch"] == "Navy")
        assert navy["substitution_signal_pct"] is None
