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
source line, not a parse error. All 53 jurisdiction codes printed across these years are covered
by `us-jurisdiction-strict-v1`, including AS, so no published-table row is dropped. On the export
side there is exactly one out-of-grid exclusion per affected year; see the note under Finding 1.

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

**One export row is excluded from the recomputation, explicitly.** The pinned export carries
exactly one award-year-2014 row whose `State` is Marshall Islands (verified by scanning the full
export: two MH rows in total, award-years 2014 and 2019, the same firm).
`us-jurisdiction-strict-v1` maps Marshall Islands to no code — a deliberate profile decision —
and the published FY2014 table prints no MH row, so the row is recorded here as an out-of-grid
exclusion rather than silently dropped: 5,263 of the 5,264 export rows enter the comparison.
Admitting MH would be a versioned profile change, not an implementation choice.

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

The committed cell band covers 99.80% of the 1470 non-zero cells across eight years; 3 non-zero
cells breach it (FY2014 KY SBIR Phase I +8 on 15 published; FY2017 AZ STTR Phase I +7 on 11;
FY2017 RI SBIR Phase I +8 on 5). Two maxima must not be conflated. The largest **negative**
deviation is FY2014 CA SBIR Phase II, 351 published against 310 recomputed (-41). The largest
**absolute** deviation is FY2018 AZ SBIR Phase I, **0 published against 44 recomputed (+44)** —
a zero-published cell outside the 1470, faithfully captured (the report prints 0 and the row's
SBIR total identity holds), and one that breaches even the widened floor, since
max(8 rows, 20%) of zero published is 8.

**FY2014 should not be pooled until it is understood.** Its published table may rest on a different
year basis, in which case it belongs outside the envelope rather than inside a widened one. Widening
a band to absorb an observation that may be definitionally different would be fitting the contract
to an artefact - the same error this study has avoided elsewhere. The honest options are to
investigate FY2014's basis first, or to adopt the two-sided ±5% band and record FY2014 as its
justification.

## Provenance

Recomputation uses the pinned 2026-09-17 export
(`studies/sba-annual-report-tables/award-export-2026-09-17.meta.json` records the retrieval).
The newly captured tables live under `data/`; the extension comparisons live under `extension/`,
a separate directory from the study's `results/` deliverables because design.md requires a
current-data extension to be reported separately with separate claims — a generic consumer of
`results/` must never pick these up as study output. The comparison is
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

## Does it make sense to extend? Yes — to six years, not eight

The reach question and the basis question give different answers, and the basis question governs.

**Eight report-years are extractable. Six are usable.** FY2013, FY2014 and FY2015 predate the
count-basis statement, so they cannot enter a tolerance envelope regardless of how cleanly they
parse. The usable panel is the contiguous run that states its basis:

| Report year | Basis stated | Table extractable | In the panel |
| --- | :---: | :---: | :---: |
| FY2013, FY2014 | no | yes | **no** — basis grounds |
| FY2015 | no | no (image) | **no** — both grounds |
| FY2016, FY2017, FY2018 | yes | yes | **yes, newly** |
| FY2019 | yes | no (image) | only with OCR |
| FY2020, FY2021, FY2022 | yes | yes | yes, already |

So extending **doubles** the panel from three report-years to six, spanning report ages 3 to 9, all
on one stated basis. OCRing FY2019 would make seven and close the only gap in the run. Extending to
eight would mean pooling observations on an unstated basis, which is the error this study has
avoided elsewhere.

### What the six-year panel does to the bands

| Quantity | Committed | On the six-year stated-basis panel |
| --- | --- | --- |
| Total count | +3%, one-sided | **holds** on all six: +0.85% to +2.92%, all positive - but 0.08pp headroom at FY2016 |
| Cell count | max(6 rows, 20%) | covers 99.82% of 1,112 non-zero cells; **2 breach**; tightest 100% cover is max(9 rows, 15%) |
| Dollars | none | none - the basis statement itself says dollars include prior-year funding |

### This withdraws Finding 1

Finding 1 above reported that the one-sided count band is refuted, on the strength of FY2014
recomputing 4.53% below its published table. **FY2014 is the only observation below zero, and it is
now excluded on basis grounds, so that refutation falls with it.** On the six-year stated-basis
panel every observation is positive and the one-sided band holds. Finding 1 is withdrawn as a
refutation and stands only as a caution: the FY2014 database count is also 2.17% below that report's
narrative, and FY2013's is 0.99% below its own, so the database *can* hold fewer awards for a year
than the publisher counted. That is a reason not to treat one-sidedness as structurally guaranteed;
it is not evidence that the band fails on the years the band covers.

**Finding 2 survives unchanged.** Across the six stated-basis years the deviations run +2.92%,
+1.24%, +1.32%, +2.51%, +1.44%, +0.85% at report ages 9, 8, 7, 5, 4, 3 - the largest at the oldest
and the smallest at the youngest, but not monotone in between. There is no time signature to
extrapolate from, so the band remains an empirical envelope rather than a modelled one.

**Finding 3 survives unchanged**, and is now reinforced: the very sentence that establishes the
count basis also states that the dollar column includes prior-year funding, which is why the dollar
comparison is definitionally mismatched.

### The case for doing it

Two of the three findings in this record only became visible by extending past three years, and one
of them - the count-basis change at FY2016 - bears on whether the existing three-year result means
what it says. The headroom at FY2016 is 0.08pp, so a seventh year could breach the committed band;
that is worth knowing before the band is relied on. Against that, the extension is bounded work:
the parser already handles all five new years, the layout is uniform, and every new year satisfies
its count identities exactly.

## FY2019: recovered, partial, and defective in a second way

Extracted by rasterising the embedded table image with `pypdfium2` and reading it with a vision
model, then validating against the table's own three identities - the same check every text-layer
year passes. No OCR engine was needed or installed.

### The table is partial, confirmed four ways

The maintainer asked whether "partial" was safe to assert. It is:

1. **The image is not cropped.** Its native raster is 874 x 608 px and its placement on the page is
   604.4 x 420.5 pt - aspect 1.438 against 1.437. A clipped image would be far taller natively than
   its placement allows.
2. **No other large image in the document is a state table.** Every image over 400 x 250 pt across
   all 103 pages was measured; only this one has the wide landscape table shape, the rest being
   charts at roughly 468 x 250 or 648 x 360 pt.
3. **No page is missing.** Printed page numbers run 50, 51, 52, 53 continuously, and the table of
   contents lists Table 19 as a single entry immediately followed by Table 20, which appears on the
   next printed page.
4. **The report discusses states it does not print.** Its own narrative names California,
   Massachusetts, Virginia, Maryland, Colorado, Ohio, Pennsylvania, New York and Texas as the
   concentration of FY19 dollars. **Five of those nine - VA, OH, PA, NY, TX - have no row in the
   table**, all of them alphabetically after MS.

The table covers AK through MS: 27 jurisdictions against the 53 its neighbours print.

### A second defect: the STTR phase columns are misaligned by one row

Rows AK through ME - 22 of them - satisfy every identity exactly. From MH onward the STTR phase
columns are displaced one row upward, so each row's printed STTR Total equals the *previous* row's
printed phase sum:

| Row | STTR P1 + P2 as printed | STTR Total as printed | Previous row's P1 + P2 |
| --- | ---: | ---: | ---: |
| MH | 23 / $13,824,406 | 0 / $0 | 1 / $249,250 |
| MI | 10 / $8,094,339 | 23 / $13,824,406 | **23 / $13,824,406** |
| MN | 17 / $6,838,206 | 10 / $8,094,339 | **10 / $8,094,339** |
| MO | 2 / $332,356 | 17 / $6,838,206 | **17 / $6,838,206** |
| MS | 2 / $994,290 | 2 / $332,356 | **2 / $332,356** |

Four consecutive exact matches in **both** counts and dollars - eight independent numbers - which a
transcription error cannot produce. The totals columns are internally consistent throughout and the
SBIR phase columns satisfy their identity on all 27 rows, so the displacement is confined to the two
STTR phase columns. MH printing zero STTR is also the correct value: Marshall Islands rows are all
zeros in FY2020 and FY2021.

Recorded as printed, with the five affected rows flagged in `sttr_phase_misaligned` rather than
silently corrected. Dollar residuals are at most $2 on six rows, the familiar rounding.

### What it contributes

For the 27 jurisdictions it does print, the export holds **4,263 awards against 4,250 published,
+0.31%** - the smallest deviation of any year measured, and inside the committed band. It cannot
contribute a year total, so the FY2016-FY2022 run still has a gap at FY2019 for total-count purposes.
One wrinkle FY2019 shares with FY2014: the export's second and last Marshall Islands row carries
award-year 2019, and FY2019's table *does* print an MH row — so a future FY2019 cell comparison
must handle that row explicitly instead of letting `us-jurisdiction-strict-v1` drop it silently.

## The mechanism behind the drift is the snapshot date, not the report age

FY2019's table note states something no earlier year's does: the data "reflects a snapshot in time
and was retrieved on August 13, 2021". Searching every report for such a statement found four:

| Report year | Snapshot date | Years after FY close | Deviation, same 27 jurisdictions |
| --- | --- | ---: | ---: |
| FY2019 | 2021-08-13 | 1.87 | +0.31% |
| FY2020 | 2021-09-30 | 1.00 | +2.47% |
| FY2021 | 2023-02-09 | 1.36 | +1.06% |
| FY2022 | 2023-09-13 | 0.95 | +1.28% |
| FY2016, FY2017, FY2018 | none stated | unknown | +2.94%, +1.47%, +1.89% |

All seven restricted to the same 27 jurisdictions, so jurisdiction mix is controlled.

Correlations against the deviation:

| Candidate | r |
| --- | ---: |
| Years between FY close and the snapshot | **-0.810** |
| Years between the snapshot and the 2026 export | +0.058 |
| Report age, all seven years | +0.453 |

**The signature is on the snapshot lag, and it runs opposite to the report-age intuition.** The
longer SBA waited after the fiscal year closed before taking its snapshot, the *less* the database
has since diverged from the published table - which is mechanically what should happen, because a
later snapshot already contains more of the post-close corrections. Elapsed time from snapshot to
export carries essentially no signal, which is the direct refutation of an accumulation story: what
matters is how much correction the published table already absorbed, not how long the database has
had to move since.

FY2019 and FY2020 make the point on their own. Their snapshots are seven weeks apart (August and
September 2021), so both tables were built from nearly the same database state - yet FY2019's was
taken 1.87 years after its fiscal year closed and FY2020's only 1.00 year after, and their
deviations are +0.31% against +2.47%.

**Status: four observations, correlation only.** No model was fitted and no band is proposed on this
basis - four points cannot support either. It is recorded because it names a measurable covariate
where Finding 2 could only report the absence of one, and because it sharpens Finding 2 rather than
replacing it: there is still no usable *report-age* signature, which is what Finding 2 claimed.

**It also makes the FY2023 and FY2024 reports more valuable than the corpus assessment argued.** If
those volumes state snapshot dates, they are out-of-sample tests of a specific directional
prediction, not merely two more observations.
