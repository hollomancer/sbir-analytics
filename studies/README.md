# Study contracts

This directory records the epistemic status of analyses without changing the runtime
package structure. Each study lives at `studies/<study-id>/study.yaml`; CI verifies its
schema, frozen-artifact hashes, and implementation entry points.

The status vocabulary is intentionally small:

- `exploratory`: useful working analysis, not a stable result;
- `reproducible`: specified inputs and implementation can be rerun;
- `validated`: the study's preregistered validation design was run as written
  and its result, with uncertainty, is on the record. `validated` does **not**
  mean the threshold was met; it means the test was fair and its outcome is
  known. A manifest at `validated` or `citable` must carry both a
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

- `citable`: `validated`, with `threshold_met: true`, and approved for the
  claims listed in its manifest;
- `retired`: retained for provenance but superseded or no longer supported.

These ranks are the only backing for reserved **Status** words in
[`docs/research-questions.md`](../docs/research-questions.md):

| Inventory Status | Required `evidence_status` |
|---|---|
| `Computable` / `Partially computable` | `reproducible` or higher |
| `Validated` | `validated` with a met threshold, or `citable` |
| `Citable` | `citable` |

An exploratory study does not authorize `Computable`. CI
(`scripts/ci/check_research_question_status.py`) rejects a reserved Status
claim whose *section* ID is missing from every live manifest or whose highest
matching study is below the required rank. Authorization is per section
(`B2`, `F3`), not per question bullet. Negations (`Not computable`, `never
computable`, `not yet validated`, `no citable claim`, `non-citable`) are
refusals and do not need a study; the negating word has to come before the rank
word, so `Citable claim: …` still reads as a claim. The verb `validates` is not
the `validated` rank.

Promotion changes the manifest only after the study meets the next status's requirements.
A manifest does not make an analysis citable by itself, and a closed materialization gate
must name the unresolved blocker.

A `validated` study whose `threshold_met` is `false` is a legitimate and useful end state:
it says the preregistered test was run fairly and the method did not clear its own bar.
That is a finding, and it may be cited as one. What it may not do is authorize the
substantive claim the design was meant to support, and it does not become `citable`.

External analysis providers (see
[`docs/research/external-analysis.md`](../docs/research/external-analysis.md)) are
execution backends, not study contracts. Imported artifacts live under
`studies/<id>/exploratory/external/<provider>/<run-id>/` and are always
`exploratory` / not citable. They cannot promote the study.
