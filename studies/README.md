# Study contracts

This directory records the epistemic status of analyses without changing the runtime
package structure. Each study lives at `studies/<study-id>/study.yaml`; CI verifies its
schema, frozen-artifact hashes, and implementation entry points.

The status vocabulary is intentionally small:

- `exploratory`: useful working analysis, not a stable result;
- `reproducible`: specified inputs and implementation can be rerun;
- `validated`: the study's stated validation design has passed.
  A manifest at `validated` or `citable` must carry a `validation_design` block:

  ```yaml
  validation_design:
    addressable_population: >-
      How many units the estimand can reach, and how that was counted.
    expected_yield: >-
      What the study expects to find, from what prior.
    decision_threshold: >-
      The number the result must clear.
    threshold_derivation: >-
      Why that number, and the power to clear it at the expected yield.
  ```

  Write it before capture. Its purpose is to make a study state, in advance,
  whether it could detect the effect it is looking for.
  The M&A discovery recall study, landing with PR #705, failed three times
  against a recall floor of 10 that was never normalised to a shrinking
  eligible pool; at the observed detection rate that floor passes about 30%
  of the time even when the method works as measured.
- `citable`: approved for the claims listed in its manifest;
- `retired`: retained for provenance but superseded or no longer supported.

These ranks are the only backing for reserved **Status** words in
[`docs/research-questions.md`](../docs/research-questions.md):

| Inventory Status | Required `evidence_status` |
|---|---|
| `Computable` / `Partially computable` | `reproducible` or higher |
| `Validated` | `validated` or higher |
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
