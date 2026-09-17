# Vintage drift measurement — 2026-09-17

Evidence for the reproduction tolerances in `sources.yaml`. Compares three SBIR.gov award
exports over the same closed fiscal years (FY2020–FY2022).

**All three are from the canonical endpoint**
`https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`, which is the URL
`sbir_etl/extractors/source_downloads/sbir.py` uses. See the endpoint caution at the bottom —
an earlier version of this measurement was invalid because it used a different URL.

| Vintage | Pinned | Export records | FY20–22 unique awards | Schema |
| --- | --- | ---: | ---: | --- |
| 2026-05-11 (canonical) | sha256 in `sources.yaml:inputs` | 219,501 | 20,721 | 42 cols, UEI present |
| 2026-08-30 | **no — file not retained** | 219,503 | 20,722 | 42 cols, UEI present |
| 2026-09-17 | sha256 in `sources.yaml:inputs` | 219,590 | 20,722 | 42 cols, UEI present |

The schema is **unchanged** across all three. The export grew by 89 records over four months,
which is ordinary accretion of newly published awards.

**The band evidence is the two pinned vintages.** The 2026-08-30 export was measured but its
file was not retained, so it has no hash, path, or `source_url` entry in `sources.yaml:inputs`
and cannot support SHA enforcement. Its rows in this report are context only; every tolerance
in `sources.yaml` derives from the 2026-05-11 → 2026-09-17 comparison alone.

## Measured drift, 2026-05-11 → 2026-09-17 (4.2 months)

Matched on agency tracking number, contract, company, and award year, restricted to FY2020–FY2022:

| Quantity | Value |
| --- | ---: |
| FY20–22 total dollars | $12.2040B → $12.2097B (**+$5.67M, +0.0465%**) |
| Unique awards | 20,721 → 20,722 (**+1**) |
| Records removed / added | 135 / 136 |
| Matched records with changed amount | **34 (0.17%)**, net +$4.04M, largest single change $1,928,322 |
| Matched records with changed state | **32 (0.16%)** |

The unretained August measurement showed intermediate intervals similarly quiet: 36 amount
changes (0.17%) from May to August, 43 (0.21%) from August to September. That observation is
unpinned context against episodic bulk republication, not band evidence; drift in the pinned
window is small and gradual.

`State` carries full state names (`California`) in every vintage. No format change.

## What this licenses

Exact published-sample reproduction remains impossible for a reason unrelated to drift: no
report-era vintage survives. `docs/data/awards-refresh.md` records that SBIR.gov serves only the
current snapshot, so a past vintage exists nowhere else once upstream overwrites it. The oldest
vintage available here is 2026-05-11, which post-dates all three reports in [L18].

What the measurements above support is a **vintage-tolerant reproduction** with narrow bands: the
published cells are compared against a pinned vintage, and a difference inside the band is recorded
as agreement rather than as `pipeline_defect`. At 0.047% observed movement over four months, the
bands can be tight. `StudyManifest.reproduction` is the contract for this; its docstring notes that
bit-exact reproducibility "is unachievable against a source someone else updates".

The derived bands are in `sources.yaml` under `proposed_reproduction_contract`. They rest on a
**single four-month observation window**, and extrapolating them across the multi-year gap to the
[L18] reports is an assumption, not a measurement. Re-derive when a longer baseline exists.

Every run must pin the vintage it read; a comparison against an unpinned "latest" is not
reproducible at any tolerance.

## Endpoint caution

Two URLs on the same host serve different products:

| URL | Result |
| --- | --- |
| `data.www.sbir.gov/mod_awarddatapublic/award_data.csv` | **Canonical.** 42 columns, `UEI` present, ~394 MB |
| `data.www.sbir.gov/awarddatapublic/award_data.csv` | Legacy. 41 columns, **no `UEI`**, `Women Owned` instead of `Woman Owned`, `State` as USPS abbreviations, ~367 MB |

The second URL appears in `docs/archive/deployment/actions-migration-plan.md`. A first pass of this
measurement used it and produced a spurious finding — an apparent "republication event" that removed
the UEI column, dropped 11,770 records, and moved FY20–22 dollars by $279M. Every one of those
differences was a difference between the two endpoints, not a change over time. Pin the URL in the
retrieval manifest and compare only like endpoints.
