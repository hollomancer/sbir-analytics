# Verification practices for matchers, classifiers, and artifact boundaries

**Date:** 2026-09-10
**Status:** design, approved for planning
**Epistemic tier:** this document is process guidance, not a study. It makes no
numerical claim.

## Problem

Between 2026-09-08 and 2026-09-10, ten defects were found in the M&A detection
pipeline. Seven would have been caught by tests that did not exist. Two were
caught by tests that existed and asserted the defect. One could not have been
caught by any test.

The defects, and what would have found each:

| defect | would have been caught by |
|---|---|
| Coverage gate computed `scored == cut` identically, so it could never fire | end-to-end: run `main()` twice, assert the second fails coverage |
| Demoted rows still counted as exits by presence-only consumers | artifact-boundary invariant |
| Tavily API key transmitted to Brave's endpoint | any test of the live search path; there were none |
| `_TimedExtractor` wrote freeze rows after reporting a timeout | integration: inspect the freeze file after a timeout |
| Three of four direction rules assigned role from an unanchored window | adversarial unit cases |
| Exit date sourced from an acquirer-side Form D filing | one unit test on `merge_events` |
| `sbir_ma_events.jsonl` reproduced from no committed code | regenerate-and-diff |
| Form D Item 10 marks the **acquirer**, not the target | ground-truth calibration — but see below, the ground truth for it does not exist here |

The last row is the important one. It moved the reported exit rate from 8.1% to
5.1% and invalidated 407 "high-confidence" events. Finding it required reading
Form D Item 10, learning what a Rule 145 transaction is, and pulling 645
`clarificationOfResponse` texts from EDGAR.

A unit test checks that code does what its author meant, so it cannot report
that the author was wrong about what a source field means. A **ground-truth
calibration test** can: assert that a signal fires on cases where the answer is
already known. That tests the claim rather than the implementation, and it is
the only category that reaches this defect.

**The repository has no ground truth that can serve it.** The obvious candidate
is `confirmatory-run-manifest.json`, whose `strict_pairs` holds 13
human-adjudicated acquisitions at 0/19 false positives. Testing the Form D flag
against them appears damning -- 0 of the 4 present carry it -- but the estimand
selects "Form-D-**missing** rows", so those pairs were chosen precisely because
they lack a Form D signal. The test is circular and proves nothing.

Every label set in the repository has the same property: `labels.jsonl`,
`confirmatory-labels.jsonl` and `form_d_join_adjudication.jsonl` are all labels
*on the detector's own output*, so each inherits the detector's selection. An
acquisition list assembled independently of any signal does not exist here.

Building one is a prerequisite for this category of test, not a test to write.
It is out of scope for this design and worth its own issue.

### Tests that encoded the defect

Absence of tests is not the whole story. Two suites asserted the broken
behaviour:

- `tests/unit/enrichers/test_press_wire.py` holds 28 tests. The matcher it
  covers has 0/18 precision. The tests assert that `"Acme Defense Systems"`
  matches; none tries `BAL` against `"global"`. They test that matching works,
  never that it does not over-match.
- `test_assign_confidence_form_d_is_high` asserted the inverted grading and
  passed for months. Fixing the defect required superseding the test.

A first attempt at the coverage test asserted `main() == 1`, which passed with
the gate disabled, because a missed recall floor also exits 1.

The common cause is tests written from the happy path by the author, which
reproduce the author's assumptions rather than challenging them.

### Why the epistemic tiers did not help

`docs/steering/epistemic-tiers.md` governs what an artifact may claim, not how
likely its code is to be wrong. `classify_direction` lived in
`scripts/archive/` at `exploratory` tier and fed a preprint's headline number.
58 modules declare `pipelines` or `primitives`; the defects were not
concentrated among them. **Tier describes maintenance obligation, not defect
risk.** Any filter built on tier will look in the wrong places.

## Scope

The repository holds 208 functions whose names suggest matching, classifying,
normalising, or scoring. Auditing all of them is not a plan. The defects
clustered in two classes. Reading each candidate rather than trusting the
grep narrows this to **six files**:

**Class A — free-text role assignment.** Decides who did what to whom by
reading prose. A false positive inverts a relationship.

- `refine_ma_medium_tier.py` (`classify_direction`) — at
  `scripts/archive/data/` on `main`, moving to `scripts/data/` in #705
- `sbir_etl/ucc/matcher.py` (`is_debtor_side_match`)
- `sbir_etl/enrichers/sec_edgar/enricher.py` (`_classify_mention`)

**Class B — cross-population entity matching.** Decides whether two names are
the same firm. A false positive attributes one firm's activity to another.

- `sbir_etl/identity/company_names.py` — `company_name_similarity` and four
  fuzzy metrics. The canonical primitive the repository routes identity
  through, so its blast radius is every consumer. 62 tests, **one** negative
  assertion.
- `sbir_etl/enrichers/press_wire.py` (`_match_company`, plain substring, 0/18
  precision, #708)
- `sbir_etl/enrichers/sec_edgar/form_d_scoring.py` (`token_set_ratio`)
- `sbir_etl/enrichers/company_fuzzy_matcher.py` (`fuzz.process`)
- `sbir_etl/ucc/matcher.py` (`classify_match`) — also class A

**Excluded on audit.** An earlier draft of this list was built by grepping for
`classif` and `match`, and swept in seven files that do not carry the risk:

| file | why it is out |
|---|---|
| `usaspending/client.py` `classify_award_id` | parses an identifier format |
| `models/sbir_identification.py` `classify_sbir_award` | category, not relationship |
| `supply_chain/nsf_direct.py` `classify_nsf_award_status` | status, not relationship |
| `utils/tech_census.py` | topic classification; a false positive mis-buckets an award rather than inverting a relationship |
| `enrichers/award_history.py` | no cross-population name matching |
| `enrichers/pi_enrichment.py` | no cross-population name matching |
| `enrichers/pubmed_client.py` | no cross-population name matching |

A field normaliser such as `_normalize_state` is out of scope: it cannot
produce a false positive that reads as evidence.

## Design

### 1. Adversarial cases as a convention

For any function in class A or B, the test suite must contain, for every rule
or branch that can return a positive result, at least one input where that rule
must **not** fire.

`tests/unit/scripts/test_refine_ma_direction.py`, landing with #705, is the
worked example. Its
`ACQUIRER_SIDE_OR_NOISE` table lists phrasings where the subject company is the
buyer, the seller, or merely mentioned. Running that table against the
classifier found six failures across three rules in about twenty minutes.

The convention goes in `CLAUDE.md` beside the existing testing guidance,
because agents read it and the defects were introduced by agents.

### 2. Artifact-boundary invariants

Any artifact a separate stage reads gets one test asserting the invariant its
consumers rely on, stated in terms of what a consumer can observe.

The exit artifact has one, also landing with #705:
`test_presence_alone_implies_an_exit_for_downstream_consumers` asserts that
every row remaining carries target-side evidence, because
`agency_private_capital/asset.py`, `phase2_outcomes.py`, and
`run_agency_private_capital_phase1.py` key off row presence and never read
`confidence`.

Missing: the non-exit artifact, and the `capital_events` builder inputs.

### 3. Rewrite #704 along scope-guard's lines

scope-guard reviewed #704 and returned NARROW. Two findings stand:

- The CI regenerate-and-diff job has **zero targets**. Neither study at
  `reproducible` freezes a derived artifact, and both have gitignored inputs.
- `epistemic-tiers.md:59` already requires a `pipelines` artifact be
  "reproducible from a declared data cut." The clause exists; enforcement does
  not. Adding a requirement one tier up does not fix that.

So: drop the CI job. Add a `validation_design:` block to the `study.yaml`
schema, required only when a manifest targets `validated`, holding addressable
population, expected yield, decision threshold with its derivation, and power
to clear that threshold. Enforce in `scripts/ci/validate_study_manifests.py`,
which already parses those manifests and already checks `frozen_artifacts`
hashes.

This is the only part of the design with any purchase on the Form D direction
inversion, and the purchase is indirect: writing down what a source field means
and what would make the estimate wrong is the step at which someone might ask
what Item 10 actually marks.

## Delivery

Three pull requests, independent, in any order.

**PR 1 — #704 rewrite and the testing convention.** `study.yaml` schema
addition, enforcement in `validate_study_manifests.py`, documentation at
`studies/README.md`, and the class-A/B convention in `CLAUDE.md`. Does not
touch `epistemic-tiers.md`; scope-guard's finding was that the four-item
contract is the wrong home for both halves.

**PR 2 — artifact-boundary invariants.** Tests for the non-exit artifact and
the `capital_events` builder inputs, following the exit-artifact example.

**PR 3 — class-A/B audit.** Adversarial cases for each of the six files, fixes
for what they find. `press_wire._match_company` first, since #708 already
documents its 0/18 precision.

## Risks

**PR 3's yield is unknown, but the scope is now six files rather than
fourteen.** The M&A audit found six failures in seventeen cases across three
rules. `identity/company_names.py` is the one to watch: it is primitives tier,
whose contract is "comprehensive tests", and it has 62 of them with a single
negative assertion. That is the same shape as `press_wire.py`, which has 28
tests and 0/18 precision. If the audit finds a defect there it affects every
consumer in the repository. Mitigation: audit that file first, and split the PR
if the findings exceed roughly four files' worth of changes.

**A convention in `CLAUDE.md` is not enforcement.** Nothing fails CI when
adversarial cases are missing. Making it enforceable would require detecting
class-A/B membership automatically, which is not obviously possible. Accepted:
the convention is guidance, and review is the enforcement.

**None of this catches a misread source field.** Stated again because it is the
largest defect of the ten and the design does not solve it. `validation_design`
raises the odds someone asks the question; it does not guarantee the answer.
