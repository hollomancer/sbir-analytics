"""Unit tests for scripts/data/dod_form_d_followups.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "data" / "dod_form_d_followups.py"
_spec = importlib.util.spec_from_file_location("dod_form_d_followups", SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dod_form_d_followups"] = _mod
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# classify_acquirer: the new function compared to other scripts
# ---------------------------------------------------------------------------


class TestClassifyAcquirer:
    """Classification heuristic for M&A acquirers — the function whose
    accuracy directly determines whether PR #342's "Navy commercializes
    via defense-prime acquisition" hypothesis is confirmed or refuted."""

    @pytest.mark.parametrize(
        "name",
        [
            "LOCKHEED MARTIN CORP",
            "Northrop Grumman Corporation",
            "RAYTHEON TECHNOLOGIES CORP",
            "L3 TECHNOLOGIES, INC.",
            "L3Harris Technologies, Inc.",
            "KRATOS DEFENSE & SECURITY SOLUTIONS, INC.",
            "Mercury Systems Inc.",
            "TELEDYNE TECHNOLOGIES INC",
            "Leidos Holdings, Inc.",
            "CACI INTERNATIONAL INC /DE/",
            "KBR, INC.",  # was previously misclassified due to "KBR " trailing space
            "Booz Allen Hamilton",
            "BAE Systems plc",
            "Boeing Company",
            "Huntington Ingalls Industries",
        ],
    )
    def test_classifies_known_defense_primes(self, name):
        assert _mod.classify_acquirer(name) == "defense_prime"

    @pytest.mark.parametrize(
        "name",
        [
            "Golub Capital BDC 3, Inc.",
            "Hercules Capital, Inc.",
            "Horizon Technology Finance Corp",
            "Churchill Capital Corp X/Cayman",
            "HCM II Acquisition Corp.",
            "Shell Midstream Partners, L.P.",
            "PennantPark Floating Rate Capital Ltd.",
        ],
    )
    def test_classifies_known_financial_sponsors(self, name):
        assert _mod.classify_acquirer(name) == "financial_sponsor"

    @pytest.mark.parametrize(
        "name",
        [
            "Arrayit Corp",
            "Riot Blockchain, Inc.",
            "Continental Cement Company, L.L.C.",
            "META MATERIALS INC.",
            "BRUKER CORP",
            "Redwire Corp",
            "WiderThan Co., Ltd.",
            "Wayside Technology Group, Inc.",
            "Ortho Clinical Diagnostics Holdings plc",  # WAS misclassified as financial in v1
            "Alarm.com Holdings, Inc.",  # WAS misclassified as financial in v1
            "SUPERIOR CONSULTANT HOLDINGS CORP",  # WAS misclassified as financial in v1
        ],
    )
    def test_classifies_commercial(self, name):
        """These are real commercial operating companies; some have
        'Holdings' in their name which the v1 classifier wrongly
        caught as financial_sponsor."""
        assert _mod.classify_acquirer(name) == "commercial"

    def test_none_returns_unknown(self):
        assert _mod.classify_acquirer(None) == "unknown"
        assert _mod.classify_acquirer("") == "unknown"

    def test_kbr_word_boundary(self):
        """KBR must match in real-world variants but not in spurious
        substrings."""
        assert _mod.classify_acquirer("KBR Inc.") == "defense_prime"
        assert _mod.classify_acquirer("KBR, INC.") == "defense_prime"
        assert _mod.classify_acquirer("KBR-Wyle") == "defense_prime"
        # No false-positive on substrings that happen to contain "KBR"
        assert _mod.classify_acquirer("SOMEKBRCO") != "defense_prime"


# ---------------------------------------------------------------------------
# load_sbir_firm_index — DoD-specific aggregation
# ---------------------------------------------------------------------------


class TestLoadSbirFirmIndex:
    @pytest.fixture
    def csv_path(self, tmp_path):
        rows = [
            "Company,Award Year,Award Amount,Agency,Branch\n",
            # AcmeAF: Air Force-dominant, $1M
            "AcmeAF,2020,500000,Department of Defense,Air Force\n",
            "AcmeAF,2021,500000,Department of Defense,Air Force\n",
            # MultiAF: Multi-agency, AF dominant by $
            "MultiAF,2020,500000,Department of Defense,Air Force\n",
            "MultiAF,2021,200000,National Science Foundation,\n",
            # NonDoD: HHS only
            "NonDoD,2020,1000000,Department of Health and Human Services,\n",
            # Out-of-window (excluded)
            "AcmeAF,2005,999999,Department of Defense,Air Force\n",
        ]
        p = tmp_path / "awards.csv"
        p.write_text("".join(rows))
        return p

    def test_dod_dollars_excludes_non_dod(self, csv_path):
        firms, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # MultiAF: 500K DoD + 200K NSF → total 700K, dod_dollars 500K
        assert firms["MULTIAF"]["total"] == 700000.0
        assert firms["MULTIAF"]["dod_dollars"] == 500000.0

    def test_non_dod_firm_has_no_branch(self, csv_path):
        firms, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        assert firms["NONDOD"]["dominant_dod_branch"] is None
        assert firms["NONDOD"]["dod_dollars"] == 0.0

    def test_program_by_branch_year(self, csv_path):
        _, by_by = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        # 2020 Air Force: AcmeAF 500K + MultiAF 500K = 1M
        assert by_by[("Air Force", 2020)] == 1_000_000.0
        # 2021 Air Force: AcmeAF 500K = 500K
        assert by_by[("Air Force", 2021)] == 500_000.0

    def test_dollars_by_year_per_firm(self, csv_path):
        firms, _ = _mod.load_sbir_firm_index(csv_path, 2009, 2024)
        assert firms["ACMEAF"]["dod_dollars_by_year"][2020] == 500_000.0
        assert firms["ACMEAF"]["dod_dollars_by_year"][2021] == 500_000.0


# ---------------------------------------------------------------------------
# item_2_per_firm_leverage_by_branch
# ---------------------------------------------------------------------------


class TestItem2PerFirmLeverage:
    def _firms(self):
        return {
            "AF_1": {"dod_dollars": 100.0, "dominant_dod_branch": "Air Force"},
            "AF_2": {"dod_dollars": 200.0, "dominant_dod_branch": "Air Force"},
            "NAVY_1": {"dod_dollars": 50.0, "dominant_dod_branch": "Navy"},
            "NON_DOD": {"dod_dollars": 0.0, "dominant_dod_branch": None},
        }

    def test_per_firm_ratios_aggregated_by_branch(self):
        firms = self._firms()
        # AF_1 raised 200 → 200/100 = 2.0x; AF_2 raised 1000 → 1000/200 = 5.0x
        fd = {"AF_1": 200.0, "AF_2": 1000.0, "NAVY_1": 100.0, "NON_DOD": 9999.0}
        out = _mod.item_2_per_firm_leverage_by_branch(firms, fd, min_n_firms=1)
        by_branch = {r["branch"]: r for r in out}
        # Air Force: 2.0 and 5.0 → median 3.5, mean 3.5
        assert by_branch["Air Force"]["n_firms"] == 2
        assert by_branch["Air Force"]["median_per_firm_leverage"] == pytest.approx(3.5)
        assert by_branch["Air Force"]["mean_per_firm_leverage"] == pytest.approx(3.5)
        # Navy: 100/50 = 2.0x
        assert by_branch["Navy"]["median_per_firm_leverage"] == pytest.approx(2.0)

    def test_skips_non_dod_firms(self):
        firms = self._firms()
        fd = {"AF_1": 100.0, "NON_DOD": 99999.0}
        out = _mod.item_2_per_firm_leverage_by_branch(firms, fd, min_n_firms=1)
        # NON_DOD has no DoD branch → must not contribute
        assert sum(r["n_firms"] for r in out) == 1

    def test_skips_firms_with_zero_dod_dollars(self):
        firms = {"X": {"dod_dollars": 0.0, "dominant_dod_branch": "Air Force"}}
        fd = {"X": 1000.0}
        out = _mod.item_2_per_firm_leverage_by_branch(firms, fd, min_n_firms=1)
        assert out == []  # would be div-by-zero, must be skipped

    def test_min_n_firms_filter(self):
        firms = self._firms()
        fd = {"AF_1": 200.0, "AF_2": 1000.0, "NAVY_1": 100.0}
        # min_n_firms=2 → Navy (n=1) should be excluded
        out = _mod.item_2_per_firm_leverage_by_branch(firms, fd, min_n_firms=2)
        branches = [r["branch"] for r in out]
        assert "Navy" not in branches
        assert "Air Force" in branches


# ---------------------------------------------------------------------------
# item_3_time_series_branch_ratios
# ---------------------------------------------------------------------------


class TestItem3TimeSeries:
    def test_basic_time_series_aggregation(self):
        firms = {
            "F1": {"dominant_dod_branch": "Air Force"},
            "F2": {"dominant_dod_branch": "Air Force"},
        }
        fd_per_firm_year = {
            "F1": {2020: 100.0, 2021: 200.0},
            "F2": {2020: 50.0},
        }
        program_by_branch_year = {
            ("Air Force", 2020): 1000.0,
            ("Air Force", 2021): 500.0,
        }
        out = _mod.item_3_time_series_branch_ratios(
            firms, fd_per_firm_year, program_by_branch_year, 2019, 2022, min_program_usd=0
        )
        assert "Air Force" in out
        rows = {r["year"]: r for r in out["Air Force"]}
        # 2020: 150 FD / 1000 program = 0.15
        assert rows[2020]["ratio"] == pytest.approx(0.15)
        # 2021: 200 FD / 500 program = 0.40
        assert rows[2021]["ratio"] == pytest.approx(0.40)
        # 2019: no data → 0
        assert rows[2019]["ratio"] == 0.0

    def test_excludes_minor_branches_via_threshold(self):
        firms = {"F1": {"dominant_dod_branch": "Tiny Branch"}}
        fd_per_firm_year = {"F1": {2020: 100.0}}
        program_by_branch_year = {("Tiny Branch", 2020): 50_000.0}  # only $50K
        out = _mod.item_3_time_series_branch_ratios(
            firms, fd_per_firm_year, program_by_branch_year, 2020, 2020, min_program_usd=100_000.0
        )
        assert out == {}


# ---------------------------------------------------------------------------
# item_4_navy_acquirer_analysis
# ---------------------------------------------------------------------------


class TestItem4NavyAcquirers:
    @pytest.fixture
    def ma_events_path(self, tmp_path):
        records = [
            # Navy firms
            {
                "company_name": "NavyFirm1",
                "acquirer": "LOCKHEED MARTIN CORP",
                "event_date": "2020-01-01",
            },
            {
                "company_name": "NavyFirm2",
                "acquirer": "Acme Commercial Inc.",
                "event_date": "2021-01-01",
            },
            {
                "company_name": "NavyFirm3",
                "acquirer": "Golub Capital BDC",
                "event_date": "2022-01-01",
            },
            # Air Force firms
            {
                "company_name": "AfFirm1",
                "acquirer": "RAYTHEON TECHNOLOGIES CORP",
                "event_date": "2020-01-01",
            },
            {
                "company_name": "AfFirm2",
                "acquirer": "Megacorp Industries",
                "event_date": "2021-01-01",
            },
            # Firm not in any branch — should be ignored
            {"company_name": "Stranger", "acquirer": "Whoever", "event_date": "2023-01-01"},
            # Event with no acquirer — should not affect classified counts
            {"company_name": "NavyFirm4", "acquirer": None, "event_date": "2020-01-01"},
        ]
        p = tmp_path / "ma.jsonl"
        with open(p, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return p

    def test_classifies_by_branch(self, ma_events_path):
        firms = {
            "NAVYFIRM1": {"dominant_dod_branch": "Navy"},
            "NAVYFIRM2": {"dominant_dod_branch": "Navy"},
            "NAVYFIRM3": {"dominant_dod_branch": "Navy"},
            "NAVYFIRM4": {"dominant_dod_branch": "Navy"},
            "AFFIRM1": {"dominant_dod_branch": "Air Force"},
            "AFFIRM2": {"dominant_dod_branch": "Air Force"},
        }
        out = _mod.item_4_navy_acquirer_analysis(firms, ma_events_path)
        # Navy: 4 events total, 3 with named acquirer (LM=defense, Acme=commercial, Golub=financial)
        navy = out["Navy"]
        assert navy["n_branch_firms"] == 4
        assert navy["n_ma_events"] == 4
        assert navy["n_unique_firms_with_named_acquirer"] == 3
        assert navy["type_counts"]["defense_prime"] == 1
        assert navy["type_counts"]["commercial"] == 1
        assert navy["type_counts"]["financial_sponsor"] == 1
        # Air Force: 2 events, both named (1 defense, 1 commercial)
        af = out["Air Force"]
        assert af["type_counts"]["defense_prime"] == 1
        assert af["type_counts"]["commercial"] == 1

    def test_handles_invalid_json_lines(self, tmp_path):
        p = tmp_path / "broken.jsonl"
        p.write_text(
            '{"company_name":"NavyFirm","acquirer":"LOCKHEED MARTIN","event_date":"2020-01-01"}\n'
            "not json\n"
        )
        firms = {"NAVYFIRM": {"dominant_dod_branch": "Navy"}}
        out = _mod.item_4_navy_acquirer_analysis(firms, p)
        # Should not crash; valid line should still be processed
        assert out["Navy"]["type_counts"]["defense_prime"] == 1


# ---------------------------------------------------------------------------
# Top-level helpers
# ---------------------------------------------------------------------------


class TestParseAmount:
    def test_dollar_and_comma_stripped(self):
        assert _mod._parse_amount("$1,234,567") == 1234567.0

    def test_none(self):
        assert _mod._parse_amount(None) is None


class TestNormName:
    def test_uppercase_strip(self):
        assert _mod._norm_name("  Acme Corp  ") == "ACME CORP"

    def test_none(self):
        assert _mod._norm_name(None) == ""
