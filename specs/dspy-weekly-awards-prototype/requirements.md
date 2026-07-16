# DSPy Weekly Award Narratives Prototype — Requirements

> **Status:** Active evaluation plan; implementation not started. Production
> adoption is gated on the offline and shadow criteria below. Anchors inventory
> question **E6** in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E6 — continuous monitoring and rolling analytics
**Answers for:** pipeline engineers, SBIR program managers
**Complexity tier:** Foundational infrastructure evaluation

---

## Done when

> A pipeline engineer can state: "On a versioned, human-reviewed, time-held-out
> corpus, we compared the current award-description prompt, provider-native
> structured output, unoptimized DSPy, and optimized DSPy using the same source
> fields and inference model. The reproducible report shows schema and
> award-record integrity,
> solicitation-alignment accuracy, grounding, critical failures, blind human
> preference, cost, and latency, and records an adopt-native, adopt-DSPy, defer,
> or reject decision. No production behavior changed during the evaluation."

## Background

The weekly report generates three-to-four-sentence award narratives from award,
solicitation, and optional company context. The current implementation requests
positional JSON for batches of ten awards and manually parses it. Existing tests
cover non-AI rendering and HTTP transport but do not measure semantic quality,
grounding, or cross-award contamination.

DSPy could make the stage typed and optimizable, but provider-native structured
output could supply much of the schema benefit with less machinery. The
prototype must separate those effects and make a negative DSPy result useful.
The evaluation rationale is recorded in
[`docs/decisions/dspy-evaluation.md`](../../docs/decisions/dspy-evaluation.md).

## Glossary

- **Legacy arm:** The current batched prompt and manual parser evaluated on the
  restricted official-text corpus. It is a control, not a complete production
  baseline.
- **Native arm:** Provider-native structured output using the local typed
  contract, without DSPy.
- **DSPy signature arm:** The local typed contract expressed as an unoptimized
  DSPy program.
- **DSPy optimized arm:** The same DSPy program compiled offline on the training
  set with a declared optimizer and metric version.
- **Critical failure:** A wrong award or company attribution, invented outcome,
  contract, compliance, or transition claim, cross-record leak, or obedience to
  an instruction embedded in source text.
- **Grounded output:** A prediction with no material claim unsupported by the
  numbered official source sentences supplied to the model.
- **Sealed set:** The held-out examples whose labels and candidate outputs are
  unavailable during prompt, program, optimizer, and metric development.

---

## Requirements

### Requirement 1 — Bounded and reviewable corpus

**User story:** As a pipeline engineer, I want a representative gold corpus
with leakage-resistant splits, so that an apparent improvement generalizes to
future weekly reports.

#### Acceptance Criteria

1. WHEN corpus construction begins, THE Prototype SHALL use only public award
   fields and official solicitation text; it SHALL exclude company web
   research, press releases, officer data, and PI data.
2. WHEN source text is stored, THE Prototype SHALL retain source provenance,
   the source award ID, the canonical compound award-record key, normalized
   company IDs, solicitation-topic IDs, retrieval dates, and numbered source
   sentences; it SHALL reject compound-key collisions between nonidentical
   records.
3. WHEN the rubric is calibrated, THE Prototype SHALL use 30 examples that are
   relabeled under the frozen rubric and may then enter the training set.
4. WHEN the corpus is frozen, THE Prototype SHALL contain 90 training, 30
   development, and at least 60 sealed evidence-bearing examples, plus a separate
   20-example challenge set.
5. WHEN examples are split, THE Prototype SHALL prevent the same normalized
   company or solicitation topic from crossing train, development, and sealed
   partitions and SHALL enforce
   `max(train/development award week) < min(sealed award week)`.
6. WHEN the sealed set is assembled, THE Prototype SHALL begin with 20 examples
   per `direct`, `partial`, and `unclear` class and preserve class balance if
   the power analysis requires expansion.
7. WHEN the challenge set is assembled, THE Prototype SHALL cover missing
   solicitation text, truncated and long inputs, malformed identifiers, and
   embedded instruction, role, JSON/schema, and DSPy adapter-marker text such
   as `[[ ## field ## ]]`.
8. WHEN labels are finalized, THE Prototype SHALL dual-label every sealed
   example and at least 25% of train and development examples, adjudicating
   disagreements before candidate outputs are inspected.
9. WHEN sealed labels and challenge expectations are created, THE Prototype
   SHALL keep them outside every developer checkout in a separately
   permissioned immutable artifact, commit only evaluation inputs/IDs and the
   artifact hash, and record an explicit release event after the candidate is
   frozen.
10. BEFORE the sealed labels are released, THE Prototype SHALL use paired
    development results to demonstrate at least 80% power at alpha 0.05 for the
    five-percentage-point alignment macro-F1 comparison; otherwise the
    custodian SHALL expand and rebalance the sealed set before release.

### Requirement 2 — Fair, reproducible experiment

**User story:** As a pipeline engineer, I want controls that isolate DSPy's
incremental contribution, so that schema improvements are not mistaken for
optimizer improvements.

#### Acceptance Criteria

1. WHEN the benchmark runs, THE Prototype SHALL evaluate the restricted legacy,
   native, DSPy signature, and DSPy optimized arms and SHALL record actual
   production telemetry separately as an observational reference.
2. WHEN arms are compared, THE Prototype SHALL hold official input fields,
   model revision, temperature, token limits, and sealed examples constant.
3. WHEN the legacy arm runs, THE Prototype SHALL preserve its batch-of-ten and
   positional-parser behavior and SHALL report batching and omitted production
   context as explicit factors.
4. WHEN the native and DSPy arms run, THE Prototype SHALL operate per award and
   SHALL key outputs by the compound award-record ID rather than a batch ordinal.
5. WHEN optimizer development occurs, THE Prototype SHALL compile only against
   training examples, select only against development examples, and keep the
   sealed labels inaccessible until configuration is frozen.
6. WHEN latency, cost, compilation, or stability are scored, THE Prototype
   SHALL disable DSPy memory cache, disk cache, and LM request cache; it SHALL
   record provider-side cached tokens separately.
7. WHEN a DSPy arm runs, THE Prototype SHALL pin `JSONAdapter`, use the same
   JSON schema as the native arm, record adapter configuration and rendered
   schema/prompt hashes, and count every response-format fallback or additional
   adapter request as a separately reported schema-path failure and API call.
8. WHEN calls are dispatched, THE Prototype SHALL declare one retry owner with
   an explicit retry count and one global concurrency budget shared by
   evaluation and compilation; no phase SHALL create nested parallelism.
9. WHEN nondeterminism is assessed, THE Prototype SHALL run three repetitions
   on a fixed 20-example stability slice and report output and metric variance.

### Requirement 3 — Typed, evidence-bearing output

**User story:** As an SBIR program manager, I want each narrative tied to the
correct award and official evidence, so that I can distinguish a clear
assessment from plausible but unsupported prose.

#### Acceptance Criteria

1. WHEN any non-legacy arm returns a prediction, THE Prototype SHALL validate a
   typed record containing the compound `award_record_id`, atomic typed claims,
   per-claim source sentence IDs, `alignment`, alignment evidence, and
   limitations.
2. WHEN `alignment` is emitted, THE value SHALL be one of `direct`, `partial`,
   `unclear`, or `not_applicable`.
3. WHEN solicitation text is absent, THE Prototype SHALL require
   `alignment=not_applicable` and SHALL not fabricate an alignment rationale.
4. WHEN a prediction cites a source sentence, THE Prototype SHALL verify that
   the sentence ID belongs to the same award input and is attached to one
   atomic claim; citation existence SHALL not be treated as semantic support.
5. IF an output is malformed, missing, duplicated, assigned to another award,
   or cites a foreign sentence ID, THEN THE Prototype SHALL record a failed
   example and SHALL continue evaluating the remaining examples.
6. WHEN output is rendered for human comparison, THE Prototype SHALL use one
   deterministic renderer for the native and DSPy arms and preserve the
   current three-to-four-sentence report shape.
7. WHEN evaluation executes through `dspy.Evaluate`, THE Prototype SHALL set an
   error allowance greater than the evaluated corpus size and a declared
   failure score, or use an equivalent all-results executor, so every input
   yields a success or explicit failure record.

### Requirement 4 — Validated quality metrics

**User story:** As a pipeline engineer, I want independent deterministic and
human metrics, so that the optimizer cannot win by exploiting a single proxy.

#### Acceptance Criteria

1. WHEN rubric calibration completes, THE Prototype SHALL require Cohen's
   kappa of at least 0.70 for alignment labels; otherwise work SHALL stop until
   the rubric or corpus is revised.
2. WHEN a run is scored, THE Prototype SHALL report schema validity, record-ID
   integrity, alignment macro-F1 and per-class F1, `not_applicable` accuracy,
   grounded-output rate, required-fact recall, critical failures, and
   cross-award leaks as separate metrics.
3. WHEN human evaluation occurs, THE Prototype SHALL randomize and blind arm
   identity and SHALL report preference for clarity and analytical usefulness,
   including ties.
4. WHEN uncertainty is reported, THE Prototype SHALL include paired bootstrap
   confidence intervals for primary comparative metrics.
5. WHERE an LM judge is used for triage, THE judge SHALL remain secondary and
   SHALL not determine optimizer selection or promotion.
6. WHEN results are sliced, THE Prototype SHALL report agency, phase, input
   length, alignment class, and solicitation-availability strata where sample
   size permits.
7. WHEN semantic grounding, required-fact recall, or critical failures are
   scored, THE Prototype SHALL use blinded human claim-level review; automatic
   evidence-ID validity SHALL remain a separate integrity metric.
8. WHEN legacy prose is compared, THE Prototype SHALL use blinded reviewers to
   infer its alignment class and inspect its claims; metrics that require typed
   fields SHALL be marked not applicable rather than synthesized silently.

### Requirement 5 — Cost, safety, and reproducibility controls

**User story:** As a pipeline engineer, I want a bounded experiment with
auditable artifacts, so that a framework evaluation cannot create uncontrolled
spend, sensitive logs, or irreproducible claims.

#### Acceptance Criteria

1. WHEN DSPy is introduced for the prototype, THE dependency SHALL live in an
   optional `dspy-eval` extra and SHALL not enter the core or `stack-dev` extras.
2. WHEN a run starts, THE Prototype SHALL enforce declared call, elapsed-time,
   and spend ceilings; initial ceilings SHALL be no more than $100 per compile
   and $25 per evaluation run unless separately approved. Before dispatch, it
   SHALL reserve worst-case cost for every permitted in-flight call.
3. WHEN DSPy is configured, THE Prototype SHALL configure it once in a
   standalone process and SHALL apply one global concurrency budget to the
   active evaluator or optimizer while every nested worker setting is one.
4. WHEN inputs are constructed, THE Prototype SHALL delimit source text as
   untrusted data, forbid following embedded instructions, and provide no web,
   retrieval, database, filesystem, or pipeline tools.
5. WHEN scored runs execute, THE Prototype SHALL explicitly disable DSPy memory
   and disk cache and set LM request caching false; it SHALL not log raw
   prompts, completions, secrets, or personal information in CI.
6. WHEN a compiled program is saved, THE Prototype SHALL save state-only JSON
   to private ignored scratch space, scan it for secrets, publish the exact
   artifact to a preregistered immutable store, and SHALL not persist or load
   whole-program pickle/cloudpickle artifacts.
7. WHEN an artifact is loaded, THE Prototype SHALL reconstruct and verify the
   adapter from the manifest and fail closed on any incompatible Python, DSPy,
   LiteLLM, provider SDK, Pydantic, adapter, optimizer dependency, schema,
   metric, or program version instead of relying on loader warnings.
8. WHEN a run finishes, THE Prototype SHALL emit a manifest containing Git SHA,
   Python, DSPy, LiteLLM, provider SDK, Pydantic, adapter, and optimizer-package
   versions; every task/student, teacher, proposer, or judge LM and parameters;
   dataset and split hashes; signature, schema, renderer, and metric versions;
   optimizer and seed; cache settings; program hash; calls, adapter fallbacks,
   provider-cached tokens, retries, failures, cost, and elapsed time.
9. WHEN evidence supports a decision, THE Prototype SHALL publish a sanitized
   manifest and summary in the repository and retain the exact program,
   normalized predictions, released labels, and scoring bundle in the
   preregistered immutable store with a URI, SHA-256, access policy, and
   retention period recorded in the decision memo.

### Requirement 6 — Predeclared decision gate

**User story:** As a pipeline engineer, I want an explicit stop/go rule, so that
the repository adopts the smallest approach supported by evidence.

#### Acceptance Criteria

1. WHEN the sealed and challenge sets are scored, THE candidate eligible for
   further testing SHALL achieve 100% schema and record-ID integrity on valid
   inputs, correct rejection of every invalid record ID before LM dispatch,
   100% `not_applicable` accuracy, zero instances of critical failure,
   obedience to embedded instruction/adapter markers, or cross-award leakage,
   grounded-output rate of at least
   95%, alignment macro-F1 of at least 0.85, and no evidence-bearing alignment
   class F1 below 0.75.
2. WHEN optimized DSPy is compared with the strongest non-DSPy arm, THE DSPy
   arm SHALL either improve alignment macro-F1 by at least five percentage
   points with the lower bound of its paired 95% bootstrap interval above zero,
   or reduce inference cost by at least 20% while the lower confidence bound
   for its alignment macro-F1 difference is no worse than minus two percentage
   points.
3. WHEN blind preference is measured, THE optimized DSPy arm SHALL be preferred
   to the strongest non-DSPy arm on more than 55% of at least 40 non-tied sealed
   examples and the lower 95% confidence bound SHALL exceed 50%; otherwise the
   preference result SHALL be inconclusive.
4. WHEN cost is measured, THE optimized DSPy arm SHALL cost no more than 1.25
   times the restricted legacy arm; actual production cost SHALL remain a
   separately reported observational reference.
5. IF optimized DSPy fails to materially beat provider-native structured
   output but the native arm clears its offline gates, THEN only the native arm
   SHALL advance to full-context and shadow testing; `adopt-native` SHALL remain
   unavailable until those later gates pass.
6. IF rubric agreement, integrity, grounding, critical-failure, quality, or
   cost gates fail, THEN THE Prototype SHALL not enter full-context or shadow
   testing.

### Requirement 7 — Shadow and production boundary

**User story:** As a pipeline engineer, I want candidate behavior isolated from
published reports, so that evaluation cannot silently alter an operational
briefing.

#### Acceptance Criteria

1. WHEN an offline candidate passes, THE Prototype SHALL identify the selected
   candidate as native or DSPy, preregister a 40-example
   natural-prevalence full-context corpus from disjoint later weeks, freeze the
   same company/web/press context for the selected candidate and restricted
   legacy control, retain the native arm as an additional control when DSPy is
   selected, dual-review at least 20 examples, and enforce a separate $25 spend
   ceiling.
2. WHEN full-context robustness is scored, THE candidate SHALL retain 100%
   schema and record-ID integrity, 100% correct missing-solicitation behavior,
   zero instances of critical failure, embedded-instruction obedience, or
   cross-record leakage, at least 95% grounded outputs, a point quality
   difference no worse than minus two percentage points with a lower paired 95%
   confidence bound no worse than minus five points, and inference cost no more
   than 1.25 times the control; otherwise it SHALL not enter prospective shadow.
3. WHEN robustness gates pass, THE Prototype SHALL run at least four
   prospective weekly shadows and at least 100 combined candidate award
   predictions while legacy prose remains authoritative and candidate prose is
   not posted to the GitHub job summary.
4. WHEN shadow runs are assessed, THE Prototype SHALL require zero report-stage
   fallbacks, fewer than 1% failed candidate award predictions across the named
   denominator, zero critical failures, and every full report to finish in no
   more than both 1.10 times its matched legacy run and 576 seconds, which is
   80% of the current 720-second internal timeout.
5. WHEN the evaluation concludes, THE Prototype SHALL publish an
   `adopt-native`, `adopt-DSPy`, `defer`, or `reject` decision with the sealed
   and challenge metrics, confidence intervals, full-context and shadow
   evidence, compile cost, recurring cost, limitations, and artifact hashes.
6. IF production adoption is recommended, THEN implementation SHALL require a
   separate accepted ADR and PR with a typed injected generator, an explicit
   backend flag defaulting to legacy, stage-level fallback, observability, and
   rollback instructions.
7. WHILE the prototype is incomplete, THE weekly report, orchestrator,
   workflow, `pyproject.toml`, and `uv.lock` SHALL remain unchanged by this
   documentation PR.

---

## Dependencies

- Weekly awards report modularization — **EXISTS / MAINTENANCE**
- OpenAI transport and current prompt baseline — **EXISTS**
- Solicitation extraction and award digests — **EXISTS**
- Injected generator and typed award-description returns — **NOT COMPLETE**;
  required only for a later production integration PR
- Human annotation time for corpus and sealed review — **REQUIRED**
- Approved API spend for live compile/evaluation — **REQUIRED BEFORE LIVE RUN**

## Out of scope

- Production changes in the planning PR.
- Weekly synopsis, company or PI diligence, and live retrieval. Frozen company
  web context is permitted only in the preregistered robustness phase.
- RAG, vector storage, tool-using agents, raw Cypher, Dagster execution, or MCP
  exposure.
- Entity-resolution, topic-clustering, mission-alignment, or NAICS-to-BEA
  decisions.
- Changing the rendered weekly report schema during evaluation.
- Treating model confidence as a calibrated probability.
