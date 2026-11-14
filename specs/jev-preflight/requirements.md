# Jev Preflight Requirements

**Research question anchor:** A1 / D1 — annual-report portfolio composition and award totals
**Target epistemic tier:** `exploratory`
**Operational duty:** Refuse unsupported study claims before analysis or release work.
**Status:** active
**Out of scope:** Evidence promotion; publication approval; CI enforcement; M&A discovery.

## Done when

A researcher can submit a typed claim contract and receive a deterministic
`GO`, `NARROW`, `REDESIGN`, or `STOP` decision. The result names the first
material blocker, the cheapest next test, and exact repository evidence.

The annual-report adapter must distinguish a blocked published-sample
reproduction claim from the permitted current-snapshot structural check. A
private Jev shadow run may compare typed model decisions with the deterministic
result. Jev must not set authoritative readiness.

## Requirements

### Requirement 1 — Typed claim contract

1. THE contract SHALL declare the claim, population, denominator, measurement,
   horizon, decision use, target evidence status, and required source outcome.
2. THE contract SHALL reject unknown fields and blank required values.
3. THE contract SHALL declare whether a narrower claim is available.
4. THE result SHALL label every supporting item as `OBSERVED`, `INFERRED`,
   `UNSUPPORTED`, or `BLOCKED`.

### Requirement 2 — Deterministic readiness

1. THE engine SHALL return only `GO`, `NARROW`, `REDESIGN`, or `STOP`.
2. THE engine SHALL select the first blocker from a versioned precedence list.
3. IF a required source outcome is impossible and a narrower claim exists,
   THEN THE engine SHALL return `NARROW`.
4. IF a required source outcome is impossible and no narrower claim exists,
   THEN THE engine SHALL return `STOP`.
5. IF a required input is unpinned, a required definition is absent, or a
   required validation is incomplete, THEN THE engine SHALL return `REDESIGN`.
6. IF no configured blocker applies, THEN THE engine SHALL return `GO`.
7. THE result SHALL say "No configured blocker found" instead of "approved".

### Requirement 3 — Inspectable evidence

1. EVERY decision fact SHALL cite a repository-relative file and field path.
2. THE annual-report adapter SHALL load the validated `study.yaml` contract.
3. THE adapter SHALL read the published-sample verdict and method from
   `sources.yaml`.
4. THE adapter SHALL validate frozen-artifact paths and hashes before returning
   `GO` for the structural-check claim.
5. THE adapter SHALL not silently reinterpret `blocked` as reproduction.

### Requirement 4 — Frozen evaluation matrix

1. THE synthetic matrix SHALL contain expected `GO`, `NARROW`, `REDESIGN`, and
   `STOP` cases.
2. THE evaluator SHALL join predictions by stable case ID.
3. THE evaluator SHALL report missing, unexpected, and incorrect decisions.
4. THE evaluator SHALL mark all fixture metrics non-citable and synthetic.
5. A synthetic matrix SHALL test deterministic contracts, not claim Jev performance.

### Requirement 5 — Jev shadow boundary

1. THE Jev request SHALL contain the typed preflight state and atomic Choice or
   Noul questions.
2. THE Jev response SHALL be validated before comparison.
3. THE API key SHALL be read from `TYPESAFE_API_KEY` at run time.
4. A Jev error SHALL leave the deterministic decision unchanged.
5. Live model results and performance measurements SHALL not be committed.
6. The shadow command SHALL make no repository or CI decision.

## Explicit exclusions

- No generic repository-chat agent.
- No generated chain of thought or prose explanation.
- No GitHub status check, merge control, retry, label, or comment.
- No changes to the annual-report study's evidence status or permitted claims.
- No new source-data loader, provenance module, comparison module, or manifest schema.
- No public benchmark or performance claim about Jev.
