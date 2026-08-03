---
Type: Development Guide
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Specification Workflow

Specifications connect research intent to bounded implementation work. They live in `specs/`, but
the presence of a directory does not make a spec active: check [the status registry](../../specs/status.md)
before starting work.

## Scope gate

Every new or revived spec must state:

1. The research-question ID it serves, or the concrete operational obligation it addresses.
2. The target [epistemic tier](../steering/epistemic-tiers.md): `primitives`, `pipelines`,
   `evidence`, or `exploratory`.
3. What is explicitly out of scope.
4. The verification that will prove the work complete.

If no current question or obligation needs the capability, do not create an implementation spec.
Capture a short research note instead.

## Required files

```text
specs/<feature>/
├── requirements.md    required behavior, scope, tier, and acceptance criteria
├── design.md          component boundaries and decisions when design is non-trivial
└── tasks.md           ordered, verifiable implementation work
```

### Requirements

Begin `requirements.md` with a compact context block:

```markdown
# <Feature> Requirements

- Research question: B3
- Target epistemic tier: pipelines
- Status: active
- Out of scope: causal claims; new external services
```

Write measurable acceptance criteria. EARS phrasing is useful when it makes behavior clearer:

- `THE <system> SHALL <behavior>`
- `WHEN <event>, THE <system> SHALL <response>`
- `IF <failure>, THEN THE <system> SHALL <safe behavior>`

Do not use formal phrasing to hide an unmeasurable requirement.

### Design

Add `design.md` when work changes package boundaries, data contracts, identity behavior,
orchestration, persistence, security, or deployment. Cover only what the implementation needs:

- current and proposed data flow;
- components and interfaces;
- configuration and failure behavior;
- data provenance and identity assumptions;
- testing and migration strategy;
- consequences for evidence or citability.

Follow the [architecture overview](../architecture/detailed-overview.md) and steering contracts.
Record difficult-to-reverse technology choices as an [ADR](../decisions/README.md), not only in a
feature spec.

### Tasks

Tasks should be small, ordered, and independently verifiable:

```markdown
- [ ] 1. Add the parser
  - Verify: focused unit tests pass
  - Requirements: 1.1, 1.2

- [ ] 2. Expose the Dagster asset
  - Verify: definitions load and the asset test passes
  - Requirements: 2.1
```

Optional work must be marked and must not be required by the definition of done.

## Lifecycle

1. **Orient:** check `specs/status.md`, the research questions, current code, and archived decisions.
2. **Challenge scope:** confirm the smallest change that answers the stated need.
3. **Implement:** work through tasks in dependency order and keep requirements traceable.
4. **Verify:** run the narrowest relevant tests plus repository guards.
5. **Reconcile:** update tasks, status registry, architecture/runbooks, and user-facing docs.
6. **Archive:** move completed or superseded specs under `specs/archive/` when the status registry
   identifies them as archive candidates.

Do not silently treat a deferred, gated, or archive-candidate spec as current architecture.

## Evidence promotion

Code completion can establish a primitive or pipeline; it does not automatically establish
validated evidence. Work targeting the `evidence` tier also needs a versioned
`studies/<study-id>/study.yaml` contract with frozen inputs, parameters, implementation references,
permitted claims, and validation status. Follow [Study contracts](../../studies/README.md).

Question statuses should distinguish:

- **computable:** the repository can produce a bounded result;
- **validated:** a study contract and checks support the interpretation;
- **citable:** the manifest explicitly permits external claims.

## Historical OpenSpec content

The OpenSpec migration is complete. Its records remain under
`specs/archive/completed-migrations/openspec-to-kiro-migration/` for provenance only. Do not use
that material as active requirements.

## Related references

- [Specification status registry](../../specs/status.md)
- [Research questions](../research-questions.md)
- [Epistemic tiers](../steering/epistemic-tiers.md)
- [Architecture overview](../architecture/detailed-overview.md)
- [Testing index](../testing/index.md)
