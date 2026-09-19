# Jev CI Failure Triage — Requirements

> **Lifecycle status:** Active
> **Spec-file progress:** In progress

**Target epistemic tier:** `exploratory`

**Research question:** none directly. Operational obligation: diagnose failed
continuous-integration checks without changing their result.
**Answers for:** pipeline engineers

---

## Done when

> A pipeline engineer can collect structured JUnit artifacts, convert them into
> bounded redacted envelopes, exercise the complete CI path with a fake Jev
> transport, and score saved predictions with the offline evaluator. The path is
> internal-pull-request-only and non-blocking. It makes no network call to Jev.

---

## Background

The CI workflow already decides pass or fail through deterministic linters,
guards, tests, and security scans. A decision model may help classify a failure,
route it to an owner, or recommend one bounded retry. It must not replace those
gates or receive unrestricted logs.

The pilot is exploratory because its classifications are probabilistic. The
surrounding sanitizer, contracts, policy, and renderer are deterministic, but
their presence does not promote the model output to the `pipelines` tier.

## Glossary

- **Failure envelope:** The strict, size-bounded record that may be sent to Jev.
- **Shadow mode:** Jev produces an artifact or summary but cannot affect a check result.
- **Supporting decision:** A bounded probability used by deterministic policy.

---

## Requirements

### Requirement 1 — Bounded input

**User story:** As a pipeline engineer, I want failed-check data reduced to a
strict envelope, so that CI does not send unrestricted logs or source text to an
external service.

#### Acceptance Criteria

1. WHEN a JUnit report is processed, THE pilot SHALL retain only failed test IDs,
   exception types, bounded diagnostic excerpts, and declared run metadata.
2. WHEN text enters the envelope, THE pilot SHALL redact authorization values,
   credential assignments, credential-bearing URLs, and token-like strings.
3. WHEN lists or excerpts exceed their limits, THE pilot SHALL truncate them
   deterministically.
4. IF the JUnit document is malformed, THEN THE pilot SHALL fail before any
   transport call.
5. THE failure envelope SHALL reject undeclared fields.
6. THE failure envelope SHALL enforce per-item string limits when constructed directly.
7. IF JUnit contains a DTD or entity declaration, THEN parsing SHALL stop before expansion.

### Requirement 2 — Typed decisions

**User story:** As a pipeline engineer, I want a fixed decision vocabulary, so
that CI code does not parse generated prose.

#### Acceptance Criteria

1. THE pilot SHALL type failure class, owner area, and supporting probabilities.
2. THE pilot SHALL reject probabilities outside the inclusive range zero to one.
3. THE pilot SHALL include an `UNKNOWN` failure class and a `GENERAL` owner area.
4. The no-key contract SHALL use a fake transport and SHALL make no network request.

### Requirement 3 — Deterministic action policy

**User story:** As a pipeline engineer, I want policy outside the model, so that
retry behavior is explicit and testable.

#### Acceptance Criteria

1. THE policy SHALL default to human triage.
2. THE policy SHALL recommend one retry only for a known-flake classification
   above both frozen probability thresholds.
3. THE policy SHALL refuse a retry after the first attempt.
4. A Jev decision SHALL NOT change the underlying check conclusion.

### Requirement 4 — Deterministic explanation

**User story:** As a pipeline engineer, I want a stable summary of the decision,
so that the output does not imply access to hidden model reasoning.

#### Acceptance Criteria

1. THE renderer SHALL report the selected classes and supporting probabilities.
2. THE renderer SHALL describe the result as a triage decision, not model reasoning.
3. THE renderer SHALL produce byte-identical output for identical inputs.

### Requirement 5 — Live integration gate

**User story:** As a repository maintainer, I want external access reviewed
before use, so that an experimental diagnostic cannot weaken CI or disclose data.

#### Acceptance Criteria

1. BEFORE a live call is implemented, THE maintainer SHALL record API versioning,
   authentication, retention, rate limits, and timeout behavior.
2. BEFORE GitHub Actions receives credentials, THE maintainer SHALL approve the
   input fields, disclosure terms, and secret-handling design.
3. A future shadow job SHALL be non-blocking and SHALL skip fork-originated pull requests.
4. A future shadow job SHALL exclude secret-scan output.
5. Automated retries SHALL require a separate approved task after a held-out evaluation.

### Requirement 6 — Offline evaluation

**User story:** As a pipeline engineer, I want the evaluation machinery ready
before credentials arrive, so that the first real Jev results face a frozen test.

#### Acceptance Criteria

1. THE evaluator SHALL join predictions to labels by a stable case ID.
2. THE evaluator SHALL report missing and unexpected predictions.
3. THE evaluator SHALL report failure-class accuracy, owner-routing accuracy,
   retry precision, unsafe retries, availability, latency, sanitizer acceptance,
   and confidence calibration.
4. Synthetic fixture reports SHALL declare `citable: false` and
   `synthetic_fixture: true`.
5. Synthetic fixture metrics SHALL NOT be represented as Jev performance.

---

## Out of scope

- Live Jev API calls or credentials in Stage 0.
- A live Jev job or repository credential.
- Pull-request comments, labels, approvals, or merge control.
- Test suppression or removal of deterministic path filters.
- Security-finding classification.
- Natural-language reasoning or chain-of-thought generation.
- Research evidence, entity resolution, or M&A classification.

## Dependencies

- Existing GitHub Actions checks — EXISTS.
- Pydantic 2 typed contracts — EXISTS.
- TypeSafe API documentation and credentials — BLOCKED for live integration.
- Approved data-retention and disclosure terms — BLOCKED for live integration.
