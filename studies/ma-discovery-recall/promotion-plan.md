# Promotion plan — `ma-discovery-recall` — CLOSED

**Outcome:** the study stays `exploratory`. The held-out 1501-2500 result is
recorded with `confirmatory: false`, `threshold_met: false`, and five
`post_hoc_analyses` entries. Implemented 2026-09-13.

This plan originally proposed promoting to `validated` with a missed threshold,
on the reasoning that PR #726 made a fair-test-that-failed a legitimate
`validated` end state. That reasoning is sound and the promotion still fails,
for a reason the plan did not consider.

## Why it fails

`study.yaml` pins `held-out-1501.md` at `e7090020...`. Those bytes first exist
in git at `9bcb6dc9`, **2026-09-09 07:30:41 EDT**. The replay ran
**2026-09-08 21:25 EDT**; the capture ran 09-07 to 09-08.

The pinned design postdates the run it is supposed to have preregistered by
about ten hours. `confirmatory` asserts the design bytes were fixed in git
before the evaluated run, so it is false on the schema's plain wording, and
`StudyManifest` refuses to promote a study whose result is not confirmatory.

No weighing of the recorded provenance defects is required. The plan's central
question — whether a frozen design carrying a false sentence still counts as
frozen — was the wrong question.

## What the plan got wrong, recorded so the errors are not repeated

1. **It classified two of the four recorded defects as "instrument" problems.**
   Both are design-compliance problems. The `unverified_empty` retry class was
   introduced after 948 of 1000 rows existed and applied to 476 of them; retry
   eligibility must be pre-specified, and re-querying changes the snippets
   freeze that determines the number.
2. **It stated that the frozen bytes still carry the uncorrected claim.** They
   do not. The pinned `e7090020` contains the correction and the superseded
   hash. The sentence quoted was from `provenance_defects[2]`, written in the
   present tense against an earlier version — so a frozen manifest now
   misdescribes another frozen artifact, which is its own defect and is recorded
   as a fifth post-hoc entry.
3. **It presented `4 of 307` as the preregistered metric.** The denominator is a
   replay output. The preregistered gate is a count floor of 10 over the
   1000-pair cut. The interval is a post-hoc enumeration and is labelled as one.
   It does not change the outcome: 4 is below 10 on any denominator.

## What holds

`held-out-1501.yaml` is byte-identical from `0023e204` to `main`, and the diff
on `held-out-1501.md` from that commit forward is a pure insertion — 89 lines
added, nothing deleted or modified. The estimand, cut, stop rule, and the floor
of 10 were fixed before capture and were not moved to fit a 4. **The miss is
real and honestly reported.** Only the confirmatory label fails.

## Where the numbers now live

`study.yaml` carries a full `validation_design` and `validation_result` at
`exploratory` — the schema's early return allows it, so declining the promotion
costs no recorded detail. `amendments.md` records the audit, the merge-strategy
lesson, and the four conditions a later cut would have to meet.

## The separate finding

`0023e204` is not reachable from `main`: PR #699 was squash-merged and five
commits collapsed into `fff0cef3`. The freeze ordering is legible only in a
deleted branch. That is a genuine provenance problem, it will recur, and it is
recorded in `amendments.md` — but it is **not** what blocked this cut. Restoring
the pre-capture hash would make things worse, since that version authorizes no
retry class and the run re-queried 476 rows under one.
