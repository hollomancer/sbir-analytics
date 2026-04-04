"""R ↔ Python parity test for Leontief I-O math.

Runs the same economic impact calculations in both R (base R, no stateior)
and Python using a shared mock BEA Use table, then asserts that all
intermediate and final results match within floating-point tolerance.

This validates that our Python implementation produces identical results
to the standard R linear-algebra routines (solve, %*%) that stateior uses
internally.

Requires: R installed (``Rscript`` on PATH).  No CRAN packages needed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sbir_etl.transformers.bea_io_functions import (
    apply_demand_shocks,
    calculate_employment_coefficients,
    calculate_employment_from_production,
    calculate_leontief_inverse,
    calculate_technical_coefficients,
)

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
R_SCRIPT = SCRIPTS_DIR / "r_parity_reference.R"

# Tolerance for floating-point comparison
ATOL = 1e-10


def r_available() -> bool:
    """Check if Rscript is on PATH."""
    return shutil.which("Rscript") is not None


pytestmark = [
    pytest.mark.skipif(not r_available(), reason="Rscript not available"),
]


# ---------------------------------------------------------------------------
# Shared mock data (must match r_parity_reference.R exactly)
# ---------------------------------------------------------------------------

SECTORS = ["11", "21", "31", "42", "44", "54"]

USE_VALUES = np.array([
    [10,  2,  8,  1,  1,  0],
    [ 1, 15,  5,  1,  0,  2],
    [ 5,  8, 60, 10,  5, 15],
    [ 2,  1,  8, 12,  3,  4],
    [ 1,  0,  3,  2,  8,  2],
    [ 3,  5, 12,  6,  4, 30],
], dtype=float)

# Value-added per sector (wages, profits, taxes — not in the Use table)
VALUE_ADDED = np.array([50, 40, 150, 50, 30, 80], dtype=float)

EMPLOYMENT_TOTAL = np.array([500, 200, 1500, 800, 2000, 1200], dtype=float)


@pytest.fixture(scope="module")
def r_output(tmp_path_factory):
    """Run the R parity script and return the output directory."""
    out_dir = tmp_path_factory.mktemp("r_parity")
    result = subprocess.run(
        ["Rscript", str(R_SCRIPT), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(f"R script failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
    return out_dir


@pytest.fixture(scope="module")
def python_results():
    """Compute all results using the Python implementation."""
    use_table = pd.DataFrame(USE_VALUES, index=SECTORS, columns=SECTORS)
    # Industry output = intermediate inputs + value added (matches R script)
    industry_output = use_table.sum(axis=0) + pd.Series(VALUE_ADDED, index=SECTORS)

    tech_coeff = calculate_technical_coefficients(use_table, industry_output)
    leontief_inv = calculate_leontief_inverse(tech_coeff)

    # Per-sector $1M shocks
    shock_results = {}
    for sector in SECTORS:
        shocks_df = pd.DataFrame({
            "bea_sector": [sector],
            "shock_amount": [1.0],
        })
        production = apply_demand_shocks(leontief_inv, shocks_df)
        shock_results[sector] = production

    # Employment coefficients
    emp_df = pd.DataFrame({
        "ColCode": SECTORS,
        "DataValue": EMPLOYMENT_TOTAL,
    })
    emp_coeff = calculate_employment_coefficients(emp_df, industry_output)

    # Full impact: $2M shock to sector 31
    shocks_31 = pd.DataFrame({
        "bea_sector": ["31"],
        "shock_amount": [2.0],
    })
    production_31 = apply_demand_shocks(leontief_inv, shocks_31)
    employment_31 = calculate_employment_from_production(production_31, emp_coeff)

    return {
        "tech_coeff": tech_coeff,
        "leontief_inv": leontief_inv,
        "industry_output": industry_output,
        "shock_results": shock_results,
        "emp_coeff": emp_coeff,
        "production_31": production_31,
        "employment_31": employment_31,
    }


# ---------------------------------------------------------------------------
# Parity tests
# ---------------------------------------------------------------------------


class TestRPythonParity:
    """Compare R and Python Leontief I-O results element-by-element."""

    def test_industry_output(self, r_output, python_results):
        """Industry output (column sums) match."""
        r_df = pd.read_csv(r_output / "r_industry_output.csv")
        r_output_vals = r_df.set_index("sector")["output"]

        py_output = python_results["industry_output"]

        for sector in SECTORS:
            r_val = float(r_output_vals[int(sector)])
            py_val = float(py_output[sector])
            assert abs(r_val - py_val) < ATOL, (
                f"Industry output [{sector}]: R={r_val}, Python={py_val}"
            )

    def test_technical_coefficients(self, r_output, python_results):
        """Technical coefficients matrix A matches element-by-element."""
        r_tc = pd.read_csv(r_output / "r_tech_coefficients.csv", index_col=0)
        py_tc = python_results["tech_coeff"]

        # R CSV may use X-prefixed column names for numeric headers
        r_tc.columns = [c.lstrip("X") for c in r_tc.columns]
        r_tc.index = [str(i).lstrip("X") for i in r_tc.index]

        for i in SECTORS:
            for j in SECTORS:
                r_val = float(r_tc.loc[i, j])
                py_val = float(py_tc.loc[i, j])
                assert abs(r_val - py_val) < ATOL, (
                    f"Tech coeff [{i},{j}]: R={r_val:.10f}, Python={py_val:.10f}"
                )

    def test_leontief_inverse(self, r_output, python_results):
        """Leontief inverse L = (I-A)^{-1} matches element-by-element."""
        r_li = pd.read_csv(r_output / "r_leontief_inverse.csv", index_col=0)
        py_li = python_results["leontief_inv"]

        r_li.columns = [c.lstrip("X") for c in r_li.columns]
        r_li.index = [str(i).lstrip("X") for i in r_li.index]

        for i in SECTORS:
            for j in SECTORS:
                r_val = float(r_li.loc[i, j])
                py_val = float(py_li.loc[i, j])
                assert abs(r_val - py_val) < ATOL, (
                    f"Leontief inverse [{i},{j}]: R={r_val:.10f}, Python={py_val:.10f}"
                )

    @staticmethod
    def _clean_sector(val) -> str:
        """Normalize R sector codes (e.g. '11.0' → '11')."""
        s = str(val)
        if s.endswith(".0"):
            s = s[:-2]
        return s

    def test_demand_shocks_all_sectors(self, r_output, python_results):
        """Production impacts from $1M shocks match for every sector pair."""
        r_shocks = pd.read_csv(r_output / "r_shock_results.csv")
        py_shocks = python_results["shock_results"]

        for _, row in r_shocks.iterrows():
            shock_sec = self._clean_sector(row["shock_sector"])
            target_sec = self._clean_sector(row["target_sector"])
            r_val = float(row["production_impact_millions"])
            py_val = float(py_shocks[shock_sec][target_sec])

            assert abs(r_val - py_val) < ATOL, (
                f"Shock {shock_sec}→{target_sec}: "
                f"R={r_val:.10f}, Python={py_val:.10f}"
            )

    def test_employment_coefficients(self, r_output, python_results):
        """Employment coefficients (jobs per $1M) match."""
        r_emp = pd.read_csv(r_output / "r_employment_coefficients.csv")
        py_emp = python_results["emp_coeff"]

        for _, r_row in r_emp.iterrows():
            sector = self._clean_sector(r_row["sector"])
            r_coeff = float(r_row["employment_coefficient"])

            py_row = py_emp[py_emp["sector"] == sector]
            if py_row.empty:
                pytest.fail(f"Python missing employment coefficient for sector {sector}")

            py_coeff = float(py_row["employment_coefficient"].iloc[0])
            assert abs(r_coeff - py_coeff) < ATOL, (
                f"Employment coeff [{sector}]: R={r_coeff:.10f}, Python={py_coeff:.10f}"
            )

    def test_full_impact_manufacturing_shock(self, r_output, python_results):
        """Full $2M manufacturing shock: production + employment match."""
        r_impact = pd.read_csv(r_output / "r_full_impact_31.csv")
        py_production = python_results["production_31"]
        py_employment = python_results["employment_31"]

        for _, r_row in r_impact.iterrows():
            sector = self._clean_sector(r_row["sector"])

            # Production (in millions)
            r_prod = float(r_row["production_impact_millions"])
            py_prod = float(py_production[sector])
            assert abs(r_prod - py_prod) < ATOL, (
                f"Production [{sector}]: R={r_prod:.10f}, Python={py_prod:.10f}"
            )

            # Employment (jobs)
            r_emp = float(r_row["employment_impact"])
            py_emp = float(py_employment[sector])
            assert abs(r_emp - py_emp) < ATOL, (
                f"Employment [{sector}]: R={r_emp:.10f}, Python={py_emp:.10f}"
            )

    def test_leontief_identity_property(self, python_results):
        """Verify L × (I - A) = I (sanity check on both implementations)."""
        tech_coeff = python_results["tech_coeff"]
        leontief_inv = python_results["leontief_inv"]

        identity = np.eye(len(SECTORS))
        result = leontief_inv.values @ (identity - tech_coeff.values)

        np.testing.assert_allclose(
            result, identity, atol=1e-10,
            err_msg="L × (I - A) should equal identity",
        )

    def test_output_multiplier_range(self, python_results):
        """All output multipliers should be >= 1.0 (economic identity)."""
        leontief_inv = python_results["leontief_inv"]

        for sector in SECTORS:
            multiplier = float(leontief_inv.loc[sector, sector])
            assert multiplier >= 1.0, (
                f"Sector {sector} self-multiplier {multiplier:.4f} < 1.0"
            )
