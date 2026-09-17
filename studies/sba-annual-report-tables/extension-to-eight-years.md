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

## Addendum: what the FY2014 anomaly actually is

Finding 1 above reported FY2014 recomputing 4.53% below its published state table and left the
cause open. It is now resolved, and the resolution changes how the observation should be used.

### The report has two different award counts, and they straddle the database

Each annual report states an award count in its narrative as well as in the state table. For
FY2014 the narrative (p20, corroborated at p24) gives a complete, internally consistent
breakdown - 3,162 SBIR Phase I plus 1,513 SBIR Phase II equals the stated 4,675 SBIR total, and
492 STTR Phase I plus 213 STTR Phase II equals the stated 705 - for **5,380 new awards**. The
state table on p25-26 totals **5,513**. The database holds **5,263**.

| Report year | Narrative | State table | Database | Table vs narrative | Database vs narrative |
| --- | ---: | ---: | ---: | ---: | ---: |
| FY2013 | 5,154 | 5,091 | 5,103 | -1.22% | -0.99% |
| FY2014 | 5,380 | 5,513 | 5,263 | **+2.47%** | **-2.17%** |

**The 4.53% gap is not one large effect.** It is the published state table sitting 2.47% above the
report's narrative count and the database sitting 2.17% below it - two discrepancies of about the
same size in opposite directions, which compound. Whether either is an *error* is not established;
see the basis question below. Neither alone is remarkable against the
2.92% already observed in FY2016. FY2013 shows both numbers on the same side of its narrative and
within 1.25%, so the straddling is specific to FY2014.

By program, SBIR drives it: narrative 4,675, table 4,802, database 4,561. STTR is close on all
three (705 / 711 / 702). Within SBIR the table's excess over its narrative is concentrated in
Phase II, +115 of +133.

### This is not recent churn

The award-year counts for 2012 through 2018 are **identical across all three export vintages**
(2026-05-11, 2026-08-30, 2026-09-17) - zero change in any year. The FY2014 shortfall is a stable
structural difference, not a deletion in progress, and these older report-years are no longer
accreting at all. That further undercuts the report-age story in Finding 2: the years that should
show the most accumulated drift are the ones that have stopped moving.

### Consequence for the band

**FY2014 should be excluded from the envelope, for a reason that is now specific rather than a
suspicion: the basis of its state table is undetermined.** The report gives two different award
counts and does not say what its state table counts, so for that year the table is not a sound
comparison target. Excluding it, the one-sided +3% total-count band holds
across the remaining seven years (+0.24% to +2.92%), though Finding 2's point stands: it holds as
an empirical envelope, not because of the time signature the derivation claims.

The database is nonetheless below the narrative in both FY2013 and FY2014, by 0.99% and 2.17%. So
the direction of Finding 1 survives - the database can hold fewer awards for a year than the
publisher counted - even though the FY2014 magnitude is inflated by a discrepancy inside the report whose cause is
undetermined. A
one-sided band remains unsafe in principle; it is the -4.53% figure that should not be used to
size it.

### A separate finding: the award-year field is the wrong basis

Testing what basis reproduces the published counts best, across the six years where
`Proposal Award Date` coverage exceeds 90%:

| Basis | Mean absolute error vs published |
| --- | ---: |
| Federal fiscal year on the award date (Oct-Sep) | **0.88%** |
| `Award Year` field (what the implementation uses) | 1.71% |
| Calendar year on the award date | 4.22% |

A federal-fiscal-year basis on `Proposal Award Date` fits about twice as well as the `Award Year`
field the implementation currently uses. This is not actionable for the full panel yet - date
coverage is 98% or better from award-year 2015 onward but only 76% to 81% for 2011 to 2014, so the
basis cannot even be evaluated for FY2013 or FY2014, let alone adopted for them. Recorded as a
candidate improvement to the recomputation for FY2015 onward, not adopted.

### Is the FY2014 report in error? Not established - and the obvious explanation fails

An earlier draft of this record called the table-versus-narrative gap an error in the report. That
was not established and the claim is withdrawn. Two candidate explanations were tested and neither
holds.

**Candidate 1: the state table counts prior-year awards while the narrative counts only new ones.**
This is the natural reading, because from FY2016 the reports state exactly that split for dollars -
counts are new awards only, dollars include prior-year funding - and because FY2014's narrative
does separate the two, naming $41.2M of SBIR obligations against prior-year Phase I awards and
$596.7M against prior-year Phase II. **The arithmetic refutes it.** The table's excess over the
narrative in SBIR Phase II is 115 awards. Spreading $596.7M across 115 awards implies $5.19M each,
about 35 times the $150K median FY2014 award in the export; at that median the same sum would cover
roughly 3,978 awards, not 115. The excess is far too small to be the prior-year population and the
dollars are far too large to be those 115 awards.

**Candidate 2: the table is on the total-obligations basis throughout.** Also unsupported. The
table's SBIR dollars total $2.046B, which sits 11.1% below the narrative's stated ~$2.3B of total
SBIR obligations and 27.9% above its ~$1.6B of new-award obligations - neither basis. STTR is worse
in the other direction: the table's $284M exceeds even the narrative's stated $231M total by 23.1%.
The narrative's dollar figures are rounded to one or two significant figures, so this test is weak
in any case; it simply fails to support either basis rather than ruling one out.

**What is established.** The FY2014 report contains two award counts that differ by 2.47% - an
exact narrative breakdown that sums correctly to 5,380 new awards, and a state table totalling
5,513 - and it does not state what its state table counts. Later reports do state it. The cause of
the difference is undetermined on the available evidence, and calling it an error attributes a
defect to the publisher that this analysis cannot demonstrate.

That is enough to exclude FY2014 from a tolerance envelope, because a comparison target of unknown
basis cannot size a band. It is not enough to say the report is wrong.

### Why FY2014 differs: it predates the counting convention later reports state explicitly

The previous section established that FY2014's table-versus-narrative gap is real and withdrew the
claim that it is an error. Localising it identifies the cause, and also shows that one step in that
withdrawal was itself wrong.

**The gap is confined to a single cell.**

| FY2014 cell | Narrative | State table | Database |
| --- | ---: | ---: | ---: |
| SBIR Phase I | 3,162 | 3,174 (**+0.38%**) | 3,086 (-2.40%) |
| SBIR Phase II | 1,513 | 1,628 (**+7.60%**) | 1,475 (-2.51%) |
| STTR Phase I | 492 | 491 (**-0.20%**) | 493 (+0.20%) |
| STTR Phase II | 213 | 220 (**+3.29%**) | 209 (-1.88%) |

Three of the four cells agree with the narrative to better than 0.4%. Only **SBIR Phase II**
diverges, by 7.60%. So this is not a whole-table offset and not a transcription problem - a parse
fault would not spare three columns and hit one. Separately, the database is **uniformly 1.9% to
2.5% below the narrative in every cell**, which is a single consistent shortfall unrelated to the
table question.

**The basis statement is absent before FY2016 and present from FY2016.**

| Report year | "The number of awards are only for new awards during FYxx" |
| --- | --- |
| FY2013, FY2014 | **absent** |
| FY2016, FY2017, FY2018, FY2020, FY2021, FY2022 | present |

The FY2013 and FY2014 tables are introduced only as showing "the total dollar amount and number of
SBIR and STTR Phase I and Phase II awards", with no restriction to new awards, while their
narratives say "new". From FY2016 SBA added the sentence that fixes the count basis explicitly.
**FY2014 differs because it belongs to the era before that convention was stated.**

That also predicts where the divergence should land. The FY2014 report names $41.2M of SBIR
obligations against prior-year Phase I awards and **$596.7M against prior-year Phase II** - 14.5
times as much. If an unstated basis admits continuing awards, Phase II is overwhelmingly where it
would show, and Phase II is exactly the cell that diverges. FY2013 fits the same picture from the
other side: its table sits 1.22% *below* its narrative, which is what an unsettled rather than a
systematic basis looks like.

**Correcting the previous section.** That section refuted the continuing-award reading by dividing
the $596.7M of prior-year Phase II obligations across the 115-award excess to get $5.19M per award.
**That arithmetic was invalid**: the $596.7M spans every prior-year Phase II award receiving FY2014
money, a much larger population than the 115 rows by which the table exceeds the narrative. The two
figures describe different sets and cannot be divided into one another. The refutation is withdrawn;
the continuing-award reading is not excluded and is now the best-supported explanation.

**What was tested and does not explain it.**

- *A localised database gap.* No agency shows an anomalous FY2014 dip. Against the mean of FY2013
  and FY2015, DoD is -34.5 awards, HHS +161.5, NASA +65.0, NSF -48.5 - ordinary variation. The
  database's FY2014 is normal.
- *Second or sequential Phase II awards.* Only **15** FY2014 SBIR Phase II awards carry a tracking
  number that already held a Phase II, against 23 in FY2015 and 22 in FY2016. Far short of 115, and
  not distinctive to FY2014. (An earlier version of this test counted 494 by matching any prior
  tracking number, which is wrong: a Phase II shares its number with its own Phase I, so that
  counts normal progressions.)
- *A total-obligations basis for the whole table.* The table's SBIR dollars of $2.046B sit 11.1%
  below the narrative's stated total and 27.9% above its new-award figure; STTR exceeds even the
  stated total by 23.1%. The narrative dollars are rounded to one or two significant figures, so
  this test is weak either way, but it does not support a whole-table basis switch - consistent
  with the divergence being confined to one cell rather than applying throughout.
- *A restatement in a later report.* FY2015, FY2016 and FY2017 contain no restatement of FY2014
  award counts, so no later volume adjudicates it.

**Status.** Best-supported explanation, not established. What is established is that the divergence
is confined to SBIR Phase II, that FY2013 and FY2014 state no count basis while FY2016 onward do,
and that continuing-award funding in FY2014 is concentrated in Phase II by 14.5 to 1. Settling it
would need SBA's FY2014 table-construction methodology, which the corpus does not contain.

**Consequence, unchanged.** FY2014 stays out of the tolerance envelope, and the reason is now
sharper: its state table's count basis is unstated and its one divergent cell is consistent with a
basis the later reports explicitly rule out. A comparison target on a different basis cannot size a
band. This applies to FY2013 equally - both years predate the convention - so the envelope should
rest on FY2016 onward, where the basis is stated.
