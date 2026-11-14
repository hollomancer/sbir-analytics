# Recovered definitions — SBA SBIR/STTR Annual Report, FY22

Source: `SBA_FY22_SBIR_STTR_Annual_Report.pdf`, `sha256=5ba60852f1cc44b23afdbf810ecf0cff77d714d10ffc786a9b73416d7c000fd1`
(94 pages, text layer). Quotations are **verbatim**, including the report's own typographical
errors, and each carries its PDF page number. Extracted 2026-09-17.

The frozen protocol (`design.md`) requires nine definitions before any comparison. **Three are
recovered, two are partial, and four are not stated in the report at all.** Absences are recorded
as source limitations, not filled with assumptions.

## Recovered

**1. Fiscal-year rule — awards are counted by obligation within the reporting cycle** (p9)

> Information required by statute on all awards obligated during the reporting cycle must be uploaded through SBIR.gov (SBIR Policy Directive§10(f)).

Corroborated by the minimum-spending test (p31):

> SBA determined whether the Participating Agencies met this minimum spending requirement by calculating the percentage of an agency’s extramural R/R&D obligations which funded SBIR/STTR awards and activities, as compared to an agency’s total extramural R/R&D obligations for the fiscal year.

**2. Dollar basis — obligations, not outlays or ceiling values** (p10)

> In FY22, Participating Agencies’ total SBIR obligations amounted to $4,115,812,863 of which $3,286,050,956 (80%) were attributed to DoD and HHS.

> In FY22, Participating Agencies’ total STTR obligations amounted to $618,272,163 of which $524,186,495 (85%) were attributed to DoD and HHS.

**3. STTR treatment — reported separately, with a combined total** (p52)

> Table 20 on the following page shows the total dollar amount and number of SBIR and STTR Phase I and Phase II awards across the U.S.

Table 20's header carries seven column groups: SBIR Phase I, STTR Phase I, SBIR Phase II, STTR
Phase II, SBIR Total, STTR Total, and SBIR/STTR Total. So STTR is disaggregated *and* combined;
a replication must choose the matching column rather than assume either.

## Partial

**4. Phase labels — Table 20 has only Phase I and Phase II columns.** The report discusses
Phase IIB and sequential Phase II awards elsewhere (p47, on awards exceeding guideline amounts)
but never states how those map into the two published columns. A replication must decide whether
sequential Phase II and Phase IIB roll into `Phase II`; the report does not say.

**5. Agency attribution — participating-agency level only.** Chart 1 names 11 agencies obligating
SBIR dollars and Chart 2 names 5 obligating STTR dollars. DoD components (Air Force, Navy, Army,
DARPA and the rest) are not broken out in the program-total charts, so an agency-level replication
must aggregate components to the department before comparing.

## Not stated in the report

**6. State attribution.** The report indicates firm location (p52):

> Approximately 68% of total FY22 SBIR dollars and 63% of FY22 STTR dollars went to small businesses located in California, Massachusetts, Virginia, Maryland, Pennsylvania, New York, Colorado, North Carolina, Texas, and Ohio.

but never states *which* address is used or as of *when* — the address of record at award time, or
the firm's current registered address. This matters: the SBIR.gov award export carries a single
current `State` field, so a firm that relocated after its award will land in a different cell than
the published table. Unrecoverable from this source.

**7. First-time-winner window.** The statistic is published without its rule (p48):

> For FY22, 39% of all Phase I award winners were first-time winners across the eleven Participating Agencies.

No lookback window is given — first-time relative to all prior program history, or to a fixed
number of years? Note that a *different* measure on p51 does state its window explicitly, which
makes the omission here conspicuous rather than implied:

> Multiple Award Winners (>15 Phase IIs FY17-FY21)

**8. Amendments and modifications.** No mention anywhere in the report. Whether a Phase II
modification that adds funds appears as a new award row, increases an existing row, or is excluded
is undetermined.

**9. Zero-dollar records.** No mention. Table 20 does contain zero *cells* (e.g. `ND` STTR Phase II
`0 $0`), but a zero-count cell is not a zero-dollar award record, and the report does not say how
zero- or negative-value obligations are handled.

## Also recovered — the report's own drift warning

Relevant to the vintage-tolerant reproduction contract, the report states of its own data (p52):

> This data is also publicly available on a searchable database at www.SBIR.gov and remains current to include subsequent funding of ongoing projects.

This is the publisher saying the live database is not a frozen copy of the published table: it keeps
accruing subsequent funding to projects already counted. The published cells are a point-in-time
snapshot of a source that moves afterwards, which is the condition
`StudyManifest.reproduction` exists to handle.

## Validation of the captured tables

Table 20 (52 rows: 50 states, DC, Puerto Rico) was checked against itself. Five of six
within-row identities hold **exactly** for all 52 rows: SBIR total = Phase I + Phase II (count and
dollars), the same for STTR, and the combined count. The sixth — combined dollars = SBIR + STTR —
is off by **exactly ±$1 on 14 rows** (+1 on ten, −1 on four). Consistent with the published table
summing sub-dollar amounts and presenting whole dollars; stated as inference, not established.

The agency table reconciles to the report's own narrative:

| Check | Captured | Report narrative | Difference |
| --- | ---: | ---: | ---: |
| SBIR, all agencies | $4,115,812,862 | $4,115,812,863 | −$1 |
| STTR, all agencies | $618,272,163 | $618,272,163 | $0 |
| SBIR, DoD + HHS | $3,286,050,956 | $3,286,050,956 | $0 |
| STTR, DoD + HHS | $524,186,495 | $524,186,495 | $0 |

**Table 20 does not sum to the program totals, and this is definitional, not an error.**
Table 20 totals $3,814,888,304 SBIR and $614,232,137 STTR, which fall
$300,924,559 (7.31%) and $4,040,026 (0.65%)
short of the narrative totals. Quote 3 above resolves it: Table 20 covers **Phase I and Phase II
awards**, whereas the program totals are all SBIR/STTR *obligations*, which include obligation
categories outside those two phases. Any replication must not reconcile these two figures to each
other.
