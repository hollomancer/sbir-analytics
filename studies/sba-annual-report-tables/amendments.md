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
post-dates all three reports in [L18]. The exact-vintage published-sample outcome is
therefore **`blocked`**, exactly as the frozen protocol's source-vintage section states.

What proceeds is the **labelled structural check** that same section permits: recompute the
table structure and definitions against a *pinned* later vintage and report it as a
structural check, keeping the `blocked` verdict on the published-sample cells. Two contracts
divide the work and must not be conflated:

- **Input drift between pinned vintages** is classified by `StudyManifest.reproduction` via
  `sbir_etl.quality.reproduction.classify_rebuild`, under the declared bands. That contract
  compares a pinned retrieval of the live export with a later retrieval of the same export.
  It never grades a published cell against a recomputed one.
- **Cell differences** are classified one at a time under the frozen protocol's four classes.
  A band is never a reason to record a cell as agreeing: `revised_upstream` must be
  demonstrated from the specific award records that moved between pinned vintages, or the
  difference stays `pipeline_defect` territory. The FY2020–FY2022 aggregate bands ($30M on
  ~$12.2B; 200 unique awards) would otherwise absorb differences larger than many Table 20
  rows and larger than the documented $4,040,026 Table 20 vs program-total STTR gap.

The proposed contract is in `sources.yaml:proposed_reproduction_contract`, with its scope
stated in the same terms.

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

## 2026-09-17 (later) — source captured; gate partially satisfied

**Capture.** The maintainer supplied the FY20, FY21 and FY22 SBA SBIR/STTR Annual Reports
directly, which resolves the retrieval blocker recorded above. sbir.gov continues to refuse
non-browser clients (HTTP 403 on www.sbir.gov and on the /impact/ path of data.www.sbir.gov,
which serves award_data.csv normally); the user agent was not altered to evade that refusal.
FY22 is the selected report-year under the protocol's selection rule; FY20 and FY21 are recorded
with hashes but not extracted.

**Extracted from FY22** (`sha256=5ba60852f1cc44b2...`, 94 pages, text layer):

- Table 20, awards by U.S. state and territory — 52 rows, Phase I and Phase II only
- Charts 1 and 2, obligations by participating agency — 16 rows, all obligation categories

The transcription checks held on both. Five of six within-row identities in Table 20 hold
exactly for all 52 rows; the sixth is off by exactly +/-$1 on 14 rows, consistent with
sub-dollar amounts presented as whole dollars. The agency table reconciles to the report's
narrative totals (SBIR -$1, STTR exact, both DoD+HHS concentration figures exact). These are
internal arithmetic checks on the captured CSVs, not a `validation_result` in the
`studies/README.md` sense; the study rank is unchanged.

**Table 20 does not sum to the program totals** — -300,924,559 SBIR (-7.31%)
and -4,040,026 STTR (-0.65%). This is definitional: Table 20 covers Phase I
and Phase II awards while the program totals cover all obligations. Recorded so no future run
treats it as a reconciliation failure.

**The gate stays unsatisfied, deliberately.** Of the nine definitions the frozen protocol requires
verbatim, three are recovered (fiscal-year rule, dollar basis, STTR treatment), two are partial
(phase-label rollup, agency attribution), and **four are not stated in the report at all**: state
attribution, the first-time-winner lookback window, amendment and modification handling, and
zero-dollar records. Notably the report publishes the first-time-winner statistic ("39% of all
Phase I award winners were first-time winners") without its window, while a neighbouring measure
on the previous page does state one (">15 Phase IIs FY17-FY21") — so the omission is conspicuous
rather than implied.

Those four cannot be recovered from this source. Under the protocol they become documented
decisions recorded here before comparison, not assumptions buried in the implementation. They are
listed in `sources.yaml:next_actions` and remain open.

**Newly recovered, and relevant to the tolerance contract.** The report states of its own data
that it "remains current to include subsequent funding of ongoing projects" (p52) — the publisher
confirming the live database is not a frozen copy of the published table. This is independent
support for the vintage-tolerant structural check adopted in the amendment above.

## 2026-09-17 (later) — denominator-integrity check admits the published ±$1 identity

The frozen blocking check requires every total to equal the sum of its published parts.
The published Table 20 itself fails that literally: combined dollars (SBIR + STTR) are off
by exactly ±$1 on 14 of 52 rows, which `definitions-fy22.md` records as whole-dollar
presentation of sub-dollar amounts. **Deviation:** denominator integrity admits the
published ±$1 combined-dollar identity on Table 20, classified as `rounding`, and does not
fail the study. Any discrepancy other than exactly ±$1 on that identity, or any discrepancy
on the other five within-row identities, still fails the check.
