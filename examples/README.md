# Examples

Standalone scripts that demonstrate how the library pieces fit together. They are
**exploratory tier** (see [epistemic tiers](../docs/steering/epistemic-tiers.md)):
illustrative, not citable, and not part of any scheduled pipeline.

Install the stack once before running any of them:

```bash
make install
```

## Fiscal impact

| Script | What it shows | Needs |
|---|---|---|
| [`sbir_fiscal_impact_offline.py`](sbir_fiscal_impact_offline.py) | The full award → tax/jobs impact flow using stand-in multipliers | nothing beyond `make install` |
| [`sbir_fiscal_impact_example.py`](sbir_fiscal_impact_example.py) | The same flow against real EPA StateIO models | R + StateIO, via Docker |
| [`sbir_fiscal_impact_by_district_example.py`](sbir_fiscal_impact_by_district_example.py) | Allocating state-level impacts down to congressional districts | R + StateIO, via Docker |

Start with the offline variant — it runs with no external services. See
[fiscal-impact.md](fiscal-impact.md) for the Docker setup the other two need.

## Entity resolution and enrichment

| Script | What it shows | Needs |
|---|---|---|
| [`enhanced_matching_demo.py`](enhanced_matching_demo.py) | Phonetic, Jaro-Winkler, abbreviation, and ORCID-based name matching | nothing beyond `make install` |
| [`multi_source_enrichment_demo.py`](multi_source_enrichment_demo.py) | Joining SBIR, USAspending, and SAM.gov into one enriched dataset | `--use-sample-data`, or API keys for live data |
| [`congressional_district_resolution.py`](congressional_district_resolution.py) | A proof-of-concept for geocoding award addresses to districts | nothing beyond `make install` |

## Report rendering

[`army-procurement-transition.md`](army-procurement-transition.md) documents a
synthetic monthly procurement-transition packet. Every company, award, amount,
and score in it is fabricated — it exists to show report *structure* and must not
be read as acquisition intelligence.

The four `army_science_technology_*` files backing it are committed
deliberately: they are the fixtures for
`tests/unit/reporting/test_procurement_transition.py`, which renders the report
and asserts byte-equality against `army_science_technology_report.md`. Changing
them will fail that test.
