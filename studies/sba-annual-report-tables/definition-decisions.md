# Definition decisions — sba-annual-report-tables

The frozen protocol (`design.md`) requires nine definitions verbatim from the source before any
comparison. Three were recovered and two are partial (`definitions-fy22.md`); **four were absent
from FY2020, FY2021 and FY2022 alike** (`cross-year-fy20-fy22.md`). Absent definitions become
documented project decisions recorded here, never assumptions inside the implementation.

**Status: 4 of 4 closed.** Amendment handling was closed from SBA's own methodology statement
rather than by a project decision; see `assembly-methodology.md`. The capture gate is satisfied,
but the four are closed at different evidence levels, recorded in `sources.yaml`
`definition_decisions.evidence_ladder`. Those levels are not equivalent: the first-time-winner
rule is inferred by reproducing a published figure, not recovered from the source.

Every figure below is measured against the pinned 2026-09-17 award export
(`data/raw/sbir/history/2026-09-17/award_data.csv`, canonical
`mod_awarddatapublic` endpoint), FY2020–FY2022 window, 20,836 rows.

---

## 1. Amendment and modification handling — **CLOSED from source methodology**

**Undetermined.** When an award is later modified — funds added, an option exercised, a no-cost
extension granted — does the published table show a second row, an increased row, or nothing?

**Why it blocks.** The export carries more award rows than the published tables count, every year,
and it is not a jurisdiction effect: only 1 of 20,836 FY20–22 rows falls outside the published
jurisdiction sets.

| Year | Export rows | Distinct award keys | Duplicate rows | Published count | Residual after dedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| FY2020 | 7,316 | 7,278 | 38 | 7,136 | +142 (+1.99%) |
| FY2021 | 6,881 | 6,837 | 44 | 6,783 | +54 (+0.80%) |
| FY2022 | 6,639 | 6,607 | 32 | 6,583 | +24 (+0.36%) |

Award key = agency tracking number + contract + upper-cased company + award year. De-duplicating on
it removes 32–44 rows a year; a residual of +24 to +142 remains. This rule therefore moves
**0.36%–1.99% of every published count**, and it touches every cell of every year — counts and
dollars, all 52–53 jurisdictions. It is the one blocker that cannot be worked around.

**Indirect evidence on export behaviour.** Between the 2026-05-11 and 2026-09-17 vintages, 34
FY20–22 records changed their award *amount* in place (largest single change $1,928,322) while the
row count barely moved. That is the signature of modifications being folded into an existing row
rather than appended as a new one — which would make the export closer to one row per award than
one row per action, and would mean the residual above needs a different explanation. **Not
established**; recorded as a lead, not a finding.

**Closed 2026-09-17, and not by choosing a counting rule.** SBA states the published tables are
"a summation of the individual awards uploaded to SBA", so there is no amendment-counting rule to
recover; post-publication corrections are pushed to SBIR.gov while the report is not revised
(FY2016 annual report, p39). The surplus is a vintage phenomenon, carried as the count tolerances
in `sources.yaml` `published_table_tolerances`. Full evidence in `assembly-methodology.md`.

The text above is preserved as the state of knowledge before that statement was found; it is not
the current contract.

---

## 2. First-time-winner lookback — **CLOSED by empirical recovery**

**Undetermined in the source.** FY22 publishes "39% of all Phase I award winners were first-time
winners" with no window and no basis. FY2020 and FY2021 publish no such statistic at all, so this
target is single-year, not a panel.

**How it was closed.** Rather than assume a rule, every combination of identity key, lookback window
and counting basis was computed for FY22 Phase I awards and compared against the published 39%.
Identity keys use `normalize_company_name(..., profile=ENTITY_RESOLUTION_V1)` from
`sbir_etl.identity.company_names` — the repository's own profile, imported, not reimplemented.

| Basis | All program history | 5-year (FY17–FY21) |
| --- | ---: | ---: |
| Share of **awards** | 27.4%–28.8% | 29.2%–31.5% |
| Share of **distinct firms** | **37.6%–39.4%** | 40.2%–43.2% |

**Decisions.**

- **Basis: distinct awardee firms, not awards.** An awards basis yields 28.2%; SBA would have
  printed "28%". This settles the ambiguity in the phrase "Phase I award winners" — winners are firms.
- **Window: all program history, not a fixed lookback.** A five-year window yields 40.2%–43.2%,
  two to four points high. Note this means the Multiple Award Winner chart's explicit five-year
  convention (FY17–FY21, p51) does **not** carry over to this statistic.
- **Identity key: UEI, with normalized-name fallback.** Matching the convention
  `sbir_etl/extractors/README.md` already states for the Phase III census. Justification below.

Under these decisions the recomputed FY22 rate is **38.65%** on 2,559 distinct firms
(3,888 Phase I rows; the report states 3,859 awards selected, a +29 row difference that is
itself subject to decision 1).

**Residual choice, requires sign-off.** Whether "prior" means any prior SBIR/STTR award (38.65%) or
a prior Phase I specifically (39.39%). Both round to 39% and the evidence cannot separate them.
**Recorded decision: any prior SBIR/STTR award**, on the reading that "first-time winner" refers to
the programme rather than to a phase. Reversing it changes the recomputed rate by 0.74pp and
nothing else.

**Epistemic status.** This rule was **inferred by reproducing the published statistic**, not read
from the source. It is weaker evidence than a verbatim definition and must not be described as one.
It also cannot be cross-validated: FY2020 and FY2021 publish no comparable figure.

### Why UEI needs a name fallback

UEI has been back-filled onto historical awards, but unevenly:

| Award years | UEI populated |
| --- | ---: |
| 1983-99 | 34.7% |
| 2000-09 | 63.3% |
| 2010-15 | 84.8% |
| 2016-19 | 96.1% |
| 2020-21 | 99.2% |
| 2022-26 | 100.0% |

A UEI-only all-history lookback under-detects prior awards for firms whose history predates 2010 —
it would mark a 2005 winner as first-time in 2022. Name matching covers that tail, and on this
corpus the two keys are near-equivalent: **0 of 17,171 UEIs map to more than one
`ENTITY_RESOLUTION_V1` key**, i.e. SBIR.gov's Company field is internally consistent per firm. That
equivalence is why the UEI and name estimates agree to 0.01pp. DUNS yields 37.6% on 97.8%
coverage and is the weaker key.

---

## 3. Zero-dollar records — **CLOSED as not applicable in scope**

**Undetermined in the source.** No report states how zero- or negative-value obligations are counted.

**Measured.** Of 20,836 FY20–22 export rows, rows with award amount ≤ 0 or missing: **zero**. All
20,836 carry a positive amount.

**Decision: not applicable for the FY2020–FY2022 scope.** No rule is needed because no such records
exist in the window. **Revisit if the panel extends to other report-years** — the corpus triage
identifies 27 OCR-free years, and this measurement does not generalise to them.

Note the zero cells in the published state table (`ND` STTR Phase II, `0 $0`) are zero *counts*, not
zero-dollar awards, and do not bear on this.

---

## 4. State attribution — **CLOSED as a tolerance, not a rule**

**Undetermined in the source.** The reports indicate firms "located in" the named states but never
state which address is used, or as of when.

**Why no rule is recoverable.** The export carries a single current address block with no
award-time history, so the published cell assignment cannot be reconstructed. One FY2020 row has a
null state.

**Measured instability.** Across the 2026-05-11 → 2026-09-17 vintages, on 20,586 matched FY20–22
records:

| Field | Changed | Rate |
| --- | ---: | ---: |
| State | 32 | 0.155% |
| City | 247 | 1.200% |
| Zip | 337 | 1.637% |
| Address1 | 459 | 2.230% |

**Decisions.**

- **Use the export's current `State` value** and carry the resulting misassignment in the
  reproduction tolerance rather than claiming an exact rule.
- **Treat 0.155% over four months as a floor, not the expected error.** FY22 was published in
  2023; every relocation since moves a record into the wrong cell and the export offers no way to
  recover the award-time address. The tolerance band must reflect elapsed time since publication,
  not the four-month measurement.
- **Do not go finer than state.** The drift gradient is the reason: relocations are mostly
  within-state, so each finer level moves faster — zip drifts 11x as often as state over the same
  interval. State is both the most stable geography available and the only one the published tables
  use. Zip- or city-level work needs a point-in-time address source, not this export.
- **Note the representation difference:** the published tables use two-letter codes (`CA`); the
  export uses full names (`California`). Map explicitly; do not compare raw.

---

## Incidental finding, outside this study

`normalize_company_name` is order-sensitive under `ENTITY_RESOLUTION_V1`: suffix stripping runs
before punctuation removal, so a trailing `INC.` never matches the ` INC` suffix.
`"Acme Robotics, Inc."` normalizes to `ACME ROBOTICS INC` while `"ACME ROBOTICS INC"` normalizes to
`ACME ROBOTICS` — the same firm, two keys. **On this corpus it costs nothing** (0 of 17,171 UEIs
split), because SBIR.gov formats Company consistently. It would split identities against any source
that punctuates differently, which is precisely the cross-source joining the Phase III census
performs. Raised here only because it surfaced while validating decision 2; it belongs to the
identity-resolution work, not to this study.
