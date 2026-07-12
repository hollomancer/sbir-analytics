"""Tests for the state tax rate refresh CLI."""

import json

import pytest

pytestmark = pytest.mark.fast

from sbir_etl.transformers.fiscal.refresh_state_rates import (
    merge_fiscal_year,
    parse_income_tax_table,
    parse_sales_tax_table,
    refresh_state_rates,
    write_csv_rows,
)

SAMPLE_INCOME_TABLE = """
| State | Single Filer (Rates) | Single Filer (Brackets) |
| --- | --- | --- |
| California (a) | 1.00% | > | $0 |
| - California | 13.30% | > | $1,000,000 |
| Texas | none | none |
| Oregon (a) | 4.75% | > | $0 |
| - Oregon | 9.90% | > | $125,000 |
"""

SAMPLE_SALES_TABLE = """
| State | State Tax Rate | Average Local Tax Rate | Max Local Rate | Combined Tax Rate | Combined Rank |
| --- | --- | --- | --- | --- | --- |
| California | 7.25% | 1.78% | 5.25% | 9.03% | 7 |
| Texas | 6.25% | 1.95% | 2.00% | 8.20% | 14 |
| Oregon | 0.00% | 0.00% | 0.00% | 0.00% | 47 |
"""


class TestParseTaxFoundationTables:
    def test_parse_income_top_marginal(self):
        rates = parse_income_tax_table(SAMPLE_INCOME_TABLE)
        assert rates["CA"] == pytest.approx(0.133)
        assert rates["TX"] == 0.0
        assert rates["OR"] == pytest.approx(0.099)

    def test_parse_sales_combined_rate(self):
        rates = parse_sales_tax_table(SAMPLE_SALES_TABLE)
        assert rates["CA"] == pytest.approx(0.0903)
        assert rates["TX"] == pytest.approx(0.082)
        assert rates["OR"] == 0.0


class TestMergeFiscalYear:
    def _base_row(self, abbr: str, fips: str, year: int = 2024) -> dict[str, str]:
        return {
            "state_fips": fips,
            "state_abbr": abbr,
            "fiscal_year": str(year),
            "income_rate": "0.1",
            "sales_rate": "0.08",
            "property_rate": "0.09",
            "has_income_tax": "True",
            "has_sales_tax": "True",
            "income_source": "old income",
            "sales_source": "old sales",
            "property_source": "old property",
        }

    def test_overwrites_existing_year(self, tmp_path):
        existing = [self._base_row("CA", "06"), self._base_row("TX", "48")]
        merged, count = merge_fiscal_year(
            existing,
            fiscal_year=2024,
            income_by_state={"CA": 0.133, "TX": 0.0},
            sales_by_state={"CA": 0.087, "TX": 0.082},
            edition="Tax Foundation 2024 test",
        )
        assert count == 2
        ca_rows = [
            row for row in merged if row["state_abbr"] == "CA" and row["fiscal_year"] == "2024"
        ]
        assert len(ca_rows) == 1
        assert float(ca_rows[0]["income_rate"]) == pytest.approx(0.133)
        assert ca_rows[0]["property_rate"] == "0.09"
        assert ca_rows[0]["property_source"] == "old property"

    def test_appends_new_year(self):
        existing = [self._base_row("CA", "06", year=2024)]
        merged, count = merge_fiscal_year(
            existing,
            fiscal_year=2025,
            income_by_state={"CA": 0.133},
            sales_by_state={"CA": 0.087},
            edition="Tax Foundation 2025 test",
        )
        assert count == 1
        years = sorted(int(row["fiscal_year"]) for row in merged if row["state_abbr"] == "CA")
        assert years == [2024, 2025]


class TestRefreshStateRatesCli:
    def test_rates_json_updates_csv(self, tmp_path):
        csv_path = tmp_path / "state_effective_rates.csv"
        write_csv_rows(
            csv_path,
            [
                {
                    "state_fips": "06",
                    "state_abbr": "CA",
                    "fiscal_year": "2024",
                    "income_rate": "0.133",
                    "sales_rate": "0.087",
                    "property_rate": "0.091",
                    "has_income_tax": "True",
                    "has_sales_tax": "True",
                    "income_source": "old",
                    "sales_source": "old",
                    "property_source": "census",
                }
            ],
        )
        bundle = tmp_path / "bundle.json"
        bundle.write_text(
            json.dumps(
                {
                    "edition": "manual test bundle",
                    "income": {"CA": 0.14},
                    "sales": {"CA": 0.09},
                }
            ),
            encoding="utf-8",
        )

        count = refresh_state_rates(
            fiscal_year=2025,
            csv_path=csv_path,
            income_by_state={"CA": 0.14},
            sales_by_state={"CA": 0.09},
            edition="manual test bundle",
        )
        assert count == 1

        rows = list(__import__("csv").DictReader(csv_path.open(encoding="utf-8")))
        ca_2025 = next(
            row for row in rows if row["state_abbr"] == "CA" and row["fiscal_year"] == "2025"
        )
        assert float(ca_2025["income_rate"]) == pytest.approx(0.14)
        assert ca_2025["property_source"] == "census"
