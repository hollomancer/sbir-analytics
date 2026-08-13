# Design: SBIR M&A Signal Counts by Fiscal Year

## Decision

Replace the invalid FY match-rate design with one standard-library diagnostic:

```text
fingerprinted curated JSONL
  -> strict schema/date validation
  -> normalized-name-key deduplication
  -> signal-observation federal FY
  -> deterministic CSV + Markdown counts
```

There is no award denominator, cross-source reconstruction, Dagster asset,
firm-level output, network access, or committed generated report.

## Input contract

`scripts/data/sbir_ma_signal_counts_by_fy.py` reads
`data/sbir_ma_events.jsonl` by default. Every nonblank line must be a UTF-8 JSON
object with:

- nonempty string `company_name`;
- exact `confidence` in `high`, `medium`, or `low`; and
- optional top-level `event_date`, which is missing when absent, null, or the
  empty string, valid only when it is an exact ISO `YYYY-MM-DD` date, and
  otherwise invalid.

Duplicate JSON keys, blank JSONL lines, nonstandard JSON constants, an empty
file, invalid types, and unknown tiers fail closed. Extra historical fields are
retained outside this calculation and do not affect the result.

The script reads the source bytes once, computes SHA-256 and byte count from
those bytes, decodes them as UTF-8, then validates the decoded rows.

## Grain and deduplication

The descriptive unit is a normalized company-name key:

```python
company_key = company_name.strip().casefold()
```

No punctuation, suffix, alias, fuzzy, CIK, UEI, or DUNS normalization is
introduced. Repeated normalized keys collapse only when their top-level date
status/value and exact confidence tier agree. A conflicting date or tier fails
the run and identifies both source lines.

## Fiscal-year aggregation

For a valid observation date:

```python
signal_fy = event_date.year + 1 if event_date.month >= 10 else event_date.year
```

Each selected FY row reports:

- `high_signal_name_keys`;
- `medium_signal_name_keys`;
- `high_medium_signal_name_keys`;
- `low_sensitivity_signal_name_keys`; and
- `total_signal_name_keys`.

The selected window defaults to FY2015–FY2024. Every distinct key belongs to
exactly one of four date categories: in-window, valid-out-of-window, missing,
or invalid. Those categories reconcile overall and within each confidence
tier. High plus medium and total counts reconcile within every FY row.

## Rendering and failure behavior

The CLI defaults are:

```text
--input data/sbir_ma_events.jsonl
--csv-output reports/sbir_ma_signal_counts_by_fy.csv
--markdown-output reports/sbir_ma_signal_counts_by_fy.md
--start-fy 2015
--end-fy 2024
```

Both renderers are deterministic for the same source path, bytes, and FY
arguments. Input and output paths must be distinct and report destinations may
not be symbolic links. Validation and rendering complete before either output
is opened. Both products are staged in their destination directories before
publication; if the second replacement fails, the first is rolled back to its
prior content (or removed when it did not previously exist). Missing or invalid
input returns nonzero and creates neither output. Output write failures also
return nonzero.

The Markdown includes source path, SHA-256, bytes, row/key/deduplication counts,
the FY table, overall and per-tier date diagnostics, the exact normalization and
FY rules, and the interpretation boundary.

## Interpretation boundary

`event_date` is labeled `signal-observation date`. It is a hybrid of Form D
filing and aggregate EFTS mention timing, not a transaction date. The reporter
does not infer that counts are acquisitions or exits and does not interpret
higher/lower observed counts as incidence. SEC coverage is incomplete, the
input is SBIR-only, and low-confidence rows remain sensitivity evidence.

The supplied tier values are treated as data, not independently reproduced.
The tracked repository lacks the historical refinement/apply-back artifacts
needed to reconstruct the final published tier totals.

## Why the original rate design was rejected

The former design grouped matched names by signal FY but grouped awardees by
their first award FY, and even allowed a signal to precede the first award.
Dividing those groupings compares unlike populations. A valid award-vintage
rate requires a single cohort definition and fixed follow-up window, plus
identity, censoring, and symmetric coverage rules. That is a separate research
design, not a small extension of this count diagnostic.
