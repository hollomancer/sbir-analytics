# NIH SBIR versus R01-equivalent allocation transaction costs

**Audience:** OSTP, agency R&D directors, SBIR program managers, GAO/OMB staff
**Evidence status:** reproducible under `studies/allocation-transaction-costs/study.yaml`; not approved for citation
**Date:** 2026-09-12
**Command:** `uv run python scripts/data/allocation_transaction_costs.py`

> **Conclusion:** result depends on specific observable assumptions. A
> directional claim that SBIR allocates federal R&D with lower transaction
> cost per awarded dollar is currently underidentified. The identified
> result is the break-even hour count.

Hours per award, dollars per award, and cost per awarded dollar are kept
separate. They are not one efficiency score.

## Finding

NIH public data measure applications, awards, success rates, and award
size. They do not measure how long a small business spends on an SBIR
proposal. Once award size and success rate are in the formula, that
missing hour count is what decides the ranking.

For NIH SBIR Phase I versus R01-equivalent grants, if an R01 takes 160
applicant hours, a Phase I proposal could consume only **45–69 hours**
before cost per awarded dollar equals, when R01 size is treated as an
**annual** average. If that same R01 is treated as a **four-year
project**, the threshold falls to **11–17 hours**. No cell in the 20–200
hour SBIR grid beats a 160-hour R01 under the four-year convention.

That is the competing hypothesis in numbers: smaller awards and lower
success rates can offset a shorter proposal.

Algebra, same wage, agency cost omitted:

```text
h_sbir* = h_r01 × (s_sbir × D_sbir) / (s_r01 × D_r01)
```

`s` is awards / applications. `D` is mean award dollars under a named
duration convention.

## What public data can and cannot establish

| Quantity | Status | Evidence class |
|---|---|---|
| NIH applications, awards, success rates | Measured in RePORT Table #215 and Data Book report 29 | Administrative counts |
| NIH award dollars / average size | Table #215 total funding; Data Book report 158 annual average | Accounting / administrative |
| Phase I vs Phase II vs Fast Track vs STTR | Separated in Table #215 | Administrative counts |
| Applicant hours, SBIR firms | Not observed | — |
| Applicant hours, university R01 PIs | FDP 2018 time-use survey; wrong population for SBIR | Behavioral survey, transfer only |
| Reviewer hours | Reviewer *count* is a convention (~3); hours are scenarios | Proxy + assumption |
| Agency selection cost | 3% statutory SBIR admin ceiling only; CSR budget not allocatable | Statutory cap / missing |
| PRA burden hours | Not used | Administrative estimate, refused |
| University F&A rates | Not used | Wrong construct, refused |

## NIH mechanism-year comparison

Sources: RePORT Table #215 (SBIR/STTR, FY2015–2025) and NIH Data Book
reports 29 + 158 (R01-equivalent). Success rates below are recomputed as
awards / applications, not the rounded published percentages.

| Year | SBIR I apps / award | R01-eq apps / award | SBIR I mean $ | R01-eq annual mean $ | SBIR I $ / application | R01-eq annual $ / application |
|---|---|---|---|---|---|---|
| 2015 | 6.7 | 5.3 | 227,842 | 435,525 | 34,193 | 82,189 |
| 2020 | 8.0 | 4.7 | 271,945 | 559,680 | 33,805 | 119,918 |
| 2023 | 6.4 | 4.6 | 323,896 | 600,957 | 50,723 | 130,089 |
| 2024 | 10.1 | 5.4 | 330,834 | 606,393 | 32,834 | 113,260 |
| 2025 | 12.8 | 7.7 | 352,780 | 664,005 | 27,556 | 86,449 |

R01-equivalent still delivers more awarded dollars per application in
every overlapping year, even on the annual-size convention that *favors*
SBIR. FY2025 success rates fell on both sides (Phase I 7.8%, R01-eq
13.0%).

STTR Phase I is a different mechanism: FY2024 6.6 applications per award
and mean $342,797. It is not folded into SBIR. Regular Phase II is
different again (FY2024 3.7 applications per award, mean about $1.03M)
and is not combined with Direct Phase II, Phase IIB, Fast Track, or CRP.

## Break-even SBIR Phase I hours (R01 = 160 hours)

| Year | Annual-size h* | Four-year project h* |
|---|---|---|
| 2015 | 66.6 | 16.6 |
| 2016 | 50.8 | 12.7 |
| 2017 | 63.9 | 16.0 |
| 2018 | 62.7 | 15.7 |
| 2019 | 68.5 | 17.1 |
| 2020 | 45.1 | 11.3 |
| 2021 | 48.9 | 12.2 |
| 2022 | 58.5 | 14.6 |
| 2023 | 62.4 | 15.6 |
| 2024 | 46.4 | 11.6 |
| 2025 | 51.0 | 12.8 |

Scale linearly for other R01 hour assumptions: at 80 R01 hours, divide
by two; at 200, multiply by 1.25.

Example hours per funded award, not per dollar, FY2024, applicant side
only: a 40-hour Phase I proposal implies about 403 hours per funded
award (10.1 applications per award). A 160-hour R01 implies about 856
hours per funded award. Phase I still looks lighter *per award* in that
cell. It does not look lighter *per awarded dollar* once the $330k
versus $606k (annual) or $2.43M (four-year) size gap is applied.

Wage cancels when it is the same on both sides. Switching from the BLS
medical-scientist mean ($53.99/hour) to the NIH salary-cap hourly rate
($108.51) changes dollar totals, not the hour break-even.

## Sensitivity: which assumptions flip the ranking

Cost per awarded dollar, applicant + reviewer, agency cost missing,
reviewers = 3, reviewer hours = 4, R01 hours = 160, no success-rate or
size shocks:

| SBIR Phase I hours | Years cheaper, annual size (11 years) | Years cheaper, four-year R01 |
|---|---|---|
| 20 | 11 / 11 | 0 / 11 |
| 40 | 9 / 11 | 0 / 11 |
| 60 | 1 / 11 | 0 / 11 |
| 80 and above | 0 / 11 | 0 / 11 |

Duration convention dominates. Award size is next. Success-rate shocks
of ±25% move the annual-size threshold but do not rescue SBIR under the
four-year convention inside this hour grid. Reviewer hours move both
sides together when both use three reviewers.

FDP 2018 university-PI time-use transfers to roughly 170 hours per
proposal. That number is the wrong population for SBIR firms. If it is
used only for the R01 side, the Phase I break-even under annual size is
still about 50–70 hours.

## Proposal-complexity index (proxy, not hours)

Hand-coded from the NIH page-limit table. Formal complexity is not
observed writing time.

| Mechanism | Research strategy pages | Commercialization plan pages | RI coordination | Complexity score |
|---|---|---|---|---|
| R01-equivalent | 12 | 0 | no | 18 |
| SBIR Phase I | 6 | 0 | no | 14 |
| STTR Phase I | 6 | 0 | yes | 16 |
| SBIR Phase II | 12 | 12 | no | 33 |
| STTR Phase II | 12 | 12 | yes | 35 |

Phase I looks simpler on paper than an R01. Phase II does not: the
commercialization plan adds 12 pages on top of a 12-page research
strategy. STTR adds research-institution coordination. None of these
scores are hours.

## Agency administrative cost

`GC` is missing in the headline run. 15 U.S.C. §638 allows not more than
3 percent of SBIR program funds for administration, outreach, reporting,
and related activities. That is extra statutory funding, not NIH's total
selection cost, and not a share of the Center for Scientific Review
budget. Attaching a 3% ceiling to the SBIR side only would raise SBIR
cost per dollar and cannot support a claim that SBIR is cheaper to
administer.

University F&A rates measure awardee overhead, not allocation
transaction cost.

## Other agencies (inventory, not implemented)

| Agency | SBIR application counts | Conventional-grant comparator | This study |
|---|---|---|---|
| NSF | SBA annual reports; NSF full-proposal rates ~10–20% | Research-grant funding rate exists (~24–27%) | Not built. Project Pitch is an extra funnel with no official series. |
| DOE | SBA annual reports | Office of Science success rates are not the same object | Not matched |
| NASA | SBA annual reports; NASEM NASA review [L48] | No clean NSPIRES research-grant application series here | Not matched |
| DoD | SBA annual reports give component proposal counts | “Conventional DoD research grant” is not one mechanism | SBIR rates usable; comparator unmatched |

## What would require new primary data

| Gap | Why it binds | Smallest collection |
|---|---|---|
| SBIR/STTR applicant hours by phase | Break-even is identified; the ranking is not | Time-use survey of applicants, including unfunded firms |
| Reviewer hours by mechanism | Review cost uses scenarios | CSR / agency reviewer time logs |
| Allocated agency selection cost | `GC` is missing | Agency cost accounting that splits SBIR from R01 review |
| NSF Project Pitch counts | Full-proposal rates understate NSF burden | NSF pitch invitations and time |
| DoD research-grant application series | No matched comparator | A defined 6.1/6.2 or BAA denominator |
| STTR coordination hours | Institutional requirements differ | STTR-specific applicant time, not SBIR |

## Recommended next steps

1. Keep the NIH break-even as the public-data result. Do not promote a
   point ranking.
2. Field a bounded applicant time-use instrument on NIH Phase I and R01
   (or R01-equivalent) submissions, funded and unfunded.
3. Ask NIH whether CSR can report reviewer hours by activity code.
4. Add NSF only after Project Pitch counts are public or are explicitly
   excluded from the applicant-hour denominator.

## Conclusion

**Result depends on specific observable assumptions.** Under the annual
R01-size convention, NIH SBIR Phase I is cheaper per awarded dollar only
if Phase I proposals are short relative to R01s — on the order of 45–69
hours when the R01 is 160 hours. Under a four-year R01 project total,
that threshold is 11–17 hours. Public data do not say which hour count
is true. They do say how large the size-and-success-rate gap is.

Non-citable. Do not quote a directional efficiency ranking from this
study.
