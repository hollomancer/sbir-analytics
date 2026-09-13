# Promotion plan — `phase-iii-census`

**From:** `reproducible`
**To:** `validated`

This is the cleanest study in the repository and the only one with a realistic
path to a *met* threshold. It has a frozen, fixture-verified design, two frozen
artifacts, four registered implementations, materialization allowed, and zero
open blockers. Nothing is in its way. It simply has never been given a
validation design.

It also already has most of one, half-built and unfinished.

## What is already in place

- **A frozen estimand** — uncoded post-completion follow-on procurement proxies
  among exact-UEI Phase II award and federal prime contract action pairs, under
  every preregistered time-window and agency-continuity cell.
- **A materialized result** — the complete February cumulative ladder and all
  six sensitivity cells, from provenance-verified inputs, with the blocking
  one-factor check passing.
- **A negative control that ran** — under the frozen fixed-seed cross-firm
  completion-date placebo, the actual frame exceeds the placebo frame on every
  complete-filter metric and in every cell.

That last item is a validation design in everything but name. It was
preregistered, it was frozen, it ran, and it separated. What it does not have is
uncertainty.

## The gap that matters

The study's own first limitation states it plainly:

> The materialized placebo is one non-uniform cyclic derangement, not an
> inferential permutation distribution; labeled validation remains unresolved.

One derangement gives a direction, not a magnitude. "The actual frame exceeds
the placebo" is true, and with a single draw there is no way to say whether that
margin is large or whether a second derangement would have produced the same
ordering by chance. `ValidationResult` requires an interval and an interval
method, and a single draw cannot supply either.

## Two candidate designs; only one is reachable

### A. Permutation separation — **recommended, achievable now**

Replace the single derangement with N independent fixed-seed derangements and
record where the observed statistic falls in the resulting empirical null.

- `threshold_basis: proportion`
- `threshold_value`: the preregistered separation level, e.g. the observed
  statistic must exceed the null in at least a stated fraction of draws
- `numerator` / `denominator`: draws the observed value exceeded, over draws run
- `interval_method`: an exact binomial or Wilson interval on that proportion

This needs no new data, no labels, and no external corpus. The placebo machinery
is already frozen and already ran once; the change is running it N times and
recording the distribution. **This is the design to preregister.**

### B. Labeled precision of the proxy — **not reachable**

Measure how often an uncoded lineage proxy corresponds to a real statutory
Phase III award. This is the question a reader most wants answered, and it
cannot be answered here: there is no adjudicated ground-truth label set, which
is exactly what "labeled validation remains unresolved" records. Attempting it
would mean building the label set first, which is a separate study.

## What `validated` would and would not mean here

Under design A, `validated` would mean: **the observed separation from the
frozen placebo is larger than chance, by a preregistered margin, with a stated
interval.**

It would *not* mean the proxy identifies genuine Phase III awards. The study's
own limitation already says an uncoded lineage proxy is not proof of a statutory
Phase III award, and promotion must not be read as retiring that sentence. The
distinction should be written into `permitted_claims` at promotion time, not
left for a reader to infer.

This matters more than usual because `validated` with a met threshold is the
rank that authorizes the public `Validated` word in the inventory. That word
will be read as "this measures Phase III correctly" unless the manifest says
otherwise in its own voice.

## Steps

1. Write the permutation design: N, the derangement construction, the seed
   policy, the statistic, `threshold_basis`, `threshold_value`, and
   `threshold_derivation` including the power to clear it at N draws.
2. **Freeze it before running** — add it to `frozen_artifacts` and commit, so
   `design_path` and `design_sha256` can point at pinned bytes and
   `confirmatory: true` is defensible from the PR's own commit order. Note the
   ordering lives in the PR's history, not in `main`'s, once squash-merged.
3. Run N derangements against the frozen inputs. Record the full distribution,
   not only the summary.
4. Write `validation_result` with the numerator, denominator, interval, method,
   and `threshold_met`.
5. Rewrite `permitted_claims` and `limitations` so the separation claim and the
   not-a-statutory-Phase-III claim both survive promotion.
6. Set `evidence_status: validated`; if the threshold is met this becomes the
   repository's first `Validated` inventory rank, so run `evidence-auditor`
   before merging.
7. `uv run python scripts/ci/validate_study_manifests.py` and
   `uv run python scripts/ci/check_research_question_status.py`.

## Why this is the one worth doing

The other two candidate promotions both terminate in records rather than
findings: `ma-discovery-recall` records a missed threshold, and
`transition-scoring` reaches `reproducible` without measuring anything. This
study is the only one where a preregistered test can plausibly *pass*, and where
passing would authorize a public rank the repository does not currently hold.

It is also the largest piece of work of the three, and it is research work
rather than paperwork.
