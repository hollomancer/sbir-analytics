# Capital Events & UCC1 Pilot

Assembles a per-firm "capital events" dataset — funding, M&A, patents, federal
contracts, and UCC liens — for the Form D high-confidence cohort. Code lives in
`sbir_etl/capital_events/`; the UCC1 pilot that feeds it lives in `sbir_etl/ucc/`.

All paths below are under the data root, overridable with the `SBIR_DATA_DIR`
environment variable. No API credentials are required for either subsystem.

## Build capital events

```bash
python scripts/data/build_capital_events.py
```

Requires the cohort file (`--cohort`, default `form_d_high_conf_cohort.jsonl`). Each
optional source is skipped if its input file is missing:

| Source | Flag | Default input |
|--------|------|---------------|
| Cohort (required) | `--cohort` | `form_d_high_conf_cohort.jsonl` |
| SBIR awards | `--sbir-awards` | `raw/sbir/award_data.csv` |
| Form D | `--form-d` | `form_d_details.jsonl` |
| M&A | `--ma-events` | `enriched_sbir_ma_events.jsonl` |
| USASpending | `--usaspending` | `processed/sbir_phase3/usaspending_phase3_contracts.jsonl` |
| Patents | `--patents-dir` | `transformed/uspto/` (newest `patents_*.jsonl`) |
| UCC | `--ucc-matches` | `ucc1_pilot_matches.jsonl` |

**Outputs:** `capital_events.parquet` (long form), `capital_events_per_firm.parquet`
(one row per firm), and `capital_events_sample.jsonl` (first 100 events).

## UCC1 pilot (California)

Extracts UCC-1 financing statements from the California bizfileOnline registry.
No login is required, but the registry blocks plain HTTP clients, so the extractor
uses TLS impersonation via `curl_cffi` — installed through an optional extra:

```bash
uv sync --extra ucc1-pilot
```

### Pipeline

```bash
# 1. Build the Form D → SBIR cohort
python -m sbir_etl.ucc.export_cohort --out form_d_high_conf_cohort.jsonl

# 2. Extract UCC filings (resumable via --checkpoint)
python -m sbir_etl.ucc.ca_extractor --cohort ucc1_pilot_ca_org_cohort.jsonl \
    --out ucc1_pilot_raw.jsonl --delay 1.0
```

`ca_extractor` emits one row per filing event and appends to `--out` (checkpointed).
The matcher (`sbir_etl/ucc/matcher.py`) then produces `ucc1_pilot_matches.jsonl`, which
is what `build_capital_events.py --ucc-matches` consumes.

## Related

- [Form D data dictionary](../research/form-d-data-dictionary.md)
- [SBIR pathway cohorts](../research/sbir-pathway-cohorts.md)
- [UCC1 pilot notes](../research/sbir-ucc1-pilot.md)
