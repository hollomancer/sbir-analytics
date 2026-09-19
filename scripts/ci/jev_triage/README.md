# Jev CI triage pilot

This exploratory package proves the CI boundary without a Jev credential. It
does not affect check conclusions, skip tests, or make network calls.

## Run the no-key contract

```bash
uv run python -m scripts.ci.jev_triage.cli dry-run \
  --junit-dir tests/fixtures/jev_ci_triage \
  --fake-decision tests/fixtures/jev_ci_triage/fake-decision.json \
  --output-dir reports/jev-ci-triage/local-fixture

uv run python -m scripts.ci.jev_triage.cli evaluate \
  --corpus tests/fixtures/jev_ci_triage/evaluation-corpus.jsonl \
  --predictions tests/fixtures/jev_ci_triage/evaluation-predictions.jsonl \
  --output reports/jev-ci-triage/local-evaluation.json \
  --synthetic-fixture
```

The dry run writes:

- `failure_envelopes.jsonl`: strict redacted records that may cross the future API boundary.
- `triage_results.jsonl`: fake decisions plus deterministic local policy.
- `summary.md`: deterministic text for a GitHub step summary.
- `run_manifest.json`: input hashes, mode, counts, and `network_calls: 0`.

The checked-in evaluation files are synthetic contract fixtures. Their metrics
test the evaluator. They are not evidence about Jev performance.

## Live integration gate

Do not add an HTTP client from guessed examples. A live transport requires the
official API contract, authentication scheme, model/version field, retention
terms, timeout and rate-limit behavior, and a repository secret. The first
real request must run against the private labeled holdout and must not write
raw prompts, credentials, or unrestricted logs to GitHub artifacts.
