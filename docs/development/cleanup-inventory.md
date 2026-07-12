---
Type: Reference
Owner: devops@project
Last-Reviewed: 2026-07-07
Status: active
---

# Cleanup Inventory

This inventory tracks codebase simplification work: live specs, stale docs,
archived scripts, test drift, and CI drift. It is not a feature spec. Use it as
the starting point for cleanup PRs, and use
[`docs/research-questions.md`](../research-questions.md) as the scope gate.

## Cleanup Rules

Keep a file, test, or workflow when it satisfies at least one condition:

- It directly supports a live research question or output product.
- It is part of the current ETL, Dagster, ML, Neo4j, data-refresh, or CI path.
- It is needed for reproducibility of a published analysis.
- It is historical context under an explicit archive directory.

Otherwise, update it, archive it, or delete it. Do not keep stale content merely
because it may become useful later.

## Current Shape

Snapshot from the July 2026 cleanup review:

| Area | Current signal | Cleanup implication |
| --- | --- | --- |
| Python source and tests | ~206k Python LOC across `sbir_etl/`, `packages/`, `scripts/`, and `tests/` | Prioritize large modules and duplicate test setup only after low-risk stale cleanup. |
| Tests | 214 unit test modules, 3 slow test modules, plus integration/e2e/validation suites | Test taxonomy must be simpler and documented in one place. |
| Docs/specs | 108 docs Markdown files and 103 spec files | Live docs need link/path audits; archive docs can remain historical. |
| Scripts | `scripts/archive/` contains ~12k Python LOC; `scripts/data/` contains ~3.7k LOC | Archive scripts need a clear reactivation policy. |
| CI | Six workflows plus nine composite actions | Workflows share repeated setup, Python path, AWS, and summary logic. |

## Live Spec Inventory

Status strings below come from spec files where available; task counts came from
`specs/*/tasks.md`. `specs/status.md` is the current top-level status registry.
"Cleanup action" is the next simplification decision, not a feature
implementation commitment.

| Spec | Current signal | Cleanup action |
| --- | --- | --- |
| `agency-private-capital-comparison` | Phase 1 implemented; 7 done, 13 pending | Keep Phase 2 gated until private-capital cohort comparison is selected. |
| `company-categorization` | Requirements say 77% complete; 32 done, 8 pending | Update old `src/` paths; decide whether Neo4j loader work is still live. |
| `cross-agency-taxonomy` | Gated backlog; 0 done, 16 pending | Promote only when M3 cross-agency taxonomy reporting is selected. |
| `data-imputation` | Gated backlog; implementation not started; 30 pending | Defer unless missing-field recovery becomes the next data-quality priority. |
| `follow-on-multiplier-validation` | Design-only spec, no task file | Either add tasks and make active, or leave as design note. |
| `iterative_api_enrichment` | USAspending refresh live; 18 done, 2 pending | Split Phase 2 source expansion into a new spec or archive Phase 1 as complete. |
| `modernbert_analysis_layer` | Maintenance; core embeddings/similarity implemented | Keep Neo4j, quality, and Bayesian work as scoped follow-ups. |
| `naics-enricher-consolidation` | Maintenance cleanup; 11 done, 5 pending | Close obsolete audit/golden-file tasks as superseded; finish docs cleanup. |
| `ot-consortium-subaward-attribution` | Gated backlog; 17 pending | Keep gated on coverage probe; do not implement before T0 decision. |
| `patent-cost-spillover` | Gated backlog; 23 pending | Defer unless C3 patent-cost analysis is the next research priority. |
| `phase-3-solicitation-alerts` | Maintenance; S1 shipped, S2/S3 backlog | Avoid adding another ingestion path until SAM.gov Opportunities is prioritized. |
| `sbir_ma_match_rate_by_fy` | Gated backlog; 19 pending | Keep only if it will produce a near-term analysis artifact. |
| `state-local-tax-rates` | Maintenance; hardcoded provider exists | Good low-risk cleanup: make rates data-driven when fiscal v2 resumes. |
| `ucc1-financing-analysis` | Archive candidate; 24 done, 14 deferred | Archive completed pilot; move deferred lifecycle/lender work to a follow-up only if active. |
| `weekly-awards-report-refactor` | Maintenance; 12 done, 4 pending | Finish injection/coverage cleanup; drop alias cleanup only if still meaningful. |
| `fiscal-tax-impact-v2.md` | Gated backlog | Keep inactive until fiscal-model refresh is selected. |

## Stale Content Signals

These are concrete drift examples found during the review:

- `src/` references remain in active docs/specs even though the repo now uses
  `sbir_etl/` and `packages/`.
- Poetry commands appear in validation docs and active specs, while the repo
  uses `uv`.
- `black` appears in the Makefile and docs, while current formatting standard is
  Ruff.
- `pytest-shard` is installed and documented, but current CI workflows do not
  run shard matrices.
- Steering quick-reference Cypher still uses legacy `:Company` / `:Award`
  examples while schema docs describe `:Organization` /
  `:FinancialTransaction`.
- `.pre-commit-config.yaml` comments reference a nonexistent
  `.github/workflows/static-analysis.yml`.
- `docs/research-questions.md` says `docs/commercialization-benchmark-methodology.md`
  is not committed, but the file is present in the repo.

Recommended treatment:

- Live docs/specs: update or delete stale references.
- `docs/archive/` and `specs/archive/`: preserve historical text unless it is
  misleadingly linked from current docs.
- Historical ADRs: keep old paths when the old path is the point of the ADR.

## Scripts Archive Policy

Default policy for `scripts/archive/`:

- Archived scripts are not current operational entrypoints.
- Active code, CI, and Makefile targets should not import or call archived
  scripts.
- Archived scripts should not be extended for new features.
- If an archived script is needed again, move it to the appropriate live
  directory, update docs, and add focused tests.
- Tests under `tests/unit/scripts/archive/` need an explicit reason to remain;
  otherwise they should move with the reactivated script or be deleted with the
  archived behavior.

Deletion rule:

- Delete archived scripts only when no active doc/spec cites them as provenance
  and they are not needed to reproduce a published result.

## Test And CI Drift

Current drift to resolve:

| Area | Drift | Preferred fix |
| --- | --- | --- |
| Test taxonomy | Docs describe `pytest -m fast`; CI uses `tests/unit/ -m "not slow and not integration"` | Pick one definition and update docs/CI together. |
| Validation scripts | Some operator CLIs live under `tests/validation/test_*.py` with zero pytest tests | Rename CLIs or keep explicit exceptions in the integrity guard. |
| Sharding | `pytest-shard` is installed and documented but unused | Reintroduce sharding intentionally or remove the dependency/docs. |
| Setup | Workflows mix composite setup, direct `pip install`, and `uv pip install` | Route normal Python setup through one action; allow documented tool bootstraps only. |
| Dagster jobs | Workflows repeat `PYTHONPATH` and `dagster job execute` summary blocks | Create a reusable script/action for Dagster job execution and summaries. |
| CI typo | `data-refresh.yml` summary job has a checkout step named "Configure AWS credentials" | Fix naming/step intent while simplifying the summary job. |
| Test safeguards | Integrity guard focuses on integration/e2e/validation empty suites | Add marker/tier drift checks only after taxonomy is settled. |

## Proposed Cleanup Checks

Add these checks incrementally after the first stale-content cleanup PR:

1. Live-doc path audit:
   - scan `docs/steering/`, `docs/development/`, `docs/testing/`, top-level
     `docs/*.md`, and top-level `specs/*`
   - ignore `docs/archive/`, `specs/archive/`, and ADRs by default
   - flag old `src/` executable paths, Poetry commands, Black commands, and
     missing local links

2. Spec status audit:
   - compare `Status:` text with task counts
   - flag specs with no tasks unless they are explicitly design-only
   - flag active specs with no research-question anchor

3. Archive import guard:
   - fail if live code, CI, or Makefile references `scripts/archive/`
   - allow docs and archived specs to cite archive paths

4. Runtime-artifact guard:
   - fail if tracked files include `__pycache__`, `.pyc`, `.pytest_cache`, or
     generated report artifacts

## First Cleanup PRs

Suggested order:

1. Fix low-risk command/doc drift: Makefile Ruff formatting, invalid ML extras,
   pre-commit comments, CI sharding docs, and validation CLI command examples.
2. Update spec statuses and archive/defer clearly stale specs.
3. Add the live-doc path audit.
4. Add the archive import guard.
5. Tackle code simplification modules after docs/tests/CI stop moving underfoot.
