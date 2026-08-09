# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
under the repository policy in [docs/steering/versioning.md](docs/steering/versioning.md).
The root project and all packages under `packages/` release as one synchronized
version.

## [Unreleased]

Substantial work has landed since `v0.3.0` and is not yet released. The themes:

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
- Lint now runs over the whole repository, including exploratory `scripts/` and
  `notebooks/`; formatting remains scoped to the primitives and pipelines trees.
- Relocated the generated `pytest-split` timing file to `tests/.test_durations`.

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

[Unreleased]: https://github.com/hollomancer/sbir-analytics/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/hollomancer/sbir-analytics/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/hollomancer/sbir-analytics/releases/tag/v0.2.0
