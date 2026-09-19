# Jev CI Failure Triage — Design

**Status:** Stage 0 implementation is active. Live integration is gated.
**Date:** 2026-09-19.

## Decision

Build a small exploratory package under `scripts/ci/jev_triage/`. Do not add a
generic AI client to `sbir_etl`. CI may execute the package, but no
primitives-, pipelines-, or evidence-tier module may import it.

The no-key implementation has this data flow:

```text
synthetic JUnit XML + declared metadata
                  |
                  v
      deterministic parser and sanitizer
                  |
                  v
        strict FailureEnvelope
                  |
                  v
          fake Jev transport
                  |
                  v
        typed probabilistic decision
                  |
          +-------+-------+
          |               |
          v               v
 deterministic policy   deterministic renderer
```

The fake transport makes the boundary testable without credentials. A later
transport may replace it only after the live-integration gates pass.

## Components

```text
scripts/ci/jev_triage/
  models.py       strict input, decision, and policy-output contracts
  redaction.py    shared credential redaction for every construction path
  sanitize.py     JUnit parsing, redaction, grouping, and size limits
  client.py       transport protocol and fake implementation
  classify.py     transport-neutral orchestration
  policy.py       explicit retry thresholds and fallback action
  render.py       stable Markdown summary
  evaluate.py     offline labels, predictions, and metrics
  cli.py          no-key dry run and evaluation commands
```

## Data boundary

The failure envelope permits:

- Check name and command family.
- Exit code and attempt number.
- Runner operating system.
- Failed test IDs.
- Exception types.
- Bounded, redacted diagnostic excerpts.
- Coarse changed-path groups supplied by deterministic code.

It does not permit environment dumps, source files, fixture bodies, raw job
logs, authorization headers, or security-scan findings.

Redaction is defense in depth, not permission to send arbitrary text. The model
also applies redaction and per-item bounds during direct construction, so a new
caller cannot bypass the sanitizer by instantiating the contract itself. A
future workflow must still construct the envelope from structured outputs.

The parser rejects DTD and entity declarations before XML parsing. It also
limits raw input size before parsing.

## Failure behavior

- Malformed JUnit fails before classification.
- Contract violations fail before classification.
- A transport error produces no decision and cannot fail the original CI job.
- Policy defaults to `HUMAN_TRIAGE`.
- The underlying deterministic check conclusion is immutable.

## Explanation boundary

Jev returns bounded decisions and probabilities. It does not supply prose
reasoning. The renderer reports the observable decisions and labels the output
as triage. It must not claim that the probabilities are a faithful explanation
of hidden reasoning.

## No-key workflow contract

The fast-test shards upload three-day JUnit artifacts. The mock contract job
runs only when Jev pilot files change on an internal pull request. It downloads
those artifacts, runs the fake transport, evaluates checked-in synthetic
fixtures, uploads bounded outputs, and appends the deterministic summary.

The job has read-only `actions` and `contents` permissions. It is non-blocking.
It reads no repository secret. The synthetic evaluator output tests metric
behavior and makes no Jev performance claim.

## Future live shadow workflow

The future workflow will run only after a failed internal pull-request check.
It will have read-only permissions and `continue-on-error: true`. It will not
use `pull_request_target`. It will upload a bounded JSON result and append a
deterministic step summary.

Security results remain excluded. External fork pull requests remain excluded
because GitHub does not expose repository secrets safely to untrusted fork code.

## Verification

The no-key implementation requires focused unit tests for:

- JUnit extraction.
- Credential redaction.
- Deterministic truncation.
- Strict model validation.
- Retry-policy boundaries.
- Fake transport orchestration.
- Stable Markdown rendering.
- CLI artifact generation with zero network calls.
- Offline metric calculation, including unsafe retries.
- Internal-pull-request and read-only workflow constraints.

Repository tier and hygiene guards must also pass.
