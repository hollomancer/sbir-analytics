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

Both validated. Five of six within-row identities in Table 20 hold exactly for all 52 rows; the
sixth is off by exactly +/-$1 on 14 rows, consistent with sub-dollar amounts presented as whole
dollars. The agency table reconciles to the report's narrative totals (SBIR -$1, STTR exact, both
DoD+HHS concentration figures exact).

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
support for the vintage-tolerant reproduction adopted in the amendment above.

## 2026-09-17 (later) — Order 1 extended to FY2020 and FY2021

**Scope.** The FY22 extraction path applied unchanged to the other two report-years [L18] cites.
State tables captured and validated for all three; findings in `cross-year-fy20-fy22.md`.

**Three findings change how the comparison must be written.**

1. **The ±$1 total-column residual recurs in every year** (4 rows in FY20,
   4 in FY21, 14 in FY22, never exceeding $1). Three independent years
   support the FY22 inference of sub-dollar amounts printed as whole dollars. This is a per-cell
   allowance and belongs in the contract separately from the vintage bands, which cover upstream
   movement rather than publication rounding.
2. **The jurisdiction set is not constant.** FY20 and FY21 carry 53 rows, FY22 carries 52; the
   difference is `MH` (Marshall Islands). The jurisdiction list must be read per report, not fixed.
3. **The Phase I+II shortfall against program totals moves sharply** — -2.95% in FY20,
   -2.67% in FY21, -7.31% in FY22 on SBIR. The FY20 report names the categories
   outside Phase I/II (Phase III, TABA, CRPP, AFPP) in a per-agency table on p12. Whether FY22's
   widening is growth in those categories or a scope change in Table 20 is **not established**, and
   it must be resolved before publishing any cross-year total.

**The four undetermined definitions remain undetermined.** The corpus triage speculated the older
volumes might state what FY22 omits. They do not: state attribution, first-time-winner lookback,
amendment handling, and zero-dollar records are absent from FY2020 and FY2021 as well. Keyword
matches were incidental prose — outreach programmes for "first-time SBIR/STTR grant applicants",
DOE training "modifications", DOT "no-cost-extensions" — not counting rules. Adding report-years
does not resolve them; project decisions are required.

**Scope reduction for Order 1.** The roadmap names "first-time-winner counts and shares" as a
target. FY22 publishes it; FY2020 and FY2021 publish no such statistic. That target is a
single-year comparison in this window, not a panel.

**Not captured.** No FY20/FY21 agency-level table. Those charts do not parse reliably from the text
layer (labels wrap two agencies per line; neighbouring tables pollute the capture — one attempt
reconciled $701,449 short, a second at twice the true total). Rather than commit an unvalidated
table, the limitation is recorded: the per-agency obligation table on p12 of each report is the
better target and needs column-aligned parsing.

## 2026-09-17 (later) — three of four absent definitions closed; one blocker remains

Decisions and their measured basis are in `definition-decisions.md`. Measured against the pinned
2026-09-17 export from the canonical `mod_awarddatapublic` endpoint, FY2020–FY2022, 20,836 rows.

**First-time-winner lookback — closed by empirical recovery, not by reading the source.** Rather
than assume a rule, every combination of identity key, lookback window and counting basis was
computed for FY22 Phase I awards and compared against the published 39%. Two of three open choices
resolve decisively: the basis is **distinct awardee firms** (an awards basis yields 28.2%, so SBA
would have printed "28%"), and the window is **all programme history** (a five-year window yields
40.2%–43.2%). Notably the Multiple Award Winner chart's explicit five-year convention does not
carry over. Identity uses UEI with a normalized-name fallback via
`normalize_company_name(..., profile=ENTITY_RESOLUTION_V1)` — the repository's own profile,
imported rather than reimplemented — because UEI back-fill is uneven (34.7% of 1983–99 awards
rising to 100% of 2022–26), so a UEI-only history under-detects pre-2010 prior awards. The
recomputed FY22 rate is **38.65%** on 2,559 distinct firms.

This rule was **inferred by reproducing a published number**, which is weaker evidence than a
verbatim definition and is recorded as such. It cannot be cross-validated: FY2020 and FY2021
publish no comparable statistic. One residual choice needs maintainer sign-off — whether "prior"
means any prior SBIR/STTR award (38.65%) or a prior Phase I specifically (39.39%). Both round to
39%; the recorded decision is any prior award, on the reading that "first-time winner" refers to the
programme rather than to a phase.

**Zero-dollar records — closed as not applicable.** Of 20,836 FY20–22 export rows, **zero** have an
award amount at or below zero, or missing. No rule is required in this window. Flagged to revisit if
the panel extends to other report-years, since the measurement does not generalise.

**State attribution — closed as a tolerance rather than a rule.** The export carries a single
current address block with no award-time history, so the published cell assignment cannot be
reconstructed; the decision is to use the current value and carry the misassignment in the
tolerance. Four-month drift on 20,586 matched records: state 0.155%, city 1.200%, zip 1.637%,
address 2.230%. Two consequences are recorded: the state figure is a **floor**, not the expected
error against a table published in 2023; and **no geography finer than state** should be attempted
from this source, because relocations are mostly within-state and zip therefore drifts 11x as often.

**Amendment handling — open, and now the single gate blocker.** The export carries more award rows
than the published tables count every year, and it is not a jurisdiction effect (1 of 20,836 rows
falls outside the published jurisdiction sets). De-duplicating on the award key removes
38–44 rows a year and leaves a residual of +24 to +142, so the rule moves
**0.36%–1.99% of every published count** and touches every cell of every year. No
recommendation is recorded: the evidence is consistent with more than one counting rule. As a lead
only, 34 FY20–22 records changed award amount in place between the May and September vintages while
row counts barely moved, which would suggest the export holds one row per award rather than one per
action — not established.

**Incidental, outside this study.** `normalize_company_name` under `ENTITY_RESOLUTION_V1` is
order-sensitive: suffix stripping precedes punctuation removal, so a trailing `INC.` never matches
the ` INC` suffix and `"Acme Robotics, Inc."` and `"ACME ROBOTICS INC"` produce different keys. On
this corpus it costs nothing (0 of 17,171 UEIs split), but it would split identities against any
source that punctuates differently — which is what the Phase III census joins across. Raised
because it surfaced while validating the first-time-winner decision; it belongs to the
identity-resolution work.
