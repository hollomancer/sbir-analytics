# Prospective Fidelity Validation — Structural Comparison v1

**Status:** Candidate freeze. Do not run the evaluated extraction until this
file and the blank population are committed and the pre-run evidence audit is
recorded.

## Validation target

This validation tests whether the study faithfully captures and transforms its
declared sources. It does not test whether SBIR.gov and the annual reports agree.
It does not validate the existing `+3%` or `max(6, 20%)` bands.

The addressable population contains 1,264 values:

- 632 published award-count cells transcribed independently from the FY2020,
  FY2021, and FY2022 report PDFs; and
- 632 export-derived award-count cells computed independently from the pinned
  September 17, 2026 award export.

The blank population in `validation-population-v1.csv` fixes every eligible
unit before the evaluated extraction. It contains keys and target types only.
It contains no expected count values.

## Sources

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| FY2020 annual-report PDF | 2,505,195 | `f1f51abb29c71d631451868f31babf2f6f1fe3845df91e534052f1d40dece3d3` |
| FY2021 annual-report PDF | 2,444,751 | `30b4dfa9b4c2c2220fc15938d5bd1a44bee92d5aa746b8756dc7d66217c6df55` |
| FY2022 annual-report PDF | 2,038,536 | `5ba60852f1cc44b23afdbf810ecf0cff77d714d10ffc786a9b73416d7c000fd1` |
| SBIR.gov award export | 394,636,989 | `aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a` |

The reviewer must verify these identities before extraction. A source with a
different byte count or digest is ineligible for this run.

## Independence boundary

The independent extractor receives only:

1. this design;
2. the four verified source files;
3. the blank validation population; and
4. the jurisdiction mapping in the next section.

Before submitting values, the extractor must not read:

- `studies/sba-annual-report-tables/data/`;
- `studies/sba-annual-report-tables/results/`;
- the comparison script or its tests;
- prior comparison prose that states cell values; or
- any filled validation output.

The extractor records its identity, extraction tools and versions, start and
finish times, and the SHA-256 of every output. A separate coordinator compares
the submitted values with the production sidecar only after submission is
frozen.

## Published-count extraction

For each `published_count` unit, read the cell printed in:

- FY2020 Table 18;
- FY2021 Table 18; or
- FY2022 Table 20.

Use the row keyed by the printed state or territory abbreviation and the column
keyed by program and phase. Extract award counts only. Do not extract or use
dollar values. Preserve printed zeros. Do not infer a count from a row total.

Every submitted value records the report year, table number, PDF page, and a
short locator that another reviewer can follow. A value that cannot be read is
submitted as missing; it is not inferred.

## Export-derived extraction

For each `recomputed_count` unit, use an implementation independent of the
production study code and shared award-export loader. The reference extraction
must:

1. parse the CSV with a standard RFC 4180-aware parser;
2. require the exact ordered 42-column header recorded in the source metadata;
3. keep one countable unit per parsed source row, with no deduplication;
4. parse nonblank `Award Year` values as integers without a date fallback;
5. keep FY2020, FY2021, and FY2022 only;
6. keep only `SBIR` and `STTR` program values;
7. keep only `Phase I` and `Phase II` phase values;
8. drop a blank `State` and report the number dropped;
9. map a nonblank full state or territory name to the printed USPS code using
   the explicit mapping below, and fail on any unmapped value; and
10. count rows by report year, jurisdiction, program, and phase, filling an
    eligible cell with zero when no row maps to it.

The expected dropped-blank count is not disclosed to the extractor. The
coordinator records it after submission as a diagnostic, not as a decision
threshold.

### Jurisdiction mapping

Use this frozen full-name-to-code mapping. Alternate spellings are not accepted
silently. `Marshall Islands` is present because the published tables contain an
`MH` row; the production study years contain no export row with that value.

```text
Alabama=AL; Alaska=AK; Arizona=AZ; Arkansas=AR; California=CA
Colorado=CO; Connecticut=CT; Delaware=DE; District of Columbia=DC; Florida=FL
Georgia=GA; Hawaii=HI; Idaho=ID; Illinois=IL; Indiana=IN; Iowa=IA
Kansas=KS; Kentucky=KY; Louisiana=LA; Maine=ME; Maryland=MD
Marshall Islands=MH; Massachusetts=MA; Michigan=MI; Minnesota=MN
Mississippi=MS; Missouri=MO; Montana=MT; Nebraska=NE; Nevada=NV
New Hampshire=NH; New Jersey=NJ; New Mexico=NM; New York=NY
North Carolina=NC; North Dakota=ND; Ohio=OH; Oklahoma=OK; Oregon=OR
Pennsylvania=PA; Puerto Rico=PR; Rhode Island=RI; South Carolina=SC
South Dakota=SD; Tennessee=TN; Texas=TX; Utah=UT; Vermont=VT
Virginia=VA; Washington=WA; West Virginia=WV; Wisconsin=WI; Wyoming=WY
```

The extractor records the implemented mapping as a separate output before
seeing production values. No address history or firm relocation inference is
part of this validation.

## Decision rule

**Threshold basis:** `count_on_frozen_population`

**Threshold value:** 1,264 exact values out of 1,264 frozen units.

The complete population is checked, so this is a reconciliation threshold, not
a sampling estimate. Its interval is recorded as `[1.0, 1.0]` with method
`complete-population reconciliation; no sampling interval` only if all 1,264
values agree.

The threshold is strict because the target is deterministic transcription and
transformation fidelity. One unequal or missing value is enough to show that the
released sidecar does not faithfully implement its source contract.

## Failure and adjudication

The coordinator first classifies a disagreement as one of:

- independent-extraction defect;
- production capture defect;
- production transformation defect;
- source identity failure; or
- unresolved.

That classification requires direct source evidence. Agreement with a tolerance
band is not evidence. Dollar values cannot affect a count classification.

If any unit is unequal or missing, this confirmatory run records
`threshold_met: false` and cannot promote the study. Corrections may be reported
as post-hoc work. A new promoting run requires a new independent extractor and
an amended design frozen before that extractor begins.

## Permitted interpretation after a pass

A pass supports this statement only:

> An independent full-population extraction reproduced every published and
> export-derived count value used by the FY2020-FY2022 structural comparison.

A pass does not establish historical-vintage reproduction, source completeness,
official-report equivalence, dollar comparability, commercialization outcomes,
or program effects.
