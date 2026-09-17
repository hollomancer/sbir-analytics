# Extending the structural check from three report-years to eight

Answers the maintainer's question "how far can we extend?" and reports three findings that bear
directly on the committed reproduction contract. **Two of the three go against work already
committed on this branch.** Nothing in `study.yaml` is changed by this record; the band decisions
it implies need maintainer sign-off, on the same basis as every other band in this study.

## How far the corpus reaches

| Report year | State table | Status |
| --- | --- | --- |
| FY2013 | present, text layer | **extractable** (needed decimal-point and dash-pair handling) |
| FY2014 | present, text layer | **extractable** |
| FY2015 | listed in contents, not in text layer | needs OCR |
| FY2016 | present, text layer | **extractable** |
| FY2017 | present, text layer | **extractable** |
| FY2018 | present, text layer | **extractable** (53 jurisdictions; includes AS) |
| FY2019 | listed in contents, not in text layer | needs OCR |
| FY2020-FY2022 | already captured | in the study |
| FY2012 | state totals only, no program/phase grid | partial: year and state level only |
| FY2009-FY2011 | no state table located | unavailable |
| pre-2009 | separate SBIR and STTR volumes, mostly no text layer | unavailable without OCR |

**Eight report-years are extractable now** - FY2013, FY2014, FY2016, FY2017, FY2018, FY2020,
FY2021, FY2022 - which is 1,672 published cells against 632 today. FY2015 and FY2019 would make
ten if their tables are OCRed. FY2012 can contribute only a state-level total.

All five newly parsed years satisfy every count identity exactly (SBIR total = Phase I + Phase II,
likewise STTR, and combined = SBIR + STTR, on every row). Dollar residuals are at most $1 except
FY2013, where one row misses by $10 - that is the publisher's arithmetic, verified against the
source line, not a parse error. All 53 jurisdiction codes across these years are covered by
`us-jurisdiction-strict-v1`, including AS, so no row is dropped.

### One layout for every year, and a correction

FY2013 through FY2022 all use the **interleaved** column order - SBIR Phase I, STTR Phase I, SBIR
Phase II, STTR Phase II, then the three total pairs. During this work I briefly suspected the
committed FY2020-FY2022 captures were mis-mapped; they are not. Checked against the source line
for FY2022 NC (`84 $22,639,960 35 $9,468,368 74 $111,994,115 ...`), the committed CSV is correct:
`sbir_tot_n` 158 = 84 + 74. The error was in a throwaway parser written during this extension, not
in the study.

## Finding 1: the one-sided count band is refuted

`published_table_tolerances` bands the total count **one-sided at +3%**, on the stated ground that
post-publication correction can only add records. **FY2014 recomputes 4.53% BELOW its published
table** - 5,263 against 5,513.

This is not an export gap. The export holds 5,264 rows for award-year 2014, sitting normally between
its neighbours (5,103 for 2013 and 5,170 for 2015), so no records are missing from the file. The
published FY2014 table counts roughly 250 awards that the current database no longer holds *under
that award year*. Records can therefore leave a year bucket - by deletion or by having their award
year revised - and accretion is not the only process acting.

The deficit is broad rather than local: SBIR Phase II -9.40%, SBIR Phase I -2.77%, spread across
every large state (CA -59, VA -32, MA -25, TX -24, MD -22). It is not one jurisdiction and not one
cell.

## Finding 2: the time-signature justification does not survive

The band's derivation argues for extrapolability from a monotone relationship with report age
(+2.51%, +1.44%, +0.85% at ages 5, 4, 3). Over eight years there is no such relationship:
**FY2013 is +0.24% at age 12 while FY2016 is +2.92% at age 9.** The three-year monotonicity was
coincidence. The band may still be defensible as an empirical envelope, but not on the mechanism
the derivation claims.

## Finding 3: the published dollar column is not comparable to a recomputation

This is the most consequential finding, and it supersedes my own earlier explanation of the dollar
behaviour as post-publication amount revision. Every report from FY2016 onward - including all three
years already in the study - states beneath the table:

> "The number of awards are only for new awards during FY19. The dollars obligated includes funding
> for both new and prior year awards."

(FY2019 p52; the same sentence appears at FY2016 p52, FY2017 p57, FY2018 p54, FY2020 p54,
FY2021 p52 and FY2022 p54, with the year changed.)

So the published counts and the published dollars are **on different bases**. Counts are new awards
in the report year. Dollars include obligations against awards made in earlier years. The
recomputation sums `Award Amount` over rows whose `Award Year` equals the report year, which is the
new-award basis for both columns - correct for counts, wrong for dollars by construction.

The dollar deltas are therefore measuring a definitional mismatch, not database drift. That is a
stronger reason not to band them than the one currently recorded, and it means no number of
additional report-years would make a dollar band meaningful. A dollar comparison would first need an
obligation-year basis that this export does not carry.

Incidentally this also explains the sign reversal that has been unexplained until now: whether the
mismatch runs positive or negative in a given year depends on how much prior-year funding that
year's report absorbed, which has no reason to be monotone.

## What the bands would become

Recorded as derivations, not adopted.

| Quantity | Committed | Over 8 years | Excluding FY2014 |
| --- | --- | --- | --- |
| Total count | +3%, one-sided | **two-sided, ±5%** | +3% one-sided still holds |
| Cell count | max(6 rows, 20%) | **max(8 rows, 20%)** | max(8 rows, 20%) |
| Dollars | none | none, and now for a documented reason | none |

The committed cell band covers 99.80% of the 1470 non-zero cells across eight years;
3 cells breach it. The largest single deviation is FY2014 CA SBIR Phase II, 351 published
against 310 recomputed.

**FY2014 should not be pooled until it is understood.** Its published table may rest on a different
year basis, in which case it belongs outside the envelope rather than inside a widened one. Widening
a band to absorb an observation that may be definitionally different would be fitting the contract
to an artefact - the same error this study has avoided elsewhere. The honest options are to
investigate FY2014's basis first, or to adopt the two-sided ±5% band and record FY2014 as its
justification.

## Provenance

Recomputation uses the pinned 2026-09-17 export
(`studies/sba-annual-report-tables/award-export-2026-09-17.meta.json` records the retrieval).
Newly captured tables and the year and cell comparisons accompany this record. The comparison is
year-total and cell-level counts only; it does not run the committed implementation's difference
classification, so it is an extension measurement rather than a validated study result and is not
citable.
