# Study contracts

This directory records the epistemic status of analyses without changing the runtime
package structure. Each study lives at `studies/<study-id>/study.yaml`; CI verifies its
schema, frozen-artifact hashes, and implementation entry points.

## Immutable release registry

`studies/releases.yaml` binds a completed study to an annotated release tag, commit, and Git tree.
CI validates that tagged tree instead of applying the moving repository environment to the release.
For a released study, CI checks the implementation files in the tagged release tree, not their HEAD copies.
It also requires the current `studies/<study-id>/` subtree to have the tagged paths and bytes.
Checksum errata must name one exact path and both expected hashes. Unused or changed errata fail.

The status vocabulary is intentionally small:

- `exploratory`: useful working analysis, not a stable result;
- `reproducible`: specified inputs and implementation can be rerun;
- `validated`: the study's preregistered validation design was run as written
  and its result, with uncertainty, is on the record. `validated` does **not**
  mean the threshold was met; it means the test was fair and its outcome is
  known. A manifest at `validated` or `approved` must carry both a
  `validation_design` block and a `validation_result` block:

  ```yaml
  validation_design:
    addressable_population: >-
      How many units the estimand can reach, and how that was counted.
    expected_yield: >-
      What the study expects to find, from what prior.
    decision_threshold: >-
      What the result must clear, in the quantity threshold_basis names.
    threshold_derivation: >-
      Why that level, and the power to clear it at the expected yield.
    threshold_basis: proportion          # or count_on_frozen_population
    threshold_value: 0.60                # the same threshold as a number;
    #   checked against the basis, so a count floor cannot be filed as a
    #   proportion. A proportion basis takes a value in (0, 1]; a count basis
    #   takes a whole number.
    # frozen_population_artifact: studies/<id>/eligible_units.csv
    #   required when threshold_basis is count_on_frozen_population; must
    #   also appear in frozen_artifacts.

  validation_result:
    design_path: studies/<id>/design.md
    #   the frozen artifact that was evaluated; a study may pin several
    #   designs (a pilot and a confirmatory one), so it is named, not inferred
    design_sha256: <hash of that design as pinned before the run>
    evaluated_on: 2026-09-13
    metric: strict recall on held-out pairs
    numerator: 13
    denominator: 19
    interval_low: 0.460
    interval_high: 0.848
    interval_method: Wilson 95%
    threshold_met: true
    confirmatory: true
    post_hoc_analyses: []
  ```

  Write the design before capture. Its purpose is to make a study state, in
  advance, whether it could distinguish success from failure. For a census or
  enumeration, describe expected coverage and reconciliation criteria instead
  of inventing an effect size. Three rules govern the pair:

  1. **Thresholds are proportions unless the population is frozen.** A
     `decision_threshold` stated as an absolute count is only meaningful over
     a population fixed with the design. `threshold_basis:
     count_on_frozen_population` therefore requires
     `frozen_population_artifact`, pinned in `frozen_artifacts`. A count floor
     over a population that shrinks as capture proceeds becomes unreachable
     for reasons unrelated to the study, and CI rejects it.
  2. **The result travels, with its interval.** `validation_result` records
     numerator, denominator, and a confidence interval with its method. Every
     number the study emits carries this result alongside it. A reader
     discounts a 13/19; a reader cannot discount "passed".
  3. **Confirmatory and post-hoc are both reportable, and only one promotes.**
     `design_path` and `design_sha256` must match a `frozen_artifacts` entry
     exactly -- the hash must belong to the design the result names, not merely
     to some pinned file. `confirmatory: true` additionally asserts those bytes
     were fixed in git before the evaluated run; the schema does not check that
     ordering, so the auditor verifies it against history. Analyses
     run after the data were seen — an enlarged cut, a restated cost cap, a
     changed eligibility rule — are listed under `post_hoc_analyses` and may be
     reported anywhere the study is reported, labelled as such. They cannot be
     the `confirmatory` result and cannot promote the study. What is forbidden
     is not post-hoc analysis; it is post-hoc analysis presented as
     confirmation.

- `approved`: `validated`, with `threshold_met: true`, plus one final pinned
  `claim_approval` review authorizing the claims listed in its manifest. The
  review path and SHA-256 must also appear in `frozen_artifacts`.
  `claim_boundary_sha256` binds the approval to the exact `estimand`,
  `permitted_claims`, and `limitations` that were reviewed; compute it with
  `sbir_etl.quality.study_manifest.claim_boundary_sha256`. A later edit to any
  of them fails validation until a new review records the new digest. The review
  must be its own file, not the validation design or population, and its text
  must contain the study ID and the `claim_boundary_sha256` value it approves.
  `approved_on` cannot be in the future. A `claim_approval` block is rejected
  below `approved`:

  ```yaml
  claim_approval:
    review_path: studies/<id>/reviews/claim-approval.md
    review_sha256: <hash of the final approval review>
    claim_boundary_sha256: <digest of estimand, permitted_claims, and limitations>
    approved_on: 2026-09-23
  ```
- `retired`: retained for provenance but superseded or no longer supported.

These ranks are the only backing for reserved **Status** words in
[`docs/research-questions.md`](../docs/research-questions.md):

| Inventory Status | Required `evidence_status` |
|---|---|
| `Computable` / `Partially computable` | `reproducible` or higher |
| `Validated` | `validated` with a met threshold, or `approved` |
| `Approved evidence` | `approved` |

An exploratory study does not authorize `Computable`. CI
(`scripts/ci/check_research_question_status.py`) rejects a reserved Status
claim whose *section* ID is missing from every live manifest or whose highest
matching study is below the required rank. Authorization is per section
(`B2`, `F3`), not per question bullet. Negations (`Not computable`, `never
computable`, `not yet validated`, `no approved evidence`) are
refusals and do not need a study; the negating word has to come before the rank
word, so `Approved evidence: …` still reads as a claim. The verb `validates` is not
the `validated` rank.

Promotion changes the manifest only after the study meets the next status's requirements.
Evidence approval is independent of operational materialization and bibliographic citation.
A closed materialization gate must name its operational blocker. A study result may be cited
from an immutable release only when the study is `reproducible` or higher, and only with its
actual evidence status attached. Exploratory and retired studies may not be cited.

A `validated` study whose `threshold_met` is `false` is a legitimate and useful end state:
it says the preregistered test was run fairly and the method did not clear its own bar.
That is a finding, and it may be cited as one. What it may not do is authorize the
substantive claim the design was meant to support, and it does not become `approved`.

## Captured published tables

This convention comes from `sba-annual-report-tables`. `allocation-transaction-costs` also
keeps transcribed tables in `data/`. Apply the convention to any new study that captures a
published table.

A study that reproduces a published table keeps its transcription of that table at
`studies/<study-id>/data/*.csv`. One CSV holds one printed table for one report year.
`studies/sba-annual-report-tables/data/` follows this layout. It does not yet meet every rule
below: its `sources.yaml` hashes only the FY2012, FY2016, FY2020, FY2021, and FY2022 PDFs.

Apply these rules when you capture a table:

1. Record each value exactly as printed.
2. Do not correct a printed value, even when it is wrong.
3. Flag a defect in a separate column. Do not edit the value.
4. Hash each source PDF with SHA-256.
5. Record the hash in the study's `sources.yaml`.
6. Validate the table against its own identities before you use it.
   For example, a total must equal the sum of its parts.
7. Investigate each identity failure.
8. Read the source line to find the cause.
9. Fix a transcription error in the CSV.
10. Keep a source defect as printed.
11. Record the source defect in a flag column or in the study's amendments.

Examples from `studies/sba-annual-report-tables`, each verified against its source PDF:

- FY1995 California prints 665 Phase I and 280 Phase II awards with a total of 940.
  The parts sum to 945. `data/awards_by_state_fy95.csv` keeps 940
  (`extension-to-eight-years.md`).
- In FY2019, from the MH row onward, the STTR phase columns are one row out of place.
  `data/awards_by_state_fy19_partial.csv` keeps the printed values and sets
  `sttr_phase_misaligned` to `True` on the affected rows
  (`extension-to-eight-years.md`).
- Six FY2020 and FY2021 cells print zero awards with positive dollars. The CSVs keep
  them as printed (`amendments.md`).

A comparison output can also exclude a cell because of a source defect. Give the reason
in an `exclusion_reason` column. `extension/extension_fy2019_cells.csv` uses this column.

### Image-only PDFs

Some report PDFs have no text layer. `studies/sba-annual-report-tables` read these tables
without an OCR engine:

1. Rasterise the page images. The study used `pypdfium2`.
2. Render labelled contact sheets of the volume.
3. Use the contact sheets to find the pages that hold the table.
4. Transcribe the table from the rasterised image with a vision model.
5. Validate the transcription against the table's identities, as for any other table.

A one-row shift in a column has a clear signature. Each row's printed total equals the
previous row's sum of parts. Read the source line to find where the shift occurs. In
FY2019, the shift is in the printed report, not in the transcription.

## Extension outputs

This convention also comes from `sba-annual-report-tables`, the only study with an
`extension/` directory today.

An extension applies a study's code to years or cells outside the study's declared scope.
Write extension outputs to `studies/<study-id>/extension/`. Do not write them to
`results/`. A generic consumer of `results/` must never read an extension as study output.
Report an extension separately from the study's result, with its own claims.
State in the extension's own record whether it may be cited. The
`sba-annual-report-tables` extension is not citable because it skipped difference
classification (`extension-to-eight-years.md`).

This rule comes from `studies/sba-annual-report-tables/design.md`. Its "Two separate
products" section keeps the published-sample replication and the current-data extension
apart. Its "Done when" section requires that "the current-data extension, if run, is
reported in a separate directory with separate claims."
`studies/sba-annual-report-tables/extension/` holds that study's extension outputs.
`extension-to-eight-years.md` in that study records them as not citable.
