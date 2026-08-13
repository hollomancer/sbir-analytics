# SBIR Fiscal Impact Examples

These examples demonstrate the shape of the exploratory fiscal-impact pipeline.
They are integration aids, not validated economic findings.

## Examples

- `sbir_fiscal_impact_example.py` exercises the current Python implementation,
  which uses BEA input-output data when `BEA_API_KEY` is configured.
- `sbir_fiscal_impact_offline.py` uses hand-authored multipliers so the data
  flow can be inspected without network access. Its numerical outputs are
  illustrative and must not be cited.
- `sbir_fiscal_impact_by_district_example.py` demonstrates how the mock output
  can be grouped geographically. It carries the same evidence limitation.

The repository no longer ships an R, StateIO, or USEEIOR runtime. Docker Compose
does not install those tools, and there is no `r` dependency extra.

## Run the deterministic demonstration

From a development checkout:

```bash
make install
.venv/bin/python examples/sbir_fiscal_impact_offline.py
```

The mock implementation uses simplified sector multipliers and emits
`quality_flags=mock_data`. It is useful for inspecting schemas, aggregation,
and reporting behavior only.

## Run the current BEA-backed implementation

Register for a BEA API key, export it, and run:

```bash
export BEA_API_KEY=replace-with-your-key
.venv/bin/python examples/sbir_fiscal_impact_example.py
```

The current calculator maps NAICS codes to BEA sectors and applies national
input-output tables. Its tax and employment estimates remain exploratory and
non-citable; see the epistemic-tier declaration in
`sbir_etl/transformers/sbir_fiscal_pipeline.py`.

When `BEA_API_KEY` is absent, or a BEA request fails, this path falls back to
hard-coded placeholder multipliers. Check `quality_flags`: only
`bea_api_with_ratios` and `bea_api_default_ratios` identify BEA-backed rows;
`placeholder_computation` is illustrative fallback output.

The Python and mock calculator examples require these award columns:

- `award_amount`
- `state`
- `naics_code`
- `fiscal_year`

The district example additionally requires `company_address`, `company_city`,
`company_state`, and `company_zip` for geographic resolution. Its sample also
includes `award_id` and `company_name` for readability, but neither calculator
requires them.

For the project-wide evidence boundaries, see the
[research output status index](../docs/research/README.md).
For the fiscal pipeline schema and quality flags, see the
[fiscal pipeline guide](../docs/fiscal/sbir-fiscal-pipeline-guide.md).
