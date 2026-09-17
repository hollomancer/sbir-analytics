# Amendments — sba-annual-report-tables

Deviations from the frozen protocol in `design.md` are recorded here, with a date and a
reason. The protocol itself is not edited after freezing.

## 2026-09-17 — protocol frozen

Initial freeze, before source capture. No amendments yet.

The start gate ("exact table definitions and report-year source files captured") is
**not** satisfied at freeze time: the SBA annual reports could not be retrieved from the
analysis environment (see `sources.yaml:targets[].retrieval_blocker`). The protocol is
frozen first deliberately, so that the definitions recovered at capture time cannot be
shaped by what the pipeline happens to produce.

## 2026-09-17 — vintage constraint relaxed to a tolerance contract

**Maintainer decision.** The exact-vintage requirement is relaxed for bulk upstream sources
such as SBIR.gov, which publish only a current snapshot.

Exact published-sample reproduction remains impossible, for a reason unrelated to drift: no
report-era vintage survives anywhere. `docs/data/awards-refresh.md` records that SBIR.gov
serves only the current snapshot, and the oldest vintage available here (2026-05-11)
post-dates all three reports in [L18]. In its place the study performs a **vintage-tolerant
reproduction** — published cells compared against a *pinned* vintage under declared bands,
with an in-band difference recorded as agreement rather than `pipeline_defect`. This uses
`StudyManifest.reproduction`, whose docstring notes that bit-exact reproducibility is
unachievable against a source someone else updates. The proposed contract is in
`sources.yaml:proposed_reproduction_contract`.

Measured drift supports narrow bands: over 4.2 months the FY20–22 total moved +$5.67M
(+0.0465%), 34 matched records (0.17%) changed amount, 32 (0.16%) changed state, and the
export grew by 89 records. Details in `vintage-drift-2026-09-17.md`.

**Methodological note — a retracted finding.** A first pass of this measurement fetched the
award export from `data.www.sbir.gov/awarddatapublic/award_data.csv`, a URL taken from
`docs/archive/deployment/actions-migration-plan.md`. That is a legacy endpoint serving a
different 41-column product without `UEI`. Comparing it against the canonical
`mod_awarddatapublic` export produced a spurious "republication event" — an apparent removal
of the UEI column, a loss of 11,770 records, and a $279M swing in FY20–22 dollars. None of it
was real; all of it was a difference between two endpoints. The retrieval manifest now pins
the exact URL, and the drift report records the caution. Compare only like endpoints.

**Standing limits.** Two constraints from the frozen protocol are unaffected: differences must
still be classified rather than absorbed, and definitions must still be recovered verbatim from
the report before any comparison. A band is not a licence to tune toward the published number.
Every run must pin the vintage it read.
