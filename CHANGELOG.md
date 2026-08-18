# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
under the repository policy in [docs/steering/versioning.md](docs/steering/versioning.md).
The root project and all packages under `packages/` release as one synchronized
version.

## [Unreleased]

## [0.7.1] — 2026-08-18

### Added

- Hermetic end-to-end coverage for `core_refresh_job` (#649).
- Job-level execution tests for `phase_transition_latency_job`,
  `cet_full_pipeline_job`, and `cet_drift_job` (#650).
- Unit tests for the previously untested Neo4j categorization, SEC EDGAR,
  organization, and patent-loading paths, plus weekly-report LLM digest
  builders (#651).

### Changed

- Specs that declared `evidence` without the four-item contract were
  retiered; `phase-iii-census` remains the only evidence target, and CI now
  requires amendments SHA paperwork plus a declared estimand (#635).
- The evidence-tier checker fence-strips `amendments.md` before the SHA
  scan. The new job tests pin `core_refresh_job` membership, the production
  `cet_drift_job` selection, and the CET pipeline skip path (#652).

### Fixed

- `OrganizationLoader.create_subsidiary_relationships` kept an invalid pair
  (with a `None` child) and dropped a later valid pair when a mixed batch
  contained a hole (#652).

## [0.7.0] — 2026-08-18

### Added

- `SourceAdapter` protocol and `SourceRefreshRunner`, with `USAspendingAPIClient`
  wrapped as the reference adapter, restoring `uv run refresh-enrichment
  --source usaspending` (#619).
- Pipelines-tier `AnalysisSpec` / `AnalysisRun` platform with a registry-driven
  runner, snapshot compare, and `scripts/data/run_analysis.py --profile`; the
  prior hard-coded tech-area builder CLIs remain as deprecated shims (#619).
- STTR spinout-linkage exploratory kernel: identity resolution, generic-token
  guard, typed dimension-absence reasons, and the frozen Order 0–4 linkage
  cascade (#623), its D1 award-spine loader and design freeze-hash guard
  (#627), and a D4 money/paper-trail scorer scoring the subcontract and
  spinout signals as two independent directions (#632).
- STTR spinout-linkage partner-type seed lists: FFRDC, IPEDS, new-model-org,
  fiscal-sponsor, and IRS nonprofit-registry data captured; the
  research-hospitals list is left honestly pending on two dead-end sources
  (#624).
- `evidence-auditor` and `deployment-safety-reviewer` specialist review
  agents, cross-checked against the actual evidence-tier contract and
  self-hosted server runbook they enforce (#646).
- A crosswalk from the canonical 21-area CET taxonomy to the 14 national
  security CET areas in Appendix A of the August 2026 National Security
  Science and Technology Strategy, with Appendix B's priority-need alignment
  and a `docs/nssts-2026-alignment.md` explainer of what the strategy does
  and does not license (#647).

### Changed

- `specs/sttr-spinout-linkage` frozen as Revision 1: all 12 open design
  questions resolved, including a second research pass confirming no public
  or paid source directly supplies Bayh-Dole research-institution-to-SBC
  license records (#620, #626).
- `make lint-boundaries` now runs the same eight guard scripts as the CI
  quality job, including two that were previously CI-only (#633).
- Remaining `(str, Enum)` classes migrated to `StrEnum`, enforced by a
  targeted `UP042` check in `make lint` and CI; Python version wording
  unified to 3.11–3.12 throughout (#634).
- CLAUDE.md and agent role instructions deduplicated behind a single shared
  pointer (#636).
- The steering glossary and requirements template point confidence bands at
  their owning config or doc instead of restating them, and disambiguate
  enrichment "evidence" from the epistemic `evidence` tier (#637).
- Steering checklists that read as CI gates but were not enforced anywhere
  are relabeled as guidance, with the genuinely CI-enforced contracts kept
  in their own table (#638).
- Per-spec glossaries scrubbed of confidence bands they never owned;
  archived specs keep only glossary terms still used in their own
  requirements text (#639).

### Fixed

- The USAspending refresh pipeline: requests carried only `award_id` and
  could never match an award, the runner checkpoint was never cleared so an
  award refreshed once was skipped forever, and NaN identifiers reached the
  API as the literal string `"nan"` (#621).
- The analysis platform: `run_analysis.py --profile` wrote no census
  artifacts, the calibration-drift gate was unreachable from the CLI, and a
  malformed analysis registry could crash the entire Dagster definitions
  load instead of just the affected cohort assets (#622).
- The STTR linkage kernel: a generic-token guard bypass on the exact-match
  identity path, a guard failure that collapsed into a measured negative
  instead of blocking the label, `D4MoneyTrail`'s single shared status
  letting one direction's typed absence suppress the other's real signal,
  and an unreachable cascade branch (#628).
- `D4MoneyTrail` construction after the kernel's status-field split, which
  had been failing `Fast Tests` on every open pull request (#647).

## [0.6.0] — 2026-08-15

### Added

- OpenAlex and PubMed enricher clients with sync facades and mocked unit tests
  (#616).
- STTR spinout–subcontract linkage Phase 0 spec (exploratory, gated), dedicated
  B1/B2 inventory questions, and an exploratory partner-type commercialization
  notebook (#615).
- Bayh-Dole / D3 license-source research as O-12: no public microdata for
  research-institution-to-SBC licenses (#617).
- A blocking hygiene check that every top-level spec declares a
  research-question anchor (#612).

### Changed

- Outside-reader Status lines and Form D / Massachusetts report leads now use
  plain language while staying inside study boundaries (#613).

### Fixed

- Corrected the live-server health check to use production Neo4j variables and
  dependencies instead of E2E-only assumptions (#611).
- Made the Tailscale route helper runnable with the macOS system Python used by
  host preflight checks (#611).
- Made server rebuilds remove services retired from the Compose definition
  (#611).
- Restored the non-root `sbir` runtime contract for all three Dagster services,
  including one-time ownership migration for existing persistent directories
  (#611).

## [0.5.1] — 2026-08-12

### Added

- A weekly comprehensive test and branch-coverage lane with a 70% floor, plus
  hermetic end-to-end tests on every pull request (#602, #603).
- Operated-path coverage for CET analytics and validation, weekly enrichment,
  and congressional-district fiscal allocation (#605).

### Changed

- Lint now runs over the whole repository, including exploratory `scripts/` and
  `notebooks/`; formatting remains scoped to the primitives and pipelines trees.
  `make lint` runs the same three steps as the CI job.
- Reframed the README around what is verifiable, promoted epistemic tiers into
  the reading path, and added a "Verifying a checkout" gate list.
- Normalized spec and document naming to kebab-case, and added an index for
  `examples/`.
- Relocated the generated `pytest-split` timing file to `tests/.test_durations`.
- Reclassified component-level tests into unit and integration suites, leaving
  the E2E suite to execute two production Dagster workflows with hermetic inputs
  and explicit network rejection (#604).
- Removed environment-variable skips that silently prevented slow ML tests from
  running in the comprehensive suite (#603).

## [0.5.0] — 2026-08-12

### Added

- NSF private-capital Phase 1 gate: a repaired, horizon-bounded Phase I→II
  graduation estimand with connected-component identity resolution, and a
  pinned exploratory review artifact with a deterministic manifest (#577).
- Fail-closed FY M&A signal counts, replacing the incoherent match-rate spec
  with a count diagnostic that refuses to publish without a real input (#588).

### Fixed

- Neo4j load summaries report canonical graph labels and distinguish rows
  submitted from nodes written, so an idempotent re-run no longer reads as a
  failure and a partial load no longer reads as a success (#574).

## [0.4.0] — 2026-08-12

### Added

- **Epistemic tier system.** A four-tier contract (`primitives`, `pipelines`,
  `evidence`, `exploratory`) governing what each artifact may claim, documented in
  `docs/steering/epistemic-tiers.md`, declared across `sbir_etl`, `packages/`, and
  the analysis scripts, and enforced by a blocking import guard
  (`scripts/ci/check_tier_boundaries.py`) wired into CI and `make lint-boundaries`.
- **Study contracts** under `studies/` for reproducible, citable research, with
  manifest validation in CI. Transition scoring is the first contract.
- **Notebook-first research workflow** — `notebooks/` workbench, template,
  backlog, and companion notebooks over the canonical script artifacts.
- **Tech-area cohort reporting** parameterized by technology area, with a
  reproducible composition emitter and figure audit.
- **Repository guards**: large-file blocking at 5 MiB, configuration-boundary
  checks that route YAML loading through `read_yaml_mapping`, spec-registry
  coverage, and dead documentation-link detection.
- End-to-end coverage for the weekly report render and the Neo4j graph
  round-trip.

### Changed

- Promoted source-download pipelines, jurisdiction identity, exact award
  identity, and the SBIR award grain out of scripts into library modules.
- Consolidated the seven production `yaml.safe_load` call sites behind a single
  loader with an explicit `allow_empty` policy.
- Declared `sbir-graph` loaders as `pipelines` tier and `sbir_etl` config,
  models, and company-name handling as `primitives` tier.

### Fixed

- CI coverage reporting no longer implies a coverage gate that was not enforced.
- Corrected precision-gate documentation: the ≥85% Phase III HIGH-precision
  benchmark is enforced on PRs by a fixture-level canary, not by a full-corpus
  CI run.
- Repaired rotted end-to-end and functional tests, and wired the health check
  into server operations.

### Removed

- The phantom ML vectorizer API — a zero-byte module plus documentation for five
  classes that were never implemented.
- The private analytics API and the stale API map.

## [0.3.0] — 2026-08-04

### Changed

- Generalized the self-hosted server runbook so host-specific paths and
  materialization state live in an untracked local file.
- Improved developer onboarding.

### Removed

- Private analytics API.

## [0.2.0] — 2026-08-04

First release under the synchronized versioning policy, with versions aligned
across the root project and the three packages under `packages/`.

## Earlier tags

`0.1` and `v0.11` predate the versioning policy and do not follow the
`vMAJOR.MINOR.PATCH` form it requires. Per that policy published tags are never
moved or reused, so they remain as historical markers.

[Unreleased]: https://github.com/hollomancer/sbir-analytics/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/hollomancer/sbir-analytics/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/hollomancer/sbir-analytics/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/hollomancer/sbir-analytics/releases/tag/v0.2.0
