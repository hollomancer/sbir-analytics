# Jev Preflight

This exploratory tool evaluates whether a claim has a configured study blocker.
Deterministic rules are authoritative. Jev runs only as a private shadow.

## Annual-report application

```bash
uv run python -m scripts.jev_preflight.cli annual-report \
  --case-id annual-report-published-reproduction \
  --output-json /tmp/published-reproduction.json \
  --output-markdown /tmp/published-reproduction.md

uv run python -m scripts.jev_preflight.cli annual-report \
  --case-id annual-report-structural-check \
  --output-json /tmp/structural-check.json
```

The first claim must return `NARROW`. The second must return `GO`. `GO` means
only that `preflight-rules-v1` found no configured blocker. It is not approval
and does not promote the study.

## Synthetic matrix

```bash
uv run python -m scripts.jev_preflight.cli matrix \
  --output /tmp/jev-preflight-matrix.json
```

The matrix covers all four readiness statuses. It tests the deterministic
contract. It is not evidence about Jev.

## Private Jev shadow

Set `TYPESAFE_API_KEY` in the process environment. Then run:

```bash
uv run python -m scripts.jev_preflight.cli shadow-matrix \
  --output /tmp/jev-preflight-live-matrix.json

uv run python -m scripts.jev_preflight.cli shadow-annual-report \
  --output /tmp/jev-preflight-live-annual-report.json
```

Do not commit live outputs or describe them as a public model benchmark.

## Deterministic CI enforcement

Run the same offline contract check used by pull requests:

```bash
make check-jev-preflight
```

The check compares both annual-report decisions with
`specs/jev-ci-enforcement/policy.yaml`. It fails on ruleset, claim-coverage,
status, or first-blocker drift. It never reads `TYPESAFE_API_KEY` or calls Jev.
