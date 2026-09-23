# Prospective Fidelity Validation — SBA Structural Comparison v1

**Status:** Candidate freeze. Do not run the evaluated extraction until Revision 1
records approval, the frozen hashes, the named roles, and the release commit.

## Validation target

This validation tests source-capture and transformation fidelity. It does not
test whether SBIR.gov and the SBA annual reports agree. It does not validate the
post-hoc `+3%` total band or the post-hoc `max(6, 20%)` cell band.

The estimand is the signed and absolute difference for all 632 award-count cells
printed in these tables:

- FY2020 Table 18;
- FY2021 Table 18; and
- FY2022 Table 20.

Each printed cell is compared with a count computed from the pinned September
17, 2026 SBIR.gov export. The computation uses one parsed export row as one
countable unit. It uses the `Award Year` field. It does not deduplicate rows.

The addressable validation population contains 1,264 operands:

- 632 published award-count values transcribed independently from the PDFs; and
- 632 export-derived award-count values computed independently from the CSV.

The blank population in `validation-population-v1.csv` fixes every eligible
operand before extraction. It contains keys and target types only. It contains
no expected values.

This design does not reproduce the unavailable publication-era SBIR.gov
export. A pass supports fidelity of this current-vintage comparison only.

## Prior expectation and detection boundary

The prior expectation is 1,264 exact agreements out of 1,264 if source capture
and both transformations are correct.

The complete population gives full detection power for any defect that changes
one or more of these 1,264 values. It does not detect shared-mode rule errors.
It does not cover values outside the fixed estimand. It does not validate the
meaning, completeness, or correctness of either upstream source.

## Source identity and preflight

`source-manifest.json` fixes the four source identities, the three captured
table identities, and the ordered 42-column export header. Verify every byte
count, digest, row or page count, and schema field before use.

Abort the run without a validation score when any of these conditions holds:

1. A source or captured table is missing.
2. A byte count or SHA-256 does not match.
3. A durable source URI cannot retrieve the declared bytes.
4. A page count, parsed row count, column count, or ordered header does not
   match.
5. The design, population, production implementation, or production sidecar
   does not match its frozen digest.
6. The blind packet is incomplete or has a digest mismatch.
7. The extractor has seen production values or prior cell-level results.

A source-identity, packet-integrity, or blinding failure is an invalid run. It
is not a zero-score validation result.

## Production target

The coordinator must create the final count-only production sidecar before the
independent extractor starts. The freeze record must identify:

- the release commit;
- the production implementation path and SHA-256;
- the production sidecar path and SHA-256;
- every source and captured-table SHA-256;
- the design and population SHA-256; and
- the environment lock SHA-256.

The production sidecar contains mechanical facts only:

- report year, table, jurisdiction, program, and phase;
- published count;
- export-derived count;
- signed difference;
- absolute difference; and
- `exact` or `unresolved` comparison status.

The sidecar contains no tolerance-band verdict. It does not infer
`revised_upstream`, `pipeline_defect`, firm relocation, or another cause from a
difference. Dollar values do not enter this product.

For each row, the producer must enforce:

```text
signed_difference = export_derived_count - published_count
absolute_difference = abs(signed_difference)
comparison_status = exact if signed_difference == 0 else unresolved
```

The producer must block on a wrong arithmetic result, an unexpected key, a
duplicate key, a missing key, or any output-schema mismatch.

Any later change to a count, rule, implementation, sidecar, or frozen input
requires a new validation run.

## Independence boundary

The coordinator and independent extractor must be different named roles. Record
both identities before the run. The extractor receives one checksummed minimal
packet. The packet contains only:

1. this design;
2. `source-manifest.json`;
3. the four verified source files;
4. the blank validation population;
5. the jurisdiction mapping in this design; and
6. the submission schema and extraction instructions in this design.

The packet must not contain a repository checkout. Before sealing a submission,
the extractor must not read:

- captured table CSVs;
- production source code or tests;
- production sidecars or rendered results;
- historical comparison results; or
- any filled validation output.

The extractor records an exposure attestation. It states whether any prohibited
material was seen. A positive or missing attestation aborts the run.

Before unblinding, record these immutable facts:

- packet SHA-256;
- extractor identity;
- coordinator identity;
- tool names and versions;
- independent extraction implementation SHA-256;
- jurisdiction-mapping output SHA-256;
- start and finish times;
- submitted output SHA-256; and
- sealed production-sidecar SHA-256.

Use the first sealed submission. Do not repair a mismatch and call the repaired
submission confirmatory. Preserve the first submission, every failed run, and
every amendment.

## Independent published-count extraction

For each `published_count` unit, read the cell printed in FY2020 Table 18,
FY2021 Table 18, or FY2022 Table 20.

Use the printed jurisdiction row. Use the printed program and phase column.
Extract award counts only. Do not extract dollar values. Preserve printed zero.
Do not infer a count from a row total.

Identify a jurisdiction row from its printed label and the table's count-column
geometry. A numeric line with no mapped jurisdiction label is not by itself a
jurisdiction row. It can be a continuation, header, footer, or total. Exclude
such a line only after the PDF structure shows that it is outside the printed
jurisdiction rows. Abort if the line could be an unreadable jurisdiction row.
Do not classify every line with the table's numeric-column count as a
jurisdiction row.

Independently verify table completeness before submission:

- FY2020 has 53 printed jurisdiction rows;
- FY2021 has 53 printed jurisdiction rows;
- FY2022 has 52 printed jurisdiction rows;
- each row has four eligible count columns; and
- no printed key is omitted or duplicated.

A value that cannot be read is submitted as missing. It is not inferred.

## Independent export-derived extraction

Use an implementation independent of the production code and the shared award
export loader. Apply these rules in order:

1. Parse the CSV with an RFC 4180-aware parser.
2. Decode with `utf-8-sig`.
3. Require the exact ordered header in `source-manifest.json`.
4. Keep one countable unit per parsed source row.
5. Do not deduplicate.
6. Parse every nonblank `Award Year` as an integer without a date fallback.
7. Abort on an invalid nonblank `Award Year` in any source row.
8. Retain FY2020, FY2021, and FY2022.
9. Require retained `Program` values to be exactly `SBIR` or `STTR`.
10. Require retained `Phase` values to be exactly `Phase I` or `Phase II`.
11. Treat blank or unexpected retained program or phase values as blocking.
12. Drop a retained row with blank `State` and record the number dropped.
13. Map every nonblank retained `State` with the frozen mapping below.
14. Abort on an unmapped state value.
15. Abort when a mapped key is outside the frozen population.
16. Count rows by report year, jurisdiction, program, and phase.
17. Fill an eligible absent group with zero.

The expected dropped-blank count is not disclosed. Record it after submission
as a diagnostic. It is not a decision threshold.

### Jurisdiction mapping

Use this exact full-name-to-code mapping. Do not accept alternate spellings.

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

Write the implemented mapping to a separate output. Seal its SHA-256 before
unblinding. Do not make an address-history or firm-relocation inference.

## Submission schema

Submit UTF-8 CSV with this exact ordered header:

```text
unit_id,target,report_year,table_number,jurisdiction,program,phase,value,status,source_page,source_locator,missing_reason
```

Apply these constraints:

- Submit exactly 1,264 unique `unit_id` values.
- Match every unit in `validation-population-v1.csv` exactly once.
- Use integer `report_year` and nonnegative integer `value`.
- Use `status=observed` when `value` is present.
- Use `status=missing` and an empty `value` when extraction fails.
- Require a nonempty `missing_reason` only for `status=missing`.
- Require `table_number=18` for FY2020 and FY2021 published values.
- Require `table_number=20` for FY2022 published values.
- Leave `table_number` empty for export-derived values.
- Require `source_page` and `source_locator` for published values.
- Leave `source_page` empty for export-derived values.
- Require `source_locator` for every value.
- Reject any extra column, key, target, year, jurisdiction, program, or phase.

The population-completeness checker must derive the 53, 53, and 52 printed row
counts from the PDFs. It must not use captured CSVs or the production sidecar.

## Decision rule

**Threshold basis:** `count_on_frozen_population`

**Threshold value:** 1,264 exact values out of 1,264 frozen units.

Compare the first sealed submission with the sealed production sidecar. Record
the numerator and denominator for every complete evaluated run.

Record an exact complete-population point interval:

```text
interval_low = interval_high = numerator / 1264
interval_method = exact complete-population point interval; no sampling
```

One unequal or missing value sets `threshold_met: false`. A failed evaluated
run remains on the record. It cannot materialize a citable result.

## Failure handling

Do not adjudicate a mismatch into confirmatory agreement. After unblinding, a
reviewer may classify direct evidence as one of:

- independent-extraction defect;
- production-capture defect;
- production-transformation defect;
- source-identity failure; or
- unresolved.

The classification is diagnostic only. The first sealed score does not change.
A new promoting run requires a new extractor and a new approved freeze.

## Permitted interpretation after a pass

A pass supports this statement only:

> An independent full-population extraction reproduced all 1,264 published and
> export-derived count operands used to calculate the 632 differences in the
> FY2020-FY2022 current-vintage structural comparison.

A pass does not establish publication-era reproduction, source completeness,
official-report equivalence, award-dollar comparability, commercialization
outcomes, program effects, M&A linkage, or trust in other repository outputs.
