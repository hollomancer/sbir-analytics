# Promotion plan — `ma-discovery-recall`

**From:** `exploratory`
**To:** `validated` with `validation_result.threshold_met: false`, or a recorded
post-hoc result that leaves the study at `exploratory`.

This study was blocked four times. Two of those blocks were process defects the
discipline was right to catch. The other two were the shape of the gate, and
PR #726 changed that shape: a count floor now has to declare the frozen
population it is taken over, and `validated` now means the preregistered test
ran and its outcome is on the record, not that the threshold was met.

Everything this promotion needs is already frozen. The work is one manifest
edit and one decision.

## What is already in place

| Requirement | Where it comes from | State |
|---|---|---|
| `threshold_basis: count_on_frozen_population` | `recall_floor` is a count, not a rate | derivable |
| `threshold_value: 10` | `held-out-1501.yaml` `recall_floor` | pinned |
| `frozen_population_artifact` | `studies/ma-discovery-recall/held-out-1501.yaml`, which pins `events_sha256` | already in `frozen_artifacts` |
| `design_path` | `studies/ma-discovery-recall/held-out-1501.md` | already in `frozen_artifacts` |
| The result itself | `held-out-run-manifest.json` → `replay_result` | recorded |

## The number to record

From `replay_result` in `held-out-run-manifest.json`:

```
strict_medium_high_n:        4
strict_eligible_pairs_in_cut: 307
strict_recall_rate:          0.01303
recall_floor:                10
recall_floor_met:            false
```

As a `validation_result` block that is `4/307`, point estimate `0.01303`,
Wilson 95% `[0.0051, 0.0330]`, `threshold_met: false`.

Note the two quantities are not the same test. The floor of 10 is a count over
the cut; `4/307` is the strict recall rate. The manifest records the rate with
its interval and the count as the threshold, which is why `threshold_basis` has
to be `count_on_frozen_population` and why the floor needs its population named.

## The decision this turns on

`StudyManifest` refuses to promote a study whose `validation_result.confirmatory`
is false: a post-hoc result may be reported but cannot promote. So the whole
promotion reduces to one question.

**Can `confirmatory: true` be asserted honestly?**

The argument for yes: `held-out-1501.md` was hashed and committed before the
capture ran. That is what `confirmatory` means in the schema docstring — the
design bytes were fixed in git before the evaluated run.

The arguments against are recorded in the run manifest's own
`provenance_defects`, by the people who ran it:

1. **948 of the 1000 cut pairs were captured by code whose state is not
   recoverable from git** — the script had uncommitted changes at capture time.
   The design was frozen; the instrument was not.
2. **476 snippet rows are marked `unverified_empty`**, captured before fault
   instrumentation existed and re-queried afterwards.
3. **The frozen `held-out-1501.md` contains a statement that is false** — it
   says no Brave or LLM call had touched pairs 1501+ before two named commits,
   and 948 of them had. A superseded-hash note records the correction, but the
   frozen bytes still carry the original claim.
4. The earlier 528-pair capture reported `strict_medium_high_n: 2` and is
   superseded by the 1000-pair replay.

Defect 1 does not bear on preregistration, but defect 3 does: a design whose
frozen text misdescribes what had already touched the held-out population is
not obviously a design that was fixed before the run in the sense the gate
cares about.

**This is an evidence-auditor call, not a schema question, and it should be
made before any manifest edit.**

### Secondary obstacle: the freeze ordering is no longer visible on `main`

`0023e204` — "hash held-out-1501 protocol before capture" — is not reachable
from `main`. PR #699 was squash-merged, so on `main` the protocol and the
results arrive in a single commit, `fff0cef3`. The ordering is real and it is in
the PR's commit history; it is not in `main`'s.

Any future mechanical check of `confirmatory` has to read the originating PR's
commits, not `main`'s. A check that reads `main` would fail on honest work.

## Two possible end states

**A. `validated`, threshold not met.** If the auditor accepts `confirmatory:
true`, add `threshold_basis`, `threshold_value`, `frozen_population_artifact`,
and the `validation_result` block. The study authorizes `Computable` — not
`Validated`, because the threshold missed. The four-times-blocked study becomes
a finished, reportable finding about the method.

**B. `exploratory`, result recorded post-hoc.** If the auditor rejects it, put
the same numbers under `post_hoc_analyses`, leave `evidence_status` at
`exploratory`, and record why the result cannot be confirmatory. PR #726 made
post-hoc analyses reportable rather than a blocking defect, so this is a real
end state and not a refusal.

Both are better than the current state, which is a study with five open
blockers and no recorded outcome.

## Steps

1. **Run `evidence-auditor` on the `confirmatory` question alone**, with the
   four `provenance_defects` and the squash-merge note above as its input.
   Output: A or B.
2. Amend `amendments.md` with the auditor's determination and the reasoning,
   including the `0023e204` ordering and where it is visible.
3. Edit `study.yaml` for the chosen end state.
4. Under A only: close or restate the five `materialization.blockers`, since
   two of them ("did not pass", "floor is not reachable") become the recorded
   result rather than open blockers.
5. `uv run python scripts/ci/validate_study_manifests.py` and
   `uv run python scripts/ci/check_research_question_status.py`.

## What this plan does not do

It does not rerun the capture, change the recall floor, or reinterpret the
result. The number is `4` against a floor of `10` either way. `replay_rules` in
the run manifest is explicit that a second replay against a changed freeze is a
new reviewable version, not a correction.
