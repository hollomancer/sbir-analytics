# How SBA assembles the annual-report tables — recovered from the source

Answers the question the amendment blocker rested on: what counting rule does SBA apply when
building the published tables from agency submissions? **The methodology is documented in the
reports themselves**, most explicitly in the FY2016 volume. It is not a counting rule.

Sources: `FY16 SBIR Annual Report 04082019.pdf` (sha256 `ac82797e2798df9f6a6ceaae6c3134eac720e070d8bf3c5f0d98ac17d30c6e7d`),
`SBIR-STTR_FY_2012_Report_Final.pdf`, and the FY2020–FY2022 volumes already pinned in `sources.yaml`.

## The assembly rule

FY2016, p39 — SBA states the design intent directly:

> "SBA requires the data in this report to be a summation of the individual awards uploaded to SBA.
> This ensures the report data matches that available through the SBIR.gov site."

The published tables are the **sum of the individual award records agencies upload**, and they are
intended to equal SBIR.gov. There is therefore no separate amendment- or modification-counting rule
to recover: at publication, the table and the database were meant to be the same number.

The same page describes the upload path:

> "The DoD Office of Small Business Programs (OSBP) collects all the component data and uploads it
> through the SBA Annual Report submission site."

FY2020–FY2022 carry the weaker standing form of this (p12/p23, p12/p23, p11/p22 respectively):

> "This data was submitted by the Agencies through the SBA annual report submission site, verified
> by SBA, and further analyzed to develop percent ratios for many of the reported fields."

## Why the database now exceeds the published tables

FY2016, p39, on that year's DoD data:

> "The DoD had significant challenges in submitting their FY16 data with the first submission being
> 177 days late... After a review of the data SBA determined that it was incomplete and would need
> to be resubmitted."

> "SBA has worked closely with DoD over the last year and received many additional uploads in an
> effort to correct the data with the last upload used for this report being received in December
> 2018."

> "If SBA identifies substantial corrections to the data in this report, SBA intends to update the
> data through SBIR.gov. SBA determined it was more important to publish the FY16 report and focus
> on preparing the FY17 and FY18 reports."

**That is the mechanism.** Post-publication corrections are pushed to the database; the published
report is not revised. SBA's accuracy assessment for that year's data, after the corrections:

> "SBA and the DoD have spent substantial resources in correcting and validating this data and SBA
> now believes the funding and award data to be over 95% accurate."

That figure is specific to FY2016 DoD data and is not a general claim, but a ~5% residual brackets
the surplus measured here.

The FY2012 Reporting Agency Scorecard (p24, p34) shows the same pattern in table form: DoD
"Original 04/24/2013, Resubmission 04/23/2014" against a 03/15/2013 deadline — a resubmission a
full year after the original.

## Submission timeliness in the study years

Each report prints an agency submission table (FY20 p9–10, FY21 p9–10, FY22 p9–10).

| Report | DoD submitted | Deadline | Days late | Row surplus vs export |
| --- | --- | --- | ---: | ---: |
| FY2020 | 2021-08-12 | 2021-03-15 | 150 | +180 (+2.52%)¹ |
| FY2021 | 2022-08-11 | 2022-03-15 | 149 | +98 (+1.44%) |
| FY2022 | 2023-03-15 | 2023-03-15 | **0** | +56 (+0.85%) |

Every other agency submitted within a few days of deadline in all three years (earliest EPA, 33
days early in FY22); DoD is the entire lateness story. That is consistent with the surplus being
almost entirely SBIR, where DoD is the largest agency, and with STTR reconciling to 0.00–2.00%.

**Extraction caution.** The FY2020 and FY2021 tables *print* "1501" and "1491" in the days column.
Those are 150 and 149 with a footnote marker flattened into the digits by text extraction. Verified
against the stated 03/15 deadlines: 2021-03-15 to 2021-08-12 is exactly 150 days, and 2022-03-15 to
2022-08-11 is exactly 149. **Do not read those cells literally.**

Three observations cannot separate "DoD submitted late" from "more elapsed time since publication" —
they order identically here. Both mechanisms are now documented rather than hypothesised.

¹ The FY2020 window holds 7,316 export rows, of which one carries a blank jurisdiction and
cannot be placed in any published cell. Counting all 7,316 gives +180 (+2.52%); the implementation
compares the 7,315 placeable rows and reports +179 (+2.51%). Both figures appear in this study and
differ by exactly that row.

## What this resolves

The blocker as framed — decide how amendments are counted — **dissolves**. Supporting measurements,
all against the pinned 2026-09-17 export:

- Distinct `(Contract, Phase)` pairs, the most defensible award key, **exceed** the published count
  by +144/+81/+45. SBA counts fewer awards than there are distinct award actions, so no merging rule
  can close the gap; the difference is records the published count did not contain.
- After de-duplicating on `Contract`, the residual awards have **distinct contract numbers** — 116
  more distinct contracts in FY2020 than awards published. These are separate awards, not
  modifications of counted ones.
- `Contract` is a project identifier, not an award identifier: of 421 duplicate-contract groups,
  89.5% have differing amounts, only 19.5% stay within one phase, 67.5% span more than one award
  year, and DOE accounts for 703 of 853 rows (82%).
- `Agency Tracking Number` is shared across awards: de-duplicating on it **undershoots** by
  −42/−105/−123.
- Eliminated: agency coverage (export and published chart both carry exactly the same 11 SBIR
  agencies), zero-dollar records (none exist in the window), jurisdiction exclusion (1 row of
  20,836).

The surplus is therefore a **vintage** phenomenon, not a definitional one, and it falls under the
reproduction contract already in `sources.yaml` — extended from dollars to counts.

## What this does not resolve

The exact publication-era figure cannot be reconstructed. SBIR.gov serves only the current snapshot
(`docs/data/awards-refresh.md`), so no report-era export survives to compare against. Any
replication compares a corrected database to an uncorrected published table, and the tolerance must
absorb that difference rather than pretend it away.

## Derived count tolerances

Basis: **632** published cells (state x program x phase) across FY2020–FY2022, compared against
the pinned export. Of those, **569 carry a non-zero published count**; the remaining 63 are
printed as zero and reach at most 2 awards in the export, inside the six-row floor. Both bands
below were verified to cover 100% of the full 632 and of the 569 non-zero subset.

| Tolerance | Band | Basis |
| --- | --- | --- |
| Total award count | one-sided, export may exceed published by up to **+3%** | observed +0.85%, +1.44%, +2.51%; one-sided because correction only adds records |
| Per-cell award count | **max(6 rows, 20%)** | tightest band on the tested grid covering 100% of 569 cells; `max(4 rows, 20%)` covers 99.82% |

A hybrid band is required because the two failure modes differ by cell size. Small cells move a
little in absolute terms but enormously in relative terms; large cells the reverse:

| Published cell size | Cells | Match exactly | Max abs deviation | Max relative |
| --- | ---: | ---: | ---: | ---: |
| 1–5 | 171 | 66% | 4 rows | 200% |
| 6–20 | 194 | 40% | 4 rows | 50% |
| 21–100 | 156 | 17% | 13 rows | 29% |
| 101+ | 48 | 4% | 23 rows | 13% |

Cells sum to the 569 non-zero cells. **Match exactly** here is count-only agreement, which is why
it differs from the stricter `exact` class in `results/comparison_cells.csv`, where a cell must
also agree on dollars.

The 101+ row is what the largest single deviation belongs to. Largest single deviation: FY2020 CA
SBIR Phase II, published 466 against 489 in the export (+23,
+4.9%).

**The per-cell band is wide because it absorbs two superimposed effects**, and a replication must
not read it as a count tolerance alone. Only 41.5–46.6% of cells match exactly, and cells run under
as often as over (FY2022: 62 over, 49 under, net +56). The under-cells are firm relocation — FL +16,
CO +15, NC +12, TX +8 gaining against PA −7, DE −7, VA −6, WA −5 losing — i.e. the state-attribution
tolerance, not the count surplus. At least 83–97 rows per year sit in the wrong cell. Validate
totals against the count band and cells against the combined band; do not attribute cell
displacement to counting.

## Secondary finding — a caveat on the fiscal-year definition

`definitions-fy22.md` records the fiscal-year rule as recovered from FY22 p9 ("all awards obligated
during the reporting cycle"). FY2016 p39 adds a caveat that stands against it:

> "SBA would also like to receive that data by the funding appropriation year and funding obligation
> year. This would enable SBA to report both by obligation year and year of funding appropriation to
> address the challenge DoD has in obligating SBIR funding at the same rate as other funding."

So SBA states it **cannot currently** distinguish obligation year from appropriation year for DoD.
The recovered rule stands, but for the largest agency the obligation-year basis is not cleanly
separable. Recorded rather than acted on.

Relatedly, FY2020–FY2022 all repeat verbatim:

> "SBA cannot validate whether DoD met the SBIR/STTR minimum spending requirements because the total
> extramural R/R&D obligations is unknown, and the budget authority may be different."
