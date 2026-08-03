# Claude Code Instructions

## Project

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

**Intent / north star:** [docs/research-questions.md](docs/research-questions.md) is the canonical inventory of what this repo exists to answer. Use it to judge whether a proposed change serves a real question vs. adds incidental scope.

Architectural patterns and technical docs live in `docs/steering/`. Feature specs live in `specs/`.

## Epistemic tiers

Every artifact sits in one tier, which fixes what it costs to maintain and how
much weight it can carry. Full contracts:
[docs/steering/epistemic-tiers.md](docs/steering/epistemic-tiers.md).

| Tier | Contract | Where today |
|------|----------|-------------|
| `primitives` | One implementation per concept, versioned behavior, comprehensive tests | `sbir_etl/identity/`, `sbir_etl/config/`, `sbir_etl/models/` |
| `pipelines` | Deterministic, reproducible from a declared data cut, no inference | `sbir_etl/`, `packages/` |
| `evidence` | Frozen spec + SHA enforcement + blocking asset checks + declared estimand — all four | Phase III census |
| `exploratory` | Labeled non-citable. Nothing else required. | most of `scripts/` |

Three rules:

- **Declare the tier.** Specs state their target tier in `requirements.md`; new
  assets and modules state theirs. Unstated means `exploratory`.
- **Build to the tier, not above it.** Exploratory code getting tests and
  abstractions is the most common form of waste here. Untended `scripts/` is the
  design working, not a backlog.
- **Promotion is explicit work.** Nothing moves up by being useful, by gaining
  importers, or by having its numbers quoted. A number cannot be cited, or a
  research question marked answerable, on exploratory-tier work.

Reuse primitives rather than forking them: company-name normalization and
similarity go through `sbir_etl.identity` (add a named profile if you need new
behavior); config goes through `sbir_etl/config/loader.py`.

## Live deployment

Before any deployment, server operation, or live Dagster materialization, read
[the Mac mini runbook](docs/deployment/mac-mini-server.md#live-instance-on-this-mac-mini).
On the live host, also read the ignored
`docs/deployment/mac-mini-status.local.md` file when it exists; current
materialization state belongs there, not in tracked documentation.
The only live checkout is `/Users/conradhollomon/projects/sbir-analytics-server`;
never operate the live stack from the development checkout. Preserve
`.env.server`, `/Volumes/SSDmini/sbir-analytics`, and the Docker `dagster_home`
volume. Ingress must remain Tailscale Serve only; never enable Funnel.

## Agents

Custom agents in `.claude/agents/`:

| Agent | When to Use | Model |
|-------|-------------|-------|
| `spec-implementer` | Implementing spec tasks, "work on [spec-name]" | opus |
| `test-fixer` | Failing tests, broken coverage, test diagnostics | sonnet |
| `quality-sweep` | Lint/type errors, code cleanup after large changes | sonnet |
| `scope-guard` | Before large implementations — challenges scope creep | opus |

For **spec work**: scope-guard → spec-implementer → test-fixer → quality-sweep.
For **bug fixes**: skip to test-fixer or quality-sweep directly.

Each agent reads the tier from the spec and holds to it: `scope-guard` checks the
declared tier against the contract and can return `RETIER`, `spec-implementer`
builds to the tier and refuses silent promotion, `test-fixer` and `quality-sweep`
scale coverage and cleanup effort by tier rather than uniformly.

## Skills

| Skill | Use Case |
|-------|----------|
| `/review-spec [spec-name\|all]` | Review spec relevance against codebase |

## Key Directories

```text
sbir_etl/                 # Core ETL library (extractors, enrichers, transformers, validators, models, config, quality, utils)
packages/
  sbir-analytics/         # Dagster assets, jobs, sensors
  sbir-graph/             # Neo4j loaders
  sbir-ml/                # ML models (CET, transition detection)
config/base.yaml          # Thresholds, paths, performance settings
```

## Common Patterns

- **Monitoring:** Use `sbir_etl.utils` decorators and `AlertCollector`
- **CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
- **Tests:** Place in `tests/unit|integration|e2e/`, run `pytest -v --cov=sbir_etl`
- **Neo4j:** Modify `packages/sbir-graph/sbir_graph/loaders/`, use MERGE operations

## Testing

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.

## Code Standards

- Line length: 100
- Target: Python 3.11
- Ruff rules: E, W, F, I, B, C4, UP
- Use `StrEnum` not `str, Enum`
- Use `datetime.UTC` not `timezone.utc`
- Do NOT use `from __future__ import annotations` in Dagster asset files — it breaks runtime context type validation

## Principles

- **Simplicity First**: Simplest change that solves the problem. No speculative abstractions, no "flexibility" that wasn't requested. If 200 lines could be 50, rewrite it. Ask: "Would a senior engineer say this is overcomplicated?"
- **No Laziness**: Root causes, not temporary fixes. Senior developer standards.
- **Surgical Changes**: Only touch what the task requires. Don't "improve" adjacent code. Match existing style. If your changes orphan imports/variables, remove them — but don't remove pre-existing dead code unless asked. Every changed line should trace to the request.
- **Verify Before Done**: Prove it works — run tests, check logs, demonstrate correctness. Transform tasks into verifiable goals:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```
