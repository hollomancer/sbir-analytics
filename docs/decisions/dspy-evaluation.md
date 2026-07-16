---
Type: Evaluation
Owner: data@project
Last-Reviewed: 2026-07-16
Status: prototype-recommended
---

# Evaluation: DSPy for Weekly Award Narratives

## Recommendation

Proceed with a bounded, offline prototype of DSPy for the weekly report's
award-description and solicitation-alignment stage. Defer production adoption
until the prototype demonstrates that DSPy adds measurable quality or cost
value beyond provider-native structured output.

This is not a recommendation to introduce DSPy across the ETL pipeline, add it
to core dependencies, replace the existing OpenAI web-search client, build a
RAG system, or generate production narratives dynamically. The governing
prototype is specified in
[`specs/dspy-weekly-awards-prototype/`](../../specs/dspy-weekly-awards-prototype/requirements.md).

## What DSPy would add

DSPy represents language-model behavior as typed signatures and composable
modules, then can optimize instructions and demonstrations against a dataset
and metric. It also supplies structured-output adapters, evaluation helpers,
program serialization, and provider abstraction.

Those facilities are useful only when the target behavior is repeated,
bounded, and measurable. They do not make an unvalidated prompt reliable by
themselves, and an optimizer can amplify weaknesses in a bad metric. For this
repository, the labeled corpus and evaluation rubric are therefore the main
investment; the DSPy wrapper is secondary.

## Current SBIR-analytics seam

The weekly report is a good evaluation target because it is already a
recurring production LM workflow with a narrow output purpose:

- [`generate_award_descriptions`](../../sbir_etl/reporting/weekly/llm.py)
  sends batches of ten awards to `gpt-4.1-mini`, asks for a JSON object keyed by
  batch ordinal, strips Markdown fences, and calls `json.loads`. A malformed
  response drops the complete batch.
- The prompt already contains a qualitative rubric for technology summaries
  and solicitation alignment, but it requires the model not to hedge rather
  than giving it an explicit `unclear` result.
- [`OpenAIClient`](../../sbir_etl/enrichers/openai_client.py) owns HTTP
  transport, retries, a concurrency semaphore, token logging, and the separate
  Responses API web-search path.
- [`WeeklyAwardsReportBuilder`](../../sbir_etl/reporting/weekly/orchestrator.py)
  runs synopsis and award descriptions in a thread pool as part of a pipeline
  with a 720-second internal timeout and a 15-minute GitHub Actions job limit.
- The weekly report golden test runs with `--no-ai`; current OpenAI client tests
  exercise transport behavior, not semantic accuracy or grounding.
- The existing weekly-report refactor still tracks injected LM dependencies and
  typed return values as unfinished work in
  [`tasks.md`](../../specs/weekly-awards-report-refactor/tasks.md).

This means the repository currently knows whether the report renders without
AI, but not whether an AI-generated description is accurate, grounded, stable,
or worth its cost.

## Fit assessment

| DSPy capability | Fit | Reason |
|---|---|---|
| Typed award-description output | High | Replaces positional JSON with a collision-checked compound award-record ID, enum alignment, and claim-level evidence references |
| Offline prompt/demo optimization | Potentially high | Weekly repetition can amortize compile cost, provided a trustworthy labeled corpus exists |
| Evaluation and metric plumbing | High | The repository has no semantic regression harness for this stage today |
| Provider abstraction | Medium | Useful for experiments, but not a reason to replace the existing web-search client |
| Retrieval-augmented generation | Low | The first question is grounded transformation of known public fields, not retrieval |
| Agent/tool orchestration | Low | ETL, Dagster, and curated services already own operations; agents must not gain raw data or execution privileges |
| Broad entity-resolution replacement | Low initially | False merges are higher-risk and require a separate gold set and abstention policy |

## Why award descriptions are the first prototype

The target has bounded public inputs, a visible production baseline, a repeated
schedule, and outputs that can be decomposed into deterministic and human
metrics. It is safer and easier to label than company or PI diligence, and it
does not require DSPy to perform web search.

The first corpus includes only official award fields and solicitation text. It
excludes company web research, press releases, officers, and PI data. This
keeps grounding checkable, limits privacy exposure, and prevents framework
evaluation from being confounded by retrieval quality. A separate full-context
robustness experiment is required before any production recommendation.

## Alternatives considered

### Keep the current prompt and parser

Lowest implementation cost, but it preserves batch-level parse failures,
positional identifiers, untyped results, and the absence of semantic
regression evidence. Retain it as the production baseline and fallback, not as
the only evaluated option.

### Use provider-native structured output without DSPy

This is the strongest control and may be the correct final answer. It can
eliminate most parsing failures while keeping the existing provider and a
smaller dependency surface. The prototype must include this arm so schema
reliability is not incorrectly credited to DSPy.

### Build a local Pydantic contract and custom evaluation harness

The repository already depends on Pydantic, so typed inputs, outputs, rendering,
and deterministic metrics should remain dependency-free. A fully custom harness
would avoid DSPy, but would recreate optimizer, example-selection, evaluation,
and program-artifact behavior. The prototype uses local contracts around all
arms and tests whether DSPy's additional layer pays for itself.

### Adopt DSPy directly in production

Rejected. There is no labeled corpus, validated metric, compile budget,
semantic baseline, or shadow evidence yet. Adding a production dependency now
would make the decision irreversible before its value is known.

### Adopt a general agent or RAG framework

Rejected for this use case. Award-description generation is a bounded
transformation, not a tool-using agent problem. Retrieval and autonomous data
access would add failure modes without answering the evaluation question.

## Prototype decision rule

The prototype compares four arms:

1. The current batched prompt and parser on the restricted official-text
   corpus as a legacy control.
2. Provider-native structured output as the strongest non-DSPy control.
3. An unoptimized DSPy signature to measure framework overhead.
4. The same DSPy program compiled offline against the training corpus.

All arms use the same frozen official source fields, model revision, generation
parameters, and sealed test set. The current batching behavior is preserved and
reported as an explicit design difference; the provider-native and DSPy arms
operate per award with stable identifiers. Because this corpus omits the richer
web/company context used in production, actual weekly telemetry is a separate
observational reference and no restricted-corpus quality result is presented as
an estimate of full production behavior.

DSPy advances only if it passes the hard integrity, grounding, quality, cost,
and latency gates in the prototype requirements and materially beats the
strongest non-DSPy control. If native structured output fixes reliability and
optimized DSPy does not add material value, the correct result is to reject
DSPy and adopt the smaller native approach. A negative result is a successful
evaluation outcome.

## Risks and controls

| Risk | Control |
|---|---|
| Optimizer overfits or games the metric | Freeze train/development/sealed splits; keep primary metrics deterministic or human-labeled; never optimize on the sealed set |
| Native schema benefits are mistaken for DSPy benefits | Include provider-native structured output as an independent control |
| Cross-award contamination from batch ordinals | Use the repository's compound award-record key, reject collisions, and treat any swap or leak as a critical failure |
| Unsupported claims | Require source-sentence references, validate references deterministically, and manually review atomic claims |
| Instructions embedded in source text | Treat abstracts and solicitations as untrusted delimited data; include adversarial challenge cases; provide no tools or retrieval |
| Sensitive content enters caches or traces | Exclude PI/diligence data; disable DSPy memory, disk, and LM request caches for scored runs; do not log raw prompts or completions in CI |
| Cost is hidden by caches, adapter fallbacks, or retries | Pin and instrument the adapter; assign one retry owner; report every call, fallback, provider-cached token, compile cost, and inference cost separately |
| Thread-local configuration or nested concurrency drifts | Run standalone with one global concurrency budget, no nested parallelism, and worst-case in-flight spend reserved before dispatch |
| Serialized programs execute untrusted code or drift across environments | Save state-only JSON, keep it private because it contains demos/traces, reconstruct the pinned adapter, and fail closed on manifest incompatibility; never load whole-program pickle/cloudpickle artifacts |
| Framework or model upgrades invalidate results | Pin and record DSPy, model, dataset, signature, metric, and preprocessing versions; rerun the gate after any change |

## Consequences

- This evaluation PR changes documentation only. It adds no dependency and
  changes no weekly report behavior.
- The first implementation remains outside the production report path and can
  be deleted cleanly after a no-go result.
- Production integration, if justified, requires a separate ADR and PR with an
  injected typed generator, legacy fallback, feature flag, shadow evidence,
  and rollback procedure.
- Other possible DSPy uses—borderline entity resolution, topic comparison,
  mission alignment, and NAICS-to-BEA tie-breaking—remain separate evaluation
  questions and are not authorized by this prototype.

## Sources

- [DSPy overview](https://dspy.ai/)
- [Installation and supported Python versions](https://dspy.ai/getting-started/installation/)
- [Signatures in depth](https://dspy.ai/diving-deeper/signatures-in-depth/)
- [Modules](https://dspy.ai/diving-deeper/modules/)
- [Choosing an optimizer](https://dspy.ai/diving-deeper/choosing-an-optimizer/)
- [Metrics and evaluation](https://dspy.ai/diving-deeper/metrics-and-evaluation/)
- [Structured-output adapters](https://dspy.ai/diving-deeper/adapters/)
- [Settings, context, and thread behavior](https://dspy.ai/diving-deeper/settings-and-context/)
- [Caching behavior](https://dspy.ai/tutorials/cache/)
- [Saving and loading programs](https://dspy.ai/diving-deeper/saving-and-loading/)
