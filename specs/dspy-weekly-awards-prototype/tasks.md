# DSPy Weekly Award Narratives Prototype — Tasks

> **Status:** Planned. This documentation PR defines the experiment only. No
> DSPy dependency, corpus, live call, or production integration has been added.

Tasks are sequenced so each stage can stop the experiment without leaving a
partial production architecture. Each implementation stage should land in a
separate PR where practical.

## Stage 0 — Freeze the experiment contract

- [ ] **T0.1 Preregister the experiment.** Copy the four arms, metric
      applicability, adapter/schema configuration, thresholds, cache/retry and
      global concurrency settings, cost caps, split rules, immutable artifact
      location, and stop conditions into a versioned run configuration before
      labels or model outputs are inspected.
      - Verify: the config schema test passes and its SHA-256 is recorded in a
        dry-run manifest.
      - _Requirements: R2, R4, R5, R6_
- [ ] **T0.2 Select and isolate the DSPy dependency.** Confirm the current
      non-beta release and Python 3.11 compatibility, add a narrowly bounded
      optional `dspy-eval` extra, and commit the exact `uv.lock` resolution.
      Lock and record DSPy, LiteLLM, provider SDK, Pydantic, and any selected
      optimizer-specific extra. Do not add the extra to core dependencies or
      `stack-dev`.
      - Verify: `uv sync --extra dspy-eval --frozen` succeeds and ordinary
        `uv sync --frozen` does not install DSPy.
      - _Requirements: R5_
- [ ] **T0.3 Add dependency-free contracts and rendering.** Implement stable
      compound award-record identity, input/output Pydantic models, alignment
      and claim-kind `StrEnum` values, atomic claims with per-claim evidence,
      evidence ownership validation, and the deterministic renderer.
      - Verify: unit tests cover all alignment values, missing solicitation,
        foreign evidence IDs, and stable rendering.
      - _Requirements: R3_
- [ ] **T0.4 Add the standalone evaluation CLI skeleton.** Parse explicit model,
      adapter, optimizer, seed, global concurrency, retry, call, time, spend,
      cache, corpus, and output arguments. Configure every scored mode with
      DSPy memory/disk and LM request caching off, and configure the evaluator
      to preserve a result or failure record for every input. Do not import it
      from production modules.
      - Verify: a fake-model dry run with more than ten failures still writes a
        complete manifest without network access or weekly-report changes.
      - _Requirements: R2, R5, R7_

## Stage 1 — Build and validate the gold corpus

- [ ] **T1.1 Implement source normalization.** Export only approved public
      award and solicitation fields, attach provenance, generate stable
      compound award-record/company/topic IDs, reject nonidentical key
      collisions, and number source sentences deterministically.
      - Verify: repeated exports from the same input have identical IDs and
        dataset hashes; tests reject unsupported source fields.
      - _Requirements: R1, R3, R5_
- [ ] **T1.2 Write the annotation guide.** Define alignment classes, material
      claim, required fact, grounding, critical failure, and adjudication with
      positive and negative examples.
      - Verify: both reviewers independently label the same 30 calibration
        examples and every disagreement receives a recorded resolution.
      - _Requirements: R1, R4_
- [ ] **T1.3 Pass the rubric calibration gate.** Compute alignment agreement on
      the 30-example round, revise the guide without viewing candidate outputs,
      then relabel the calibration examples under the frozen guide.
      - Verify: Cohen's kappa is at least 0.70; otherwise mark the prototype
        deferred and do not start optimizer work.
      - _Requirements: R1, R4, R6_
- [ ] **T1.4 Complete and freeze the corpus.** Produce 90 train, 30 development,
      at least 60 sealed, and 20 challenge examples, with dual review and
      adjudication at the required rates and a hard temporal cutoff.
      - Verify: schema, count, class-balance, temporal boundary, company/topic
        leakage, compound-key collision, duplicate, provenance, and hash checks
        all pass.
      - _Requirements: R1_
- [ ] **T1.5 Place the initial holdout in custody.** Commit evaluation inputs and IDs only;
      place sealed labels and challenge expectations with an independent
      custodian in a permissioned immutable artifact. Do not attempt the power
      calculation until the paired development candidates are frozen.
      - Verify: no developer checkout or development command can read the gold
        labels or expectations; the committed artifact hash matches the
        custodian copy and a logged deliberate release is required to score it.
      - _Requirements: R1, R2_

## Stage 2 — Establish non-DSPy controls

- [ ] **T2.1 Implement independent metrics.** Add schema/ID checks, evidence
      ownership, alignment confusion metrics, `not_applicable` accuracy,
      paired bootstrap intervals, usage accounting, and exports for blinded
      human scoring of grounding, required-fact recall, and critical failures.
      - Verify: hermetic tests with hand-computed fixtures reproduce expected
        automatic values, never infer semantic support from citation existence,
        and preserve failures as per-example records.
      - _Requirements: R3, R4, R5_
- [ ] **T2.2 Implement Arm A, the restricted legacy control.** Reuse the current
      prompt, batch size, parser, and retry-owning client against only the
      frozen official fields. Preserve batch failure behavior for measurement.
      - Verify: a fake-response test covers valid batches, malformed JSON,
        missing/duplicate ordinals, and cross-award swaps.
      - _Requirements: R2, R3, R4_
- [ ] **T2.3 Implement Arm B, provider-native structured output.** Use the same
      provider/model and local typed contract per award without importing DSPy.
      - Verify: mocked provider responses validate through the common contract
        and deterministic renderer; malformed examples fail independently.
      - _Requirements: R2, R3, R4_
- [ ] **T2.4 Run train/development controls and capture the production
      reference.** Record output, cost, latency, retries, failure modes, and
      stability for Arms A and B without opening sealed labels; record matched
      actual weekly telemetry separately without treating it as labeled quality
      evidence.
      - Verify: the report names omitted context and batching confounds, marks
        typed-only legacy metrics not applicable, and links a complete manifest
        with uncached usage and provider-cached tokens separated.
      - _Requirements: R2, R4, R5_

## Stage 3 — Implement and compile DSPy arms

- [ ] **T3.1 Implement Arm C, the unoptimized signature.** Express the common
      typed contract as the smallest DSPy signature/module, pin `JSONAdapter`
      and the native arm's schema, and configure the LM once in the standalone
      CLI.
      - Verify: fake-LM tests exercise valid, malformed, missing, and foreign-ID
        predictions plus adapter fallback accounting without a live provider.
      - _Requirements: R2, R3, R5_
- [ ] **T3.2 Implement a gold-label metric for optimization.** Use deterministic
      record/evidence integrity, alignment labels, and conservative gold fact
      coverage. Keep human semantic grounding and critical-failure review out
      of the automatic score; do not use an LM judge as the primary metric.
      - Verify: a wrong record ID or foreign evidence receives zero, while tests
        prove a valid citation alone is not labeled semantically grounded.
      - _Requirements: R4, R6_
- [ ] **T3.3 Compile Arm D with the simplest optimizer.** Try labeled few-shot,
      then `BootstrapFewShot` only if necessary, using train for compilation and
      development for selection. Disable all DSPy caches, enforce one global
      concurrency budget, reserve in-flight spend, and enforce the declared
      $100 compile ceiling.
      - Verify: the run stops dispatching before any call/time/spend cap,
        records actual compile cost, and saves state-only JSON plus hashes.
      - _Requirements: R2, R5_
- [ ] **T3.4 Decide whether advanced optimization is justified.** Consider an
      advanced optimizer only when the simple optimizer fails, the scalar
      metric remains valid, optimizer-specific dependencies are locked, and a
      separate budget is approved. Use GEPA only when reliable natural-language
      per-example feedback also exists; otherwise consider MIPROv2's scalar
      search.
      - Verify: the run manifest cites the approval and new preregistered cap;
        otherwise record the task as intentionally skipped.
      - _Requirements: R4, R5, R6_
- [ ] **T3.5 Freeze the candidate.** Select one DSPy program on development
      data, freeze signatures/metrics/renderer/adapter configuration, publish
      the exact state-only program to the preregistered immutable store, and
      record every hash before unsealing.
      - Verify: a clean checkout with access can fetch, compatibility-check,
        hash, load with the reconstructed adapter, and rescore the exact saved
        artifact. Stochastic live recompilation is not the reproducibility test.
      - _Requirements: R2, R5, R6_
- [ ] **T3.6 Power and finalize the sealed comparison.** Use paired native/DSPy
      development results to confirm at least 80% power at alpha 0.05 for the
      five-point alignment macro-F1 effect. If needed, have the custodian expand
      and rebalance later-week sealed examples without exposing their labels,
      then issue and commit the new input and withheld-label hashes.
      - Verify: the candidate remains byte-identical and frozen; the power
        report passes before any sealed label or challenge expectation is
        released.
      - _Requirements: R1, R2, R6_

## Stage 4 — Run the sealed evaluation

- [ ] **T4.1 Execute all four arms on the sealed and challenge sets.** Use the
      frozen configuration, all DSPy caches disabled, one global concurrency
      budget, and the $25 evaluation ceiling.
      - Verify: every input has a success or explicit failure record; calls,
        retries, tokens, cost, and latency reconcile with the manifest.
      - _Requirements: R2, R4, R5_
- [ ] **T4.2 Conduct blinded human comparison.** Randomize arm identity and
      collect technical fidelity, clarity, alignment usefulness, omission, and
      claim-level grounding and preference judgments before revealing aggregate
      metrics. Continue review or declare preference inconclusive if fewer than
      40 comparisons are non-ties.
      - Verify: the review export contains no arm labels and the report includes
        reviewer agreement, ties, counts, and paired confidence intervals.
      - _Requirements: R4, R6_
- [ ] **T4.3 Apply the offline gate without exceptions.** Check integrity,
      expected challenge behavior, critical failures, grounding,
      macro/per-class F1, confidence-bound human preference, powered
      incremental DSPy value, cost, and latency exactly as preregistered.
      - Verify: a machine-readable gate result names each pass/fail and maps to
        `advance-native`, `advance-DSPy`, `defer`, or `reject`.
      - _Requirements: R6_
- [ ] **T4.4 Publish the offline benchmark summary.** Include per-arm and sliced
      results, confidence intervals, compile vs inference cost, confounds,
      challenge results, artifact hashes, durable URI/access/retention, and
      limitations. Commit the sanitized summary and manifest.
      - Verify: another authorized developer can fetch the immutable bundle and
        reproduce every aggregate from the exact predictions and released
        labels without recompiling a remote-LM program.
      - _Requirements: R4, R5, R6_

## Stage 5 — Robustness and prospective shadow, only after an offline pass

- [ ] **T5.1 Run the full-context robustness experiment.** Freeze the same
      company/web/press inputs for the selected native-or-DSPy candidate and
      restricted legacy control on a preregistered 40-example disjoint,
      natural-prevalence corpus; retain native as an additional control when
      DSPy is selected, dual-review at least 20, enforce a $25 cap, and apply
      the full-context integrity, safety, grounding, and cost gates.
      - Verify: no arm gains live retrieval or tools, the evidence bundle is
        durable, and any failed gate returns the decision to `defer` or narrows
        the selected scope.
      - _Requirements: R1, R5, R7_
- [ ] **T5.2 Add a manually invoked shadow runner.** Keep legacy prose
      authoritative, store candidate prose privately, and never post candidate
      text to the GitHub job summary.
      - Verify: a dry run proves report output is byte-identical whether shadow
        mode is disabled or candidate generation fails.
      - _Requirements: R7_
- [ ] **T5.3 Complete prospective weekly shadows.** Run at least four weeks and
      until at least 100 combined candidate award predictions exist. Review
      natural prevalence, report-stage and per-award failure, critical errors,
      cost, and matched full-report runtime.
      - Verify: report-stage fallback is zero, per-award candidate failure is
        below 1% over the named denominator, critical failures are zero, and
        every report finishes within both 1.10 times its matched legacy run and
        576 seconds. Do not label four observations a p95 estimate.
      - _Requirements: R7_

## Stage 6 — Record the decision

- [ ] **T6.1 Write the final decision memo.** Choose `adopt-native`,
      `adopt-DSPy`, `defer`, or `reject`; cite sealed, challenge, full-context,
      and shadow manifests plus durable evidence URIs, costs, limitations, and
      every gate result. Preserve negative findings.
      - Verify: `docs/decisions/dspy-evaluation.md` links the dated result and
        the spec status is updated consistently.
      - _Requirements: R6, R7_
- [ ] **T6.2 Close the prototype cleanly after a no-go.** Remove no production
      code because none was integrated; archive or retain the corpus according
      to the decision and document why the work stopped.
      - Verify: ordinary installs, the weekly workflow, and rendered reports are
        unchanged from the pre-prototype baseline.
      - _Requirements: R7_
- [ ] **T6.3 If adoption is recommended, open a separate ADR and production
      spec.** Define the injected generator, backend flag defaulting to legacy,
      one retry owner, one global concurrency budget, stage-level fallback, observability,
      deployment, reevaluation triggers, and environment-variable rollback.
      - Verify: no production implementation begins until the ADR is accepted
        and the separate PR names the validated artifact and model versions.
      - _Requirements: R7_

## Explicitly excluded tasks

- Do not add DSPy to the current documentation PR.
- Do not change the scheduled weekly workflow during offline evaluation.
- Do not compile an optimizer in CI or at report runtime.
- Do not include PI/diligence data in the first corpus.
- Do not add retrieval, web tools, database tools, raw Cypher, Dagster control,
  or MCP exposure.
- Do not expand this prototype to entity resolution, topic clustering, agency
  mission alignment, or NAICS-to-BEA mapping.
