# Cross-year replication — SBA annual-report state tables, FY2020–FY2022

Extends the FY22 capture to the other two report-years [L18] cites. Same extraction path, same
internal-identity checks. Roadmap Order 1.

| Report-year | Source pages | Rows | SBIR Phase I+II | STTR Phase I+II | Awards |
| --- | --- | ---: | ---: | ---: | ---: |
| FY2020 | 53–56 | 53 | $3,429,157,542 | $454,766,126 | 7,136 |
| FY2021 | 51–54 | 53 | $3,365,675,990 | $523,097,227 | 6,783 |
| FY2022 | 53–54 | 52 | $3,814,888,304 | $614,232,137 | 6,583 |

## 1. The ±$1 residual is systematic, not an FY22 artefact

Within-row identity failures are confined to the **total-dollar** columns and never exceed **$1**.
Award-count identities hold exactly in all three years. The number of failing classes differs by
year — two in FY2020, three in FY2021, one in FY2022 — so this is not a single-class artefact:

| Year | Rows failing `sbir_tot=p1+p2` | `sttr_tot=p1+p2` | `all_tot=sbir+sttr` | Max abs residual |
| --- | ---: | ---: | ---: | ---: |
| FY2020 | 6 | 0 | 4 | $1 |
| FY2021 | 9 | 1 | 4 | $1 |
| FY2022 | 0 | 0 | 14 | $1 |

Three independent report-years all showing sub-dollar disagreement in the total columns support the
FY22 inference: the published tables sum amounts carrying cents and print whole dollars. A
replication should therefore treat a $1-per-row discrepancy as agreement, not as a defect. This
belongs in the tolerance contract as a per-cell allowance distinct from the vintage bands, which
cover a different source of movement.

## 2. Jurisdiction coverage is not constant across years

FY2020 and FY2021 carry **53 rows**; FY2022 carries **52**. The difference is **`MH`, the Marshall
Islands**, present in FY20 and FY21 and absent in FY22. All three include DC and PR.

A replication keyed on a fixed 52-row jurisdiction list would silently drop a row for FY20/FY21, and
one keyed on 53 would report a spurious missing row for FY22. The jurisdiction set must be read from
each report rather than assumed.

## 3. The Phase I+II shortfall against program totals varies sharply

Table 20 covers Phase I and Phase II awards; the narrative program totals cover all obligations.
The FY22 capture recorded this as definitional. Across years the magnitude is far from stable:

| Year | SBIR shortfall | STTR shortfall |
| --- | ---: | ---: |
| FY2020 | $-104,330,064 (-2.95%) | $-5,834,328 (-1.27%) |
| FY2021 | $-92,386,027 (-2.67%) | $-5,584,991 (-1.06%) |
| FY2022 | $-300,924,559 (-7.31%) | $-4,040,026 (-0.65%) |

FY22's SBIR shortfall is roughly **2.5x** the FY20 and FY21 shares. The FY20 report identifies the
obligation categories that sit outside Phase I and Phase II — Phase III, Technical and Business
Assistance (TABA), the Commercialization Readiness Pilot Program (CRPP), and the Administrative
Funding Pilot (AFPP) — in a per-agency table on p12. **Whether the FY22 widening is growth in those
categories or a change in Table 20's scope is not established here**, and it should be resolved
before any cross-year total is published: a panel built on Table 20 is not a panel of program
obligations, and the wedge between them moves.

## 4. The four undetermined FY22 definitions are not resolved by the earlier years

The FY22 capture left four definitions undetermined because the report does not state them. The
corpus triage speculated that earlier volumes might be more explicit. **They are not.** All four are
absent from FY2020 and FY2021 as well:

| Definition | FY2020 | FY2021 | FY2022 |
| --- | --- | --- | --- |
| State attribution | absent | absent | absent |
| First-time-winner lookback | absent | absent | absent |
| Amendment / modification handling | absent | absent | absent |
| Zero-dollar records | absent | absent | absent |

Keyword matches in FY20/FY21 turned out to be incidental prose, not counting rules: outreach
programs aimed at "first-time SBIR/STTR grant applicants" (FY20 p71, FY21 p66), DOE "minor
modifications" to training (FY20 p66), and DOT "contract modifications for no-cost-extensions"
(FY21 p89). None defines how the published tables count anything.

These four therefore need documented project decisions, and adding report-years does not help.

## 5. The first-time-winner statistic exists only in FY22

Order 1 names "first-time-winner counts and shares" as a target table. FY22 publishes the figure
("39% of all Phase I award winners were first-time winners"); **FY2020 and FY2021 publish no such
statistic at all.** That target is therefore a single-year comparison in this window, not a panel,
and the roadmap's Order 1 scope should say so.

## 6. Agency-level tables: FY22 only

The FY22 per-agency obligation chart parses cleanly and reconciles to the narrative (SBIR −$1, STTR
exact). The equivalent FY20/FY21 charts do **not** parse reliably from the text layer — labels wrap
two agencies onto one line and neighbouring tables pollute the capture; attempts reconciled at
−$701,449 and then at 2x the true total. **No FY20/FY21 agency table is committed.** The per-agency
obligation table on p12 of each report is a genuine table rather than chart labels and is the better
extraction target, but it needs column-aligned parsing that this round did not attempt.

## Substantive pattern

Award counts fall while dollars rise: 7,136 awards / $3.88B in FY2020, 6,783 / $3.89B in FY2021,
6,583 / $4.43B in FY2022 (Phase I+II, SBIR+STTR combined, from the header table above). Dollars
are flat from FY2020 to FY2021 (+0.1%) and rise 13.9% into FY2022, for a 14.0% rise across the
three years against a 7.8% fall in award count. Reported as the published tables show it; no causal reading is offered.

## Files

| File | sha256 |
| --- | --- |
| `data/table20_fy20_awards_by_state.csv` | `0c8465c210f122a75b42b5afef147f688e73cec6a82a230f0d33f377def3403c` |
| `data/table20_fy21_awards_by_state.csv` | `cb43a8ec5de2b70a97f240f329a3a19a749b0f85910b5229593a5267dc1c1cde` |
