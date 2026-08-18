# Claude Code Instructions

## Project

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

**Intent / north star:** [docs/research-questions.md](docs/research-questions.md) is the canonical inventory of what this repo exists to answer. Use it to judge whether a proposed change serves a real question vs. adds incidental scope.

Architectural patterns and technical docs live in `docs/steering/`. Feature specs live in `specs/`.
Before implementing a spec, check `specs/status.md` and follow
`docs/development/spec-workflow-guide.md`; a directory can be gated, deferred, or
an archive candidate even when it still has unchecked tasks.

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

Before any deployment, server operation, or live Dagster materialization, read the
[self-hosted server runbook](docs/deployment/self-hosted-server.md#live-instance-on-the-server-host).
On the live host, also read the ignored
`docs/deployment/server-status.local.md` file when it exists; host-specific
checkout and storage paths as well as current
materialization state belongs there, not in tracked documentation.
Operate the live stack only from the dedicated deployment checkout recorded in
that local file, never from a development checkout. Preserve `.env.server`, the
configured persistent application data, and the Docker `dagster_home` volume.
Ingress must remain Tailscale Serve over tailnet-only HTTPS or explicitly enabled
TLS-terminated TCP; never enable Funnel and never expose server ports to the LAN
or public internet.

Treat materialization as a live-data mutation: confirm persistent storage is
mounted, the deployment checkout is clean, and the stack is healthy before
running one. Keep schedules disabled until their jobs have completed successfully
by hand with the inputs available on this host.

## Agents

Full role instructions live in `.claude/agents/`. Those files are **role-only**
(workflows, verdicts, tier-scaled effort); shared conventions stay here in
CLAUDE.md. The `.Codex/agents/` files route Codex agents to the same
instructions so the two runtimes do not maintain separate copies.

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

Shared skill instructions live under both `.claude/skills/` and `.agents/skills/`
for runtime discovery. `make docs-check` requires the copies to match.

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
studies/                  # Versioned contracts for reproducible and citable research
```

## Common Patterns

- **Monitoring:** Use `sbir_etl.utils` decorators and `AlertCollector`
- **CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
- **Tests:** Place in `tests/unit|integration|e2e/`; use the Make targets or `uv run pytest`
- **Neo4j:** Modify `packages/sbir-graph/sbir_graph/loaders/`, use MERGE operations

## Research and analysis workflow

Use a **notebook-first** workflow when the research question, cohort definition, matching rule,
statistical assumption, or visualization is still changing. New research notebooks are
`exploratory` tier and non-citable by default; a polished notebook does not promote its claims.

- Start from `notebooks/_template.ipynb`, tie the work to a concrete entry in
  `docs/research-questions.md`, and reuse the closest notebook under `notebooks/examples/`.
- Track active and migrated investigations in `notebooks/BACKLOG.md`.
- Use notebooks for exploration, evidence inspection, sensitivity analysis, and narrative. Keep
  scheduled jobs, downloads, database mutation, and recurring artifact generation in scripts,
  Dagster assets, or library modules.
- Import existing project functions and read canonical artifacts rather than copying logic from
  `sbir_etl/`, packages, or `scripts/data/` into cells.
- Record inputs, grain, keys, exclusions, as-of dates, assumptions, and deterministic seeds. Clear
  outputs and execution counts before committing.
- When exploratory work needs to become reusable, scheduled, or citable, make promotion explicit
  and satisfy the destination contract in `docs/steering/epistemic-tiers.md`. Keep the notebook as
  the research record and diagnostic front end; it is not itself an evidence contract.

Before implementing an uncertain analysis directly as a large Python script, agents must check
whether a bounded notebook would answer the open questions first. Before porting an existing
script, preserve one canonical computation path and avoid notebook/script duplication.

## Testing

The test and lint dependencies live in the `stack-dev` extra. Install it once —
bare `uv run pytest` fails on a fresh checkout because the core sync omits
pytest, loguru, and the first-party packages.

```bash
make install                           # uv sync --extra stack-dev (run this first)

make test-unit                         # Unit tests
uv run pytest -m integration           # Integration tests
uv run pytest -n auto                  # Parallel execution
make lint                              # Ruff over the repo, MyPy over sbir_etl + sbir-graph + sbir-ml
make lint-boundaries                   # Same boundary/hygiene guards as CI (incl. identity + epistemic tiers)
make docs-check                        # Hygiene subset only (also included in lint-boundaries)
```

`make lint-boundaries` must stay aligned with the CI quality job's guard step. If
Make and CI diverge, CI is authoritative and the Makefile is wrong.

Transition scoring changes must maintain the ≥85% Phase III retrospective
HIGH-precision benchmark. Enforcement today is a fixture-level canary
(`tests/unit/scripts/test_phase_iii_precision_backtest.py`) that runs on every
PR; the full benchmark against the S3 corpus is run manually via
`scripts/phase_iii_precision_backtest.py` and is not yet automated in CI.

## Releases and versioning

- Follow [Semantic Versioning 2.0.0](https://semver.org/) and the repository policy in
  [docs/steering/versioning.md](docs/steering/versioning.md).
- Treat the root project and all packages under `packages/` as one synchronized release.
- Release tags must be annotated and named `vMAJOR.MINOR.PATCH`; the version stored in every
  `pyproject.toml`, `uv.lock`, `sbir_etl.__version__`, and `config/base.yaml`'s pipeline metadata
  must match the tag without the `v` prefix.
- Do not move, replace, or reuse a published tag or version. Release corrections require a new
  version.
- Before proposing or preparing a release, classify user-visible changes since the latest release,
  select the required version increment, update all version metadata, run `uv lock`, and run
  `uv run python scripts/ci/check_versioning.py --tag vMAJOR.MINOR.PATCH`.

## Code Standards

- Line length: 100
- Target: Python 3.11–3.12 (`requires-python >=3.11,<3.13`)
- Ruff rules: E, W, F, I, B, C4, UP
- Use `StrEnum` not `str, Enum` (UP042 via `ruff --preview --select UP042` in `make lint` / CI)
- Use `datetime.UTC` not `timezone.utc`
- Do not postpone annotations on a Dagster-decorated function whose context type
  Dagster must inspect at runtime. Follow the local pattern in
  `phase_iii_census/assets.py`, `phase_iii_candidates/assets.py`, and
  `agency_private_capital/asset.py`. Other asset helpers may use
  `from __future__ import annotations`.

## Principles

- **Simplicity First**: Simplest change that solves the problem. No speculative abstractions, no "flexibility" that wasn't requested. If 200 lines could be 50, rewrite it. Ask: "Would a senior engineer say this is overcomplicated?"
- **No Laziness**: Root causes, not temporary fixes. Senior developer standards.
- **Surgical Changes**: Only touch what the task requires. Don't "improve" adjacent code. Match existing style. If your changes orphan imports/variables, remove them — but don't remove pre-existing dead code unless asked. Every changed line should trace to the request.
- **Verify Before Done**: Prove it works — run tests, check logs, demonstrate correctness. Transform tasks into verifiable goals:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```
