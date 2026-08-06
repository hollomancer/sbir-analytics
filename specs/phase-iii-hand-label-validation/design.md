# Phase III Census Hand-Label Survivor Substantiation Audit — Phase 0 Design

**Status:** Draft, unapproved, and not frozen. No pilot or confirmatory case may be
opened until the decisions in [`questions.md`](questions.md) are approved and the
resulting design is frozen. This specification authorizes no labeling, sampling,
outcome access, criterion change, or result claim.

**Research-question anchors:** B2 (follow-on contracts never labelled Phase III) and B3
(unrecorded Phase III work) in
[`docs/research-questions.md`](../../docs/research-questions.md).

**Upstream protocol:**
[`specs/phase-iii-census/`](../phase-iii-census/) defines the frozen R15 census,
negative controls, and placebo. This study evaluates the census output; it does not
change or rerun the criteria to improve agreement with human labels.

This audit is the first bounded hand-label study in the broader validation workstream.
Because it samples survivors only, calling it a validation of census sensitivity,
specificity, recall, or discrimination would overstate the design.

## Decision this note supports

The frozen census identifies an auditable set of uncoded follow-on-procurement proxy
relations. The placebo shows that shuffled dates change the proxy, while the negative
controls show substantial treated/control overlap on common support. Neither test
establishes the statutory element that target work derives from, extends, or completes a
particular prior SBIR or STTR effort.

This study asks how often a probability sample of census-surviving relations can be
substantiated from a frozen hierarchy of public evidence. It is a one-time prospective
validation study, not a labeling platform, classifier-training set, or new transition
detector.

## Estimand — one sentence

Among unique prior-Phase-II-award × target-contract relations surviving the complete
frozen R15 census rule in the provenance-verified February source universe, estimate the
design-weighted fractions that public evidence (a) substantiates as Phase III, (b)
supports as Phase-III-compatible technical lineage without proving every statutory
element, (c) contradicts, (d) leaves indeterminate, or (e) makes unassessable.

This is a **public-evidence support yield among census survivors**. It is not statutory
prevalence, recall, sensitivity, total undercount, or a legal determination.

## Why this is separate from prior adjudication

The independent ground-truth work in
[`phase3-transition-groundtruth`](../phase3-transition-groundtruth/) evaluates whether a
ranker retrieves externally publicized positive cases. The 127-case packet in
[`phase3-match-benchmark/adjudication`](../phase3-match-benchmark/adjudication/) evaluates
selected detector leads and several deliberately enriched strata. Those studies provide
useful rubric and blinding precedent, but neither is a probability sample of R15 census
survivors and neither identifies census recall.

No prior label from those studies enters the confirmatory estimate. A relation that is
selected through the frozen probability design remains eligible, but any reviewer with
prior exposure to that case must recuse. Previously reviewed cases may also be selected
separately for a disjoint rubric pilot or as blinded sentinels; those separately selected
uses never enter the confirmatory estimate.

## Claim boundary

Public records can sometimes prove an explicit Phase III designation and a link to a
specific prior SBIR/STTR effort. They often cannot prove funding provenance or technical
lineage, and an empty contract description is not contrary evidence. Therefore:

- absence of evidence is never a negative label;
- inaccessible evidence is reported separately from evidentiary uncertainty;
- a firm statement cannot by itself establish the primary substantiated category unless
  the owner explicitly changes the source rule before freeze;
- `target_research` code absence, exact UEI, timing, agency continuity, and NAICS/PSC
  agreement are sampling-frame facts, not truth evidence; and
- no result from this study can be described as legal certification of Phase III.

A statutory gold standard would require authoritative agency, contracting-office, or
contract-file confirmation for sampled positives and negatives. That is a different
study and is an unresolved decision in [`questions.md`](questions.md).

## Unit, frame, and sampling

### Unit

One confirmatory case is one unique
`prior_award_id × target_contract_key` relation surviving the full R15 rule. All target
transactions and modifications belonging to the same generated contract key are bundled
in the case packet; they are not sampled as independent contracts. If several prior
awards connect to one contract, those relations remain distinct cases because technical
lineage is award-specific.

### Frame provenance

Before sampling, the run manifest must freeze and hash:

1. the exact census source manifests and February data-cut identifier;
2. the R15 design and amendment-log revisions and digests;
3. the survivor-frame parquet and its row count and SHA-256;
4. the relation, firm, contract, and transaction keys used to construct the frame;
5. all mutually exclusive sampling strata and allocation rules; and
6. the pseudorandom seed and sampling implementation revision.

Every relation in the target frame must have a known, strictly positive inclusion
probability. Frame exclusions are listed and quantified before sampling.

No census outcome, sensitivity cell, negative-control result, placebo result, score, or
prior human label may influence which individual relations are selected after the frame
and seed are frozen.

### Probability sample

The confirmatory sample is drawn only from complete-rule R15 survivors. Sampling is
probability-based and uses mutually exclusive strata derived from pre-existing lag and
agency-continuity categories. Every sampled case retains its known selection probability
and design weight. The exact strata and allocation are frozen before case packets are
opened.

Sample size is calculated from an owner-approved confidence level, target confidence-
interval half-width, anticipated indeterminate rate, clustering allowance, and available
review budget. This draft deliberately chooses none of those numeric values.

If multiple sampled relations share a firm or target contract, estimation and uncertainty
must account for that dependence. A design that selects at most one relation per cluster
is permitted only if its inclusion probabilities, weights, and relation-level estimator
are frozen in advance and preserve strictly positive selection probability for every
frame relation.

### Optional rubric sentinels

Officially coded Phase III cases and known non-lineage cases may be inserted under random
case IDs to test whether the rubric is usable. Sentinel status remains hidden from
reviewers. Sentinels do not receive design weights and never enter the confirmatory
estimate.

## Evidence protocol

### Evidence retrieval and packet freeze

Evidence retrieval is separate from label judgment. Before confirmatory review, an
evidence compiler follows a frozen mandatory repository checklist, query template, source
cutoff date, and per-case stopping rule. The compiler records every repository attempted,
query string, result identifier, access failure, and retrieved document, including zero-
result searches. Retrieved documents and the retrieval log are hashed into a case packet.

The evidence compiler does not assign an overall label and is masked from census clause
outputs, sensitivity strata, negative-control/placebo results, scores, and prior labels.
The two reviewers judge only the same locked packet; they do not independently browse the
open web. A packet defect is returned through a logged, outcome-masked correction process and
both reviewers receive the same amended packet before either label is locked.

### Element-level findings

Reviewers record each element separately before assigning an overall category:

1. **Recipient identity:** evidence that the target performer is the Phase II awardee or
   a documented successor carrying the relevant technology.
2. **Prior-award identity:** evidence identifying the particular SBIR/STTR award, topic,
   contract, project, or technology claimed as the source.
3. **Technical lineage:** evidence that target work derives from, extends, completes,
   matures, produces, sells, or commercializes that identifiable prior effort.
4. **Non-SBIR/STTR funding:** evidence that the target work is funded outside the Phase I
   or Phase II set-aside.
5. **Official designation:** whether an authoritative source explicitly calls the target
   agreement Phase III.
6. **Contrary evidence:** affirmative evidence of a different firm, unrelated technical
   line, chronology conflict, or Phase I/II funding.

Every source-level observation is preserved. Reviewers then code each element
`supported`, `contradicted`, `conflicting`, `not_found`, `inaccessible`, or
`not_applicable`, with citations and notes for `supported`, `contradicted`, and
`conflicting`. `not_found` and `inaccessible` never become `contradicted` mechanically.
If sources disagree, the reviewer applies the frozen hierarchy; unresolved disagreement
between authoritative sources is `conflicting`, not whichever source was read last.

### Frozen source hierarchy

Evidence is considered in this order:

1. signed contract, task-order, statement-of-work, justification-and-approval, or other
   official procurement document;
2. agency program-office, award, solicitation, or contract record;
3. official SBIR/STTR award or topic record identifying the prior work;
4. government technical report, audit, testimony, or program publication;
5. patent or peer-reviewed technical publication connecting the work; and
6. firm press release, product page, investor filing, or other self-authored statement,
   used only as corroboration unless the owner approves a different rule before freeze.

For every source used, the packet records the URL or repository identifier, publisher,
document title, access date, relevant page/section, a short evidence note, and an archived
copy or content hash when legally and technically possible. Reviewers do not contact firms
or agencies in this phase.

## Overall adjudication categories

- **`publicly_substantiated_phase_iii`:** authoritative public evidence supports recipient
  identity, an identifiable prior SBIR/STTR effort, technical lineage, and non-SBIR/STTR
  funding, with the explicit-designation rule determined by the approved answer to
  Question 3 in [`questions.md`](questions.md); no required element is contradicted or
  conflicting.
- **`credible_phase_iii_compatible_lineage`:** public evidence supports recipient identity
  and specific technical continuity, but at least one other required element is not found
  rather than contradicted, conflicting, or inaccessible.
- **`contradicted`:** authoritative affirmative evidence shows the candidate relation
  fails recipient identity or specific technical lineage, predates the relevant prior
  work, or is funded as Phase I/II, and no equal-or-higher-authority source creates an
  unresolved conflict. Mere silence cannot produce this label.
- **`unassessable`:** access failure in the mandatory retrieval checklist prevents a
  judgment on recipient identity or technical lineage, and the accessible packet neither
  supports nor contradicts those required elements.
- **`indeterminate`:** every remaining case, including unresolved authoritative conflicts,
  accessible-but-insufficient evidence, and partial access failures that do not satisfy
  the `unassessable` rule.

The rules are applied in the order written and are mutually exclusive. The confirmatory
dataset preserves source-level observations and element-level findings so a reviewer can
audit how each overall label was reached.

## Outcome masking and leakage controls

Two qualified reviewers independently receive the same case packet and rubric. They are
masked from:

- census clause outcomes and criteria-met counts;
- sensitivity-cell and sampling-stratum labels;
- negative-control and placebo status or results;
- any score, rank, weight, model output, or previous human label;
- sentinel status; and
- the other reviewer's findings.

The packet necessarily contains the firm, prior-award, target-contract, date, and scope
information needed to judge lineage. Reviewers are therefore aware that confirmatory
cases are census survivors and may infer lag or agency continuity from case facts. The
design claims masking of outcome fields and explicit stratum labels, not impossible full
blinding to criteria status or inferable strata. The packet must not highlight which
fields caused R15 to pass. Case IDs and row order are randomized independently of strata.

The author of the R15 implementation may clarify source fields but may not be the sole
reviewer or sole adjudicator. Reviewers and adjudicators disclose financial, employment,
advisory, litigation, or procurement involvement with sampled firms or awards and recuse
where applicable.

## Pilot, freeze, and adjudication

A disjoint pilot may test packet usability and clarify ambiguous wording. Pilot cases are
permanently excluded from the confirmatory sample. Every rubric change prompted by the
pilot is recorded in an append-only amendment log with its reason and with a statement
that no confirmatory labels had been viewed.

Before either reviewer opens a confirmatory packet, freeze and hash:

- this design and its append-only amendment log;
- the approved answers to [`questions.md`](questions.md);
- the corresponding entries in [`decisions.md`](decisions.md);
- the case-frame and selected-sample manifests;
- the codebook, source hierarchy, search protocol, and search budget;
- reviewer qualifications, independence attestations, and conflict rules;
- primary estimands, variance method, agreement statistic, stop rules, and reporting
  templates; and
- packet generator and analysis revisions.

The implementation must fail closed if any frozen digest differs. Raw reviewer records
are immutable. After both independent reviews are locked, a third qualified adjudicator
reviews disagreements and may assign the frozen overall categories without seeing R15
clause outcomes, strata, scores, or study estimates. Adjudication is appended; it never
overwrites the original labels or evidence trail.

## Analysis and required outputs

No single count or percentage is a sufficient report. The complete report includes:

1. frame and sampling audit: population and sample counts by frozen stratum, selection
   probabilities, weights, exclusions, duplicate clusters, and manifest hashes;
2. evidence-access table: attempted and successful sources, `not_found`, inaccessible,
   and unassessable rates by source class;
3. pre-adjudication reliability: raw agreement and the owner-approved chance-corrected
   statistic, overall and by element, with uncertainty;
4. adjudication flow: each reviewer's category, disagreement pattern, recusal/replacement
   counts, and final category without erasing raw labels;
5. design-weighted fractions and confidence intervals for all five overall categories;
6. design-weighted estimated survivor-relation counts and confidence intervals for all
   five categories, reported only within this bounded public-evidence estimand;
7. design-weighted element-level support, contradiction, conflict, not-found, and
   inaccessibility rates;
8. the combined `publicly_substantiated_phase_iii` plus
   `credible_phase_iii_compatible_lineage` fraction, reported alongside—not instead of—
   its two components; and
9. descriptive stratum tables only where the frozen disclosure and sample-support rules
   permit them.

The analysis code joins labels to strata and weights only after independent labels are
locked. It cannot choose a preferred agency/window cell, delete indeterminate cases from
the denominator without displaying them, or tune any rule from observed labels.

Terms such as `precision`, `sensitivity`, `specificity`, `false positive`, and `false
negative` are prohibited in the public-evidence study report because its reference
standard is incomplete. If the owner later authorizes an agency-confirmed gold-standard
study, those metrics require a separately frozen design with both positives and verified
negatives.

## Stop conditions

Stop and return to the owner before interpretation if:

- any frozen file, manifest, sample, seed, packet, or rubric digest changes;
- reviewers need an unapproved evidence source or unequal case-specific search effort;
- the frozen source hierarchy cannot distinguish `contradicted`, `indeterminate`, and
  `unassessable` reliably;
- the approved agreement or evidence-access gate fails;
- reviewer conflicts or availability prevent the independent-review design;
- a requested claim exceeds public-evidence support yield among R15 survivors; or
- anyone proposes changing R15 clauses, adding a score, or selecting a threshold after
  labels are visible.

Artifacts may be preserved when a gate fails, but no substantiation-yield interpretation
is authorized beyond plainly reporting the failure and the complete audit tables.

## Non-goals and prohibited drift

- No change to the frozen R15 census, pair builder, sensitivity grid, controls, or
  placebo.
- No import or use of `_score_pair`, `TransitionScorer`, weights, rankings, similarity,
  embeddings, classifiers, or machine-generated labels.
- No threshold selection, criterion calibration, or training/evaluation split created
  from these labels.
- No estimate of census recall, statutory prevalence, total Phase III undercount, or all
  Phase III agreements.
- No reuse of enriched prior adjudication cases in the confirmatory estimate.
- No labeling platform, dashboard, recurring Dagster asset, or production workflow in
  Phase 0.
- No FOIA request, private database, firm outreach, agency outreach, or legal opinion in
  this public-source phase.
- No research-question status change until the study is approved, executed, and audited.

## Verification before execution

1. Owner decisions approved -> verify every item in `questions.md` has a dated answer.
2. Pilot isolated -> verify no pilot case or prior label is in the confirmatory estimate
   and reviewers with prior case exposure have recused.
3. Frame frozen -> verify source, census, frame, sample, seed, and implementation hashes.
4. Packets masked -> verify hidden fields against the packet schema before release.
5. Reviews independent -> verify locked, immutable reviewer records precede adjudication.
6. Estimates reproducible -> verify a clean rerun reproduces sample membership, weights,
   tables, and artifact hashes.
