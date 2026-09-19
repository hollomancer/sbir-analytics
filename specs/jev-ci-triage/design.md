# Jev CI Failure Triage — Design

**Status:** Stage 0 implementation is active. Live integration is gated.
**Date:** 2026-09-19.

## Decision

Build a small exploratory package under `scripts/ci/jev_triage/`. Do not add a
generic AI client to `sbir_etl`. CI may execute the package, but no
primitives-, pipelines-, or evidence-tier module may import it.

Stage 0 has this data flow:

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
  sanitize.py     JUnit parsing, redaction, grouping, and size limits
  client.py       transport protocol and fake implementation
  classify.py     transport-neutral orchestration
  policy.py       explicit retry thresholds and fallback action
  render.py       stable Markdown summary
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

Redaction is defense in depth, not permission to send arbitrary text. A future
workflow must construct the envelope from structured outputs where possible.

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

## Future shadow workflow

The future workflow will run only after a failed internal pull-request check.
It will have read-only permissions and `continue-on-error: true`. It will not
use `pull_request_target`. It will upload a bounded JSON result and append a
deterministic step summary.

Security results remain excluded. External fork pull requests remain excluded
because GitHub does not expose repository secrets safely to untrusted fork code.

## Verification

Stage 0 requires focused unit tests for:

- JUnit extraction.
- Credential redaction.
- Deterministic truncation.
- Strict model validation.
- Retry-policy boundaries.
- Fake transport orchestration.
- Stable Markdown rendering.

Repository tier and hygiene guards must also pass.
