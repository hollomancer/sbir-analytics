# DSPy Weekly Award Narratives Prototype — Design

**Status:** Proposed implementation design; production adoption deferred.
**Date:** 2026-07-16.
**Evaluation:**
[`docs/decisions/dspy-evaluation.md`](../../docs/decisions/dspy-evaluation.md).
**Builds on:**
[`specs/weekly-awards-report-refactor/`](../weekly-awards-report-refactor/requirements.md).

## Goal

Determine whether DSPy adds measurable semantic quality or inference-cost
value to weekly award narratives beyond provider-native structured output,
without changing the production weekly report during the experiment.

The prototype produces a reproducible decision artifact, not a production
framework migration. `adopt-native`, `defer`, and `reject` are equally valid
outcomes alongside `adopt-DSPy`.

## Design principles

1. **Evaluate a seam, not a framework in the abstract.** The target is only
   award-description and solicitation-alignment generation.
2. **Separate structure from optimization.** Provider-native structured output
   is an independent control.
3. **Keep evidence first-party and frozen.** Initial inputs are official award
   and solicitation fields, with no web or personal data.
4. **Keep deterministic behavior outside the LM.** Contracts, validation,
   evidence checking, rendering, splitting, hashing, and gates remain normal
   Python.
5. **Let a no-go result stop the work.** The experiment is not a migration
   disguised as a benchmark.

## Current production flow

```text
weekly awards + optional enrichments
                 |
                 v
_award_digest() for batches of 10
                 |
                 v
OpenAI chat: prose instructions + JSON request
                 |
                 v
strip code fences -> json.loads -> positional keys
                 |
                 v
dict[list_index, description] -> Markdown renderer
```

The production function accepts richer optional company context, but that
context is deliberately absent from the first experiment. The legacy arm runs
with the same frozen official fields as the other arms. Its batch-of-ten
behavior remains intact because batch-level parse failure and cross-record
contamination are part of the controlled legacy behavior.

## Experimental architecture

```text
official awards + solicitation records
                 |
                 v
source normalizer -> numbered source sentences -> versioned corpus
                                                  |
                           +----------------------+
                           |
          +----------------+----------------+----------------+
          |                |                |                |
          v                v                v                v
  A: restricted     B: native schema   C: DSPy raw     D: DSPy compiled
  legacy control       per award         per award        per award
          |                |                |                |
          +----------------+----------------+----------------+
                           |
                           v
                normalized typed predictions
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
 deterministic/gold metrics       blinded human review
          |                                 |
          +----------------+----------------+
                           |
                           v
             cost + latency + decision report
```

No experimental module is imported by the weekly report, orchestrator, or
scheduled workflow. Live evaluation is manually invoked and may read a frozen
corpus only.

## Proposed implementation layout

The implementation phase, in a later PR, should use the smallest layout that
keeps DSPy optional and the contracts reusable:

```text
pyproject.toml                         # optional dspy-eval extra only
uv.lock                                # exact resolved version

sbir_etl/reporting/weekly/
  award_descriptions.py                # dependency-free contracts + renderer

scripts/validation/
  evaluate_dspy_award_descriptions.py  # CLI, arms, optimizer, evaluation

data/reference/dspy_weekly_awards/
  README.md                             # provenance + annotation guide
  train_dev.jsonl                      # public labeled development records
  sealed_inputs.jsonl                  # inputs only; no sealed gold labels
  challenge_inputs.jsonl               # inputs only; expected behavior withheld
  splits.json                          # stable IDs + withheld-label hashes

tests/fixtures/weekly_awards_report/
  award_description_eval_small.jsonl   # synthetic hermetic test fixture

tests/unit/reporting/weekly/
  test_award_descriptions.py

tests/unit/scripts/
  test_evaluate_dspy_award_descriptions.py
```

Generated run data begins in already-ignored scratch locations:

```text
reports/benchmarks/dspy_weekly_awards/<run-id>/
  manifest.json
  predictions.jsonl
  metrics.json
  summary.md

artifacts/dspy/award-descriptions/<program-id>/
  program.json
```

Before a run can support a decision, its exact state-only program, normalized
predictions, released labels, and scoring bundle are copied to a preregistered
immutable artifact store. The repository receives a sanitized manifest and
summary; the decision memo records the durable URI, SHA-256, access policy, and
retention. Ignored local files and hashes without retrievable content are not
accepted as audit evidence.

The evaluation CLI may be split into a private sibling package if it becomes
too large, but no generic LM abstraction should be introduced before the first
run demonstrates a real need.

## Dependency boundary

The prototype adds DSPy only through an optional `dspy-eval` extra. It does not
enter core dependencies or `stack-dev`, so ordinary ETL installations and CI
jobs do not install it. The implementation PR selects a non-beta DSPy release,
bounds the compatible range narrowly, and commits the exact `uv.lock`
resolution. Any optimizer-specific extra, such as a search dependency needed
by the selected optimizer, is also explicitly selected and locked.

The reusable input/output contracts and deterministic renderer use Pydantic,
which is already a core dependency. Only the validation script imports DSPy.

## Record identity

Bare SBIR.gov identifiers are not unique. The repository has verified that the
same base ID can identify distinct awards and therefore deduplicates on
`(award_id, company, award_year, award_amount)` in
[`build_tech_area_cohort.py`](../../scripts/data/build_tech_area_cohort.py).

The prototype follows that contract:

1. `source_award_id` is the trimmed Contract value, falling back to Agency
   Tracking Number.
2. `award_record_key` contains `source_award_id`, canonical source company
   string, award year, and normalized decimal award amount.
3. `award_record_id` is the full SHA-256 of a canonical JSON serialization of
   those four components; the components remain in the record for audit.
4. Rows without a source award ID are excluded from the evidence-bearing
   corpus and may appear only as expected-rejection challenge cases.
5. Exact duplicate keys are deduplicated; a hash collision or a shared key with
   nonidentical source fields stops corpus construction.

The separate split-group company ID uses UEI, then DUNS, then normalized
company name plus state. The solicitation group ID namespaces solicitation and
topic code by agency.

## Typed contracts

The design uses stable award-record IDs and sentence-level evidence instead of
batch ordinals. The illustrative contract is:

```python
from enum import StrEnum

from pydantic import BaseModel


class Alignment(StrEnum):
    DIRECT = "direct"
    PARTIAL = "partial"
    UNCLEAR = "unclear"
    NOT_APPLICABLE = "not_applicable"


class SourceSentence(BaseModel):
    sentence_id: str
    field: str
    text: str


class ClaimKind(StrEnum):
    TECHNOLOGY = "technology"
    APPLICATION = "application"


class EvidenceLinkedClaim(BaseModel):
    kind: ClaimKind
    text: str
    source_sentence_ids: list[str]


class AwardDescriptionInput(BaseModel):
    award_record_id: str
    company_id: str
    title: str
    agency: str
    phase: str
    source_sentences: list[SourceSentence]


class AwardDescriptionOutput(BaseModel):
    award_record_id: str
    claims: list[EvidenceLinkedClaim]
    alignment: Alignment
    alignment_rationale: str | None
    alignment_source_sentence_ids: list[str]
    limitations: list[str]
```

`SourceSentence.field` is restricted by validation to the approved award and
solicitation fields. Each sentence ID is namespaced by `award_record_id`, so
evidence from another record cannot validate accidentally. Each claim carries
its own evidence list; a flat citation bag is not accepted. Sentence existence
and ownership are deterministic integrity checks, not proof that a sentence
semantically entails a claim.

The deterministic renderer joins the typed fields into the existing
three-to-four-sentence narrative shape. Rendering is identical for the native
and both DSPy arms, keeping prose assembly outside the comparison.

## Dataset design

### Inputs

Approved initial fields are:

- Compound award-record key and source award ID.
- Company name, UEI/DUNS when available, state, award amount, and award date.
- Award title and abstract, agency, program, phase, and contract number.
- Solicitation number, topic code, title, and description when present.

Company name is retained only for split grouping and wrong-company detection;
the model does not receive web research, press releases, officers, PI details,
patents, publications, or inferred diligence.

The normalizer records provenance and converts each source field into numbered
sentences. It does not silently summarize or truncate. Any configured input
limit and truncation marker becomes part of the dataset version.

### Corpus and splits

The initial corpus contains at least 200 unique examples:

- 90 train examples, including the 30-example rubric-calibration round after
  relabeling under the frozen rubric.
- 30 development examples.
- At least 60 sealed evidence-bearing examples: initially 20 each labeled `direct`, `partial`, and
  `unclear`.
- 20 challenge examples for `not_applicable`, missing/truncated/long inputs,
  malformed identifiers, and embedded instruction, role, JSON/schema, and
  adapter-marker text.

Splitting is grouped by normalized company and solicitation topic. Every
train/development week precedes every sealed week. This prevents the optimizer
from seeing a near-duplicate award or topic—or a later observation—before the
held-out comparison.

The initial 60 sealed examples are the minimum, not a fixed ceiling. Before release, a
power analysis based on paired development disagreements must show at least 80%
power at alpha 0.05 to detect the preregistered five-point alignment macro-F1
improvement. The custodian expands and rebalances the sealed corpus if it does
not. The hard temporal boundary is
`max(train/dev week) < min(sealed week)`.

Sealed labels and challenge expectations never enter a developer checkout
before the candidate freezes. A separate custodian holds them in a permissioned
immutable artifact, while the repository contains evaluation inputs, IDs, and
the artifact hash. Release is a logged event. After the decision, sanitized
labels may join the durable evidence bundle, but that set is considered public
and cannot serve as a sealed set for a future promotion.

Every sealed example is dual-labeled. At least 25% of train and development are
also dual-labeled. Reviewers adjudicate disagreements without seeing model
outputs. If alignment Cohen's kappa is below 0.70, the corpus is not fit for an
optimizer and the experiment pauses.

### Labels

Each gold record contains:

- Alignment class and a short rationale.
- Atomic technology and application facts with valid source sentence IDs.
- Required facts whose omission would make a summary materially misleading.
- Explicit limitations or missing evidence.
- Critical-error annotations.

Reference prose is optional and is never scored by exact string similarity.

## Experiment arms

| Arm | Implementation | Question answered |
|---|---|---|
| A — Restricted legacy | Current prompt, batch size ten, manual parser, frozen official fields | How does the existing prompt/parser behave on the controlled corpus? |
| B — Native | Same provider and model with native JSON-schema output per award | How much value comes from typed structure alone? |
| C — DSPy signature | Unoptimized signature/module per award | What overhead or default behavior does DSPy introduce? |
| D — DSPy optimized | Same program compiled offline on train and selected on dev | Does DSPy's optimizer add material value over B and C? |

B, C, and D have identical per-award inputs, model revision, temperature, and
token limits. A consumes identical source fields but retains current batching.
Because all experimental arms omit the richer company/web context used by the
scheduled report, A is not called a production baseline. Matched telemetry from
actual prospective legacy reports supplies a separate observational production
reference for elapsed time, cost, and failure behavior; it is not used for the
controlled quality comparison.

### Adapter control

C and D pin `dspy.JSONAdapter` and the identical JSON schema used by B. The run
manifest records the adapter class/configuration, response-format tier, and
rendered schema and prompt hashes. The prototype does not use the default
`ChatAdapter`, whose parse fallback could add a second request. Any adapter or
provider fallback from native schema to another JSON mode is retained for
diagnosis but counted as a schema-path failure and an API call. The exact
adapter is reconstructed from the manifest before a saved program is loaded;
program JSON alone does not preserve process-global adapter settings.

## Optimization sequence

1. Validate deterministic metrics and the annotation rubric before compiling.
2. Run an unoptimized signature.
3. Try labeled few-shot, then `BootstrapFewShot` if necessary.
4. Consider advanced search only if the simple optimizer fails, the scalar
   metric is reliable, and a separate compile budget is approved. Use GEPA only
   when per-example natural-language feedback is also reliable; MIPROv2 treats
   the metric as a scalar and may require an additional locked search package.

Optimizer selection uses train/development only. Compile cost is reported
separately from recurring inference cost. Optimizer compilation never occurs in
CI, the weekly job, or runtime.

## Metrics

Metrics stay separate rather than being hidden inside one weighted headline.

### Deterministic integrity

- Schema-valid prediction rate.
- Exactly one prediction for every requested compound award-record ID.
- Duplicate, missing, foreign, or malformed award-record IDs.
- Evidence sentence existence and same-award ownership.
- Correct `not_applicable` behavior when solicitation text is missing.
- Retry and fallback count.

### Gold-label quality

- Alignment macro-F1 and per-class precision/recall/F1.
- Grounded-output rate: proportion with no material unsupported claim, assigned
  by blinded claim-level human review.
- Required-fact recall from the human-reviewed atomic fact inventory.
- Human-reviewed critical-failure count and deterministic cross-award-leak
  count.
- Performance by agency, phase, source length, and solicitation availability.

### Human review

Reviewers see randomized, unlabeled output pairs and score:

- Technical fidelity.
- Clarity and plain-language usefulness.
- Solicitation assessment usefulness.
- Material omissions.
- Overall preference, including ties.

### Operations

- Input/output/cached token counts where the provider exposes them.
- Calls, retries, failures, estimated dollars, p50/p95 per-example latency, and
  full-run elapsed time.
- Three-run stability on a fixed 20-example slice.
- Paired bootstrap confidence intervals for primary comparisons.

Evidence-ID validity is not a semantic grounding score. An LM judge may
prioritize human review but cannot select the optimizer or decide promotion.

### Metric applicability by arm

| Metric | Restricted legacy | Native and DSPy |
|---|---|---|
| Transport/parse success and cardinality | Legacy JSON/batch contract | Typed per-award contract |
| Record-ID/evidence integrity | Record mapping only; evidence IDs not applicable | Deterministic typed checks |
| Alignment F1 | Class inferred by blinded reviewers from prose | Typed class checked against gold |
| Grounding, required facts, critical failures | Blinded human claim review | Blinded human claim review; evidence IDs assist audit only |
| Cost and latency | Measured directly | Measured directly with adapter fallbacks separated |

No missing typed legacy metric is silently synthesized or reported as directly
comparable schema evidence.

## Decision matrix

The sealed configuration and thresholds are preregistered before the sealed
labels are opened.

| Outcome | Decision |
|---|---|
| B clears offline gates; D does not materially beat B | Advance native structured output to full-context robustness; reject DSPy |
| D clears every hard gate and beats B with the preregistered confidence bounds | Advance DSPy to full-context robustness |
| No arm clears grounding/quality gates | Retain legacy behavior and revise the task or corpus |
| Rubric agreement is below 0.70 | Defer; improve definitions before further model work |
| D improves quality but breaches cost or latency caps | Defer or reject unless a new budget/operational decision is approved |

Offline hard gates and comparative thresholds are defined in Requirement 6.
Shadow gates are defined in Requirement 7. Thresholds may be amended only
before the sealed set is opened; any amendment is versioned in the manifest and
decision report.

## Concurrency, retries, and caching

The evaluation runs as a standalone process. DSPy is configured once at
startup. A single global concurrency budget is assigned to whichever evaluator
or optimizer phase is active, with all nested thread settings fixed to one. It
is not called through the production report's `ThreadPoolExecutor` or
`OpenAIClient` semaphore. Before dispatch, the runner reserves worst-case cost
for every allowed in-flight call so parallel work cannot silently exceed the
declared budget.

Exactly one layer owns retries for each arm:

- The legacy arm uses `OpenAIClient` retry behavior.
- The native control uses one declared transport retry policy.
- DSPy's LM owns DSPy-arm retries with an explicit `num_retries` and is not
  wrapped in `OpenAIClient`.

A failed example becomes a scored failure record; it does not abort the run.
`dspy.Evaluate` receives `max_errors=len(corpus) + 1` and an explicit failure
score, or an equivalent all-results executor is used. Adapter fallbacks are
calls, not retries.

Every compilation, scored evaluation, cost/latency run, and stability repeat
disables both DSPy memory and disk caches and sets LM request caching false.
Provider-side prompt caching may still occur; cached-token usage is recorded
separately. Memory-only caching is allowed only for explicitly unscored local
development.

For the validated DSPy version, the implementation explicitly calls
`dspy.configure_cache(enable_memory_cache=False, enable_disk_cache=False)` and
constructs every scored LM with `cache=False`; tests fail if either setting is
not in effect.

## Security and privacy

- Official source strings are untrusted data, delimited from instructions, and
  never granted tools.
- The challenge set includes abstracts containing instruction, role,
  JSON/schema, and DSPy adapter-marker text.
- No production secrets, raw requests, or completions are committed.
- No PI, officer, or non-public diligence information enters the first corpus.
- Candidate shadow prose stays in a private, short-retention artifact and is not
  posted to the GitHub job summary.
- State-only JSON is used for compiled artifacts. It can still contain demos,
  traces, training text, and LM configuration, so it is scanned and kept in the
  private evidence bundle. Pickle/cloudpickle program loading is prohibited.

## Run manifest and reproducibility

Every run records:

- Git SHA and dirty-state flag; Python, DSPy, LiteLLM, provider SDK, Pydantic,
  adapter, and optimizer-package versions.
- Every inference and compile-time task/student, teacher, proposer, or judge LM
  plus generation parameters, retry settings, and the global concurrency cap.
- Dataset SHA-256, split IDs/hash, preprocessing version, and annotation-rubric
  version.
- Signature, JSON schema, adapter configuration, rendered prompt, renderer,
  metric, optimizer, seed, and compiled-program hashes.
- Cache configuration, response-format and adapter fallbacks, calls, tokens,
  provider-cached tokens, failures, retries, cost, and elapsed time.

The decision memo commits a sanitized manifest and cites the durable evidence
bundle and program hashes. Before loading, a fail-closed compatibility check
verifies the complete manifest; DSPy's own version warnings are not considered
enforcement. A clean checkout must be able to fetch, verify, load, and rescore
the exact saved artifact. Remote-LM recompilation is stochastic and is not
expected to reproduce byte-identical program state from a seed.

Changing the model, DSPy/LiteLLM/provider/Pydantic/adapter version, signature,
schema, metric, preprocessing, dataset, or compiled program invalidates
promotion and requires a new evaluation run.

## Full-context robustness phase

Passing the official-text experiment is necessary but not sufficient for
production. Before shadowing, the selected candidate—native or DSPy—and the
restricted legacy control run on a preregistered 40-example natural-prevalence
corpus from disjoint later weeks. When DSPy is selected, the native arm remains
an additional control. The existing pipeline freezes identical company, web,
filing, and press context for every included arm. At least 20 examples receive
dual review, and the phase has its own $25 spend cap and evidence bundle.

This phase applies 100% schema/record integrity and missing-solicitation
behavior, zero critical/instruction/cross-record failures, at least 95%
grounding, a point quality difference no worse than minus two percentage points
with a lower paired 95% confidence bound no worse than minus five points, and
cost no more than 1.25 times the control. It does not add
retrieval to DSPy: the existing client continues to collect context. Failure
returns the decision to `defer` or narrows production scope to official text.

## Shadow and possible production integration

After offline and full-context gates pass, manually initiated prospective
weekly shadows continue for at least four weeks and until at least 100 candidate
award predictions exist. Legacy prose remains authoritative and candidate
prose is stored privately for review. No report-stage fallback is permitted;
candidate per-award failures must remain below 1% across the named denominator.
Every full report must finish within both 1.10 times its matched legacy run and
576 seconds. Four observations are not presented as a p95 estimate.

Only after shadow success may a separate production ADR and PR:

1. Complete the existing typed-return and dependency-injection seam.
2. Introduce an `AwardDescriptionGenerator` protocol with legacy and selected
   adapters.
3. Add `WEEKLY_DESCRIPTION_BACKEND=legacy|native|dspy`, defaulting to `legacy`.
4. Configure the selected backend once before production thread pools start.
5. Fall back for the entire description stage on schema failure, timeout, or
   budget breach, avoiding mixed narrative semantics within one report.
6. Retain the legacy implementation for at least two release cycles so rollback
   is an environment-variable change with no data migration.

The existing OpenAI web-search path remains unchanged in every outcome.

## Testing strategy

Hermetic tests use synthetic fixtures and fake predictions; they make no live
API calls. They cover:

- Contract and dataset validation.
- Sentence numbering and evidence ownership.
- Deterministic grouped/time-aware splitting and leakage detection.
- Renderer behavior for every alignment class.
- Metric calculations on known confusion matrices and grounded/unsupported
  examples.
- Malformed, partial, duplicate, foreign-ID, and missing predictions.
- Per-example failure isolation.
- Manifest hashing and artifact serialization.
- Cache, retry, call, and spend-cap accounting with mocked usage.

A live smoke test is manual or workflow-dispatch-only, marked `requires_api`,
and excluded from ordinary CI. The optimizer is never compiled in CI.

## Risks

- **Corpus selection bias:** deliberately balanced sealed labels do not reflect
  natural weekly prevalence. Mitigation: report both balanced sealed metrics
  and natural-prevalence shadows covering at least four weeks and 100 awards.
- **Small per-agency slices:** the corpus may not support agency-level claims.
  Mitigation: present slice counts and confidence intervals; do not promote
  sparse comparisons to headline results.
- **Human-label ambiguity:** solicitation alignment may be genuinely
  underdetermined. Mitigation: explicit `unclear`, dual labeling, adjudication,
  and the kappa stop condition.
- **Metric overfitting:** an optimizer can improve an aggregate while
  increasing critical errors. Mitigation: separate hard gates and a sealed set.
- **Framework churn:** DSPy and provider APIs evolve. Mitigation: narrow
  optional dependency, locked environment, state-only artifacts, and rerun on
  version changes.
- **Operational multiplication:** nested workers and retries can exhaust the
  weekly timeout or conceal spend. Mitigation: standalone evaluation, one
  global concurrency budget, one retry owner, and full accounting.

## Non-goals

- Production integration in the prototype implementation PR.
- Optimizing or replacing the weekly synopsis or diligence stages.
- Giving DSPy web, retrieval, graph, filesystem, Dagster, or other tools.
- Building a general LM framework for the repository.
- Replacing deterministic ETL, entity joins, calculations, or clustering.
- Proving that an LM-generated description is suitable for external
  publication without human editorial review.
